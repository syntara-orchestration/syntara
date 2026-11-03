import { IntegrationTypeEnum } from '@syntara/contracts'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useCallback } from 'react'
import { useForm } from 'react-hook-form'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SynForm } from '../../../../components/forms/SynForm'
import { EXECUTION_PLANE_SCOPE_HELP, EXECUTION_PLANE_SINGLETON_HELP } from '../integrationFieldHelpText'

import { IntegrationDetailsStep } from './IntegrationDetailsStep'
import { getDefaultConfiguration, type IntegrationFormData } from './integrationFormSchema'

vi.mock('../../../access/useAllProjects', () => {
  const projectsMock = () => ({
    projects: [
      { id: 'p-001', name: 'default' },
      { id: 'p-002', name: 'alice-sandbox' },
    ],
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  })
  return { useAllProjects: projectsMock, useSelectableProjects: projectsMock }
})

const { mockUseOpenShiftIntegrationExists } = vi.hoisted(() => ({
  mockUseOpenShiftIntegrationExists: vi.fn(() => ({
    exists: false,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  })),
}))

vi.mock('./useOpenShiftIntegrationExists', () => ({
  useOpenShiftIntegrationExists: () =>
    mockUseOpenShiftIntegrationExists() as ReturnType<
      typeof import('./useOpenShiftIntegrationExists').useOpenShiftIntegrationExists
    >,
  OPENSHIFT_INTEGRATION_EXISTS_QUERY_KEY: ['openshift-integration-exists'],
}))

function getDefaultFormValues(defaultType: string): IntegrationFormData {
  if (defaultType === IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM) {
    return {
      name: '',
      description: '',
      integration_type: IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM,
      configuration: {
        integration_type: IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM,
        base_url: '',
        allow_http: false,
        insecure_skip_tls_verify: false,
      },
      scope: 'global',
      project_ids: [],
    }
  }

  if (defaultType === IntegrationTypeEnum.OPENSHIFT) {
    return {
      name: '',
      description: '',
      integration_type: IntegrationTypeEnum.OPENSHIFT,
      configuration: {
        integration_type: IntegrationTypeEnum.OPENSHIFT,
        base_url: '',
        allow_http: false,
        insecure_skip_tls_verify: false,
        ca_certificate: null,
      },
      scope: 'global',
      project_ids: [],
    }
  }

  return {
    name: '',
    description: '',
    integration_type: IntegrationTypeEnum.MCP_SERVER,
    configuration: {
      integration_type: IntegrationTypeEnum.MCP_SERVER,
      base_url: '',
      allow_http: false,
      insecure_skip_tls_verify: false,
    },
    scope: 'global',
    project_ids: [],
  }
}

function TestWrapper({
  defaultType = IntegrationTypeEnum.MCP_SERVER,
  onTypeChange: onTypeChangeProp = vi.fn(),
}: {
  defaultType?: string
  onTypeChange?: (newType: string) => void
} = {}) {
  const form = useForm<IntegrationFormData>({ defaultValues: getDefaultFormValues(defaultType) })
  const { setValue } = form

  const onTypeChange = useCallback(
    (newType: string) => {
      setValue('configuration', getDefaultConfiguration(newType), { shouldValidate: false })
      setValue('integration_type', newType as IntegrationFormData['integration_type'])
      setValue('management_credential_id', null)
      if (newType === IntegrationTypeEnum.OPENSHIFT) {
        setValue('scope', 'global')
        setValue('project_ids', [])
      }
      onTypeChangeProp(newType)
    },
    [setValue, onTypeChangeProp]
  )

  return (
    <SynForm form={form}>
      <IntegrationDetailsStep setValue={setValue} onTypeChange={onTypeChange} />
    </SynForm>
  )
}

describe('IntegrationDetailsStep', () => {
  beforeEach(() => {
    mockUseOpenShiftIntegrationExists.mockReturnValue({
      exists: false,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    })
  })

  it('renders heading and description', () => {
    render(<TestWrapper />)

    expect(screen.getByText('Integration details')).toBeInTheDocument()
    expect(screen.getByText(/select an integration type/i)).toBeInTheDocument()
  })

  it('renders integration type selector', () => {
    render(<TestWrapper />)

    expect(screen.getByText('MCP Server')).toBeInTheDocument()
  })

  it('renders name field', () => {
    render(<TestWrapper />)

    expect(screen.getByRole('textbox', { name: /name/i })).toBeInTheDocument()
  })

  it('renders description field', () => {
    render(<TestWrapper />)

    expect(screen.getByRole('textbox', { name: /description/i })).toBeInTheDocument()
  })

  it('renders API URL field for MCP Server with correct placeholder', () => {
    render(<TestWrapper />)

    const apiUrlField = screen.getByRole('textbox', { name: /api url/i })
    expect(apiUrlField).toBeInTheDocument()
    expect(apiUrlField).toHaveAttribute('placeholder', 'https://mcp-server.example.com/mcp')
  })

  it('allows typing in name field', async () => {
    const user = userEvent.setup()
    render(<TestWrapper />)

    const nameInput = screen.getByRole('textbox', { name: /name/i })
    await user.type(nameInput, 'My MCP Server')

    expect(nameInput).toHaveValue('My MCP Server')
  })

  describe('Ansible Automation Platform', () => {
    it('renders API URL field for Ansible Automation Platform', () => {
      render(<TestWrapper defaultType={IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM} />)

      expect(screen.getByRole('textbox', { name: /api url/i })).toBeInTheDocument()
    })

    it('renders security section for Ansible Automation Platform', () => {
      render(<TestWrapper defaultType={IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM} />)

      expect(screen.getByText('Security')).toBeInTheDocument()
    })

    it('hides base URL and shows only AAP URL with correct placeholder', () => {
      render(<TestWrapper defaultType={IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM} />)

      const apiUrlFields = screen.getAllByRole('textbox', { name: /api url/i })
      expect(apiUrlFields).toHaveLength(1)
      expect(apiUrlFields[0]).toHaveAttribute('placeholder', 'e.g. https://aap.example.com')
    })

    it('uses "Server name / ID" label for AAP', () => {
      render(<TestWrapper defaultType={IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM} />)

      expect(screen.getByRole('textbox', { name: /server name/i })).toBeInTheDocument()
    })
  })

  describe('Execution plane infrastructure singleton', () => {
    it('keeps the option selectable when no openshift integration exists', async () => {
      const user = userEvent.setup()
      render(<TestWrapper />)

      await user.click(screen.getByRole('button', { name: 'MCP Server' }))
      const option = screen.getByRole('option', { name: /Execution plane infrastructure/i })
      expect(option).toBeEnabled()
      expect(screen.queryByText(EXECUTION_PLANE_SINGLETON_HELP)).not.toBeInTheDocument()

      await user.click(option)
      expect(screen.getByRole('textbox', { name: /connection name/i })).toBeInTheDocument()
    })

    it('disables the option with helper text when an openshift integration exists', async () => {
      mockUseOpenShiftIntegrationExists.mockReturnValue({
        exists: true,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      })
      const user = userEvent.setup()
      render(<TestWrapper />)

      await user.click(screen.getByRole('button', { name: 'MCP Server' }))
      const option = screen.getByRole('option', { name: /Execution plane infrastructure/i })
      expect(option).toBeDisabled()
      expect(screen.getByText(EXECUTION_PLANE_SINGLETON_HELP)).toBeInTheDocument()
    })

    it('does not change type when the disabled option is activated', async () => {
      mockUseOpenShiftIntegrationExists.mockReturnValue({
        exists: true,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      })
      const user = userEvent.setup()
      render(<TestWrapper />)

      await user.click(screen.getByRole('button', { name: 'MCP Server' }))
      await user.click(screen.getByRole('option', { name: /Execution plane infrastructure/i }))

      expect(screen.getByRole('button', { name: 'MCP Server' })).toBeInTheDocument()
      expect(screen.queryByRole('textbox', { name: /connection name/i })).not.toBeInTheDocument()
    })

    it('leaves other integration type options enabled when openshift exists', async () => {
      mockUseOpenShiftIntegrationExists.mockReturnValue({
        exists: true,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      })
      const user = userEvent.setup()
      render(<TestWrapper />)

      await user.click(screen.getByRole('button', { name: 'MCP Server' }))
      expect(screen.getByRole('option', { name: 'LLM Provider' })).toBeEnabled()
      expect(screen.getByRole('option', { name: 'Ansible Automation Platform' })).toBeEnabled()
      expect(screen.getByRole('option', { name: 'MCP Server' })).toBeEnabled()
    })

    it('re-enables the option after the existing integration is gone', async () => {
      mockUseOpenShiftIntegrationExists.mockReturnValue({
        exists: true,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      })
      const user = userEvent.setup()
      const { unmount } = render(<TestWrapper />)

      await user.click(screen.getByRole('button', { name: 'MCP Server' }))
      expect(screen.getByRole('option', { name: /Execution plane infrastructure/i })).toBeDisabled()
      unmount()

      mockUseOpenShiftIntegrationExists.mockReturnValue({
        exists: false,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      })
      render(<TestWrapper />)

      await user.click(screen.getByRole('button', { name: 'MCP Server' }))
      const option = screen.getByRole('option', { name: /Execution plane infrastructure/i })
      expect(option).toBeEnabled()
      expect(screen.queryByText(EXECUTION_PLANE_SINGLETON_HELP)).not.toBeInTheDocument()
    })
  })

  describe('OpenShift', () => {
    it('uses Cluster details title and provisioning description', () => {
      render(<TestWrapper defaultType={IntegrationTypeEnum.OPENSHIFT} />)

      expect(screen.getByText('Cluster details')).toBeInTheDocument()
      expect(
        screen.getByText(
          /The customer provisions the OpenShift namespace and service account\. An admin then configures this integration and an execution target\./
        )
      ).toBeInTheDocument()
    })

    it('shows Infrastructure type as plain OpenShift text', () => {
      render(<TestWrapper defaultType={IntegrationTypeEnum.OPENSHIFT} />)

      expect(screen.queryByRole('textbox', { name: /infrastructure type/i })).not.toBeInTheDocument()
      expect(screen.getByText('OpenShift')).toBeInTheDocument()
    })

    it('uses Connection name label and placeholder', () => {
      render(<TestWrapper defaultType={IntegrationTypeEnum.OPENSHIFT} />)

      const nameField = screen.getByRole('textbox', { name: /connection name/i })
      expect(nameField).toBeInTheDocument()
      expect(nameField).toHaveAttribute('placeholder', 'ocp-us-east-prod')
    })

    it('renders API endpoint field with OpenShift placeholder', () => {
      render(<TestWrapper defaultType={IntegrationTypeEnum.OPENSHIFT} />)

      const apiEndpoint = screen.getByRole('textbox', { name: /api endpoint/i })
      expect(apiEndpoint).toBeInTheDocument()
      expect(apiEndpoint).toHaveAttribute('placeholder', 'https://api.your-cluster.example.com:6443')
    })

    it('hides Description and Namespace fields', () => {
      render(<TestWrapper defaultType={IntegrationTypeEnum.OPENSHIFT} />)

      expect(screen.queryByRole('textbox', { name: /^description$/i })).not.toBeInTheDocument()
      expect(screen.queryByRole('textbox', { name: /namespace/i })).not.toBeInTheDocument()
    })

    it('shows locked Global scope text with execution-plane helper text', () => {
      render(<TestWrapper defaultType={IntegrationTypeEnum.OPENSHIFT} />)

      expect(screen.queryByRole('switch', { name: /integration scope/i })).not.toBeInTheDocument()
      expect(screen.getByText('Global')).toBeInTheDocument()
      expect(screen.getByText(EXECUTION_PLANE_SCOPE_HELP)).toBeInTheDocument()
    })

    it('does not show API URL label for OpenShift', () => {
      render(<TestWrapper defaultType={IntegrationTypeEnum.OPENSHIFT} />)

      expect(screen.queryByRole('textbox', { name: /^api url$/i })).not.toBeInTheDocument()
    })
  })

  describe('type change', () => {
    it('calls onTypeChange callback when type is selected', async () => {
      const onTypeChange = vi.fn()
      const user = userEvent.setup()
      render(<TestWrapper onTypeChange={onTypeChange} />)

      await user.click(screen.getByText('MCP Server'))
      await user.click(screen.getByText('Ansible Automation Platform'))

      expect(onTypeChange).toHaveBeenCalledWith(IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM)
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<TestWrapper />)

    let results: Awaited<ReturnType<typeof axe>>
    await act(async () => {
      results = await axe(container)
    })
    expect(results!).toHaveNoViolations()
  })

  describe('LLM Provider type', () => {
    function LLMTestWrapper() {
      const form = useForm<IntegrationFormData>({
        defaultValues: {
          name: '',
          description: '',
          integration_type: 'llm_provider',
          configuration: {
            integration_type: 'llm_provider',
            provider_hint: 'red_hat_ai',
            base_url: '',
            allow_http: false,
            insecure_skip_tls_verify: false,
          },
          scope: 'global',
        },
      })
      const { setValue } = form
      return (
        <SynForm form={form}>
          <IntegrationDetailsStep setValue={setValue} onTypeChange={vi.fn()} />
        </SynForm>
      )
    }

    it('shows provider hint dropdown when LLM Provider is selected', () => {
      render(<LLMTestWrapper />)

      expect(screen.getByText('Red Hat AI')).toBeInTheDocument()
    })

    it('shows name label as "Name" (not "Server name / ID") for LLM', () => {
      render(<LLMTestWrapper />)

      expect(screen.getByRole('textbox', { name: 'Name' })).toBeInTheDocument()
    })

    it('shows base URL field for red_hat_ai provider', () => {
      render(<LLMTestWrapper />)

      expect(screen.getByRole('textbox', { name: /api url/i })).toBeInTheDocument()
    })

    it('switching from LLM Provider to MCP Server resets configuration', async () => {
      const user = userEvent.setup()
      render(<TestWrapper />)

      const typeToggle = screen.getByText('MCP Server')
      await user.click(typeToggle)
      await user.click(screen.getByRole('option', { name: 'LLM Provider' }))

      expect(screen.getByText('Red Hat AI')).toBeInTheDocument()

      const typeToggle2 = screen.getByRole('button', { name: 'LLM Provider' })
      await user.click(typeToggle2)
      await user.click(screen.getByRole('option', { name: 'MCP Server' }))

      expect(screen.queryByText('Red Hat AI')).not.toBeInTheDocument()
      expect(screen.getByRole('textbox', { name: /api url/i })).toBeInTheDocument()
    })

    it('changes provider hint when selecting a different provider', async () => {
      const user = userEvent.setup()
      render(<LLMTestWrapper />)

      await user.click(screen.getByText('Red Hat AI'))
      await user.click(screen.getByRole('option', { name: 'OpenAI' }))

      expect(screen.getByRole('button', { name: 'OpenAI' })).toBeInTheDocument()
    })

    it('hides base URL field when selecting a provider with a default URL', async () => {
      const user = userEvent.setup()
      render(<LLMTestWrapper />)

      expect(screen.getByRole('textbox', { name: /api url/i })).toBeInTheDocument()

      await user.click(screen.getByText('Red Hat AI'))
      await user.click(screen.getByRole('option', { name: 'OpenAI' }))

      expect(screen.queryByRole('textbox', { name: /api url/i })).not.toBeInTheDocument()
    })

    it('restores base URL field when switching from hidden-URL to requiring provider', async () => {
      const user = userEvent.setup()
      render(<LLMTestWrapper />)

      await user.click(screen.getByText('Red Hat AI'))
      await user.click(screen.getByRole('option', { name: 'OpenAI' }))
      expect(screen.queryByRole('textbox', { name: /api url/i })).not.toBeInTheDocument()

      await user.click(screen.getByRole('button', { name: 'OpenAI' }))
      await user.click(screen.getByRole('option', { name: 'Custom' }))
      expect(screen.getByRole('textbox', { name: /api url/i })).toBeInTheDocument()
    })

    it('has no accessibility violations with LLM Provider selected', async () => {
      const { container } = render(<LLMTestWrapper />)

      let results: Awaited<ReturnType<typeof axe>>
      await act(async () => {
        results = await axe(container)
      })
      expect(results!).toHaveNoViolations()
    })
  })

  describe('SecurityFields', () => {
    it('expands to show all security controls', async () => {
      const user = userEvent.setup()
      render(<TestWrapper />)

      await user.click(screen.getByText('Security'))

      expect(screen.getByRole('checkbox', { name: /allow http connections/i })).toBeInTheDocument()
      expect(screen.getByRole('checkbox', { name: /disable tls certificate verification/i })).toBeInTheDocument()
      expect(screen.getByRole('textbox', { name: /ca certificate/i })).toBeInTheDocument()
      expect(screen.getByText(/PEM-encoded CA certificate/)).toBeInTheDocument()
    })

    it('collapses when toggled again', async () => {
      const user = userEvent.setup()
      render(<TestWrapper />)

      await user.click(screen.getByText('Security'))
      expect(screen.getByRole('checkbox', { name: /allow http connections/i })).toBeInTheDocument()

      await user.click(screen.getByText('Security'))
      expect(screen.queryByRole('checkbox', { name: /allow http connections/i })).not.toBeInTheDocument()
    })

    it('toggles Allow HTTP checkbox', async () => {
      const user = userEvent.setup()
      render(<TestWrapper />)

      await user.click(screen.getByText('Security'))
      const checkbox = screen.getByRole('checkbox', { name: /allow http connections/i })
      expect(checkbox).not.toBeChecked()

      await user.click(checkbox)
      expect(checkbox).toBeChecked()
    })

    it('toggles Disable TLS certificate verification checkbox', async () => {
      const user = userEvent.setup()
      render(<TestWrapper />)

      await user.click(screen.getByText('Security'))
      const checkbox = screen.getByRole('checkbox', { name: /disable tls certificate verification/i })
      expect(checkbox).not.toBeChecked()

      await user.click(checkbox)
      expect(checkbox).toBeChecked()
    })

    it('accepts CA certificate input and clears to empty', async () => {
      const user = userEvent.setup()
      render(<TestWrapper />)

      await user.click(screen.getByText('Security'))
      const textarea = screen.getByRole('textbox', { name: /ca certificate/i })
      expect(textarea).toHaveValue('')

      await user.type(textarea, 'cert-data')
      expect(textarea).toHaveValue('cert-data')

      await user.clear(textarea)
      expect(textarea).toHaveValue('')
    })

    it('renders security section for AAP type', async () => {
      const user = userEvent.setup()
      render(<TestWrapper defaultType={IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM} />)

      await user.click(screen.getByText('Security'))

      expect(screen.getByRole('checkbox', { name: /allow http connections/i })).toBeInTheDocument()
      expect(screen.getByRole('checkbox', { name: /disable tls certificate verification/i })).toBeInTheDocument()
    })

    it('hides CA certificate field when TLS verification is disabled', async () => {
      const user = userEvent.setup()
      render(<TestWrapper />)

      await user.click(screen.getByText('Security'))
      expect(screen.getByRole('textbox', { name: /ca certificate/i })).toBeInTheDocument()

      await user.click(screen.getByRole('checkbox', { name: /disable tls certificate verification/i }))
      expect(screen.queryByRole('textbox', { name: /ca certificate/i })).not.toBeInTheDocument()
      expect(screen.queryByText(/PEM-encoded CA certificate/)).not.toBeInTheDocument()
    })

    it('shows warning when TLS verification is disabled', async () => {
      const user = userEvent.setup()
      render(<TestWrapper />)

      await user.click(screen.getByText('Security'))
      expect(screen.queryByText(/will not be verified/)).not.toBeInTheDocument()

      await user.click(screen.getByRole('checkbox', { name: /disable tls certificate verification/i }))
      expect(screen.getByText(/will not be verified. Only enable in trusted networks/)).toBeInTheDocument()
    })

    it('restores CA certificate field when TLS verification is re-enabled', async () => {
      const user = userEvent.setup()
      render(<TestWrapper />)

      await user.click(screen.getByText('Security'))
      await user.click(screen.getByRole('checkbox', { name: /disable tls certificate verification/i }))
      expect(screen.queryByRole('textbox', { name: /ca certificate/i })).not.toBeInTheDocument()

      await user.click(screen.getByRole('checkbox', { name: /disable tls certificate verification/i }))
      expect(screen.getByRole('textbox', { name: /ca certificate/i })).toBeInTheDocument()
      expect(screen.queryByText(/will not be verified/)).not.toBeInTheDocument()
    })
  })

  describe('scope toggle', () => {
    it('defaults to global scope', () => {
      render(<TestWrapper />)

      const toggle = screen.getByRole('switch', { name: /integration scope/i })
      expect(toggle).toBeChecked()
    })

    it('toggles to project scope', async () => {
      const user = userEvent.setup()
      render(<TestWrapper />)

      const toggle = screen.getByRole('switch', { name: /integration scope/i })
      await user.click(toggle)

      expect(toggle).not.toBeChecked()
    })

    it('toggles back to global scope', async () => {
      const user = userEvent.setup()
      render(<TestWrapper />)

      const toggle = screen.getByRole('switch', { name: /integration scope/i })
      await user.click(toggle)
      await user.click(toggle)

      expect(toggle).toBeChecked()
    })
  })
})
