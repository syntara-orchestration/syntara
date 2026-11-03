import { Alert, Button, HelperText, HelperTextItem } from '@patternfly/react-core'

const ELIGIBILITY_HELP_TEXT_NO_SEARCH = 'No eligible workflows found.'
const ELIGIBILITY_HELP_TEXT_WITH_SEARCH = 'No workflows match your search.'
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
