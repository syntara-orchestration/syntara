# AI Agent Instructions

## Testing conventions

- Use the existing MSW server and handlers when testing HTTP or webhook behavior.
- Do not mock `fetch` or inject fake HTTP clients/notifier factories when MSW can exercise the real request boundary.
