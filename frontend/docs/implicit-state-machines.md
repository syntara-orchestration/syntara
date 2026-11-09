# Implicit State Machines in the Frontend

This report lists places in `packages/syntara-ui/src` where a state machine exists in the code but is not written as one. The state is spread over boolean flags, status strings, refs, or large reducers. The code works, but the rules for "which state can go to which state" are hidden.

## How this report was made

- The code was read by hand. No tests were run and no bug was reproduced at runtime.
- A second review checked each claim against the code. Claims that the review found wrong were removed or corrected.
- Findings marked **needs runtime check** are likely, but not proven.
- No code was changed. The repo has no state machine library (no `xstate`, `robot3`, or `@zag-js/*`).

## Why this matters

When state is stored as separate flags, the type allows combinations that should never happen. Each transition must reset the right flags by hand. When one transition forgets a flag, the UI gets an impossible state. Async work (timers, fetches, sockets) adds more risk, because a late result can arrive after the state has moved on.

Common signs in this codebase:

- Several booleans that are meant to be mutually exclusive.
- A counter or ref used to ignore late async results (`logoutCount`, `cancelled`, `bootstrapAttempted`).
- Data that is only valid in one state, stored as an optional field on a shared record.
- Transitions written as long lists of field resets.

## Findings by priority

### 1. WebSocket store: real races (high)

Files: `src/lib/websocket/store.ts`, `src/lib/websocket/types.ts`

`ConnectionState` is a real union (`connecting | connected | disconnected | reconnecting | failed`). This is the best-typed machine in the repo. The transitions, however, are written inside `connect()` closures, and three problems follow:

- **Disconnect while connecting can reconnect.** `disconnect()` calls `socket.close(1000)`. If the socket has not opened yet, the browser reports close code 1006, not 1000. The `onclose` handler treats any code other than 1000 as an error and calls `scheduleReconnect`. So a deliberate `disconnect()` can start a reconnect.
- **Two sockets for one channel.** If the sequence connect, disconnect, connect happens while the first ticket fetch is still pending, the state is `connecting` again. Both fetches pass the `state === 'connecting'` check (store.ts:249) and both create a socket. The first socket is orphaned, but its handlers still notify subscribers.
- **Old socket handlers change the new channel.** The handlers use `channelId`, not the socket itself. A late `onclose` from an old socket sets `socket: null` and `disconnected` on the new channel.

Also: `socket`, `reconnectTimeout`, and `error` are optional fields that only make sense in some states. `failed` can only be left through a new `connect()`. That call keeps `reconnectAttempts`, so if it fails it goes straight back to `failed` with no retries.

Suggested fix: store the socket in each handler's closure and ignore events from any socket that is not the current one. Also check for `disconnected` in `scheduleReconnect`. Add a failing test for each race first.

### 2. Execution WebSocket: stale handler and possible reconnect loop (high)

Files: `src/routes/workflows/stores/useExecutionStore.ts`, `src/routes/workflows/hooks/useExecutionWebSocket.ts`, `src/lib/websocket/hooks.ts`

The store keeps `isConnected`, `isStale`, and `isComplete` as separate booleans, and the hook keeps `isReconnecting`.

- `setConnectionState(connected, stale)` accepts `(true, true)`, but the hook never produces it.
- `(false, false)` means both "not connected yet" (the initial value) and "complete and disconnected".
- **Stale closure (confirmed by reading).** `handleStateChange` reads `isComplete` from a `useCallback` closure. `hooks.ts:122` passes `onStateChange` to the store by value, and the subscription only re-runs when `channelId` or `messageTypes` change. So the store keeps the first version of the callback, where `isComplete` is `false`. Any `disconnected` event after `final_snapshot` then writes `isStale = true` to the store. The hook's own returned `isStale` is computed again and is correct. No production code was found that reads the store's `isStale`, so the visible effect today is small.
- **Possible reconnect on every patch (needs runtime check).** `isReconnecting` is only cleared on `initial_snapshot`. The protocol doc says that message is sent only when replay is 0. After a reconnect the URL uses `lastEventId`, and every `activity_patch` updates `lastEventId`. A changing URL makes the hook disconnect and connect again on each patch.

Also in this store: `STATUS_ORDER` and `mergeActivityStates` store the activity lifecycle as a number rank. Its comment says that retry cycles (`completed` to `pending`) are not handled.

Suggested fix: replace the three booleans with one status union, for example `idle | connecting | live | reconnecting | completed | failed`, where `completed` cannot be left.

### 3. RunStepDialog: closing while a run is in progress (medium)

File: `src/routes/builder/components/RunStepDialog.tsx`

The dialog combines `dialogView` (`choice | mock-editor`) with `runState` (`idle | running | success | error`), plus `mockJson`, `jsonError`, `runError`, `closeTimerRef`, and `clearMocksRef`.

- The Close button is disabled while running (lines 267, 364). The modal's `onClose` (Esc key or the X button) is not (lines 218, 307). The dialog is always mounted (`BuilderDialogs.tsx:225`).
- If the user closes during a run, `handleClose` resets `runState` to `idle`. Then:
  - The first run still finishes, sets `success`, and calls `onExecutionCreated`.
  - It schedules an auto close that can close a dialog the user has opened again.
  - A second run can start while the first one is still going.

The guard `if (runState !== 'idle') return` is good, but resetting the state on close removes its protection.

Suggested fix: block `onClose` while running, or ignore results from a run that was started before the last close. A single `phase` value (`choice | editing | running | succeeded | failed`) would also remove the need to reset five fields by hand.

### 4. Builder reducer: panel state (medium)

File: `src/routes/builder/builderReducer.ts`

`BuilderState` has 30 fields. Eight of them describe which panel is open: `addStepPanelOpen`, `detailsOpen`, `historyCardOpen`, `versionHistoryOpen`, `stepEditorMode`, `selectedNode`, `replacementNodeId`, `viewingVersion`. Most panels should not be open together, but the type allows it. Each transition (`TOGGLE_*`, `OPEN_ADD_NODE_PANEL`, `NODE_CLICK`, `INIT_WORKFLOW`) repeats 8 to 20 resets by hand.

Real gaps:

- `BuilderContent.tsx:196-198` handles a change of the `?version=` URL param. It dispatches `SET_VIEWING_VERSION`, `SET_VERSION_HISTORY_OPEN true`, and `SET_HISTORY_CARD_OPEN false`. It does not close details, add-step, or the step editor. Details and version history can then be open together.
- `clearEditorAndOtherPanels` (line 177) does not reset `addStepPanelOpen`, `replacementNodeId`, or `sourceNodeId`. After `TOGGLE_*`, old add-node context stays in state.
- Exclusivity is split between the reducer and its callers. For example, `useBuilderVersionPanel.ts:119-124` closes version history before the caller opens the history card.
- Routing uses casts: `SIMPLE_ACTIONS.includes(action.type as ...)` and `action as SimpleAction`.

Not a problem today: the generic `SET_DETAILS_OPEN`, `SET_ADD_STEP_PANEL`, and `SET_SELECTED_NODE` actions are only dispatched with `false`, or not at all outside tests.

Suggested fix: use one `panel` value, for example `none | details | history | versionHistory | addStep{...} | stepEditor{...}`. Keep `viewingVersion` as a separate value. The existing reducer tests should catch regressions.

### 5. Auth store, login form, and session timeout (medium)

Files: `src/stores/useAuthStore.ts`, `src/app/AppLogin.tsx`, `src/hooks/useSessionTimeout.ts`, `src/hooks/useIdleTimer.ts`

These three form one auth lifecycle. The state is spread over `isAuthenticated`, `isRefreshing`, `accessToken`, `expiresAt`, `error`, `logoutCount`, a `sessionStorage` key, and module variables (`refreshPromise`, `refreshTimer`). `logoutCount` is used as an epoch to ignore late refresh results.

Concrete issues in `useAuthStore.ts`:

- The `catch` in `refresh` resets to `INITIAL_STATE` without keeping `logoutCount` (lines 380-383). `login` does keep it (line 313). The epoch can fall back to 0, which turns the CSRF bootstrap path back on.
- `login` has no epoch check, so a logout during a login can be overwritten when the login finishes.
- The `finally` block of an old refresh sets `isRefreshing: false` even when a newer refresh is running.

Smaller points:

- `AppLoginForm` has 10 `useState` calls and a ref guard. The error values (`loginError`, `loginErrorField`, `isLogoutError`) are always set together by hand and should be one object. `isLoggingIn` is not reset on success, but this is harmless: `login()` sets `isRefreshing`, which hides the form, and success unmounts it.
- `useSessionTimeout` has a clear `phase` union (`active | warning | expired`). It can enter `expired` from two paths, and only one writes the `sessionStorage` keys. `continueSession` can set `active` from any phase, but the UI cannot reach this, because logout unmounts the app.

Suggested fix: model auth as one lifecycle (`bootstrapping | unauthenticated | authenticating | authenticated | refreshing | loggedOut`). Fix the `logoutCount` reset first.

### 6. Smaller issues (low)

- **`useDockState`** (`src/app/useDockState.ts`): `onToggleDock` starts a timer and calls `setIsDockOverlay` inside a state updater function that is itself inside another updater (which also writes `sessionStorage`). In React Strict Mode the updater runs twice, which creates two timers and loses the first one in `focusTimerRef`. `onMobileToggle` can also collapse the dock without clearing `isDockOverlay`, so overlay without expanded is reachable.
- **`ExpressionBuilderCore`** (`src/components/expressions/ExpressionBuilderCore.tsx`): switching from raw to visual with text that cannot be parsed replaces it with an empty group. The emit effect then sends that empty group to the parent, so the user's text is lost without a warning.
- **`UnsavedChangesProvider`**: the modal's `onClose` is not disabled while `isSaving` (line 199). `proceedNavRef`, `resetNavRef`, and `pendingTargetRef` are exclusive only by convention.
- **`useApprovalSelection`**: previous props are stored in reducer state and compared during render, by reference. If a caller passes a new `filters` object on every render, this causes a render loop.
- **`ApprovalDetailContent`**: `pendingDecision` plus the mutation flags give `canSubmit`. This is clear enough. The local name `isPending` means the approval status, which is easy to confuse with the mutation's `isPending`.

## Other flag-based flows to look at

These use refs or flags as a small state machine. They were found but not studied in depth.

- `routes/builder/hooks/useBuilderWorkflowLifecycle.ts`: four `has*Ref` flags that are reset together when the workflow changes.
- `routes/builder/hooks/useRunStepDialog.ts` (`suppressPanelCloseRef`, `hasCleanedUpRef`) and `routes/builder/components/BuilderDialogs.tsx` (`autoRanRef`).
- `routes/builder/hooks/useWorkflowGraphInit.ts`: `isInitializedRef`, `isDeletingRef`.
- `routes/builder/hooks/useEdgeSynchronization.ts`: `isSyncingRef`, `isFirstSyncRef`.
- `routes/builder/ExecutionViewContent.tsx`: `hasLoadedRef`, `hasLoadedActivitiesRef`.
- In-flight guards: `routes/executions/hooks/useExecutionApprovalPanel.ts`, `routes/executions/hooks/useAutoApprovalDetection.ts`, `routes/builder/step-forms/useFileUploadState.ts`.
- `hooks/useAAPBrowser.ts`: dependent organization and template selection in one state object.
- Connection drag in `routes/builder/hooks/useConnectionHandlers.ts`: `connectionStateRef` is changed in place.

## Suggested order of work

1. Fix the WebSocket store races and check the per-patch reconnect. These may be live bugs.
2. Fix the RunStepDialog close-while-running problem. It is a small change.
3. Replace the execution store connection booleans with one status union.
4. Replace the builder panel flags with a `panel` union. Close the gaps in the `?version=` handler and `clearEditorAndOtherPanels`.
5. Fix the `logoutCount` reset in the auth store, then consider one auth lifecycle model.

For items 1 to 3, add a failing test before the fix. If the team wants a library, a small one such as `xstate` fits the WebSocket and auth machines best. A plain discriminated union is enough for the rest.
