import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

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

    it('renders long title without truncation', () => {
      const longTitle = 'This is a very long title that might need to wrap or truncate in some contexts'
      render(<SynStepTitle title={longTitle} />)

      expect(screen.getByText(longTitle)).toBeInTheDocument()
    })

    it('renders title with special characters', () => {
      render(<SynStepTitle title="Task <script> & 'quotes'" />)

      expect(screen.getByText("Task <script> & 'quotes'")).toBeInTheDocument()
    })
  })
})
