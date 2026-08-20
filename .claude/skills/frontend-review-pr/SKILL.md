---
description: "Review a frontend PR against the project's 36-item checklist and coding standards."
user-invocable: true
---

# Review PR

Follow the steps in `.claude/skills/frontend-pr-review/SKILL.md` to conduct a thorough pull request review.

Start by:

1. Reading `frontend/AGENTS.md` (especially the "Common PR Mistakes" section) and relevant project guidelines
2. Checking what files have changed (git diff or user-provided context)
3. Following all 9 steps from the PR review skill

**CRITICAL: Always run the "3a. Recurring Issues Checklist" from the PR review skill.** These are the most commonly flagged issues from real PR reviews. Every review MUST check for:

- Raw `fetch()` instead of typed API clients
- Missing `onRetry` in `useQueryState`
- Unsafe `as` casts on API responses
- Missing `vitest-axe` accessibility tests
- `fireEvent` instead of `userEvent` in tests
- `getByTestId`/`querySelector` instead of accessible queries
- Raw error markup instead of `ErrorState` component
- Manual `useState` forms instead of Zod + react-hook-form
- Edit modals not resetting `defaultValues`
- Duplicated dialog/logic patterns across files
- Inconsistent `useQueryState` / mutation error-handler usage vs project patterns
- UI changes without screenshots or screen recordings
- New API endpoints without mock API handlers in `frontend/packages/syntara-mock-api/src/handlers.ts`

Provide a structured review with the deliverables outlined in step 9.
