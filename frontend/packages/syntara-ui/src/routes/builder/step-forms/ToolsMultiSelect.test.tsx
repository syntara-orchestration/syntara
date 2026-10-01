import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import type { IntegrationWithTools, ToolSelection } from './ToolsMultiSelect'
import { ToolsMultiSelect } from './ToolsMultiSelect'

const mockIntegrations: IntegrationWithTools[] = [
  {
    id: 'int-1',
    name: 'Primary MCP Server',
    discovered_tools: [
      { id: 'tool-1', name: 'Primary MCP Server::list_resources', description: 'List all available resources' },
      { id: 'tool-2', name: 'Primary MCP Server::get_resource', description: 'Get a specific resource by ID' },
      { id: 'tool-3', name: 'Primary MCP Server::create_resource', description: 'Create a new resource' },
    ],
  },
  {
    id: 'int-2',
    name: 'Dev MCP Server',
    discovered_tools: [
      { id: 'tool-4', name: 'Dev MCP Server::dev_tool_1', description: 'Development tool 1' },
      { id: 'tool-5', name: 'Dev MCP Server::dev_tool_2', description: null },
    ],
  },
]

const NONE: ToolSelection = { strategy: 'NONE' }
const ALL: ToolSelection = { strategy: 'ALL' }
const selected = (...ids: string[]): ToolSelection => ({ strategy: 'SELECTED', toolIds: ids })

function renderComponent({
  value = NONE,
  onChange = vi.fn(),
  integrations = mockIntegrations,
  isLoading = false,
  hasNoIntegrations = false,
}: {
  value?: ToolSelection
  onChange?: (selection: ToolSelection) => void
  integrations?: IntegrationWithTools[]
  isLoading?: boolean
  hasNoIntegrations?: boolean
} = {}) {
  return render(
    <ToolsMultiSelect
      value={value}
      onChange={onChange}
      integrations={integrations}
      isLoading={isLoading}
      hasNoIntegrations={hasNoIntegrations}
    />
  )
}

describe('ToolsMultiSelect', () => {
  it('renders "No tools selected" when strategy is NONE', () => {
    renderComponent({ value: NONE })
    expect(screen.getByDisplayValue('No tools selected')).toBeInTheDocument()
  })

  it('renders "All tools selected" when strategy is ALL', () => {
    renderComponent({ value: ALL })
    expect(screen.getByDisplayValue('All tools selected')).toBeInTheDocument()
  })

  it('shows N of M tools selected when strategy is SELECTED', () => {
    renderComponent({ value: selected('tool-1', 'tool-4') })
    expect(screen.getByDisplayValue('2 of 5 tools selected')).toBeInTheDocument()
  })

  it('renders integration rows as checkboxes when dropdown is opened', async () => {
    const user = userEvent.setup()
    renderComponent()

    await user.click(screen.getByRole('textbox', { name: 'Select tools' }))

    expect(screen.getByRole('menuitem', { name: 'Primary MCP Server (3)' })).toBeInTheDocument()
    expect(screen.getByRole('menuitem', { name: 'Dev MCP Server (2)' })).toBeInTheDocument()
  })

  it('renders tool options without namespace prefix', async () => {
    const user = userEvent.setup()
    renderComponent()

    await user.click(screen.getByRole('textbox', { name: 'Select tools' }))

    expect(screen.getByText('list_resources')).toBeInTheDocument()
    expect(screen.getByText('get_resource')).toBeInTheDocument()
    expect(screen.queryByText('Primary MCP Server::list_resources')).not.toBeInTheDocument()
  })

  it('renders "All tools" option at the top of the dropdown', async () => {
    const user = userEvent.setup()
    renderComponent()

    await user.click(screen.getByRole('textbox', { name: 'Select tools' }))

    expect(screen.getByRole('menuitem', { name: 'All tools' })).toBeInTheDocument()
  })

  it('renders "All tools" even when no tools are discovered yet', async () => {
    const user = userEvent.setup()
    renderComponent({ value: NONE, integrations: [] })

    await user.click(screen.getByRole('textbox', { name: 'Select tools' }))

    expect(screen.getByRole('checkbox', { name: 'All tools' })).toBeInTheDocument()
  })

  it('"All tools" checkbox is checked when strategy is ALL', async () => {
    const user = userEvent.setup()
    renderComponent({ value: ALL })

    await user.click(screen.getByRole('textbox', { name: 'Select tools' }))

    expect(screen.getByRole('checkbox', { name: 'All tools' })).toBeChecked()
  })

  it('"All tools" checkbox is unchecked when strategy is NONE', async () => {
    const user = userEvent.setup()
    renderComponent({ value: NONE })

    await user.click(screen.getByRole('textbox', { name: 'Select tools' }))

    expect(screen.getByRole('checkbox', { name: 'All tools' })).not.toBeChecked()
  })

  it('clicking "All tools" when NONE emits ALL strategy', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    renderComponent({ value: NONE, onChange })

    await user.click(screen.getByRole('textbox', { name: 'Select tools' }))
    await user.click(screen.getByRole('checkbox', { name: 'All tools' }))

    expect(onChange).toHaveBeenCalledWith({ strategy: 'ALL' })
  })

  it('clicking "All tools" when ALL emits NONE strategy', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    renderComponent({ value: ALL, onChange })

    await user.click(screen.getByRole('textbox', { name: 'Select tools' }))
    await user.click(screen.getByRole('checkbox', { name: 'All tools' }))

    expect(onChange).toHaveBeenCalledWith({ strategy: 'NONE' })
  })

  it('selects all tools in an integration when the integration row is clicked (from NONE)', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    renderComponent({ value: NONE, onChange })

    await user.click(screen.getByRole('textbox', { name: 'Select tools' }))
    await user.click(screen.getByRole('checkbox', { name: 'Primary MCP Server (3)' }))

    expect(onChange).toHaveBeenCalledWith({ strategy: 'SELECTED', toolIds: ['tool-1', 'tool-2', 'tool-3'] })
  })

  it('deselects all tools in an integration when integration row is clicked while all selected', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    renderComponent({ value: selected('tool-1', 'tool-2', 'tool-3'), onChange })

    await user.click(screen.getByRole('textbox', { name: 'Select tools' }))
    await user.click(screen.getByRole('checkbox', { name: 'Primary MCP Server (3)' }))

    expect(onChange).toHaveBeenCalledWith({ strategy: 'NONE' })
  })

  it('adds a tool to a SELECTED set when a specific tool is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    renderComponent({ value: NONE, onChange })

    await user.click(screen.getByRole('textbox', { name: 'Select tools' }))
    await user.click(screen.getByText('list_resources'))

    expect(onChange).toHaveBeenCalledWith({ strategy: 'SELECTED', toolIds: ['tool-1'] })
  })

  it('removes a tool from SELECTED when a selected tool is clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    renderComponent({ value: selected('tool-1', 'tool-4'), onChange })

    await user.click(screen.getByRole('textbox', { name: 'Select tools' }))
    await user.click(screen.getByText('list_resources'))

    expect(onChange).toHaveBeenCalledWith({ strategy: 'SELECTED', toolIds: ['tool-4'] })
  })

  it('clicking a tool when ALL transitions to SELECTED with that tool excluded', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    renderComponent({ value: ALL, onChange })

    await user.click(screen.getByRole('textbox', { name: 'Select tools' }))
    await user.click(screen.getByText('list_resources'))

    expect(onChange).toHaveBeenCalledWith({
      strategy: 'SELECTED',
      toolIds: ['tool-2', 'tool-3', 'tool-4', 'tool-5'],
    })
  })

  it('adds tools from a second integration to an existing SELECTED set', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    renderComponent({ value: selected('tool-4'), onChange })

    await user.click(screen.getByRole('textbox', { name: 'Select tools' }))
    await user.click(screen.getByRole('checkbox', { name: 'Primary MCP Server (3)' }))

    const call = onChange.mock.calls[0][0] as ToolSelection
    expect(call.strategy).toBe('SELECTED')
    if (call.strategy === 'SELECTED') {
      expect(call.toolIds).toContain('tool-1')
      expect(call.toolIds).toContain('tool-2')
      expect(call.toolIds).toContain('tool-3')
      expect(call.toolIds).toContain('tool-4')
    }
  })

  it('shows loading placeholder when isLoading is true', () => {
    renderComponent({ value: NONE, integrations: mockIntegrations, isLoading: true })

    expect(screen.getByPlaceholderText('Loading tools...')).toBeInTheDocument()
  })

  it('disables the inner text input when isLoading is true', () => {
    renderComponent({ value: NONE, integrations: mockIntegrations, isLoading: true })

    expect(screen.getByRole('textbox', { name: 'Select tools' })).toBeDisabled()
  })

  it('shows no-results message when typeahead filter matches nothing', async () => {
    const user = userEvent.setup()
    renderComponent()

    await user.click(screen.getByRole('textbox', { name: 'Select tools' }))
    // Use keyboard (not type) to avoid the extra click that would close the dropdown
    await user.keyboard('zzznomatch')

    expect(screen.getByText(/No results match/)).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'All tools' })).not.toBeInTheDocument()
  })

  it('has no accessibility violations (closed state)', async () => {
    const { container } = renderComponent()

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations (open state)', async () => {
    const user = userEvent.setup()
    const { container } = renderComponent()

    await user.click(screen.getByRole('textbox', { name: 'Select tools' }))

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no accessibility violations with ALL strategy', async () => {
    const { container } = renderComponent({ value: ALL })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  describe('empty integrations state', () => {
    it('shows placeholder text instead of "No tools selected" when hasNoIntegrations is true', () => {
      renderComponent({ value: NONE, integrations: [], hasNoIntegrations: true })
      expect(screen.getByPlaceholderText('Select tools')).toBeInTheDocument()
      expect(screen.queryByDisplayValue('No tools selected')).not.toBeInTheDocument()
    })

    it('shows "No MCP server integrations configured" in dropdown when hasNoIntegrations is true', async () => {
      const user = userEvent.setup()
      renderComponent({ value: NONE, integrations: [], hasNoIntegrations: true })

      await user.click(screen.getByRole('textbox', { name: 'Select tools' }))

      expect(screen.getByText('No MCP server integrations configured')).toBeInTheDocument()
    })

    it('does not show "All tools" option when hasNoIntegrations is true', async () => {
      const user = userEvent.setup()
      renderComponent({ value: NONE, integrations: [], hasNoIntegrations: true })

      await user.click(screen.getByRole('textbox', { name: 'Select tools' }))

      expect(screen.queryByRole('checkbox', { name: 'All tools' })).not.toBeInTheDocument()
    })

    it('has no accessibility violations when hasNoIntegrations is true', async () => {
      const { container } = renderComponent({ value: NONE, integrations: [], hasNoIntegrations: true })

      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
