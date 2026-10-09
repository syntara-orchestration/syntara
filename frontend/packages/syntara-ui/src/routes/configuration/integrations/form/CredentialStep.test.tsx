import { IntegrationTypeEnum } from '@syntara/contracts'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { SynForm } from '../../../../components/forms/SynForm'

import { CredentialStep } from './CredentialStep'
import type { IntegrationFormData } from './integrationFormSchema'

vi.mock('../../../builder/components/CredentialSelector', () => ({
  CredentialSelector: ({
    label,
    compatibleTypeNames,
    labelHelp,
    onChange,
  }: {
    label?: string
    compatibleTypeNames?: string[]
    labelHelp?: ReactNode
    onChange?: (id: string | undefined) => void
  }) => (
    <div data-testid="credential-selector" data-compatible-types={compatibleTypeNames?.join(',')}>
      {label}
      {labelHelp && <span data-testid="label-help">{labelHelp}</span>}
      <button data-testid="select-credential" onClick={() => onChange?.('cred-123')}>
        Select
      </button>
    </div>
  ),
}))

function TestWrapper(props: Omit<Parameters<typeof CredentialStep>[0], 'setValue'>) {
  const form = useForm<IntegrationFormData>({
    defaultValues: {
      management_credential_id: null,
      integration_type: 'mcp_server',
      configuration: { integration_type: 'mcp_server', base_url: '' },
    },
  })
  const { setValue } = form
  return (
    <SynForm form={form}>
      <CredentialStep setValue={setValue} {...props} />
    </SynForm>
  )
}

describe('CredentialStep', () => {
  it('renders heading and MCP description by default', () => {
    render(
      <TestWrapper
        credentialId={null}
        integrationTypeValue={IntegrationTypeEnum.MCP_SERVER}
        isTesting={false}
        onTestConnection={vi.fn()}
        onCredentialChange={vi.fn()}
      />
    )

    expect(screen.getByText('Connection credential')).toBeInTheDocument()
    expect(screen.getByText(/credential is used to discover/i)).toBeInTheDocument()
  })

  it('renders Ansible Automation Platform description when type is ansible_automation_platform', () => {
    render(
      <TestWrapper
        credentialId={null}
        integrationTypeValue={IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM}
        isTesting={false}
        onTestConnection={vi.fn()}
        onCredentialChange={vi.fn()}
      />
    )

    expect(screen.getByText(/verify that the Ansible Automation Platform is reachable/i)).toBeInTheDocument()
  })

  it('passes health check credential label help to the selector', () => {
    render(
      <TestWrapper
        credentialId={null}
        integrationTypeValue={IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM}
        isTesting={false}
        onTestConnection={vi.fn()}
        onCredentialChange={vi.fn()}
      />
    )

    expect(screen.getByTestId('label-help')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'More info for Health check credential' })).toBeInTheDocument()
  })

  it('renders LLM Provider description when type is llm_provider', () => {
    render(
      <TestWrapper
        credentialId={null}
        integrationTypeValue={IntegrationTypeEnum.LLM_PROVIDER}
        isTesting={false}
        onTestConnection={vi.fn()}
        onCredentialChange={vi.fn()}
      />
    )

    expect(screen.getByText(/verify that the LLM provider is reachable/i)).toBeInTheDocument()
  })

  it('passes the same health check credential label help for LLM provider', () => {
    render(
      <TestWrapper
        credentialId={null}
        integrationTypeValue={IntegrationTypeEnum.LLM_PROVIDER}
        isTesting={false}
        onTestConnection={vi.fn()}
        onCredentialChange={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: 'More info for Health check credential' })).toBeInTheDocument()
  })

  it('renders credential selector', () => {
    render(
      <TestWrapper
        credentialId={null}
        integrationTypeValue={IntegrationTypeEnum.MCP_SERVER}
        isTesting={false}
        onTestConnection={vi.fn()}
        onCredentialChange={vi.fn()}
      />
    )

    expect(screen.getByTestId('credential-selector')).toBeInTheDocument()
  })

  it('enables test connection button for MCP when no credential selected', () => {
    render(
      <TestWrapper
        credentialId={null}
        integrationTypeValue={IntegrationTypeEnum.MCP_SERVER}
        isTesting={false}
        onTestConnection={vi.fn()}
        onCredentialChange={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: 'Test connection' })).not.toHaveAttribute('aria-disabled', 'true')
  })

  it('enables test connection button when credential is selected', () => {
    render(
      <TestWrapper
        credentialId="cred-1"
        integrationTypeValue={IntegrationTypeEnum.MCP_SERVER}
        isTesting={false}
        onTestConnection={vi.fn()}
        onCredentialChange={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: 'Test connection' })).toBeEnabled()
  })

  it('disables button when testing', () => {
    render(
      <TestWrapper
        credentialId="cred-1"
        integrationTypeValue={IntegrationTypeEnum.MCP_SERVER}
        isTesting={true}
        onTestConnection={vi.fn()}
        onCredentialChange={vi.fn()}
      />
    )

    const button = screen.getByRole('button', { name: /test connection/i })
    expect(button).toHaveAttribute('aria-disabled', 'true')
  })

  it('calls onCredentialChange when credential is selected', async () => {
    const user = userEvent.setup()
    const onCredentialChange = vi.fn()

    render(
      <TestWrapper
        credentialId={null}
        integrationTypeValue={IntegrationTypeEnum.MCP_SERVER}
        isTesting={false}
        onTestConnection={vi.fn()}
        onCredentialChange={onCredentialChange}
      />
    )

    await user.click(screen.getByTestId('select-credential'))

    expect(onCredentialChange).toHaveBeenCalled()
  })

  it('calls onTestConnection when button clicked', async () => {
    const user = userEvent.setup()
    const onTestConnection = vi.fn()

    render(
      <TestWrapper
        credentialId="cred-1"
        integrationTypeValue={IntegrationTypeEnum.MCP_SERVER}
        isTesting={false}
        onTestConnection={onTestConnection}
        onCredentialChange={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: 'Test connection' }))

    expect(onTestConnection).toHaveBeenCalled()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(
      <TestWrapper
        credentialId={null}
        integrationTypeValue={IntegrationTypeEnum.MCP_SERVER}
        isTesting={false}
        onTestConnection={vi.fn()}
        onCredentialChange={vi.fn()}
      />
    )

    let results: Awaited<ReturnType<typeof axe>>
    await act(async () => {
      results = await axe(container)
    })
    expect(results!).toHaveNoViolations()
  })

  it('falls back to MCP description and still passes credential label help for unknown type', () => {
    render(
      <TestWrapper
        credentialId={null}
        integrationTypeValue="unknown_type"
        isTesting={false}
        onTestConnection={vi.fn()}
        onCredentialChange={vi.fn()}
      />
    )

    expect(screen.getByText(/credential is used to discover/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'More info for Health check credential' })).toBeInTheDocument()
  })

  describe('Dynamic credential types', () => {
    function LLMTestWrapper(props: Omit<Parameters<typeof CredentialStep>[0], 'setValue'>) {
      const form = useForm<IntegrationFormData>({
        defaultValues: {
          management_credential_id: null,
          integration_type: 'llm_provider',
          configuration: { integration_type: 'llm_provider', provider_hint: 'red_hat_ai', base_url: '' },
        },
      })
      const { setValue } = form
      return (
        <SynForm form={form}>
          <CredentialStep setValue={setValue} {...props} />
        </SynForm>
      )
    }

    it('passes LLM Provider credential types when integration type is llm_provider', () => {
      render(
        <LLMTestWrapper
          credentialId={null}
          integrationTypeValue={IntegrationTypeEnum.LLM_PROVIDER}
          isTesting={false}
          onTestConnection={vi.fn()}
          onCredentialChange={vi.fn()}
        />
      )

      expect(screen.getByTestId('credential-selector')).toHaveAttribute('data-compatible-types', 'LLM Provider')
    })

    it('passes HTTP Bearer Token credential types when integration type is mcp_server', () => {
      render(
        <TestWrapper
          credentialId={null}
          integrationTypeValue={IntegrationTypeEnum.MCP_SERVER}
          isTesting={false}
          onTestConnection={vi.fn()}
          onCredentialChange={vi.fn()}
        />
      )

      expect(screen.getByTestId('credential-selector')).toHaveAttribute('data-compatible-types', 'HTTP Bearer Token')
    })

    it('shows required description text for LLM Provider', () => {
      render(
        <LLMTestWrapper
          credentialId={null}
          integrationTypeValue={IntegrationTypeEnum.LLM_PROVIDER}
          isTesting={false}
          onTestConnection={vi.fn()}
          onCredentialChange={vi.fn()}
        />
      )

      expect(screen.getByText(/credential is used to verify that the LLM provider/i)).toBeInTheDocument()
    })

    it('disables test connection button for LLM Provider when no credential selected', () => {
      render(
        <LLMTestWrapper
          credentialId={null}
          integrationTypeValue={IntegrationTypeEnum.LLM_PROVIDER}
          isTesting={false}
          onTestConnection={vi.fn()}
          onCredentialChange={vi.fn()}
        />
      )

      expect(screen.getByRole('button', { name: 'Test connection' })).toHaveAttribute('aria-disabled', 'true')
    })

    it('enables test connection button for LLM Provider when credential is selected', () => {
      render(
        <LLMTestWrapper
          credentialId="cred-1"
          integrationTypeValue={IntegrationTypeEnum.LLM_PROVIDER}
          isTesting={false}
          onTestConnection={vi.fn()}
          onCredentialChange={vi.fn()}
        />
      )

      expect(screen.getByRole('button', { name: 'Test connection' })).not.toHaveAttribute('aria-disabled', 'true')
    })
  })
})
