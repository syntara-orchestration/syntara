/** Runs a CLI entrypoint and turns uncaught failures into a non-zero exit. */
export function runScript(main: () => Promise<void>): void {
  main().catch((error: unknown) => {
    console.error('Error:', error)
    process.exit(1)
  })
}
