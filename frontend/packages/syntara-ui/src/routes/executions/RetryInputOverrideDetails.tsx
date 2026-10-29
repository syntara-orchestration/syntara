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
import { parseRetryInputOverrideDraft, type RetryInputOverrideTarget } from './retryInputOverrides'

export type RetryInputOverrideDetailsProps = Readonly<{
  target: RetryInputOverrideTarget
  canEdit: boolean
  isDisabled: boolean
  savedOverride: Record<string, unknown> | undefined
  draft: string | undefined
  error: string | undefined
  isEditing: boolean
  onEdit: (targetId: string) => void
  onCancel: (targetId: string) => void
  onSave: (targetId: string, overrides: Record<string, unknown> | undefined) => void
  onDraftChange: (
    targetId: string,
    value: string,
    parsed: Record<string, unknown> | undefined,
    error: string | undefined
  ) => void
}>

/** Edits retry-only overrides in Run details. The Parameters pane previews the effective input values. */
export function RetryInputOverrideDetails({
  target,
  canEdit,
  isDisabled,
  savedOverride,
  draft,
  error,
  isEditing,
  onEdit,
  onCancel,
  onSave,
  onDraftChange,
}: RetryInputOverrideDetailsProps) {
  const visibleDraft = draft ?? JSON.stringify(savedOverride ?? {}, null, 2)
  const parseResult = parseRetryInputOverrideDraft(visibleDraft, target.parameterNames)
  const helperTextId = `retry-input-override-help-${target.id}`

  const handleDraftChange = (_event: ChangeEvent<HTMLTextAreaElement>, value: string) => {
    const result = parseRetryInputOverrideDraft(value, target.parameterNames)
    onDraftChange(target.id, value, result.parsed, result.error)
  }

  const saveDraft = () => {
    if (!parseResult.error) onSave(target.id, parseResult.parsed)
  }

  return (
    <Stack hasGutter className={styles.container}>
      {!canEdit && (
        <StackItem>
          <HelperText>
            <HelperTextItem variant="warning">
              Workflow edit permission is required to override retry inputs.
            </HelperTextItem>
          </HelperText>
        </StackItem>
      )}

      {canEdit && !isEditing && (
        <StackItem>
          <Button variant="secondary" onClick={() => onEdit(target.id)} isDisabled={isDisabled}>
            Edit inputs
          </Button>
        </StackItem>
      )}

      {canEdit && isEditing && (
        <StackItem>
          <Stack hasGutter>
            <StackItem>
              <Content component={ContentVariants.small}>
                Enter only the parameter keys to change. Overrides apply to this retry only; the original run and saved
                workflow definition remain unchanged.
              </Content>
            </StackItem>
            <StackItem>
              <FormGroup label="Input overrides (JSON)" fieldId={`retry-input-override-${target.id}`}>
                <TextArea
                  id={`retry-input-override-${target.id}`}
                  aria-label={`Input overrides for ${target.name}`}
                  aria-describedby={helperTextId}
                  value={visibleDraft}
                  onChange={handleDraftChange}
                  isDisabled={isDisabled}
                  resizeOrientation="vertical"
                  rows={5}
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
            <StackItem>
              <Flex gap={{ default: 'gapSm' }}>
                <FlexItem>
                  <Button
                    variant="primary"
                    onClick={saveDraft}
                    isDisabled={isDisabled || Boolean(error ?? parseResult.error)}
                  >
                    Save inputs
                  </Button>
                </FlexItem>
                <FlexItem>
                  <Button variant="secondary" onClick={() => onCancel(target.id)} isDisabled={isDisabled}>
                    Cancel
                  </Button>
                </FlexItem>
              </Flex>
            </StackItem>
          </Stack>
        </StackItem>
      )}
    </Stack>
  )
}
