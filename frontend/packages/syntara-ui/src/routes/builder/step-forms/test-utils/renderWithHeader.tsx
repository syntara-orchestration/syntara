import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { cloneElement, useState } from 'react'
import type { ReactElement, ReactNode } from 'react'

/**
 * Test utility to render a form component with header content handling.
 * This allows testing forms that use onHeaderContentChange prop.
 * Also wraps components with QueryClientProvider for React Query hooks.
 *
 * @param ui - The React element to render (typically a form component)
 * @returns The result from @testing-library/react's render function
 *
 * @example
 * ```tsx
 * renderWithHeader(<MyForm onSubmit={mockOnSubmit} />)
 * ```
 */
export function renderWithHeader(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  function Wrapper() {
    const [headerContent, setHeaderContent] = useState<ReactNode | null>(null)
    return (
      <QueryClientProvider client={queryClient}>
        {headerContent}
        {cloneElement(ui as ReactElement<{ onHeaderContentChange?: (content: ReactNode | null) => void }>, {
          onHeaderContentChange: setHeaderContent,
        })}
        <button type="submit" form="action-step-form">
          Submit
        </button>
      </QueryClientProvider>
    )
  }

  return render(<Wrapper />)
}
