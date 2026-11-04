/** Generate the Kafka UI contracts from the current backend schemas. */
import { execFileSync } from 'node:child_process'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const repositoryRoot = resolve(packageRoot, '../../..')
const prefix = 'backend/src/syntara/schemas'
const outputs = []
for (const [source, output] of [
  ['workflows/v2', 'workflow-api.ts'],
  ['integrations', 'integrations-api.ts'],
]) {
  const target = join(packageRoot, 'src', output)
  execFileSync(
    process.execPath,
    [
      join(packageRoot, 'node_modules/openapi-typescript/bin/cli.js'),
      join(repositoryRoot, prefix, source, 'openapi.yaml'),
      '--output',
      target,
      '--default-non-nullable',
      'false',
    ],
    { stdio: 'inherit' }
  )
  outputs.push(target)
}
execFileSync(
  process.execPath,
  [join(repositoryRoot, 'frontend/node_modules/prettier/bin/prettier.cjs'), '--write', ...outputs],
  { stdio: 'inherit' }
)
