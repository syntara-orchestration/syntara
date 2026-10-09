---
description: "Official docs and upstream agent skills for frontend libraries. Read before writing code against these libraries."
user-invocable: false
---

# Library References

**Before writing code that uses any library listed below that provides an `llms.txt`, fetch it and use it as your primary reference for current APIs and patterns.** These files are maintained by each project and reflect their latest stable documentation. Do not rely on training-data knowledge alone — APIs change across major versions. Verify that the documentation is accurate and consistent with the code being reviewed.

When a library also publishes task-specific agent skills, read the relevant skill alongside its API docs. Check the skill's declared library version against the version in the package manifest and lockfile before applying version-specific advice. Treat upstream examples as library guidance; Syntara's existing architecture and patterns remain the guide for how to use the library in this app.

This is especially critical for:

- **React 19** — hooks, compiler, and concurrent features changed significantly from v18
- **Zod v4** — schema API has breaking changes from v3
- **Zustand v5** — store creation and middleware API changed from v4

## Libraries with `llms.txt`

| Library              | Role in this project                         | Action                                                                                                         |
| -------------------- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| **React**            | UI rendering, hooks                          | Fetch https://react.dev/llms.txt before writing any React code                                                 |
| **Zod**              | Schema validation + react-hook-form resolver | Fetch https://zod.dev/llms.txt before writing any Zod schema                                                   |
| **Zustand**          | Global state (workflow store, builder)       | Fetch https://zustand.docs.pmnd.rs/llms.txt before touching any store                                          |
| **Vitest**           | Unit and component test runner               | Fetch https://vitest.dev/llms.txt before writing or configuring tests                                          |
| **Vite**             | Dev server and build tool                    | Fetch https://vite.dev/llms.txt before modifying build config                                                  |
| **TanStack Query**   | Server state / data fetching                 | Fetch https://tanstack.com/query/latest/llms.txt before writing queries, mutations, or polling behavior        |
| **TanStack Router**  | Type-safe application routing                | Fetch https://tanstack.com/router/latest/llms.txt before modifying routes, search state, or navigation          |
| **React Flow**       | Workflow builder canvas (`@xyflow/react`)    | Fetch https://reactflow.dev/llms.txt before working on the builder canvas                                      |
| **Storybook**        | Component library and visual testing         | Fetch https://storybook.js.org/llms.txt before writing or modifying stories                                    |
| **dnd-kit**          | Drag-and-drop interactions                   | Fetch https://dndkit.com/llms.txt before implementing drag-and-drop features                                   |

## Upstream Agent Guidance

- **TanStack Router:** Read the upstream [router-core skill](https://github.com/TanStack/router/blob/main/packages/router-core/skills/router-core/SKILL.md) as the entry point. For URL search state, also read the [search-params skill](https://github.com/TanStack/router/blob/main/packages/router-core/skills/router-core/search-params/SKILL.md). Adapt their API guidance to Syntara's route setup and existing hooks; this app does not use TanStack's file-based route generation.
- **TanStack Query:** The upstream [AGENTS.md](https://github.com/TanStack/query/blob/main/AGENTS.md) covers contributions to the Query repository. For Query usage in Syntara, use the official `llms.txt` reference in the table above.

## Libraries without `llms.txt` (use official docs instead)

| Library                | Docs                                                  |
| ---------------------- | ----------------------------------------------------- |
| **TypeScript**         | https://www.typescriptlang.org/docs/                  |
| **React Hook Form**    | https://react-hook-form.com/docs                      |
| **Testing Library**    | https://testing-library.com/docs/                     |
| **Playwright**         | https://playwright.dev/docs/intro                     |
| **PatternFly**         | https://www.patternfly.org/components/all-components/ |
| **openapi-fetch**      | https://openapi-ts.dev/openapi-fetch/                 |
| **openapi-react-query**| https://openapi-ts.dev/openapi-react-query/           |
| **date-fns**           | https://date-fns.org/docs/                            |
| **Fuse.js**            | https://www.fusejs.io/                                |
| **dagre**              | https://github.com/dagrejs/dagre/wiki                 |
| **zundo**              | https://github.com/charkour/zundo                     |
