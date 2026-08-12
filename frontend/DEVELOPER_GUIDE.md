# Syntara UI Developer Guide

## Table of Contents

1. [Project Overview](#project-overview)
2. [Local Development Setup](#local-development-setup)
3. [Architecture](#architecture)
4. [Updating API Contracts](#updating-api-contracts)
5. [Development Workflow](#development-workflow)
6. [Testing](#testing)
7. [Performance Optimization](#performance-optimization)
8. [Debugging](#debugging)
9. [Common Pitfalls](#common-pitfalls)
10. [Best Practices](#best-practices)

## Project Overview

### Purpose

Syntara UI is a React-based application for building and managing complex automation workflows, focusing on type-safety, performance, and developer experience.

### Technology Stack

- **Frontend**: React 19, TypeScript, Wouter
- **Styling**: PatternFly 6
- **State Management**: TanStack Query (server state), Zustand (client state)
- **API Integration**: openapi-fetch, openapi-react-query
- **Date formatting**: date-fns (`packages/syntara-ui/src/utils/dateUtils.ts`)
- **Testing**: Vitest, React Testing Library
- **Build**: Vite, npm workspaces

## Local Development Setup

### Prerequisites

- Node.js 22+
- npm 10+
- Git

### Initial Setup

```bash
# Clone the repository
git clone https://github.com/syntara-orchestration/syntara.git
cd syntara/frontend

# Install dependencies
npm ci

# Set up git hooks (Husky) — required because ignore-scripts is enabled in .npmrc
npm run prepare

# Start development environment
npm start
```

### Environment Ports

- UI: <http://localhost:5173>
- Mock API: <http://localhost:3000>
- Storybook (+ MCP server): <http://localhost:5174>

## Architecture

### Monorepo Structure

- `packages/syntara-ui`: Main React application
- `packages/syntara-contracts`: OpenAPI TypeScript types
- `packages/syntara-mock-api`: MSW-based mock API server

### Key Architectural Patterns

- Centralized routing: path constants in `src/app/AppRoute.tsx`, route mapping in `src/app/AppRouter.tsx`
- Lazy-loaded components
- Type-safe API calls
- Automatic memoization via React Compiler

## Updating API Contracts

The `syntara-contracts` package contains auto-generated TypeScript types from the backend OpenAPI schemas. These must be updated whenever the backend API changes.

### Backend Access

- Local clone of the [nexus backend](https://github.com/syntara-orchestration/syntara) repository
- The backend repo should be at a sibling path or you'll need to adjust the paths below

### Updating Contracts

The recommended approach is using the automated gen script (see below). For manual generation with a local backend clone:

```bash
cd packages/syntara-contracts

# Replace /path/to/syntara with your local backend clone path
npx openapi-typescript /path/to/syntara/src/syntara/schemas/workflows/openapi.yaml \
  --output ./src/workflow-api.ts --default-non-nullable false

npx openapi-typescript /path/to/syntara/src/syntara/schemas/tool_manager/openapi.yaml \
  --output ./src/tool-manager.ts --default-non-nullable false

npx openapi-typescript /path/to/syntara/src/syntara/schemas/files/openapi.yaml \
  --output ./src/files-api.ts --default-non-nullable false

npx openapi-typescript /path/to/syntara/src/syntara/schemas/approvals/openapi.yaml \
  --output ./src/approvals-api.ts --default-non-nullable false

npx openapi-typescript /path/to/syntara/src/syntara/schemas/workflows/executions_openapi.yaml \
  --output ./src/executions-api.ts --default-non-nullable false

npx openapi-typescript /path/to/syntara/src/syntara/schemas/workflows/activity_types_openapi.yaml \
  --output ./src/activity-types-api.ts --default-non-nullable false

npx openapi-typescript /path/to/syntara/src/syntara/schemas/invocations/openapi.yaml \
  --output ./src/invocations-api.ts --default-non-nullable false

npx openapi-typescript /path/to/syntara/src/syntara/schemas/metrics/openapi.yaml \
  --output ./src/metrics-api.ts --default-non-nullable false

npx openapi-typescript /path/to/syntara/src/syntara/schemas/tool_manager/metrics.yaml \
  --output ./src/tool-manager-metrics.ts --default-non-nullable false

# Copy example workflows to mock API
cp -r /path/to/syntara/tests/integration/workflow/examples ../syntara-mock-api/src/

# Format the generated files
cd ../..
npm run format
```

### Alternative: Using the gen script

If you have SSH access to the backend repo, you can use the built-in script:

```bash
npm run gen
```

This will:

1. Clone the backend repo temporarily
2. Generate all TypeScript types
3. Copy example workflows
4. Clean up the cloned repo

### After Updating

1. Run tests to ensure nothing is broken: `npm test`
2. Check for TypeScript errors in the UI: `npm run tsc`
3. Update any UI code that uses changed types
4. Commit the updated contract files

### Contract Files

| File                            | Source Schema                                   | Description                          |
| ------------------------------- | ----------------------------------------------- | ------------------------------------ |
| `workflow-api.ts`               | `schemas/workflows/openapi.yaml`                | Workflow definitions and CRUD        |
| `executions-api.ts`             | `schemas/workflows/executions_openapi.yaml`     | Execution endpoints                  |
| `activity-types-api.ts`         | `schemas/workflows/activity_types_openapi.yaml` | Activity type metadata               |
| `tool-manager.ts`               | `schemas/tool_manager/openapi.yaml`             | Tool and provider management         |
| `tool-manager-metrics.ts`       | `schemas/tool_manager/metrics.yaml`             | Tool manager metrics                 |
| `files-api.ts`                  | `schemas/files/openapi.yaml`                    | File upload and management           |
| `approvals-api.ts`              | `schemas/approvals/openapi.yaml`                | Approval requests                    |
| `invocations-api.ts`            | `schemas/invocations/openapi.yaml`              | Invocations                          |
| `metrics-api.ts`                | `schemas/metrics/openapi.yaml`                  | Metrics                              |
| `settings-api.ts`               | `schemas/settings/openapi.yaml`                 | Runtime settings                     |
| `auth-api.ts`                   | `schemas/auth/openapi.yaml`                     | Authentication                       |
| `users-api.ts`                  | `schemas/users/openapi.yaml`                    | User management                      |
| `credentials-api.ts`            | `schemas/credentials/openapi.yaml`              | Credential management                |
| `identity-providers-api.ts`     | `schemas/identity_providers/openapi.yaml`       | SSO/OIDC providers                   |
| `aap-api.ts`                    | `schemas/aap/openapi.yaml`                      | AAP integration                      |
| `authz-api.ts`                  | `schemas/authz/openapi.yaml`                    | Authorization policies               |
| `roles-api.ts`                  | `schemas/roles/openapi.yaml`                    | Role definitions                     |
| `policies-api.ts`               | `schemas/policies/openapi.yaml`                 | Access policies                      |
| `projects-api.ts`               | `schemas/projects/openapi.yaml`                 | Project management                   |
| `group-role-assignments-api.ts` | `schemas/group_role_assignments/openapi.yaml`   | Group role assignments               |
| `user-role-assignments-api.ts`  | `schemas/user_role_assignments/openapi.yaml`    | User role assignments                |
| `interfaces.ts`                 | Manually maintained                             | Shared interfaces and enum constants |

## Development Workflow

### Branch Strategy

- `main`: Stable production branch
- Feature branches: `feature/descriptive-name`
- Bug fix branches: `bugfix/descriptive-name` or `fix/descriptive-name`
- Documentation branches: `docs/descriptive-name`

### Typical Development Process

1. Create a new branch
2. Make changes
3. Run tests: `npm test`
4. Format code: `npm run format`
5. Create pull request to `main`

### Package-Specific Commands

```bash
# UI Package
npm run test:ui       # Run tests
npm run build         # Build package
npm run start:ui      # Start dev server

# Mock API Package
npm run start:mock-api  # Start mock API server
```

## Testing

### Testing Tools

- Vitest
- React Testing Library
- Mock Service Worker (MSW)

### Running Tests

```bash
# Run all tests
npm test

# Run UI package tests
npm run test:ui

# Run with coverage
npm run test:coverage

# Coverage threshold is enforced by CI (per-file 80% minimum)
npm run test:coverage

# End-to-end tests (mock API)
npm run e2e            # Run headless
npm run e2e:ui         # Run with Playwright UI

# Run a specific test file
npx vitest run packages/syntara-ui/path/to/specific/test.test.ts
```

### Running E2E Tests Against the Real Backend

The backend uses HTTPS with a self-signed certificate by default. To run Playwright E2E tests against it:

1. **Start the backend** (from the monorepo root):

   ```bash
   make run-all          # Starts all backend services (API on https://localhost:8000)
   make admin-password   # Inject the admin password into the database
   ```

2. **Start the frontend** (from `frontend/`):

   ```bash
   VITE_API_URL=https://localhost:8000 npm start
   ```

3. **Run the E2E tests** (from `frontend/`):

   ```bash
   NEXUS_E2E_PASSWORD="$(cat ../backend/.secrets/admin-password)" \
   VITE_API_URL=https://localhost:8000 \
   NEXUS_E2E_BASE_URL=http://localhost:5173/ \
   NEXUS_E2E_SKIP_WEB_SERVER=1 \
   npm run e2e:ui
   ```

Environment variables explained:

| Variable                    | Purpose                                                                                         |
| --------------------------- | ----------------------------------------------------------------------------------------------- |
| `NEXUS_E2E_PASSWORD`        | Admin password generated by `make admin-password` (stored in `backend/.secrets/admin-password`) |
| `VITE_API_URL`              | Backend API URL (HTTPS)                                                                         |
| `NEXUS_E2E_BASE_URL`        | Frontend dev server URL where Playwright opens the browser                                      |
| `NEXUS_E2E_SKIP_WEB_SERVER` | Skip Playwright's built-in web server since frontend is already running                         |

The Playwright config sets `ignoreHTTPSErrors` to `true` in real-backend mode (when `NEXUS_E2E_SKIP_WEB_SERVER=1`) so the browser accepts the self-signed certificate. In mock-API mode it remains `false`.

### Writing Tests

- Use React Testing Library with `userEvent` for interactions
- Follow AAA pattern (Arrange-Act-Assert)
- Mock external dependencies with `vi.fn()` and `vi.mock()`
- All new/modified code must meet **80% coverage** (lines, statements, functions, branches)
- Use `*.test.tsx` for jsdom unit tests, `*.spec.ts` under `packages/syntara-ui/e2e/` for Playwright E2E tests
- **E2E tests** run against mock API by default, real backend supported — See [packages/syntara-ui/TESTING.md](packages/syntara-ui/TESTING.md) for setup
- **Visual regression** — every route is screenshotted and compared against baselines in CI. New routes must be added to the page registry. See [packages/syntara-ui/VISUAL_REGRESSION.md](packages/syntara-ui/VISUAL_REGRESSION.md)

## Performance Optimization

The application uses several strategies for performance:

- **React Compiler** — Automatic memoization, no manual `useMemo`/`useCallback` needed
- **Lazy-loaded routes** — Each route is loaded on demand via `React.lazy()`
- **Selective Zustand subscriptions** — Custom hooks ensure components only re-render when their specific data changes (see [docs/zustand-architecture.md](docs/zustand-architecture.md))
- **TanStack Query caching** — Server data is cached and deduplicated automatically

### Profiling

- **React DevTools** — Performance tab to identify re-renders
- **Bundle analysis** — Run `npm run build` and inspect the Vite output
- **Browser DevTools** — Network tab for API timing, Performance tab for rendering

## Debugging

### Workflow Builder

The builder is the most complex part of the codebase. Common debugging approaches:

| Symptom                             | Where to look                                                 |
| ----------------------------------- | ------------------------------------------------------------- |
| Canvas steps not laying out (Dagre) | `BuilderFlow.tsx` (Dagre layout)                              |
| Edges duplicating or missing        | `useButtonEdgeMaintenance.ts`                                 |
| Save payload looks wrong            | `buildNestedStructure.ts` + `workflowTransform.ts`            |
| Join/parallel drift                 | `useEdgeSynchronization.ts`                                   |
| State not updating                  | Check Zustand store actions via `useWorkflowStore.getState()` |

See [docs/architecture.md](docs/architecture.md) — "Where to look when debugging graph weirdness" for a visual guide.

### General Debugging

- **Zustand state inspection**: Call `useWorkflowStore.getState()` in the browser console
- **React DevTools**: Inspect component props and state
- **API responses**: Check the Network tab in browser DevTools; the Vite proxy forwards `/api/*` to the mock API or real backend
- **TypeScript errors**: Run `npm run tsc` for type-only checks

## Common Pitfalls

| Pitfall                                   | Fix                                                                                                                                     |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `npm install` creates inconsistent state  | Always use `npm ci`                                                                                                                     |
| Port 5173 or 3000 already in use          | Kill the existing process or change the port                                                                                            |
| Broad Zustand subscriptions               | Use custom hooks (`useActivities()`, etc.) instead of `useWorkflowStore()` with no selector                                             |
| Non-atomic coupled state updates          | Use `batchRemoveNodesAndEdges()` instead of separate calls                                                                              |
| String literals for activity / step types | Use enum constants from `@syntara/contracts` (e.g., `ActivityTypeEnum.CONDITION`)                                                       |
| Using display strings in logic            | Compare raw API values, not translated labels                                                                                           |
| Unary `void` for promises or side effects | Use `detachPromise(...)` from `utils/detachPromise`, `await`, or a small `async` helper — ESLint `no-void` and Sonar forbid `void expr` |

See [docs/zustand-architecture.md](docs/zustand-architecture.md) — "Common Pitfalls & Solutions" for detailed examples.

## Best Practices

### Code Quality

- Follow TypeScript strict mode — avoid `any`
- Use ESLint and Prettier (`npm run format`)
- Write comprehensive tests ([80% coverage threshold](docs/zustand-architecture.md))
- Keep components small and focused
- Use PatternFly 6 components as the foundation for all UI

### API Interaction

- Use generated OpenAPI types from `@syntara/contracts`
- Handle loading and error states with `useQueryState` and `useMutationErrorHandler`
- Use TanStack Query hooks (`workflowClient.useQuery`, `workflowClient.useMutation`)
- See [docs/data-flow.md](docs/data-flow.md) for the complete API integration guide
- See [docs/error-handling.md](docs/error-handling.md) for error handling patterns

### State Management

| Type                | Technology     | Use case                                             |
| ------------------- | -------------- | ---------------------------------------------------- |
| **Server state**    | TanStack Query | All API data (fetching, caching, background updates) |
| **Workflow state**  | Zustand        | The workflow currently being edited in the builder   |
| **WebSocket state** | Zustand        | Real-time connection state and messages              |
| **Auth state**      | Zustand        | Authentication tokens and session                    |
| **Project state**   | Zustand        | Active project scoping                               |
| **Local UI state**  | `useState`     | Component-local state (modals, forms, selections)    |

See [docs/zustand-architecture.md](docs/zustand-architecture.md) for the complete Zustand guide and [docs/websocket-architecture.md](docs/websocket-architecture.md) for WebSocket patterns.

## Troubleshooting

| Issue                                           | Solution                                                  |
| ----------------------------------------------- | --------------------------------------------------------- |
| Dependencies out of sync                        | `npm ci` from root                                        |
| Port already in use                             | Check for running processes on 5173 (UI) or 3000 (API)    |
| TypeScript errors after contract update         | Run `npm run gen` then `npm test`                         |
| WebSocket features not working                  | WebSocket requires the real backend, not the mock API     |
| Tests failing after registry / step-type change | Ensure `register*.ts` files use `export default function` |

## Further Reading

| Topic                         | Document                                                                                   |
| ----------------------------- | ------------------------------------------------------------------------------------------ |
| **AI-assisted development**   | [docs/ai-assisted-development.md](docs/ai-assisted-development.md) — prompts and workflows |
| Architecture overview         | [docs/architecture.md](docs/architecture.md)                                               |
| API integration & data flow   | [docs/data-flow.md](docs/data-flow.md)                                                     |
| Zustand state management      | [docs/zustand-architecture.md](docs/zustand-architecture.md)                               |
| WebSocket infrastructure      | [docs/websocket-architecture.md](docs/websocket-architecture.md)                           |
| Execution visualizer protocol | [docs/execution-visualizer-protocol.md](docs/execution-visualizer-protocol.md)             |
| Error handling                | [docs/error-handling.md](docs/error-handling.md)                                           |
| Workflow loading & saving     | [docs/workflow-loading-saving.md](docs/workflow-loading-saving.md)                         |
| Testing guide                 | [packages/syntara-ui/TESTING.md](packages/syntara-ui/TESTING.md)                           |
| Contributing guidelines       | [CONTRIBUTING.md](CONTRIBUTING.md)                                                         |
