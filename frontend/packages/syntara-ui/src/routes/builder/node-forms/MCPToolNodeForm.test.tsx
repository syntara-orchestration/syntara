import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { MCPToolNodeForm } from './MCPToolNodeForm'
import { renderWithHeader } from './test-utils/renderWithHeader'

const { mockUseAllEnabledMcpIntegrations, mockUseMcpIntegrationTools } = vi.hoisted(() => ({
  mockUseAllEnabledMcpIntegrations: vi.fn(),
  mockUseMcpIntegrationTools: vi.fn(),
}))

vi.mock('./useAllEnabledMcpIntegrations', () => ({
  useAllEnabledMcpIntegrations: mockUseAllEnabledMcpIntegrations,
}))

vi.mock('./useMcpIntegrationTools', () => ({
  useMcpIntegrationTools: mockUseMcpIntegrationTools,
}))

vi.mock('../components/ExpandableCodeEditor', () => ({
  ExpandableCodeEditor: ({
    code,
    onCodeChange,
    ariaLabel,
  }: {
    code: string
    onCodeChange: (value: string) => void
    ariaLabel: string
  }) => <textarea aria-label={ariaLabel} value={code} onChange={(event) => onCodeChange(event.target.value)} />,
}))

const integrations = [
  { id: 'integration-1', name: 'Filesystem MCP' },
  { id: 'integration-2', name: 'GitHub MCP' },
]

const tools = [
  { id: 'tool-1', name: 'list_directory', description: 'List files in a directory', integration_id: 'integration-1' },
  { id: 'tool-2', name: 'read_file', description: 'Read a file', integration_id: 'integration-1' },
]

function submitForm() {
  fireEvent.submit(screen.getByTestId('mcp-tool-node-form'))
}

async function setArgumentsJson(user: ReturnType<typeof userEvent.setup>, json: string) {
  const editor = screen.getByLabelText('Tool arguments JSON editor')
  await user.click(editor)
  await user.paste(json)
}

describe('MCPToolNodeForm', () => {
  const mockOnSubmit = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    mockUseAllEnabledMcpIntegrations.mockReturnValue({
      integrations,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    })
    mockUseMcpIntegrationTools.mockReturnValue({ tools, isLoading: false, isError: false, refetch: vi.fn() })
  })

  describe('Rendering', () => {
    it('renders the integration, tool, arguments and timeout fields', () => {
      renderWithHeader(<MCPToolNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByText('MCP server integration')).toBeInTheDocument()
      expect(screen.getByText('Tool')).toBeInTheDocument()
      expect(screen.getByText('Arguments')).toBeInTheDocument()
      expect(screen.getByText('Timeout')).toBeInTheDocument()
      expect(screen.getByLabelText('Tool arguments JSON editor')).toBeInTheDocument()
    })

    it('scopes the integration query to the given project', () => {
      renderWithHeader(<MCPToolNodeForm onSubmit={mockOnSubmit} projectId="p-001" />)

      expect(mockUseAllEnabledMcpIntegrations).toHaveBeenCalledWith('p-001')
    })

    it('disables the tool select until an integration is chosen', () => {
      renderWithHeader(<MCPToolNodeForm onSubmit={mockOnSubmit} />)

      expect(screen.getByRole('button', { name: 'Tool' })).toBeDisabled()
      expect(screen.getByText('Select an MCP server integration first')).toBeInTheDocument()
    })
  })

  describe('Integration selection', () => {
    it('lists only the mcp_server integrations returned by the hook', async () => {
      const user = userEvent.setup()
      renderWithHeader(<MCPToolNodeForm onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('button', { name: 'MCP server integration' }))

      expect(screen.getByRole('option', { name: 'Filesystem MCP' })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: 'GitHub MCP' })).toBeInTheDocument()
    })

    it('loads the selected integration tools and enables the tool select', async () => {
      const user = userEvent.setup()
      renderWithHeader(<MCPToolNodeForm onSubmit={mockOnSubmit} />)

      await user.click(screen.getByRole('button', { name: 'MCP server integration' }))
      await user.click(screen.getByRole('option', { name: 'Filesystem MCP' }))

      await waitFor(() => {
        expect(mockUseMcpIntegrationTools).toHaveBeenLastCalledWith('integration-1')
      })
      expect(screen.getByRole('button', { name: 'Tool' })).not.toBeDisabled()
    })

    it('clears a previously selected tool when the integration changes', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <MCPToolNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ integration_id: 'integration-1', tool_name: 'list_directory' }}
        />
      )

      expect(screen.getByRole('button', { name: 'Tool' })).toHaveTextContent('list_directory')

      await user.click(screen.getByRole('button', { name: 'MCP server integration' }))
      await user.click(screen.getByRole('option', { name: 'GitHub MCP' }))

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Tool' })).toHaveTextContent('Select a tool')
      })
    })

    it('shows an empty-state option when the integration has no discovered tools', async () => {
      const user = userEvent.setup()
      mockUseMcpIntegrationTools.mockReturnValue({ tools: [], isLoading: false, isError: false, refetch: vi.fn() })

      renderWithHeader(<MCPToolNodeForm onSubmit={mockOnSubmit} initialData={{ integration_id: 'integration-1' }} />)

      await user.click(screen.getByRole('button', { name: 'Tool' }))

      expect(screen.getByRole('option', { name: 'No tools discovered on this integration' })).toBeInTheDocument()
    })
  })

  describe('Tool selection', () => {
    it('lists the discovered tool names', async () => {
      const user = userEvent.setup()
      renderWithHeader(<MCPToolNodeForm onSubmit={mockOnSubmit} initialData={{ integration_id: 'integration-1' }} />)

      await user.click(screen.getByRole('button', { name: 'Tool' }))

      expect(screen.getByRole('option', { name: /list_directory/ })).toBeInTheDocument()
      expect(screen.getByRole('option', { name: /read_file/ })).toBeInTheDocument()
    })
  })

  describe('Validation', () => {
    it('requires an integration and a tool', async () => {
      renderWithHeader(<MCPToolNodeForm onSubmit={mockOnSubmit} />)

      submitForm()

      await waitFor(() => {
        expect(screen.getByText('Select an MCP server integration')).toBeInTheDocument()
      })
      expect(screen.getByText('Select a tool')).toBeInTheDocument()
      expect(mockOnSubmit).not.toHaveBeenCalled()
    })

    it('rejects arguments that are not a JSON object', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <MCPToolNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ integration_id: 'integration-1', tool_name: 'list_directory' }}
        />
      )

      await setArgumentsJson(user, '[1, 2]')
      submitForm()

      await waitFor(() => {
        expect(screen.getByText(/Arguments must be a JSON object/)).toBeInTheDocument()
      })
      expect(mockOnSubmit).not.toHaveBeenCalled()
    })

    it('rejects a timeout above the backend maximum', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <MCPToolNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ integration_id: 'integration-1', tool_name: 'list_directory' }}
        />
      )

      await user.type(screen.getByLabelText('Timeout in seconds'), '601')
      submitForm()

      await waitFor(() => {
        expect(screen.getByText('Timeout cannot exceed 600 seconds')).toBeInTheDocument()
      })
      expect(mockOnSubmit).not.toHaveBeenCalled()
    })

    it('submits integration, tool, arguments and timeout', async () => {
      const user = userEvent.setup()
      renderWithHeader(
        <MCPToolNodeForm
          onSubmit={mockOnSubmit}
          initialData={{ integration_id: 'integration-1', tool_name: 'list_directory', timeout_seconds: 30 }}
        />
      )

      await setArgumentsJson(user, '{"path": "/tmp"}')
      submitForm()

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            integration_id: 'integration-1',
            tool_name: 'list_directory',
            argumentsJson: '{"path": "/tmp"}',
            timeout_seconds: 30,
          }),
          expect.anything()
        )
      })
    })
  })

  describe('Accessibility', () => {
    it('has no accessibility violations', async () => {
      const { container } = renderWithHeader(<MCPToolNodeForm onSubmit={mockOnSubmit} />)

      const results = await axe(container, { rules: { 'aria-valid-attr-value': { enabled: false } } })

      expect(results).toHaveNoViolations()
    })
  })
})
