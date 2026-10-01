import { IntegrationTypeEnum } from '@syntara/contracts'

import { IntegrationTypeaheadSelector, type IntegrationTypeaheadSelectorProps } from './IntegrationTypeaheadSelector'

export type AAPIntegrationSelectorProps = Omit<
  IntegrationTypeaheadSelectorProps,
  'integrationType' | 'placeholder' | 'emptyMessage' | 'requiredHelperLabel'
>

export function AAPIntegrationSelector(props: Readonly<AAPIntegrationSelectorProps>) {
  return (
    <IntegrationTypeaheadSelector
      {...props}
      integrationType={IntegrationTypeEnum.ANSIBLE_AUTOMATION_PLATFORM}
      fieldId={props.fieldId ?? 'aap-integration-selector'}
      placeholder="Select an Ansible Automation Platform integration"
      emptyMessage="No AAP integrations configured"
      requiredHelperLabel="an AAP integration"
    />
  )
}
