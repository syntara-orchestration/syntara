import { render } from '@testing-library/react'
import { describe, it, vi } from 'vitest'

import { expectPageTitle } from '../../test/pageTitle'

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQueryClient: () => ({ prefetchQuery: vi.fn() }),
  }
})

vi.mock('../../client', () => ({
  workflowClient: {
    queryOptions: vi.fn().mockReturnValue({ queryKey: [], queryFn: vi.fn() }),
  },
}))

vi.mock('./BuilderContent', () => ({
  BuilderContent: () => <div data-testid="builder-content" />,
}))

vi.mock('@xyflow/react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@xyflow/react')>()
  return { ...actual, ReactFlowProvider: ({ children }: { children: React.ReactNode }) => <>{children}</> }
})

describe('BuilderNew', () => {
  it('sets the browser tab title', async () => {
    const { default: BuilderNew } = await import('./BuilderNew')
    render(<BuilderNew />)
    expectPageTitle('New Workflow | Workflows | Syntara')
  })
})
