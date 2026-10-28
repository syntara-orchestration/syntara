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

import { SynLabel } from '../../components/labels/SynLabel'

import styles from './RetryInputOverrideDetails.module.css'
import { parseRetryInputOverrideDraft, type RetryInputOverrideTarget } from './retryInputOverrides'

export type RetryInputOverrideDetailsProps = Readonly<{
  target: RetryInputOverrideTarget
  resolvedInputs: Record<string, unknown> | null
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

/** Shows the resolved inputs from the original run and edits retry-only overrides in Run details. */
export function RetryInputOverrideDetails({
  target,
  resolvedInputs,
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
      <StackItem className={styles.resolvedHeader}>
        <Flex alignItems={{ default: 'alignItemsCenter' }} gap={{ default: 'gapSm' }} flexWrap={{ default: 'wrap' }}>
          <FlexItem>
            <Content component={ContentVariants.small}>Resolved parameters from the original run</Content>
          </FlexItem>
          {savedOverride && (
            <FlexItem>
              <SynLabel color="blue">Edited for retry</SynLabel>
            </FlexItem>
          )}
        </Flex>
      </StackItem>

      <StackItem>
        {resolvedInputs && Object.keys(resolvedInputs).length > 0 ? (
          <pre className={styles.inputPreview}>{JSON.stringify(resolvedInputs, null, 2)}</pre>
        ) : (
          <Content component={ContentVariants.small}>No resolved input values are available for this step.</Content>
        )}
      </StackItem>

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
                Enter only the parameter keys to change. The original resolved values remain unchanged for this retry.
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
