import { Alert, Button, HelperText, HelperTextItem } from '@patternfly/react-core'

const ELIGIBILITY_HELP_TEXT_NO_SEARCH = 'No eligible workflows found.'
const ELIGIBILITY_HELP_TEXT_WITH_SEARCH = 'No workflows match your search.'
const ELIGIBILITY_GUIDANCE_TEXT =
  'This picker shows enabled, published workflows in this project with a Sub-workflow Trigger. ' +
  'To add one, publish a child workflow in this project that has a Sub-workflow Trigger, then refresh.'
const NO_PROJECT_TEXT = 'Select a project to choose a child workflow.'

export function WorkflowSelectorFeedback({
  workflowError,
  hasError,
  errorVariant,
  errorMessage,
  hasOptions,
  showEligibilityHelp,
  hasSearchTerm,
  hasProject,
  onRetry,
}: Readonly<{
  workflowError?: string
  hasError: boolean
  errorVariant: 'danger' | 'warning'
  errorMessage: string
  hasOptions: boolean
  showEligibilityHelp: boolean
  hasSearchTerm: boolean
  hasProject: boolean
  onRetry: () => void
}>) {
  const eligibilityHelpText = hasSearchTerm ? ELIGIBILITY_HELP_TEXT_WITH_SEARCH : ELIGIBILITY_HELP_TEXT_NO_SEARCH
  return (
    <>
      {workflowError && (
        <HelperText>
          <HelperTextItem variant="error">{workflowError}</HelperTextItem>
        </HelperText>
      )}
      {hasError && (
        <Alert variant={errorVariant} isInline isPlain title={errorMessage}>
          {hasOptions
            ? 'Successfully verified workflows remain selectable. '
            : 'Retry to check for eligible workflows. '}
          <Button variant="link" type="button" onClick={onRetry}>
            Retry
          </Button>
        </Alert>
      )}
      {showEligibilityHelp && !hasProject && (
        <HelperText>
          <HelperTextItem>{NO_PROJECT_TEXT}</HelperTextItem>
        </HelperText>
      )}
      {showEligibilityHelp && hasProject && (
        <HelperText>
          <HelperTextItem>{eligibilityHelpText}</HelperTextItem>
          <HelperTextItem>{ELIGIBILITY_GUIDANCE_TEXT}</HelperTextItem>
        </HelperText>
      )}
      {showEligibilityHelp && hasProject && !hasSearchTerm && (
        <Button variant="link" type="button" onClick={onRetry}>
          Refresh workflows
        </Button>
      )}
    </>
  )
}
