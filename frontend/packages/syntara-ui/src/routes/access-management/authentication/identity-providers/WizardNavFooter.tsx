import {
  ActionList,
  ActionListGroup,
  ActionListItem,
  Button,
  WizardFooterWrapper,
  useWizardContext,
} from '@patternfly/react-core'
import { useCallback } from 'react'
import { type UseFormTrigger } from 'react-hook-form'

import { SynFormCancelButton } from '../../../../components/forms/SynFormCancelButton'
import { detachPromise } from '../../../../utils/detachPromise'

import { type IdentityProviderFormData } from './identityProviderFormSchema'

const STEP1_FIELDS: (keyof IdentityProviderFormData)[] = [
  'idpType',
  'name',
  'issuerUrl',
  'clientId',
  'clientSecret',
  'scopes',
  'authorizationEndpoint',
  'tokenEndpoint',
  'jwksUri',
  'endSessionEndpoint',
]

type WizardNavFooterProps = Readonly<{
  trigger?: UseFormTrigger<IdentityProviderFormData>
  submitLabel?: string
  isSaving?: boolean
  onSubmit?: (goToStepById: (id: string) => void) => void
  onCancel?: () => void
  cancelTo?: string
}>

export function WizardNavFooter({
  trigger,
  submitLabel,
  isSaving,
  onSubmit,
  onCancel,
  cancelTo,
}: WizardNavFooterProps) {
  const { goToNextStep, goToPrevStep, goToStepById, activeStep, steps } = useWizardContext()
  const isFirst = activeStep.index === 1
  const isLast = activeStep.index === steps.length

  const handleNext = useCallback(async () => {
    if (trigger && isFirst) {
      const valid = await trigger(STEP1_FIELDS)
      if (valid) await goToNextStep()
      return
    }
    await goToNextStep()
  }, [trigger, isFirst, goToNextStep])

  return (
    <WizardFooterWrapper>
      <ActionList>
        <ActionListGroup>
          {!isFirst && (
            <ActionListItem>
              <Button variant="secondary" onClick={goToPrevStep}>
                Back
              </Button>
            </ActionListItem>
          )}
          <ActionListItem>
            {isLast ? (
              <Button isLoading={isSaving} isDisabled={isSaving} onClick={() => onSubmit?.(goToStepById)}>
                {submitLabel}
              </Button>
            ) : (
              <Button variant="primary" onClick={() => detachPromise(handleNext())}>
                Next
              </Button>
            )}
          </ActionListItem>
        </ActionListGroup>
        {(onCancel ?? cancelTo) && (
          <ActionListGroup>
            <ActionListItem>
              <SynFormCancelButton to={cancelTo} onClick={onCancel} />
            </ActionListItem>
          </ActionListGroup>
        )}
      </ActionList>
    </WizardFooterWrapper>
  )
}
