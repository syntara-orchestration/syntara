## Description

Briefly describe what this pull request does and why it's needed.

## Type of Change

- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Code refactoring (no functional changes)
- [ ] Performance improvement
- [ ] Test coverage improvement

## Changes Made

- [ ] List the specific changes made
- [ ] Include any new dependencies or configuration changes

## Out of Scope

<!-- What this PR intentionally does NOT include, to set reviewer expectations -->

## Related Issues

Fixes #(issue number)
Closes #(issue number)
Related to #(issue number)

## How to Test

<!-- Manual testing directions, for example:
1. Log in as an admin
2. Go to the `/workflows` route
3. Click on a thing
4. Validate that something changed
-->

## Backend Checklist

- [ ] I have run `make test` and all tests pass (in `backend/`)
- [ ] I have run `make lint` and code passes all checks
- [ ] I have run `make format` to ensure consistent formatting
- [ ] I have run `make typecheck` and all types are correct
- [ ] I have added tests for new functionality
- [ ] Database migrations are included if schema changed
- [ ] No sensitive information (keys, passwords, etc.) is included

## Frontend Checklist

- [ ] I have run `npm test` and all tests pass (in `frontend/`)
- [ ] I have run `npm run lint` and code passes all checks
- [ ] I have run `npm run tsc` and there are no type errors
- [ ] I have added tests (unit / E2E) for new functionality
- [ ] Accessibility has been considered (semantic HTML, labels, keyboard navigation)
- [ ] Screenshots or screen recordings are attached for UI changes

## Visual Regression

> Visual regression does **not** run automatically on this PR. If your change affects UI that's covered by `e2e/visual-regression/page-registry.ts`, update baselines yourself before requesting review — otherwise the weekly baseline-refresh PR will pick up the drift and route it to the UI/UX team instead of you.

- [ ] If this PR intentionally changes covered UI: I have commented `/update-screenshots` on this PR and confirmed the regenerated baselines look correct in the Files changed tab
- [ ] If this PR adds a new page/route: I have added an entry to `page-registry.ts` and run `/update-screenshots` to generate its baseline

## General Checklist

If your PR addresses a Jira work item, link it in the PR description. PRs that
don't reference a Jira work item are considered community contributions and
should have the `community` label. Please add it, or ask a maintainer to add it
if you don't have permission to manage labels.

- [ ] Code follows the project's coding conventions
- [ ] I have updated relevant documentation
- [ ] No secrets or credentials are included in this PR
- [ ] Breaking changes are documented with migration steps

## Screenshots / Demo (if applicable)

<!-- Add screenshots or screen recordings to demonstrate UI or UX changes -->

## Additional Notes

<!-- Add any other context, concerns, or notes for reviewers here -->
