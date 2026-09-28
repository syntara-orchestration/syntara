# Plan: Rename global Node components to SynStep components

## Goal

Rename the shared UI components that are currently called `Node*` so their names use `Step` and the global `Syn` prefix. Keep this change to names and import paths. Do not change rendering, behavior, props, labels, or workflow data.

## What I found

- The shared components are in `frontend/packages/syntara-ui/src/components/nodes/`.
- There are ten exported names there: eight rendered components and two React contexts.
- Each module has a colocated test file. There is one CSS module for semantic zoom and no Storybook stories in this group.
- The package has no general components barrel export. Current callers import these modules directly, and the package is marked private. I found no use of these names outside the frontend package.
- Canvas node renderers use most of the shared components. The builder also uses the menu and expand-all context.
- `NodeSidePanel` is defined and tested, but I found no production caller. Keep it and rename it; do not remove it as part of this work.
- The architecture guide mentions `NodeComponent` and `NodeSemanticZoomBody`. Its `NodeComponent` path is already out of date, so update those component references while renaming them.

## Rename map

Apply the same rename to each source file, exported value or type, imports, JSX tags, and colocated test file.

| Current name               | New name                      |
| -------------------------- | ----------------------------- |
| `NodeBody`                 | `SynStepBody`                 |
| `NodeBodyProps`            | `SynStepBodyProps`            |
| `NodeComponent`            | `SynStepComponent`            |
| `NodeExpandToggle`         | `SynStepExpandToggle`         |
| `NodeExpandedAllContext`   | `SynStepExpandedAllContext`   |
| `NodeExpandedContext`      | `SynStepExpandedContext`      |
| `NodeExpandedContextValue` | `SynStepExpandedContextValue` |
| `NodeHeader`               | `SynStepHeader`               |
| `NodeMenu`                 | `SynStepMenu`                 |
| local `NodeMenuProps` type | local `SynStepMenuProps` type |
| `NodeSemanticZoomBody`     | `SynStepSemanticZoomBody`     |
| `NodeSidePanel`            | `SynStepSidePanel`            |
| `NodeTitle`                | `SynStepTitle`                |

Rename the group directory from `components/nodes/` to `components/steps/`. Rename `NodeSemanticZoomBody.module.css` to `SynStepSemanticZoomBody.module.css` and update its import. Keep CSS class names inside the module unchanged.

## Files and callers to update

1. Rename all ten `.tsx` source files and their ten `.test.tsx` files in `src/components/nodes/`, then move them into `src/components/steps/`. Update test imports and `describe` labels to use the new names.
2. Update imports and JSX in the workflow canvas node renderers: `ApprovalNode`, `ConditionNode`, `ConvergeNode`, `GenericNode`, `LoopNode`, `SwitchNode`, `TaskNode`, `TaskReversedNode`, `TriggerNode`, and `WaitNode`.
3. Update `routes/workflows/canvas/nodes/common/StandardNodeHeader.tsx` to use `SynStepExpandToggle`, `SynStepHeader`, `SynStepMenu`, and `SynStepTitle`.
4. Update `routes/workflows/canvas/CanvasControls.tsx` and `routes/builder/BuilderContent.tsx` to use `SynStepExpandedAllContext`. Update the related `BuilderContent.test.tsx` test description and comments.
5. Update `routes/builder/NodeDetailsPanel.tsx` and `NodeDetailsPanel.test.tsx` for `SynStepMenu`, including the mocked module path and mocked export name.
6. Update only comments or test descriptions that name one of these shared components, including the `NodeTitle` comment in `routes/builder/panels/utils/getUpstreamNodeDisplayName.ts` and the shared-menu comment in `ConvergeNode.test.tsx`.
7. Update the component references in `frontend/docs/architecture.md` to the new names and paths. Keep unrelated architecture text unchanged.

## Keep workflow terminology intact

Do not run a global text replacement for `Node`. Many names still describe React Flow or workflow data and are outside this rename. Keep names such as `NodeProps`, `NodeType`, `TriggerNode`, `useNodeMenuActions`, `NodeMenuAction`, node IDs, and node metadata as they are.

Keep existing `data-testid` values, accessible labels, visible text, DOM structure, CSS classes, prop names, and behavior. In particular, menu action data still comes from the workflow-specific `NodeMenuAction` type; this plan does not rename that type or its hook.

## Suggested implementation order

1. Rename the shared directory, source files, test files, CSS module, and shared exported names.
2. Update imports and JSX in the canvas and builder callers listed above. Fix relative paths after moving the directory.
3. Update component-specific comments, tests, and architecture references.
4. Search for the old component names and `components/nodes/` imports. Review each remaining match by meaning; keep legitimate workflow `Node*` names.

## Validation

Before running checks, follow the repository instruction to run `make install`. Then:

- Run the `syntara-ui` TypeScript check.
- Run the renamed shared component tests and the affected caller tests, including `StandardNodeHeader`, canvas node renderer tests, `BuilderContent`, and `NodeDetailsPanel`.
- Run the `syntara-ui` lint check.
- Search the frontend source and docs for the old shared component names and old shared-component paths. There should be no stale imports or JSX references.

The change is complete when the new names are used at every shared-component call site and the checks pass, with no UI or workflow behavior changed.
