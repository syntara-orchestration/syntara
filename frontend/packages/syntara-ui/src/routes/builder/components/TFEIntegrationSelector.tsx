import { IntegrationTypeEnum } from '@syntara/contracts'

import { IntegrationTypeaheadSelector, type IntegrationTypeaheadSelectorProps } from './IntegrationTypeaheadSelector'

export type TFEIntegrationSelectorProps = Omit<
  IntegrationTypeaheadSelectorProps,
  'integrationType' | 'placeholder' | 'emptyMessage' | 'requiredHelperLabel'
>

export function TFEIntegrationSelector(props: Readonly<TFEIntegrationSelectorProps>) {
  return (
    <IntegrationTypeaheadSelector
      {...props}
      integrationType={IntegrationTypeEnum.TERRAFORM_ENTERPRISE}
      fieldId={props.fieldId ?? 'tfe-integration-selector'}
      placeholder="Select a Terraform Enterprise integration"
      emptyMessage="No TFE integrations configured"
      requiredHelperLabel="a Terraform Enterprise integration"
    />
  )
}
