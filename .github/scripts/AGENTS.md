# AI Agent Instructions

## Testing conventions

- Use the existing MSW server and handlers when testing HTTP or webhook behavior.
- Do not mock `fetch` or inject fake HTTP clients/notifier factories when MSW can exercise the real request boundary.

## Source documentation

- Add concise JSDoc descriptions for variables and functions introduced or changed in TypeScript source files.
- Describe purpose or non-obvious behavior; do not repeat type information already expressed by TypeScript or add `{Type}` annotations.
- Keep comments to one sentence when possible, and use `@param`, `@returns`, or `@throws` only when they add useful context beyond the signature.
