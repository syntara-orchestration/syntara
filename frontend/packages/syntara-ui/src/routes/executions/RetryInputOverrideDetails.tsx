import {
  Button,
  Content,
  ContentVariants,
  Flex,
  FlexItem,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Stack,
  StackItem,
  Title,
  TitleSizes,
} from '@patternfly/react-core'

import { ExpandableCodeEditor } from '../builder/components/ExpandableCodeEditor'

import styles from './RetryInputOverrideDetails.module.css'
import {
  diffRetryInputOverrides,
  getRetryInputEditorValue,
  parseRetryInputOverrideDraft,
  type RetryInputOverrideTarget,
} from './retryInputOverrides'

export type RetryInputOverrideDetailsProps = Readonly<{
  target: RetryInputOverrideTarget
  resolvedInputs: Record<string, unknown> | null
  canEdit: boolean
  isDisabled: boolean
  savedOverride: Record<string, unknown> | undefined
  draft: string | undefined
  error: string | undefined
  isEditing: boolean
  onEdit: (targetId: string, initialDraft?: string) => void
  onCancel: (targetId: string) => void
  onSave: (targetId: string, overrides: Record<string, unknown> | undefined) => void
  onDraftChange: (
    targetId: string,
    value: string,
    parsed: Record<string, unknown> | undefined,
    error: string | undefined
  ) => void
}>

/** Retry-only parameter editor. The Parameters pane hosts the heading action and viewer. */
export function RetryInputOverrideDetails({
  target,
  resolvedInputs,
  canEdit,
  isDisabled,
  savedOverride,
  draft,
  error,
  isEditing,
  onCancel,
  onSave,
  onDraftChange,
}: RetryInputOverrideDetailsProps) {
  const visibleDraft = draft ?? getRetryInputEditorValue(resolvedInputs, savedOverride, target.parameterNames)
  const parseResult = parseRetryInputOverrideDraft(visibleDraft, target.parameterNames)
  const helperTextId = `retry-input-override-help-${target.id}`
  const hasSavedOverride = Boolean(savedOverride && Object.keys(savedOverride).length > 0)

  const handleDraftChange = (value: string) => {
    const result = parseRetryInputOverrideDraft(value, target.parameterNames)
    onDraftChange(target.id, value, result.parsed, result.error)
  }

  const saveDraft = () => {
    if (parseResult.error) return
    onSave(target.id, parseResult.parsed ? diffRetryInputOverrides(resolvedInputs, parseResult.parsed) : undefined)
  }

  const resetDraft = () => {
    const original = getRetryInputEditorValue(resolvedInputs, undefined, target.parameterNames)
    const result = parseRetryInputOverrideDraft(original, target.parameterNames)
    onDraftChange(target.id, original, result.parsed, result.error)
  }

  if (!canEdit) {
    return (
      <HelperText>
        <HelperTextItem variant="warning">
          Workflow edit permission is required to override retry inputs.
        </HelperTextItem>
      </HelperText>
    )
  }

  if (!isEditing) return null

  return (
    <Stack hasGutter className={styles.container}>
      <StackItem className={styles.header}>
        <Title headingLevel="h3" size={TitleSizes.md} className={styles.title}>
          Input parameters
        </Title>
        <Content component={ContentVariants.small}>
          These parameters are used only by this retry. The workflow definition and saved node parameters stay
          unchanged.
        </Content>
      </StackItem>
      <StackItem isFilled className={styles.editorItem} data-testid="retry-input-override-scroll-area">
        <div className={styles.editor}>
          <ExpandableCodeEditor
            code={visibleDraft}
            onCodeChange={handleDraftChange}
            language="json"
            height="100%"
            modalTitle={`Input parameters for retry — ${target.name}`}
            ariaLabel={`Input parameters for ${target.name}`}
            isReadOnly={isDisabled}
          />
        </div>
        {error && (
          <FormHelperText>
            <HelperText isLiveRegion>
              <HelperTextItem id={helperTextId} variant="error">
                {error}
              </HelperTextItem>
            </HelperText>
          </FormHelperText>
        )}
      </StackItem>
      <StackItem className={styles.actions}>
        <Flex
          gap={{ default: 'gapSm' }}
          flexWrap={{ default: 'wrap' }}
          justifyContent={{ default: 'justifyContentFlexEnd' }}
        >
          <FlexItem>
            <Button
              variant="primary"
              onClick={saveDraft}
              isDisabled={isDisabled || Boolean(error ?? parseResult.error)}
            >
              Save parameters for retry
            </Button>
          </FlexItem>
          <FlexItem>
            <Button variant="secondary" onClick={() => onCancel(target.id)} isDisabled={isDisabled}>
              Cancel
            </Button>
          </FlexItem>
          {hasSavedOverride && (
            <FlexItem>
              <Button variant="link" onClick={resetDraft} isDisabled={isDisabled}>
                Reset parameters
              </Button>
            </FlexItem>
          )}
        </Flex>
      </StackItem>
    </Stack>
  )
}
