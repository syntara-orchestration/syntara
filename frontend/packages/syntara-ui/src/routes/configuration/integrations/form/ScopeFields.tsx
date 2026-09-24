import { FormHelperText, HelperText, HelperTextItem, Switch } from '@patternfly/react-core'
import type { FieldPath, FieldValues } from 'react-hook-form'

import { SynFormField } from '../../../../components/forms/SynFormField'
import { integrationHelp } from '../integrationFieldHelp'

import { ProjectMultiSelect } from './ProjectMultiSelect'

type ScopeFieldsProps<T extends FieldValues> = Readonly<{
  scope: string
  scopeName: FieldPath<T>
  projectIdsName: FieldPath<T>
  idPrefix: string
  onScopeChange?: (newScope: string) => void
}>

export function ScopeFields<T extends FieldValues>({
  scope,
  scopeName,
  projectIdsName,
  idPrefix,
  onScopeChange,
}: ScopeFieldsProps<T>) {
  const scopeHint =
    scope === 'global'
      ? 'Global integrations are available to all projects. Turn off to scope this integration to specific projects.'
      : 'This integration will only be available to selected projects.'

  return (
    <>
      <SynFormField<T, FieldPath<T>>
        name={scopeName}
        label="Scope"
        fieldId={`${idPrefix}-scope`}
        labelHelp={integrationHelp.scope}
        hideFooter
      >
        {({ field }) => (
          <>
            <Switch
              id={`${idPrefix}-scope`}
              label="Global"
              aria-label="Integration scope"
              hasCheckIcon
              isChecked={field.value === 'global'}
              onChange={(_event, checked) => {
                const newScope = checked ? 'global' : 'project'
                field.onChange(newScope)
                onScopeChange?.(newScope)
              }}
            />
            <FormHelperText>
              <HelperText>
                <HelperTextItem>{scopeHint}</HelperTextItem>
              </HelperText>
            </FormHelperText>
          </>
        )}
      </SynFormField>

      {scope === 'project' && (
        <SynFormField<T, FieldPath<T>>
          name={projectIdsName}
          label="Projects"
          fieldId={`${idPrefix}-projects`}
          isRequired
          labelHelp={integrationHelp.projects}
        >
          {({ field, fieldState }) => (
            <ProjectMultiSelect
              selectedIds={(field.value as string[]) ?? []}
              onChange={(ids) => field.onChange(ids)}
              validated={fieldState.error ? 'error' : 'default'}
            />
          )}
        </SynFormField>
      )}
    </>
  )
}
