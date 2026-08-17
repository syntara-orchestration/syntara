# V2 Workflow Schema Migration Guide

> **Status: COMPLETED.** The v2 migration is done. The UI now uses the v2 flat schema (`schema_version: '2.0.0'` with `triggers[]`, `nodes[]`, `edges[]`). The old nested format and `WorkflowTransform` class have been removed. This document is kept as historical reference.

## Migration Flow (Historical)

```
Step 1                     Step 2                      Step 3                      Step 4
─────────────────────      ─────────────────────       ─────────────────────       ─────────────────────
Backend v2 completes       Regenerate contracts        Update factory code         Delete stub types

Backend team finishes      Run `npm run gen`           Update each factory         Remove toV2Definition.ts
v2 OpenAPI spec            to generate v2              to produce v2 shapes        (stub types no longer
                           TypeScript types            instead of v1               needed — generated
                                                                                   types replace them)

         │                          │                           │                          │
         ▼                          ▼                           ▼                          ▼

v2 OpenAPI YAML            v2 TypeScript types          Unit tests go GREEN         Clean codebase
specs ready in             available in                 one by one as each          using only generated
backend repo               @syntara/contracts    factory is updated          v2 types

                                                        Update save path            E2E tests go GREEN
                                                        (getWorkflowDefinition)     confirming full stack
                                                        to send v2 format
```

### What each step produces

| Step | Action                                                              | Outcome                                                                                                                         | Tests affected                                       |
| ---- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| 1    | Backend v2 implementation complete                                  | v2 OpenAPI YAML specs in `syntara/backend/src/syntara/schemas/`                                                                 | None yet                                             |
| 2    | `npm run gen`                                                       | Generated v2 TypeScript types in `packages/syntara-contracts/src/`                                                              | Types available to code against                      |
| 3a   | Update factories (`workflowFactories.ts`) to produce v2 node shapes | Factories return `{ type: 'script', config: {...} }` instead of `{ type: 'task', task: { executor: 'script', config: {...} } }` | **Unit tests pass**                                  |
| 3b   | Update save path (`getWorkflowDefinition()`) to build v2 payload    | Save sends `{ schema_version: '2.0.0', triggers: [], nodes: [], edges: [] }`                                                    | **E2E tests pass**                                   |
| 4    | Delete `toV2Definition.ts` stub types                               | Only generated types remain                                                                                                     | No change — tests use factory output, not stub types |

### Test locations

| Layer            | File                               | What it tests                                                                  | When it passes |
| ---------------- | ---------------------------------- | ------------------------------------------------------------------------------ | -------------- |
| Unit (fast TDD)  | _(to be created during migration)_ | Each factory produces v2 node shapes                                           | After Step 3a  |
| E2E (acceptance) | _(to be created during migration)_ | Full stack: UI builds workflow, save payload is v2, reload preserves all nodes | After Step 3b  |

---

## How the UI Connects to the Backend

```
Backend (syntara/)                    Contracts                              UI (syntara-ui/)
────────────────                      ─────────                              ──────────────

src/syntara/schemas/                    packages/syntara-contracts/              packages/syntara-ui/
  workflows/openapi.yaml     ──┐
  executions_openapi.yaml    ──┤
  approvals/openapi.yaml     ──┼──  npm run gen  ──►  openapi-typescript
  tool_manager/openapi.yaml  ──┘                            │
                                                            ▼
                                     workflow-api.ts   ─────────────────►  client.tsx
                                     (generated types)                     (type-safe API clients)

                                     interfaces.ts     ─────────────────►  workflowFactories.ts
                                     (enums, aliases)                      (creates workflow nodes)
```

### The chain in detail

**1. Source of truth: OpenAPI specs in the backend**

The backend repository (`syntara-orchestration/syntara`) contains YAML OpenAPI specs that define every API endpoint, request body, and response schema. These are the single source of truth for the data contract between frontend and backend.

**2. Type generation: `npm run gen`**

Running `npm run gen` in the syntara-ui package:

- Clones the backend repository
- Runs `openapi-typescript` on each YAML spec
- Outputs generated TypeScript type definitions into `packages/syntara-contracts/src/`
- Copies workflow examples from the backend into the mock API

The generated files include full path types (every endpoint with request/response shapes) and component schema types (every data model).

**3. Type-safe API clients**

`packages/syntara-ui/src/client.tsx` creates API clients using the generated types:

```typescript
import createFetchClient from 'openapi-fetch'
import createClient from 'openapi-react-query'

const workflowFetchClient = createFetchClient<WorkflowAPI.paths>({ baseUrl: '/api/v1/' })
export const workflowClient = createClient(workflowFetchClient)
```

Every API call is type-checked at compile time. If the backend changes a field name or type, the TypeScript compiler catches it.

**4. Factory functions create workflow data**

`packages/syntara-ui/src/stores/workflowFactories.ts` contains pure functions that create properly-typed workflow entities (nodes, triggers, edges). These are what the builder UI calls when a user adds a step.

**5. Step types are hardcoded in the UI**

The available step types (Script, REST API, Task Agent, etc.) are defined in the UI's `NodeRegistry` (`src/routes/builder/registry/nodes/register*.ts`), not derived from the contracts. Each registration wires up the icon, form component, and factory function.

### What changes for v2

| Layer           | Current (v1)                                                               | Target (v2)                                                         |
| --------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Backend specs   | `workflows/openapi.yaml` defines nested activity schema                    | Updated spec defines flat `triggers[]`, `nodes[]`, `edges[]` schema |
| Generated types | `Activity = taskActivity \| conditionActivity \| ...` with nested wrappers | `Node = scriptNode \| httpRequestNode \| ...` with flat `config`    |
| API client      | `baseUrl: '/api/v1/'`                                                      | `baseUrl: '/api/v2/'` (if endpoint changes)                         |
| Factories       | `{ type: 'task', task: { executor: 'script', config: {...} } }`            | `{ type: 'script', config: {...} }`                                 |
| Save path       | `WorkflowTransform.nest()` → nested `workflow.activities[]`                | Direct mapping → flat `nodes[]` + `edges[]`                         |
| Store           | Flat activities + edges (close to v2 already)                              | Same flat structure, v2 node types                                  |
