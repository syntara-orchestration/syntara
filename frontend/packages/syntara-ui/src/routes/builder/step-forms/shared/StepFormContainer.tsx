import { Form } from '@patternfly/react-core'
import type { FormEvent, ReactNode } from 'react'

type StepFormContainerProps = {
  children: ReactNode
  formId: string
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

/**
 * Shared container for step forms to enable full-height scrolling layout.
 */
export function StepFormContainer({ children, formId, onSubmit }: StepFormContainerProps) {
  return (
    <Form
      id={formId}
      data-testid={formId}
      data-step-editor-form
      onSubmit={onSubmit}
      role="form"
      style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}
    >
      {children}
    </Form>
  )
}
