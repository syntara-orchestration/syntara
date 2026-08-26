---
description: "Walk through building a frontend UI feature step by step — gathers requirements, implements, and validates."
user-invocable: true
---

You are walking a contributor through building a UI feature from start to finish. Ask questions, wait for answers, then do the work.

## Phase 1: Understand what to build

Ask these questions one at a time. Do not move on until you get an answer.

1. **What are we building?**
   Ask for an issue key or a plain description. If you cannot access the content, just say: "I couldn't pull that issue. Can you paste the title, description, and acceptance criteria here?"

2. **What should it look like?** (optional screenshot)
   Ask if they have a mockup screenshot (Figma export or browser screenshot). If they do, ask them to paste or drag it in — save it for comparison in Phase 5. If they don't have one, ask them to describe the layout in words: what goes where, how many columns, what buttons.

3. **Where does the data come from?**
   Ask for the API endpoint (e.g. `GET /api/v1/credentials`), the key fields in the response, and which client from `frontend/packages/syntara-ui/src/client.tsx` to use. If they're not sure about the client, search `frontend/packages/syntara-ui/src/client.tsx` and suggest the right one.

4. **What should it do?**
   Ask for the specific behaviors: what actions does the user take? What happens on success or failure? What states need to exist (loaded, empty, error, filtered with no results)?

5. **Do you want E2E tests?**
   If yes, you'll write Playwright tests in Phase 4.

> **Note:** Unit tests are always included — the agent writes them alongside the code in Phase 3 (happy path, empty states, error state, and accessibility). You don't need to ask for them.

## Phase 2: Make a plan

Before writing any code:

1. **Find the most similar page or component that already exists in the codebase.** This is the starting point — always follow existing patterns and conventions rather than inventing new ones.
2. Read `.claude/skills/frontend-coding-standards/SKILL.md`, `.claude/skills/frontend-patternfly-ux/SKILL.md`, and `.claude/skills/frontend-testing-guidelines/SKILL.md`. These are the authoritative guidelines for code quality, UX, and unit/a11y tests. Do not skip the testing skill — Phase 3 always writes unit tests.
3. Write a short plan: which files you'll create or change, which PatternFly components you'll use, and how you'll handle each state. The plan must align with existing codebase patterns. **New routes** must include an entry in `frontend/packages/syntara-ui/e2e/visual-regression/page-registry.ts` (see `VISUAL_REGRESSION.md`).
4. Show the plan and wait for approval. Do not write code until the user says go.

## Phase 3: Build it

Follow the project skills for implementation. **Always match existing codebase patterns** — the coding standards and UX design system skills are the primary guidelines, not general best practices:

- Use PatternFly 6 components and design tokens for all layout and styling.
- Use typed API clients from `frontend/packages/syntara-ui/src/client.tsx`. No raw `fetch()`.
- Use Zod + react-hook-form for any forms. Use manual `useState`/controlled form controls as a last resort.
- Handle all states: data loaded, no data yet, no filter results, API error with retry.
- Write unit tests alongside the code: happy path, empty states, error state, and at least one `toHaveNoViolations()` accessibility test. Follow `.claude/skills/frontend-testing-guidelines/SKILL.md` (query order, `userEvent.setup()`, jsdom not happy-dom, dedicated `use*.test.ts(x)` for new hooks).

After the code is written, check it against the UX design system:

- Does the component selection match the PatternFly rules? (right table variant, right modal size, right form layout)
- Does the spacing use design tokens (`var(--pf-t--global--spacer--*)`) instead of hardcoded pixels?
- If the user gave you a screenshot, compare your output against it and fix anything that doesn't match.

## Phase 4: Write E2E tests (if requested)

If the user asked for E2E tests:

1. Read `.claude/skills/frontend-playwright-e2e/SKILL.md` for the project's E2E patterns.
2. Write Playwright tests for the main user flows from Phase 1.
3. Wrap test actions in `try/finally` so test data always gets cleaned up.
4. Use the same accessible selectors as unit tests (`getByRole`, `getByLabel`).
5. To **run** the suite, follow `.claude/skills/frontend-run-e2e/SKILL.md`. Never print the admin password.

## Phase 5: Validate in the browser and capture final screenshot

Start the dev server if it's not running, navigate to the page, and capture a screenshot of the final implementation using browser tools (Chrome DevTools MCP, Playwright, or ask the user to paste one).

Walk through each state:

| State                  | How to trigger                         | What to look for                                   |
| ---------------------- | -------------------------------------- | -------------------------------------------------- |
| **Loaded**             | Page loads normally                    | Layout matches the mockup (if provided)            |
| **Empty (no data)**    | Remove mock data or use an empty array | "No [resources] yet" message                       |
| **Empty (no results)** | Type a filter that matches nothing     | "No results found" with a "Clear all filters" link |
| **Error**              | Stop the mock API server and reload    | Error message with a working "Retry" button        |
| **Success**            | Create or delete an item               | Toast notification appears                         |

Check the browser console for errors or warnings. Tab through the page to verify keyboard navigation.

**Final comparison:** If the user provided a mockup screenshot in Phase 1, compare the implementation screenshot against it side-by-side. Flag any visual differences (spacing, component choice, missing elements) and fix them. This usually takes 1-2 iterations.

## Phase 6: Code review

1. Run `/frontend-review-pr` to check against the quality checklist.
2. Fix any Blocking issues it finds.
3. Show a summary: what files were created or changed, what the PR does.
4. Remind the user to include screenshots of each state in the PR description. If you added a route, confirm the visual-regression registry row exists.
