import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { RegistryStepId } from '../../../../constants'

import { renderStepIcon as renderStepIcon } from './renderStepIcon'

// Mock icon component
function MockIcon() {
  return <span data-testid="mock-icon">Icon</span>
}

// Mock icon component that accepts style prop (for custom icons)
function MockStyledIcon({ style }: Readonly<{ style?: React.CSSProperties }>) {
  return (
    <span data-testid="styled-icon" style={style}>
      Styled Icon
    </span>
  )
}

describe('renderStepIcon', () => {
  it('returns undefined when no IconComponent is provided', () => {
    const view = renderStepIcon(undefined, 'test-node')
    expect(view).toBeUndefined()
  })

  it('renders standard icon for non-custom nodes', () => {
    const view = renderStepIcon(MockIcon, 'test-node')
    render(<>{view}</>)

    expect(screen.getByTestId('mock-icon')).toBeInTheDocument()
  })

  it('renders custom icon with styling for aap node', () => {
    const view = renderStepIcon(MockStyledIcon, RegistryStepId.AAP_EXECUTION)
    render(<>{view}</>)

    const icon = screen.getByTestId('styled-icon')
    expect(icon).toBeInTheDocument()
    expect(icon).toHaveStyle({
      width: '100%',
      height: '100%',
      display: 'block',
    })
  })

  it('renders custom icon with styling for eda trigger node (smaller scale than aap)', () => {
    const view = renderStepIcon(MockStyledIcon, RegistryStepId.TRIGGER_EDA)
    render(<>{view}</>)

    const icon = screen.getByTestId('styled-icon')
    expect(icon).toBeInTheDocument()
    expect(icon).toHaveStyle({
      width: '100%',
      height: '100%',
      display: 'block',
    })
    // EDA icon fills its viewBox edge-to-edge so needs less scaling than AAP (1.8)
    expect(icon.style.transform).toContain('scale(1.4)')
  })

  it('applies rotation transform for logic-condition node', () => {
    const view = renderStepIcon(MockIcon, RegistryStepId.LOGIC_CONDITION)
    render(<>{view}</>)

    const iconWrapper = screen.getByTestId('step-icon-wrapper')
    expect(iconWrapper).toHaveStyle({ transform: 'rotate(90deg)' })
  })

  it('applies rotation transform for logic-converge node', () => {
    const view = renderStepIcon(MockIcon, RegistryStepId.LOGIC_CONVERGE)
    render(<>{view}</>)

    const iconWrapper = screen.getByTestId('step-icon-wrapper')
    expect(iconWrapper).toHaveStyle({ transform: 'rotate(90deg)' })
  })

  it('does not apply rotation for regular nodes', () => {
    const view = renderStepIcon(MockIcon, 'regular-node')
    render(<>{view}</>)

    const iconWrapper = screen.getByTestId('step-icon-wrapper')
    expect(iconWrapper).not.toHaveStyle({ transform: 'rotate(90deg)' })
  })

  it('applies color when provided so icon matches step type accent', () => {
    const token = 'var(--pf-t--global--color--brand--default)'
    const view = renderStepIcon(MockIcon, 'test-node', 'canvas', token)
    render(<>{view}</>)

    const iconWrapper = screen.getByTestId('step-icon-wrapper')
    // Assert on the literal inline style rather than toHaveStyle(): getComputedStyle can't
    // resolve var() (happy-dom does not perform real CSS cascade), so it isn't a
    // meaningful check for this brand-color token.
    expect(iconWrapper.style.color).toBe(token)
    expect(iconWrapper.style.getPropertyValue('--pf-v6-c-icon__content--Color')).toBe(token)
  })

  it('does not apply color when not provided', () => {
    const view = renderStepIcon(MockIcon, 'test-node')
    render(<>{view}</>)

    const iconWrapper = screen.getByTestId('step-icon-wrapper')
    expect(iconWrapper.style.color).toBe('')
  })

  it('uses canvas variant by default (md size)', () => {
    const view = renderStepIcon(MockIcon, 'test-node')
    render(<>{view}</>)

    const iconWrapper = screen.getByTestId('step-icon-wrapper')
    expect(iconWrapper).toHaveClass('pf-m-md')
  })

  it('uses list variant when specified (xl size)', () => {
    const view = renderStepIcon(MockIcon, 'test-node', 'list')
    render(<>{view}</>)

    const iconWrapper = screen.getByTestId('step-icon-wrapper')
    expect(iconWrapper).toHaveClass('pf-m-xl')
  })

  it('uses legend variant when specified (md size, compact rows)', () => {
    const view = renderStepIcon(MockIcon, 'test-node', 'legend')
    render(<>{view}</>)

    const iconWrapper = screen.getByTestId('step-icon-wrapper')
    expect(iconWrapper).toHaveClass('pf-m-md')
  })

  it('uses header variant when specified (xl size)', () => {
    const view = renderStepIcon(MockIcon, 'test-node', 'header')
    render(<>{view}</>)

    const iconWrapper = screen.getByTestId('step-icon-wrapper')
    expect(iconWrapper).toHaveClass('pf-m-xl')
  })

  it('applies different custom icon offset for header variant', () => {
    const view = renderStepIcon(MockStyledIcon, RegistryStepId.AAP_EXECUTION, 'header')
    render(<>{view}</>)

    const icon = screen.getByTestId('styled-icon')
    // Header variant has customIconOffsetY: 1
    expect(icon.style.transform).toContain('translateY(1px)')
  })

  it('applies zero offset for canvas variant custom icon', () => {
    const view = renderStepIcon(MockStyledIcon, RegistryStepId.AAP_EXECUTION, 'canvas')
    render(<>{view}</>)

    const icon = screen.getByTestId('styled-icon')
    // Canvas variant has customIconOffsetY: 0
    expect(icon.style.transform).toContain('translateY(0px)')
  })

  it('applies correct scale for list variant custom icon', () => {
    const view = renderStepIcon(MockStyledIcon, RegistryStepId.AAP_EXECUTION, 'list')
    render(<>{view}</>)

    const icon = screen.getByTestId('styled-icon')
    // List variant has customIconScale: 1.5
    expect(icon.style.transform).toContain('scale(1.5)')
  })

  it('applies legend scale for custom icon', () => {
    const view = renderStepIcon(MockStyledIcon, RegistryStepId.AAP_EXECUTION, 'legend')
    render(<>{view}</>)

    const icon = screen.getByTestId('styled-icon')
    expect(icon.style.transform).toContain('scale(1.25)')
  })
})
