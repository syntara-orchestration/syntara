import { render, screen, waitFor } from '@testing-library/react'
import { Suspense } from 'react'
import { describe, expect, it, vi } from 'vitest'

import {
  AccessManagement,
  AddIdentityProvider,
  Approvals,
  Authentication,
  Workflows,
  BuilderEdit,
  BuilderNew,
  EditIdentityProvider,
  ExecutionDetail,
  Executions,
  Glossary,
  IntegrationForm,
  Integrations,
  SettingsCategoryRoute,
} from './lazyRoutes'

// Stub every route component so lazy resolution succeeds without
// pulling in the full dependency tree of each page.
vi.mock('../routes/workflows/Workflows', () => ({ default: () => <div>Workflows</div> }))
vi.mock('../routes/builder/BuilderNew', () => ({ default: () => <div>BuilderNew</div> }))
vi.mock('../routes/builder/BuilderEdit', () => ({ default: () => <div>BuilderEdit</div> }))
vi.mock('../routes/executions/Executions', () => ({ default: () => <div>Executions</div> }))
vi.mock('../routes/executions/ExecutionDetail', () => ({ default: () => <div>ExecutionDetail</div> }))
vi.mock('../routes/configuration/integrations/form/IntegrationForm', () => ({
  IntegrationForm: () => <div>IntegrationForm</div>,
}))
vi.mock('../routes/configuration/integrations/Integrations', () => ({
  default: () => <div>Integrations</div>,
}))
vi.mock('../routes/configuration/settings/SettingsCategoryRoute', () => ({
  SettingsCategoryRoute: () => <div>SettingsCategoryRoute</div>,
}))
vi.mock('../routes/documentation/glossary/Glossary', () => ({ default: () => <div>Glossary</div> }))
vi.mock('../routes/approvals/Approvals', () => ({ default: () => <div>Approvals</div> }))
vi.mock('../routes/access-management/AccessManagement', () => ({
  AccessManagement: () => <div>AccessManagement</div>,
}))
vi.mock('../routes/access-management/authentication/Authentication', () => ({
  default: () => <div>Authentication</div>,
}))
vi.mock('../routes/access-management/authentication/identity-providers/AddIdentityProvider', () => ({
  AddIdentityProvider: () => <div>AddIdentityProvider</div>,
}))
vi.mock('../routes/access-management/authentication/identity-providers/EditIdentityProvider', () => ({
  EditIdentityProvider: () => <div>EditIdentityProvider</div>,
}))

describe('lazyRoutes', () => {
  it('exports all lazy components', () => {
    const components = [
      Workflows,
      BuilderNew,
      BuilderEdit,
      Executions,
      ExecutionDetail,
      IntegrationForm,
      Integrations,
      SettingsCategoryRoute,
      Glossary,
      Approvals,
      AccessManagement,
      Authentication,
      AddIdentityProvider,
      EditIdentityProvider,
    ]
    for (const component of components) {
      expect(component).toBeDefined()
    }
  })

  describe('lazy components resolve correctly', () => {
    it.each([
      ['Workflows', Workflows, 'Workflows'],
      ['BuilderNew', BuilderNew, 'BuilderNew'],
      ['BuilderEdit', BuilderEdit, 'BuilderEdit'],
      ['Executions', Executions, 'Executions'],
      ['ExecutionDetail', ExecutionDetail, 'ExecutionDetail'],
      ['IntegrationForm', IntegrationForm, 'IntegrationForm'],
      ['Integrations', Integrations, 'Integrations'],
      ['SettingsCategoryRoute', SettingsCategoryRoute, 'SettingsCategoryRoute'],
      ['Glossary', Glossary, 'Glossary'],
      ['Approvals', Approvals, 'Approvals'],
      ['AccessManagement', AccessManagement, 'AccessManagement'],
      ['Authentication', Authentication, 'Authentication'],
      ['AddIdentityProvider', AddIdentityProvider, 'AddIdentityProvider'],
      ['EditIdentityProvider', EditIdentityProvider, 'EditIdentityProvider'],
    ] as const)('resolves %s', async (_name, Component, expectedText) => {
      render(
        <Suspense fallback={<div>loading</div>}>
          <Component />
        </Suspense>
      )
      await waitFor(() => {
        expect(screen.getByText(expectedText)).toBeInTheDocument()
      })
    })
  })
})
