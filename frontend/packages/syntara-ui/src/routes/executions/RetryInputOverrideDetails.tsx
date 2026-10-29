import {
  Button,
  Content,
  ContentVariants,
  Flex,
  FlexItem,
  FormGroup,
  FormHelperText,
  HelperText,
  HelperTextItem,
  Stack,
  StackItem,
  TextArea,
} from '@patternfly/react-core'
import type { ChangeEvent } from 'react'

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

  const handleDraftChange = (_event: ChangeEvent<HTMLTextAreaElement>, value: string) => {
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
      <StackItem>
        <Content component={ContentVariants.small}>
          Edits apply to this retry only. The original run and saved workflow definition remain unchanged.
        </Content>
      </StackItem>
      <StackItem isFilled className={styles.editorItem}>
        <FormGroup label="Input parameters (JSON)" fieldId={`retry-input-override-${target.id}`}>
          <TextArea
            id={`retry-input-override-${target.id}`}
            className={styles.editor}
            aria-label={`Input parameters for ${target.name}`}
            aria-describedby={helperTextId}
            value={visibleDraft}
            onChange={handleDraftChange}
            isDisabled={isDisabled}
            resizeOrientation="vertical"
            rows={16}
            validated={error ? 'error' : 'default'}
          />
          <FormHelperText>
            <HelperText isLiveRegion>
              <HelperTextItem id={helperTextId} variant={error ? 'error' : 'default'}>
                {error ?? `Allowed parameters: ${target.parameterNames.join(', ')}. Values must be valid JSON.`}
              </HelperTextItem>
            </HelperText>
          </FormHelperText>
        </FormGroup>
      </StackItem>
      <StackItem className={styles.actions}>
        <Flex gap={{ default: 'gapSm' }} flexWrap={{ default: 'wrap' }}>
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
