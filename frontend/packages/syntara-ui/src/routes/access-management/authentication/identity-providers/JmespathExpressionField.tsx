import { Button, TextInput } from '@patternfly/react-core'

import { FormFieldHintOrError } from '../../../../components/FormFieldError'
import { SynFormField } from '../../../../components/forms/SynFormField'

import { type IdentityProviderFormData } from './identityProviderFormSchema'
import { idpHelp } from './idpFieldHelp'
import { IDP_TYPE_PRESETS } from './idpTypePresets'
import styles from './JmespathExpressionField.module.css'

export function JmespathExpressionField({ idpType }: Readonly<{ idpType?: string | null }>) {
  const defaultExpression = idpType ? (IDP_TYPE_PRESETS[idpType]?.groupMappingExpression ?? null) : null

  return (
    <SynFormField<IdentityProviderFormData, 'groupMapping.jmespathExpression'>
      name="groupMapping.jmespathExpression"
      label="Group extraction expression"
      fieldId="jmespath-expression"
      labelHelp={idpHelp.groupExtractionExpression}
      hideFooter
    >
      {({ field, fieldState }) => {
        const currentValue = field.value ?? 'groups[*]'
        const showReset = defaultExpression && currentValue !== defaultExpression

        return (
          <>
            <TextInput
              id="jmespath-expression"
              placeholder="groups[*]"
              validated={fieldState.error ? 'error' : 'default'}
              {...field}
              value={currentValue}
            />
            <FormFieldHintOrError
              error={fieldState.error}
              hint="JMESPath expression to extract group values from the ID token. Pre-filled by provider template selection."
            />
            {showReset && (
              <Button variant="link" onClick={() => field.onChange(defaultExpression)} className={styles.resetButton}>
                Reset to default for {IDP_TYPE_PRESETS[idpType ?? '']?.label ?? 'this provider'}
              </Button>
            )}
          </>
        )
      }}
    </SynFormField>
  )
}
