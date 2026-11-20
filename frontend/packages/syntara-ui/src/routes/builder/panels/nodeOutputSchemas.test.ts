import { getNodeOutputSchema } from '@syntara/contracts'
import { describe, expect, it } from 'vitest'

describe('script node output schemas', () => {
  it('exposes the Python result fields, including parsed JSON output', () => {
    const fields = getNodeOutputSchema('script_python')

    expect(fields?.map(({ name }) => name)).toEqual(['status', 'return_code', 'stdout', 'stderr', 'stdout_json'])
  })

  it('exposes Bash result fields without the Python-only JSON output', () => {
    const fields = getNodeOutputSchema('script_bash')

    expect(fields?.map(({ name }) => name)).toEqual(['status', 'return_code', 'stdout', 'stderr'])
  })
})
