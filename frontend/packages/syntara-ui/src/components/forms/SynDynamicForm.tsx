import { Button, Content, ContentVariants, Form, Stack, StackItem } from '@patternfly/react-core'
import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'

import {
  FormDataValidationError,
  FormDefinitionValidationError,
  type FormSubmissionInput,
  validateFormDefinitionDefaults,
  validateFormSubmission,
} from '../../forms'
import { detachPromise } from '../../utils/detachPromise'
import { SynErrorState } from '../states/SynErrorState'

import { applyValidationErrors } from './dynamicForm/applyValidationErrors'
import { buildDefaultValues } from './dynamicForm/buildDefaultValues'
import { SynDynamicFormField } from './dynamicForm/SynDynamicFormField'
import type { SynDynamicFormProps } from './SynDynamicForm.types'
import { SynForm } from './SynForm'

/**
 * Renders an interactive prompt / workflow form from a backend {@link FormDefinition}.
 * File upload fields are not supported yet (deferred until schema and backend support land).
 */
export function SynDynamicForm({
  definition,
  description,
  initialValues,
  isDisabled = false,
  isLoading = false,
  resolveDynamicOptions,
  onSubmit,
  onValidationError,
  submitLabel = 'Submit',
  isReadOnly = false,
  hideSubmitButton = false,
  id,
  'data-testid': dataTestId,
}: Readonly<SynDynamicFormProps>) {
  const definitionError = useMemo(() => {
    try {
      validateFormDefinitionDefaults(definition)
      return null
    } catch (error) {
      if (error instanceof FormDefinitionValidationError) {
        return error
      }
      throw error
    }
  }, [definition])

  const defaultValues = useMemo(() => buildDefaultValues(definition, initialValues), [definition, initialValues])

  const form = useForm<FormSubmissionInput>({ defaultValues, mode: 'onSubmit' })
  const { handleSubmit, reset, setError } = form
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    reset(buildDefaultValues(definition, initialValues))
  }, [definition, initialValues, reset])

  if (definitionError) {
    const message = definitionError.errors.map((err) => `${err.label}: ${err.message}`).join(' ')
    return (
      <div data-testid="syn-dynamic-form-config-error">
        <SynErrorState title="Invalid form configuration" message={message} />
      </div>
    )
  }

  const fieldsDisabled = isDisabled || isReadOnly || isLoading || isSubmitting

  const onFormSubmit = async (raw: FormSubmissionInput) => {
    try {
      const cleaned = validateFormSubmission(definition, raw)
      setIsSubmitting(true)
      await onSubmit(cleaned)
    } catch (error) {
      if (error instanceof FormDataValidationError) {
        applyValidationErrors(setError, error.errors)
        onValidationError?.(error.errors)
        return
      }
      throw error
    } finally {
      setIsSubmitting(false)
    }
  }

  const showSubmit = !hideSubmitButton && !isReadOnly

  return (
    <Form id={id} data-testid={dataTestId} onSubmit={handleSubmit((values) => detachPromise(onFormSubmit(values)))}>
      <Stack hasGutter>
        {description ? (
          <StackItem>
            <Content component={ContentVariants.p}>{description}</Content>
          </StackItem>
        ) : null}
        <StackItem>
          <SynForm form={form}>
            <Stack hasGutter>
              {definition.fields.map((field) => (
                <StackItem key={field.value_name}>
                  <SynDynamicFormField
                    field={field}
                    isDisabled={fieldsDisabled}
                    resolveDynamicOptions={resolveDynamicOptions}
                  />
                </StackItem>
              ))}
            </Stack>
          </SynForm>
        </StackItem>
        {showSubmit ? (
          <StackItem>
            <Button type="submit" variant="primary" isDisabled={fieldsDisabled} isLoading={isLoading || isSubmitting}>
              {submitLabel}
            </Button>
          </StackItem>
        ) : null}
      </Stack>
    </Form>
  )
}
