import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { SynStepTitle } from './SynStepTitle'

describe('SynStepTitle', () => {
  describe('title rendering', () => {
    it('renders title when provided', () => {
      render(<SynStepTitle title="My Task" />)

      expect(screen.getByRole('heading', { level: 2, name: 'My Task' })).toBeInTheDocument()
    })

    it('renders title as h2 heading', () => {
      render(<SynStepTitle title="Test Title" />)

      const heading = screen.getByRole('heading', { level: 2 })
      expect(heading).toHaveTextContent('Test Title')
    })
  })

  describe('subtitle rendering', () => {
    it('renders subtitle when title is not provided', () => {
      render(<SynStepTitle subTitle="Task" />)

      expect(screen.getByRole('heading', { level: 2, name: 'Task' })).toBeInTheDocument()
    })

    it('renders both title and subtitle when both provided', () => {
      render(<SynStepTitle title="My Task" subTitle="Script" />)

      // Title should be in heading
      expect(screen.getByRole('heading', { level: 2, name: 'My Task' })).toBeInTheDocument()
      // Subtitle should also be visible
      expect(screen.getByText('Script')).toBeInTheDocument()
    })

    it('subtitle appears below title when both present', () => {
      render(<SynStepTitle title="Main Title" subTitle="Subtitle Text" />)

      // Both should be visible
      expect(screen.getByText('Main Title')).toBeInTheDocument()
      expect(screen.getByText('Subtitle Text')).toBeInTheDocument()
    })
  })

  describe('edge cases', () => {
    it('renders without crashing when no props provided', () => {
      render(<SynStepTitle />)

      // Should render empty heading
      const heading = screen.getByRole('heading', { level: 2 })
      expect(heading).toBeInTheDocument()
    })

    it('renders empty title correctly', () => {
      render(<SynStepTitle title="" subTitle="Fallback" />)

      // Empty title means subtitle becomes the heading content
      expect(screen.getByRole('heading', { level: 2 })).toBeInTheDocument()
    })

    it('keeps the full title in the heading when it is visually clamped', () => {
      const longTitle = 'This is a very long title that might need to wrap or truncate in some contexts'
      render(<SynStepTitle title={longTitle} />)

      expect(screen.getByRole('heading', { level: 2, name: longTitle })).toBeInTheDocument()
    })

    it('shows a tooltip with the full title when the clamped title is hovered', async () => {
      const user = userEvent.setup()
      const scrollHeight = vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(80)
      const clientHeight = vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(20)
      const longTitle = 'A very long step title that clamps'

      render(<SynStepTitle title={longTitle} />)
      await user.hover(screen.getByRole('heading', { name: longTitle }))

      expect(await screen.findByRole('tooltip')).toHaveTextContent(longTitle)
      scrollHeight.mockRestore()
      clientHeight.mockRestore()
    })

    it('shows the title tooltip when the step focus target is focused', async () => {
      const user = userEvent.setup()
      const scrollHeight = vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(80)
      const clientHeight = vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(20)
      const longTitle = 'A very long step title that clamps'

      render(
        <button type="button" className="react-flow__node">
          <SynStepTitle title={longTitle} />
        </button>
      )
      await user.tab()

      expect(await screen.findByRole('tooltip')).toHaveTextContent(longTitle)
      scrollHeight.mockRestore()
      clientHeight.mockRestore()
    })

    it('renders title with special characters', () => {
      render(<SynStepTitle title="Task <script> & 'quotes'" />)

      expect(screen.getByText("Task <script> & 'quotes'")).toBeInTheDocument()
    })
  })
})
