import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { ExpandableCodeEditor } from './ExpandableCodeEditor'

// Mock theme hook
vi.mock('../../../providers/theme/useColorScheme', () => ({
  useColorScheme: vi.fn(() => ({
    colorScheme: 'dark',
    setColorScheme: vi.fn(),
    toggleColorScheme: vi.fn(),
  })),
}))

// Mock Monaco editor since it doesn't work well in test environment
vi.mock('@patternfly/react-code-editor', () => ({
  CodeEditor: ({
    code,
    onCodeChange,
    customControls,
    'aria-label': ariaLabel,
  }: {
    code: string
    onCodeChange: (code: string) => void
    customControls?: React.ReactNode
    'aria-label'?: string
  }) => (
    <div data-testid="code-editor" aria-label={ariaLabel}>
      <textarea
        data-testid="code-textarea"
        value={code}
        onChange={(e) => onCodeChange(e.target.value)}
        aria-label={ariaLabel}
      />
      {customControls}
    </div>
  ),
  CodeEditorControl: ({
    icon,
    onClick,
    'aria-label': ariaLabel,
  }: {
    icon: React.ReactNode
    onClick: () => void
    'aria-label'?: string
  }) => (
    <button data-testid="expand-button" onClick={onClick} aria-label={ariaLabel}>
      {icon}
    </button>
  ),
  Language: {
    plaintext: 'plaintext',
    python: 'python',
    bash: 'bash',
    json: 'json',
    javascript: 'javascript',
  },
}))

describe('ExpandableCodeEditor', () => {
  const defaultProps = {
    code: 'console.log("hello")',
    onCodeChange: vi.fn(),
  }

  it('renders the code editor with code', () => {
    render(<ExpandableCodeEditor {...defaultProps} />)

    expect(screen.getByTestId('code-editor')).toBeInTheDocument()
    expect(screen.getByTestId('code-textarea')).toHaveValue('console.log("hello")')
  })

  it('renders the expand button', () => {
    render(<ExpandableCodeEditor {...defaultProps} />)

    expect(screen.getByTestId('expand-button')).toBeInTheDocument()
    expect(screen.getByLabelText('Open in new window')).toBeInTheDocument()
  })

  it('opens modal when expand button is clicked', async () => {
    const user = userEvent.setup()
    render(<ExpandableCodeEditor {...defaultProps} modalTitle="Test Modal" />)

    // Modal should not be visible initially
    expect(screen.queryByText('Test Modal')).not.toBeInTheDocument()

    // Click expand button
    await user.click(screen.getByTestId('expand-button'))

    // Modal should now be visible
    expect(screen.getByText('Test Modal')).toBeInTheDocument()
  })

  it('closes modal when close button is clicked', async () => {
    const user = userEvent.setup()
    render(<ExpandableCodeEditor {...defaultProps} modalTitle="Test Modal" />)

    // Open modal
    await user.click(screen.getByTestId('expand-button'))
    expect(screen.getByText('Test Modal')).toBeInTheDocument()

    // Click the primary close button in footer (not the X button)
    const closeButtons = screen.getAllByRole('button', { name: /close/i })
    const footerCloseButton = closeButtons.find((btn) => btn.classList.contains('pf-m-primary'))
    await user.click(footerCloseButton!)

    // Modal should be closed
    expect(screen.queryByText('Test Modal')).not.toBeInTheDocument()
  })

  it('calls onCodeChange when code is edited', async () => {
    const onCodeChange = vi.fn()
    const user = userEvent.setup()
    render(<ExpandableCodeEditor code="" onCodeChange={onCodeChange} />)

    const textarea = screen.getByTestId('code-textarea')
    await user.type(textarea, 'new code')

    expect(onCodeChange).toHaveBeenCalled()
  })

  it('uses custom aria-label when provided', () => {
    render(<ExpandableCodeEditor {...defaultProps} ariaLabel="Python script editor" />)

    // The mock applies aria-label to both the wrapper div and textarea
    const elements = screen.getAllByLabelText('Python script editor')
    expect(elements.length).toBeGreaterThan(0)
  })

  it('uses default modal title when not provided', async () => {
    const user = userEvent.setup()
    render(<ExpandableCodeEditor {...defaultProps} />)

    await user.click(screen.getByTestId('expand-button'))

    expect(screen.getByText('Edit script')).toBeInTheDocument()
  })

  it('uses custom modal title when provided', async () => {
    const user = userEvent.setup()
    render(<ExpandableCodeEditor {...defaultProps} modalTitle="Edit Python Script" />)

    await user.click(screen.getByTestId('expand-button'))

    expect(screen.getByText('Edit Python Script')).toBeInTheDocument()
  })

  it('renders two code editors when modal is open', async () => {
    const user = userEvent.setup()
    render(<ExpandableCodeEditor {...defaultProps} />)

    // Initially one editor
    expect(screen.getAllByTestId('code-editor')).toHaveLength(1)

    // Open modal
    await user.click(screen.getByTestId('expand-button'))

    // Now two editors (inline + modal)
    expect(screen.getAllByTestId('code-editor')).toHaveLength(2)
  })

  it('shows helper text in modal', async () => {
    const user = userEvent.setup()
    render(<ExpandableCodeEditor {...defaultProps} />)

    await user.click(screen.getByTestId('expand-button'))

    // Helper text should be visible
    expect(screen.getByText(/Enter or edit the code below/i)).toBeInTheDocument()
    expect(screen.getByText(/the code will still persist/i)).toBeInTheDocument()
  })

  it('calls onBlur with latest value when modal is closed after editing', async () => {
    const onBlur = vi.fn()
    const user = userEvent.setup()
    function EditorWithState() {
      const [code, setCode] = useState('initial')
      return <ExpandableCodeEditor code={code} onCodeChange={setCode} onBlur={onBlur} modalTitle="Test Modal" />
    }
    render(<EditorWithState />)

    await user.click(screen.getByTestId('expand-button'))
    const modalTextarea = within(screen.getByTestId('modal-code-editor')).getByRole('textbox')
    await user.clear(modalTextarea)
    await user.type(modalTextarea, 'edited in modal')

    const closeButton = screen
      .getAllByRole('button', { name: /close/i })
      .find((btn) => btn.classList.contains('pf-m-primary'))
    await user.click(closeButton!)

    expect(onBlur).toHaveBeenCalledWith('edited in modal')
  })

  it('calls onDropText when text is dropped from internal source', () => {
    const onDropText = vi.fn()
    render(<ExpandableCodeEditor {...defaultProps} onDropText={onDropText} />)

    const dropTarget = screen.getByTestId('inline-code-editor')
    const dataTransfer = {
      getData: (format: string) => {
        if (format === 'application/json') return '{"type":"syntara/input-field"}'
        if (format === 'text/plain') return '${node.field}'
        return ''
      },
      dropEffect: '',
    }

    fireEvent.drop(dropTarget, { dataTransfer })

    expect(onDropText).toHaveBeenCalledWith('${node.field}')
  })

  it('rejects drops from external sources without application/json', () => {
    const onDropText = vi.fn()
    render(<ExpandableCodeEditor {...defaultProps} onDropText={onDropText} />)

    const dropTarget = screen.getByTestId('inline-code-editor')
    const dataTransfer = {
      getData: (format: string) => (format === 'text/plain' ? 'malicious code' : ''),
      dropEffect: '',
    }

    fireEvent.drop(dropTarget, { dataTransfer })

    expect(onDropText).not.toHaveBeenCalled()
  })

  it('shows drop highlight on dragOver', () => {
    render(<ExpandableCodeEditor {...defaultProps} />)

    const dropTarget = screen.getByTestId('inline-code-editor')
    const dataTransfer = { dropEffect: '' }

    fireEvent.dragOver(dropTarget, { dataTransfer })

    expect(dropTarget.style.outline).toBe('2px solid var(--pf-t--global--color--brand--default)')
  })

  it('removes drop highlight on dragLeave', () => {
    render(<ExpandableCodeEditor {...defaultProps} />)

    const dropTarget = screen.getByTestId('inline-code-editor')
    const dataTransfer = { dropEffect: '' }

    // First dragOver to add highlight
    fireEvent.dragOver(dropTarget, { dataTransfer })
    expect(dropTarget.style.outline).toBe('2px solid var(--pf-t--global--color--brand--default)')

    // Then dragLeave to remove it
    fireEvent.dragLeave(dropTarget)
    expect(dropTarget.style.outline).toBe('')
  })

  it('does not call onDropText when no text/plain data is present', () => {
    const onDropText = vi.fn()
    render(<ExpandableCodeEditor {...defaultProps} onDropText={onDropText} />)

    const dropTarget = screen.getByTestId('inline-code-editor')
    const dataTransfer = {
      getData: () => '',
      dropEffect: '',
    }

    fireEvent.drop(dropTarget, { dataTransfer })

    expect(onDropText).not.toHaveBeenCalled()
  })
})
