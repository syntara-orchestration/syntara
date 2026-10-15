# Plan: No-Flash Syntax Highlighting in Syntara

**Status:** Implemented and measured on 2026-10-13; Storybook loading-state demo added on 2026-10-14.

## Goal

Keep server-provided code readable on its first visible frame. If Shiki is already warm, show syntax colors immediately. Standalone code blocks show the source immediately on a cold start and apply syntax colors when Shiki finishes loading. Execution details keep their existing loading indicator visible until both the activity response and Shiki are ready, so their code appears colored on its first visible frame. If highlighting fails, leave the plain source visible.

## Design

- Keep REST query functions focused on server data. Do not put Shiki initialization or tokenization in a query function or a shared query observer.
- Add one shared Shiki service with a cached initialization promise and highlighter instance. Once initialization is complete, render tokens synchronously as React elements.
- Keep the current source visible in standalone code blocks while Shiki initializes; do not add a code-shaped loading placeholder. For execution details, reuse the existing activity loading indicator while Shiki initializes in parallel with the API request. During a refresh of the same content, keep the previous highlighted output visible until the updated tokens are ready. Update the displayed code, copy source, and expanded content together. Never retain another node's payload when switching nodes.
- If initialization or tokenization fails, immediately fall back to plain code using the current source. Do not leave a spinner running or keep stale code visible. A failed initialization must not permanently block future initialization attempts.
- Make syntax highlighting opt-in in `SynCodeBlock` with a language prop. Preserve the current plain-text path for non-string children and callers that do not opt in.
- Copy the original source string, not text reconstructed from token elements.
- Support the app's light and dark color schemes with a matching Shiki theme pair. Follow the app's theme setting, including its persisted override, rather than the OS preference alone.
- Keep scrolling in the consuming view. The shared highlighting service and code block must work in any location without scrolling behavior or a scrolling-specific readiness API.
- Keep Monaco for editable code.

TanStack Query's `select` shapes the data seen by one observer without changing the cached server response. It is synchronous, so it cannot await Shiki; an observer can withhold selected data until a separate preload state changes, then `select` runs again over the cached response. Shiki supports asynchronous initialization followed by synchronous highlighting and exposes token data that can be rendered by React.

## Work Steps

1. **Add a shared Shiki service.**

   Use fine-grained Shiki imports for the core, JSON grammar, and one light/dark theme pair. Load additional grammars only when a caller requests them. Choose themes that fit the app's color scheme. Cache initialization and per-language loading promises so overlapping preloads share one highlighter and grammar load. Keep the Shiki implementation in a lazy-loadable module so opt-in highlighting does not unnecessarily enlarge the initial bundle.

2. **Add opt-in highlighting to `SynCodeBlock`.**

   Add a language prop. For string children with a language, render Shiki tokens as React elements inside the existing PatternFly code block. Show the source immediately on a cold start, then replace it with tokens when ready; do not show a loading placeholder. Reuse the highlighted output in the expand modal. Preserve the existing copy, expand, scroll, wrapping, and height behavior. For non-string children or callers without a language, keep the current plain-text path.

   Keep the source string separate from rendered tokens and use the displayed source directly for copy. Preserve line breaks and whitespace in token rendering. During a refresh, Copy and Expand must use the same source that is currently visible; switch all three to the updated source together. Retaining previous output is only appropriate for the same content identity. The execution view must distinguish execution and node identities so switching nodes cannot retain another node's payload.

   Handle initialization and tokenization errors with an immediate plain-code fallback. Copy, Expand, and search marks must still work in this state. Handle failed preloads without unhandled promise rejections and allow a later initialization attempt without retrying endlessly during one mount.

   Connect token colors to the app's light/dark setting (`html.pf-v6-theme-dark` or the existing theme provider). Check contrast against the actual PatternFly code-block and search-mark backgrounds in both themes, including the expanded modal.

3. **Preserve search behavior in the execution JSON view.**

   The JSON pane currently passes React nodes containing `<mark>` elements when search is active and scrolls to the first mark. Pass the JSON source string and search term separately to the highlighted path. Find matches in each complete source line, then apply those ranges to the syntax tokens. Searching tokens independently would miss matches that span differently colored pieces, such as `"status": "failed"`. Preserve case-insensitive, literal, line-based matching and reuse syntax tokens when only the search term changes. Keep the unmarked, displayed JSON source as the copied content.

   Keep the execution view's existing search scrolling in that view. Do not add scrolling behavior or scrolling-specific callbacks to the shared highlighting API.

4. **Preload from the view layer while REST is in flight.**

   `NodeExecutionDetailsPanel` starts the shared REST query when it mounts. Start `preloadShiki()` alongside that request from `useNodeExecutionDetails`. Its observer-level `select` withholds the activity response until preload settles; combine that readiness with the query's success/loading state so `NodeContentArea` keeps using its existing activity spinner. The REST query starts immediately, and Shiki initialization stays outside the query function. If preload fails, release the data and let `SynCodeBlock` use its plain-source fallback.

   In this panel, input and output views default to JSON. Start tokenization only when a JSON view is active. Schema and table views must not tokenize code.

   If a future route has a code-only query observer, its `select` may return the source string and language. Keep Shiki initialization and highlighting outside `select`. A future TanStack Router loader can start the query and Shiki preload in parallel; a Router migration is not required.

5. **Test content consistency and fallback behavior.**

   Add tests that prove:

   - A cold code block shows its actual source immediately, then receives syntax colors when highlighting is ready without showing a loading placeholder.
   - A cold execution-details query keeps selected activity data behind the existing loading indicator until JSON highlighting is ready, then renders the code colored on its first visible frame. If preload fails, data is released and plain-source fallback remains available.
   - During a refresh of the same node, visible code, copied text, and expanded content all use the previous source until the update is ready, then all use the new source.
   - Switching nodes or executions never shows or copies a payload retained from the previous selection, including rapid switches while initialization is pending.
   - Initialization and tokenization failures promptly show the current plain source, with working Copy, Expand, and search marks. A failed initialization does not permanently prevent later attempts.
   - Search matches spanning multiple syntax tokens are marked correctly, and copying preserves the exact source, including whitespace and line breaks.
   - App theme changes apply in both inline and expanded views, and schema/table views do not tokenize code.

6. **Measure before expanding.**

   Record added bundle size and highlighting time using representative payloads. Consider a worker only if measurements show that large snippets block the page. Add other languages only when a caller needs them; Bash is needed for the webhook cURL example. Keep Monaco for editable code.

## Implementation Results and Measurements (2026-10-13)

The implementation uses Shiki 4.5.0 for opt-in JSON and Bash highlighting with GitHub Light/Dark High Contrast themes. The shared highlighter and JSON grammar load in lazy chunks; the Bash grammar is a separate chunk loaded only when the cURL example requests it. The initial entry remains 736,443 bytes raw (228,545 gzip). The Shiki chunks total 247,085 bytes raw (69,797 gzip):

| Chunk                            | Raw bytes | Gzip bytes |
| -------------------------------- | --------: | ---------: |
| Shiki core/service               |   173,932 |     56,840 |
| GitHub Light High Contrast theme |    14,272 |      3,017 |
| GitHub Dark High Contrast theme  |    14,592 |      3,083 |
| JSON grammar                     |     2,817 |        772 |
| Bash grammar                     |    41,472 |      6,085 |

Across all production JavaScript assets, the build grew from 3,500,657 bytes raw (1,166,518 gzip) before this change to 3,755,667 bytes raw (1,239,360 gzip), an increase of 255,010 raw bytes (72,842 gzip). Compared with the JSON-only build recorded earlier (3,701,757 raw / 1,229,120 gzip), this broader adoption adds 53,910 raw bytes (10,240 gzip). The totals use `gzipSync` on built JavaScript assets. JSON is registered during highlighter initialization; Bash loads only for callers that request it. Monaco remains in place for editable code.

A local Node microbenchmark loaded the service module before timing initialization, then measured warm JSON tokenization over 15 runs per payload, discarding the first three and taking the median of the remaining 12. Cold Shiki initialization took 2.13 ms. Median tokenization times were 0.19 ms for 92 bytes, 4.53 ms for 11,232 bytes, and 40.99 ms for 114,282 bytes. After adding Bash, the same method measured a 173-byte representative cURL sample at 0.42 ms median warm tokenization; highlighter initialization plus Bash grammar loading took 4.09 ms. The largest JSON sample can exceed a 60 Hz frame budget, but the Node benchmark does not establish browser long-task behavior or include rendering the token tree. No worker is added on this evidence alone; profile representative browser payloads before deciding whether to move tokenization to a worker or support larger snippets.

Standalone cold code blocks show their actual source while lazy Shiki chunks load, then update in place with syntax colors. Execution details start the same lazy preload alongside the activities request and keep their existing loading indicator visible until both complete, so their code is colored on first render. Vite's dev optimizer explicitly includes the lazy Shiki imports so first use does not discover new dependencies and reload the page.

The execution-details observer uses a memoized `select` to withhold its activity response until JSON preload settles. The API response remains cached unchanged, and the existing panel loading state covers the brief wait. The API and preload run in parallel; if preload fails, the observer releases the data so `SynCodeBlock` can use its plain-source fallback. Hook tests cover both the ready and failed-preload paths.

On 2026-10-13, opt-in highlighting was extended to policy definitions and conditions, approval context, workflow definitions and node data, builder input/output JSON, agent trace JSON and tool input, workflow-canvas JSON details, and raw identity-provider token claims. The webhook sample request uses the Bash grammar, loaded only when that example requests it. Arbitrary workflow expressions and freeform text remain plain text, and Monaco remains responsible for editable code.

Verification completed: Shiki integration tests pass for source preservation, dual-theme variables, High Contrast token colors, and Bash highlighting. Focused UI tests pass for shared code blocks, raw token claims, the cURL example, and 159 tests across eight JSON consumer test files. `npm run check` and the production build pass. The broad `npm test` run did not produce a valid green result: unrelated API-dependent tests repeatedly failed against `localhost:3000` and other workers timed out, so I stopped it and reran the affected consumer tests separately. The original Storybook visual checks covered light and dark app modes in inline and expanded JSON views; the initial pass did not include a dedicated `SynCodeBlock` story.

On 2026-10-14, the `SynCodeBlock` stories gained `AsyncHighlightStates`, a Storybook-only harness that holds the real Shiki loader. Browser verification confirmed that Pending shows the complete source as plain text, Resolve applies Shiki tokens and colored brackets, Reject keeps the plain-source fallback, and Reset returns to Pending. The status message belongs to the story harness; `SynCodeBlock` still has no loading placeholder. The JSON Default story documents the selected GitHub High Contrast light/dark theme pair. The Bash story and broader consumer pages were not re-previewed in this follow-up.

An attempted cold-load check of the execution Details route could not be completed: the available browser session redirected to login and the auth API returned 403, so no screenshot of that route is available.

## Done When

- Standalone cold code blocks show their actual source immediately, with syntax colors applied when ready and no code-shaped loading placeholder. Execution details show the existing activity loading indicator until Shiki and activity data are ready, then render syntax colors immediately. On failure, leave the current plain source visible.
- During a refresh of the same content, the previous highlighted code stays visible until the new tokens are ready. Visible code, Copy, and Expand switch sources together, with tests proving this behavior.
- Switching nodes or executions never retains another selection's payload, with tests proving this behavior.
- Copy returns the exact source string for the displayed content, including in the plain-code fallback.
- Search marks and scroll-to-first-match behavior remain intact in the execution JSON view.
- The shared highlighting API has no scrolling behavior or scrolling-specific callbacks.
- Schema and table views do not run syntax tokenization.
- PatternFly layout, wrapping, scrolling, expand behavior, and copy behavior remain intact.
- GitHub Light/Dark High Contrast themes remain legible when the app color scheme changes.
- Added bundle size and highlighting time are recorded before enabling more languages or views.

## Relevant Files

- `packages/syntara-ui/src/components/details/SynCodeBlock.tsx`
- `packages/syntara-ui/src/routes/executions/NodeExecutionDetailsPanel.tsx`
- `packages/syntara-ui/src/routes/executions/hooks/useNodeExecutionDetails.ts`
- `packages/syntara-ui/src/routes/builder/components/ExpandableCodeEditor.tsx`

## References

- [TanStack Query `useQuery`](https://tanstack.com/query/latest/docs/framework/react/reference/functions/useQuery)
- [Shiki synchronous usage](https://shiki.style/guide/sync-usage)
- [Shiki installation and usage](https://shiki.style/guide/install)
- [Shiki bundle guidance](https://shiki.style/guide/bundles)
- [Shiki light/dark themes](https://shiki.style/guide/dual-themes)
- [Shiki performance guidance](https://shiki.style/guide/best-performance)
