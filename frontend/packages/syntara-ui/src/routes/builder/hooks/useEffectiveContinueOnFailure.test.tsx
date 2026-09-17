import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { FormProvider, useForm, useFormContext } from 'react-hook-form'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { resolveEffectiveContinueOnFailure, useEffectiveContinueOnFailure } from './useEffectiveContinueOnFailure'

const { mockUseWorkflowEngineDefaults } = vi.hoisted(() => ({
  mockUseWorkflowEngineDefaults: vi.fn(),
}))

vi.mock('./useWorkflowEngineDefaults', () => ({
  useWorkflowEngineDefaults: mockUseWorkflowEngineDefaults,
}))

function mockAdminDefault(continueOnFailure: boolean | null) {
  mockUseWorkflowEngineDefaults.mockReturnValue({
    defaults: { continueOnFailure },
    isLoading: false,
  })
}

function FormWrapper({
  children,
  nodeContinueOnFailure,
}: Readonly<{ children: ReactNode; nodeContinueOnFailure?: boolean }>) {
  const methods = useForm({
    defaultValues: { settings: { continue_on_failure: nodeContinueOnFailure } },
  })
  return <FormProvider {...methods}>{children}</FormProvider>
}

function HookOutput() {
  const { isEffectivelyEnabled, source } = useEffectiveContinueOnFailure()
  const { setValue } = useFormContext()
  return (
    <div>
      <p>{`enabled: ${String(isEffectivelyEnabled)}`}</p>
      <p>{`source: ${source}`}</p>
      <button type="button" onClick={() => setValue('settings.continue_on_failure', true)}>
        Set node continue on failure
      </button>
    </div>
  )
}

describe('resolveEffectiveContinueOnFailure', () => {
  it.each([
    { node: true, admin: true, enabled: true, source: 'node-explicit' },
    { node: true, admin: false, enabled: true, source: 'node-explicit' },
    { node: true, admin: null, enabled: true, source: 'node-explicit' },
    { node: false, admin: true, enabled: false, source: 'node-explicit' },
    { node: false, admin: false, enabled: false, source: 'node-explicit' },
    { node: false, admin: null, enabled: false, source: 'node-explicit' },
    { node: undefined, admin: true, enabled: true, source: 'admin-default' },
    { node: undefined, admin: false, enabled: false, source: 'admin-default' },
    { node: undefined, admin: null, enabled: false, source: 'system-fallback' },
    { node: null, admin: false, enabled: false, source: 'admin-default' },
  ] as const)('node=$node admin=$admin → enabled=$enabled source=$source', ({ node, admin, enabled, source }) => {
    expect(resolveEffectiveContinueOnFailure(node, admin)).toStrictEqual({
      isEffectivelyEnabled: enabled,
      source,
    })
  })
})

describe('useEffectiveContinueOnFailure', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('uses the node setting when it is explicit', () => {
    mockAdminDefault(true)
    render(
      <FormWrapper nodeContinueOnFailure={false}>
        <HookOutput />
      </FormWrapper>
    )

    expect(screen.getByText('enabled: false')).toBeInTheDocument()
    expect(screen.getByText('source: node-explicit')).toBeInTheDocument()
  })

  it('uses the admin default when the node uses system default', () => {
    mockAdminDefault(true)
    render(
      <FormWrapper>
        <HookOutput />
      </FormWrapper>
    )

    expect(screen.getByText('enabled: true')).toBeInTheDocument()
    expect(screen.getByText('source: admin-default')).toBeInTheDocument()
  })

  it('falls back to disabled when admin default is unknown', () => {
    mockAdminDefault(null)
    render(
      <FormWrapper>
        <HookOutput />
      </FormWrapper>
    )

    expect(screen.getByText('enabled: false')).toBeInTheDocument()
    expect(screen.getByText('source: system-fallback')).toBeInTheDocument()
  })

  it('falls back to disabled while engine defaults are loading', () => {
    mockUseWorkflowEngineDefaults.mockReturnValue({ defaults: null, isLoading: true })
    render(
      <FormWrapper>
        <HookOutput />
      </FormWrapper>
    )

    expect(screen.getByText('enabled: false')).toBeInTheDocument()
    expect(screen.getByText('source: system-fallback')).toBeInTheDocument()
  })

  it('updates when the node continue-on-failure setting changes', async () => {
    const user = userEvent.setup()
    mockAdminDefault(false)
    render(
      <FormWrapper>
        <HookOutput />
      </FormWrapper>
    )

    expect(screen.getByText('enabled: false')).toBeInTheDocument()
    expect(screen.getByText('source: admin-default')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Set node continue on failure' }))

    expect(screen.getByText('enabled: true')).toBeInTheDocument()
    expect(screen.getByText('source: node-explicit')).toBeInTheDocument()
  })
})
