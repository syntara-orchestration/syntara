import { render, renderHook, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { axe } from 'vitest-axe'

import { StepFormTabBarProvider } from './StepFormTabBarContext'
import { useStepFormTabBar } from './useStepFormTabBar'

describe('StepFormTabBarContext', () => {
  describe('useStepFormTabBar', () => {
    it('returns undefined when used without a provider', () => {
      const { result } = renderHook(() => useStepFormTabBar())

      expect(result.current).toBeUndefined()
    })

    it('returns the tabBarAction when used inside StepFormTabBarProvider', () => {
      const testAction = <button type="button">Test Action</button>

      const { result } = renderHook(() => useStepFormTabBar(), {
        wrapper: ({ children }) => (
          <StepFormTabBarProvider tabBarAction={testAction}>{children}</StepFormTabBarProvider>
        ),
      })

      expect(result.current).toBe(testAction)
    })

    it('returns undefined when provider has no tabBarAction', () => {
      const { result } = renderHook(() => useStepFormTabBar(), {
        wrapper: ({ children }) => <StepFormTabBarProvider>{children}</StepFormTabBarProvider>,
      })

      expect(result.current).toBeUndefined()
    })
  })

  describe('StepFormTabBarProvider', () => {
    it('provides the tabBarAction value to children', () => {
      const testAction = <button type="button">Custom Action</button>

      function TestConsumer() {
        const action = useStepFormTabBar()
        return <div>{action}</div>
      }

      render(
        <StepFormTabBarProvider tabBarAction={testAction}>
          <TestConsumer />
        </StepFormTabBarProvider>
      )

      expect(screen.getByRole('button', { name: 'Custom Action' })).toBeInTheDocument()
    })

    it('renders children correctly', () => {
      render(
        <StepFormTabBarProvider>
          <div>Child Content</div>
        </StepFormTabBarProvider>
      )

      expect(screen.getByText('Child Content')).toBeInTheDocument()
    })
  })

  describe('Integration', () => {
    it('allows multiple consumers to access the same tabBarAction', () => {
      const testAction = <button type="button">Shared Action</button>

      function Consumer({ id }: { id: string }) {
        const action = useStepFormTabBar()
        return <div data-testid={id}>{action}</div>
      }

      render(
        <StepFormTabBarProvider tabBarAction={testAction}>
          <Consumer id="consumer-1" />
          <Consumer id="consumer-2" />
        </StepFormTabBarProvider>
      )

      const consumer1 = screen.getByTestId('consumer-1')
      const consumer2 = screen.getByTestId('consumer-2')

      expect(within(consumer1).getByRole('button')).toHaveTextContent('Shared Action')
      expect(within(consumer2).getByRole('button')).toHaveTextContent('Shared Action')
    })

    it('updates when tabBarAction changes', () => {
      const initialAction = <button type="button">Initial Action</button>
      const updatedAction = <button type="button">Updated Action</button>

      function TestConsumer() {
        const action = useStepFormTabBar()
        return <div>{action}</div>
      }

      const { rerender } = render(
        <StepFormTabBarProvider tabBarAction={initialAction}>
          <TestConsumer />
        </StepFormTabBarProvider>
      )

      expect(screen.getByRole('button', { name: 'Initial Action' })).toBeInTheDocument()

      rerender(
        <StepFormTabBarProvider tabBarAction={updatedAction}>
          <TestConsumer />
        </StepFormTabBarProvider>
      )

      expect(screen.queryByRole('button', { name: 'Initial Action' })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Updated Action' })).toBeInTheDocument()
    })

    it('supports complex ReactNode as tabBarAction', () => {
      const complexAction = (
        <div>
          <button type="button">Primary</button>
          <button type="button">Secondary</button>
        </div>
      )

      function TestConsumer() {
        const action = useStepFormTabBar()
        return <div>{action}</div>
      }

      render(
        <StepFormTabBarProvider tabBarAction={complexAction}>
          <TestConsumer />
        </StepFormTabBarProvider>
      )

      expect(screen.getByRole('button', { name: 'Primary' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Secondary' })).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations with tabBarAction', async () => {
      const testAction = <button type="button">Accessible Action</button>

      function TestConsumer() {
        const action = useStepFormTabBar()
        return <div>{action}</div>
      }

      const { container } = render(
        <StepFormTabBarProvider tabBarAction={testAction}>
          <TestConsumer />
        </StepFormTabBarProvider>
      )

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has no accessibility violations without tabBarAction', async () => {
      const { container } = render(
        <StepFormTabBarProvider>
          <div>Content</div>
        </StepFormTabBarProvider>
      )

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
