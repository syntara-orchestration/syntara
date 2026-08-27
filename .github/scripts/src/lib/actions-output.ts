import { appendFileSync } from 'node:fs'

/**
 * Writes a step output for downstream workflow steps.
 * Uses GITHUB_OUTPUT in Actions; falls back to the legacy set-output command locally.
 */
export function setOutput(name: string, value: string): void {
  const outputFile = process.env.GITHUB_OUTPUT

  if (outputFile) {
    appendFileSync(outputFile, `${name}=${value}\n`)
    return
  }

  console.log(`::set-output name=${name}::${value}`)
}
