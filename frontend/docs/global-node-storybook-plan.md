# Global Node Storybook Plan

## Objective

Document the global node components in `packages/syntara-ui/src/components/nodes` and make their supported visual states easy to inspect. The stories should help maintainers understand node composition, compare states, and spot visual regressions as node complexity grows.

## Agreed approach

- Center the suite on fully composed nodes rather than isolated structural primitives.
- Add one cohesive `NodeComponent.stories.tsx` story suite.
- Compose each focused story explicitly from the raw global components. Do not introduce a configurable story-only node abstraction.
- Share only infrastructure such as typed `NodeProps` construction, stable menu actions, providers, decorators, and layout styles.
- Use focused, realistically combined states as the primary documentation.
- Add a fixed, exhaustive `KitchenSink` gallery as the regression-oriented inventory.
- Do not add a controls-based playground.
- Do not add Storybook `play` assertions; existing unit tests remain responsible for behavioral verification.
- Keep menus closed in the gallery. Demonstrate the open-menu behavior in a dedicated interactive story.

## Scope

Create:

- `frontend/packages/syntara-ui/src/components/nodes/NodeComponent.stories.tsx`
- Optionally, a colocated `NodeComponent.stories.helpers.tsx` only if provider or fixture-data setup makes the main story file difficult to scan. UI composition should remain visible in the story file.

Document these components through composition:

- `NodeComponent`
- `NodeHeader`
- `NodeTitle`
- `NodeExpandToggle`
- `NodeMenu`
- `NodeBody`
- `NodeSidePanel`
- `NodeSemanticZoomBody`, indirectly through `NodeComponent`'s semantic-zoom behavior
- `NodeExpandedContext` and `NodeExpandedAllContext`, indirectly through their behavior

Do not create artificial standalone stories for the contexts or for structural wrappers whose meaning comes from the complete node.

## Story organization

Use the existing project conventions: `tags: ['autodocs']`, a useful component description, `Default`, individually named meaningful states, and `KitchenSink` last.

Recommended focused stories:

1. `Default`
   - A realistic, fully composed node with header, title/subtitle, expand toggle, menu, body, side panel, type-color bar, and normal handles.

2. `Selected`
   - A selected node in an otherwise ordinary state.

3. `Disabled`
   - A disabled node using the production `data.settings.disabled` shape.

4. `ValidationError`
   - A realistically invalid node using `data.__validationError`.

5. `ExecutionStates`
   - A side-by-side gallery of every supported execution badge status, including retry count where meaningful.
   - Derive the status list from the generated contract/type source rather than duplicating an assumed list.

6. `CollapsedAndExpanded`
   - Show both stable states together for comparison.
   - Use the real expand/collapse composition and context behavior; avoid replacing node internals with static lookalikes.

7. `Menu`
   - A focused interactive example with normal, separated, icon-bearing, and danger actions as supported by `NodeMenuAction`.
   - The menu starts closed and can be opened manually. No `play` function is required.

8. `SemanticZoom`
   - Render the compact semantic-zoom representation through `NodeComponent`.
   - Include representative normal, selected, dashed, and branching-handle variants if the story setup can set the React Flow zoom deterministically.

9. `WidthsAndTypes`
   - Compare the default 240 px node with the 360 px generic node and 360 px agentic task node.
   - Use `FlowNodeType` and `ExecutorTypeEnum` rather than discriminator string literals where constants exist.

10. `Handles`
    - Show the meaningful handle configurations: source/target, disabled source or target, reversed handles, and start/end handles.

11. `BordersAndIndicators`
    - Compare the type-color bar, dashed placeholder, selected dashed placeholder, mock-data-pinned badge, and other stable visual indicators not already clear elsewhere.

12. `KitchenSink`
    - A fixed gallery grouped by visual concern, not domain node type.

The exact number of focused stories may be reduced when two states are clearer as one comparison story. Story names should describe what a maintainer is looking for, not internal implementation details.

## Kitchen sink taxonomy

Render labeled sections in this order:

1. Base composition and structural options
2. Selection, disabled, validation, and border states
3. Execution states
4. Expanded and collapsed content
5. Semantic zoom
6. Width and node-type differences
7. Handle configurations
8. Header, title, menu, body, and side-panel variations

Use mostly realistic combinations, then include remaining orthogonal options needed for exhaustive coverage. Do not generate the full Cartesian product. Every supported visual option should appear at least once, and each example should have a visible label explaining the state being shown.

The gallery should include at minimum:

- Unselected and selected
- Enabled and disabled
- Valid and validation-error
- Standard and dashed borders, including selected dashed
- Type-color top bar
- All contract-supported execution states
- Execution badge hidden
- Retry count where supported
- Mock data pinned
- Expanded, collapsed, and non-collapsible behavior
- Default, generic, and agentic-task widths
- Normal and reversed handles
- Source disabled and target disabled
- Start and end handle options
- Semantic zoom normal, selected, dashed, and branching variants
- Title only, subtitle only, and title plus subtitle
- Menu actions including separator, icon, and danger action
- Body and side-panel content
- Long title/content where truncation or layout pressure is meaningful

## Implementation details

1. Before editing stories, run `make install` as required by the repository instructions.
2. Start Storybook if needed and call the Storybook MCP's `get-storybook-story-instructions` before creating the file.
3. Read the frontend implementation skills required by `frontend/AGENTS.md` before modifying frontend/story code.
4. Use `Meta` and `StoryObj` from `@storybook/tanstack-react`.
5. Wrap stories in `ReactFlowProvider` and any other production-required context through a decorator. Give the canvas enough padding and overflow room for handles and badges.
6. Provide stable, unique node IDs throughout a multi-node gallery.
7. Build typed node props with a small data factory to avoid unsafe casts and repeated XYFlow boilerplate. Keep state differences explicit at each call site.
8. Use the production `NodeExpandedAllContext` default where sufficient. Add a provider only where the gallery needs deterministic expand-all/collapse-all events.
9. Make semantic zoom deterministic. Prefer a real React Flow viewport setup/decorator; do not mock application hooks inside a story. If Storybook cannot reliably set the viewport below the semantic-zoom threshold, document and resolve that setup before claiming semantic-zoom coverage.
10. Use PatternFly layout components or a colocated CSS module for the gallery grid, labels, spacing, and constrained canvas. Avoid large inline-style objects.
11. Add an Autodocs component description explaining:
    - the responsibility of each global primitive;
    - the expected composition order;
    - which state is carried in `nodeProps.data`;
    - which options belong directly to `NodeComponent`;
    - that the kitchen sink is the visual state inventory.
12. Keep domain-specific production nodes (`TaskNode`, `TriggerNode`, and others) out of this suite. Their dependencies would blur the contract of the global components.

## Verification

After implementation:

1. Preview every new story through the Storybook MCP and inspect each returned preview URL.
2. Confirm there are no clipped handles, badges, menus, tooltips, or validation indicators.
3. Confirm the kitchen sink remains readable at common desktop widths and labels clearly identify every state.
4. Confirm the semantic-zoom examples actually render the compact body rather than detailed children.
5. Confirm collapsed and expanded examples begin in the advertised state.
6. Manually open the menu and verify it remains visible within the story viewport.
7. Run the relevant Storybook TypeScript, lint, formatting, and build checks after `make install`:
   - `npm --prefix frontend/packages/syntara-ui run tsc`
   - the repository-approved targeted lint/format checks for the new story files
   - `npm --prefix frontend/packages/syntara-ui run storybook:build`
8. Perform the frontend PR self-review required by `frontend/AGENTS.md` before reporting completion.

## Acceptance criteria

- A maintainer can view the supported global-node states without navigating production workflows.
- Focused stories communicate realistic node compositions and state combinations.
- `KitchenSink` exposes every supported visual option at least once in a fixed, labeled gallery.
- Raw global components are visibly composed in focused stories; no parallel `ExampleNode` API is introduced.
- Context-only and structural components are documented through the complete composition rather than artificial standalone stories.
- Interactive menu and expansion behavior can be explored manually, without controls or `play` assertions.
- Storybook Autodocs explains the composition contract and state ownership.
- The stories type-check, lint, format, build, and render without clipping or console errors.
