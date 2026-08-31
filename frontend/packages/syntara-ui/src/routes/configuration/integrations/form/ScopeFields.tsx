import { FormGroup, FormHelperText, HelperText, HelperTextItem, Switch } from '@patternfly/react-core'
import { RhUiErrorIcon } from '@patternfly/react-icons'
import { Controller, type Control, type FieldValues, type Path } from 'react-hook-form'

import { integrationHelp } from '../integrationFieldHelp'

import { ProjectMultiSelect } from './ProjectMultiSelect'

type ScopeFieldsProps<T extends FieldValues> = Readonly<{
  control: Control<T>
  scope: string
  scopeName: Path<T>
  projectIdsName: Path<T>
  idPrefix: string
  onScopeChange?: (newScope: string) => void
}>

export function ScopeFields<T extends FieldValues>({
  control,
  scope,
  scopeName,
  projectIdsName,
  idPrefix,
  onScopeChange,
}: ScopeFieldsProps<T>) {
  return (
    <>
      <FormGroup label="Scope" fieldId={`${idPrefix}-scope`} labelHelp={integrationHelp.scope}>
        <Controller
          name={scopeName}
          control={control}
          render={({ field }) => (
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
          )}
        />
        <FormHelperText>
          <HelperText>
            <HelperTextItem>
              {scope === 'global'
                ? 'Global integrations are available to all projects. Turn off to scope this integration to specific projects.'
                : 'This integration will only be available to selected projects.'}
            </HelperTextItem>
          </HelperText>
        </FormHelperText>
      </FormGroup>

      {scope === 'project' && (
        <FormGroup label="Projects" fieldId={`${idPrefix}-projects`} isRequired labelHelp={integrationHelp.projects}>
          <Controller
            name={projectIdsName}
            control={control}
            render={({ field, fieldState }) => (
              <>
                <ProjectMultiSelect
                  selectedIds={(field.value as string[]) ?? []}
                  onChange={(ids) => field.onChange(ids)}
                  validated={fieldState.error ? 'error' : 'default'}
                />
                {fieldState.error && (
                  <FormHelperText>
                    <HelperText>
                      <HelperTextItem icon={<RhUiErrorIcon />} variant="error">
                        {fieldState.error.message}
                      </HelperTextItem>
                    </HelperText>
                  </FormHelperText>
                )}
              </>
            )}
          />
        </FormGroup>
      )}
    </>
  )
}
