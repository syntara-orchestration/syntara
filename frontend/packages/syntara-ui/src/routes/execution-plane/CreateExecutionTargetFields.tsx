import {
  Button,
  Content,
  Flex,
  FlexItem,
  FormGroup,
  FormHelperText,
  FormSection,
  HelperText,
  HelperTextItem,
  Stack,
  StackItem,
  TextInput,
} from '@patternfly/react-core'
import { RhUiAddIcon, RhUiTrashIcon } from '@patternfly/react-icons'
import { useFieldArray, useFormContext } from 'react-hook-form'

import { SynFormField } from '../../components/forms/SynFormField'
import { SynTextField } from '../../components/forms/SynTextField'

import styles from './CreateExecutionTargetFields.module.css'
import { executionTargetHelp, OPENSHIFT_NODE_SELECTOR_HINT } from './executionTargetFieldHelp'
import type { ExecutionTargetFormData } from './executionTargetFormSchema'

type CreateExecutionTargetFieldsProps = Readonly<{
  clusterName: string | undefined
  isClusterPending: boolean
}>

export function CreateExecutionTargetFields({ clusterName, isClusterPending }: CreateExecutionTargetFieldsProps) {
  const { control } = useFormContext<ExecutionTargetFormData>()
  const { fields, append, remove } = useFieldArray({ control, name: 'nodeSelectors' })

  const clusterDisplay = isClusterPending ? 'Loading…' : (clusterName ?? '—')

  return (
    <>
      <FormSection className={styles.formSection} title="General" titleElement="h2">
        <SynTextField
          name="name"
          label="Execution target name"
          fieldId="execution-target-name"
          placeholder="corp-internal-target"
          isRequired
          autoComplete="off"
        />
        <FormGroup label="OpenShift Cluster" fieldId="openshift-cluster" isRequired>
          <Content id="openshift-cluster">{clusterDisplay}</Content>
        </FormGroup>
        <SynTextField
          name="namespace"
          label="Execution namespace"
          fieldId="execution-namespace"
          placeholder="aao-execution"
          isRequired
        />
      </FormSection>

      <FormSection className={styles.formSection} title="Node selector and routing labels" titleElement="h2">
        <Content className={styles.sectionDescription}>
          Node selectors choose eligible OpenShift workers. Routing labels let workflow steps target this execution
          target.
        </Content>
        <FormGroup
          label="OpenShift node selector"
          fieldId="openshift-node-selector"
          labelHelp={executionTargetHelp.nodeSelector}
        >
          <Stack hasGutter>
            {fields.map((row, index) => (
              <StackItem key={row.id}>
                <Flex alignItems={{ default: 'alignItemsFlexStart' }} gap={{ default: 'gapSm' }}>
                  <FlexItem grow={{ default: 'grow' }}>
                    <SynFormField<ExecutionTargetFormData, `nodeSelectors.${number}.key`>
                      name={`nodeSelectors.${index}.key`}
                      label={`Node selector key ${String(index + 1)}`}
                      fieldId={`node-selector-key-${String(index)}`}
                      hideFormGroupLabel
                    >
                      {({ field, fieldState }) => (
                        <TextInput
                          id={`node-selector-key-${String(index)}`}
                          aria-label={`Node selector key ${String(index + 1)}`}
                          value={field.value ?? ''}
                          onChange={(_event, value) => field.onChange(value)}
                          onBlur={field.onBlur}
                          name={field.name}
                          validated={fieldState.error ? 'error' : 'default'}
                          placeholder="region"
                        />
                      )}
                    </SynFormField>
                  </FlexItem>
                  <FlexItem aria-hidden="true">=</FlexItem>
                  <FlexItem grow={{ default: 'grow' }}>
                    <SynFormField<ExecutionTargetFormData, `nodeSelectors.${number}.value`>
                      name={`nodeSelectors.${index}.value`}
                      label={`Node selector value ${String(index + 1)}`}
                      fieldId={`node-selector-value-${String(index)}`}
                      hideFormGroupLabel
                    >
                      {({ field, fieldState }) => (
                        <TextInput
                          id={`node-selector-value-${String(index)}`}
                          aria-label={`Node selector value ${String(index + 1)}`}
                          value={field.value ?? ''}
                          onChange={(_event, value) => field.onChange(value)}
                          onBlur={field.onBlur}
                          name={field.name}
                          validated={fieldState.error ? 'error' : 'default'}
                          placeholder="us-east"
                        />
                      )}
                    </SynFormField>
                  </FlexItem>
                  <FlexItem>
                    <Button
                      variant="plain"
                      icon={<RhUiTrashIcon />}
                      aria-label={`Remove node selector ${String(index + 1)}`}
                      onClick={() => remove(index)}
                      isDisabled={fields.length <= 1}
                    />
                  </FlexItem>
                </Flex>
              </StackItem>
            ))}
            <StackItem>
              <Button variant="link" icon={<RhUiAddIcon />} onClick={() => append({ key: '', value: '' })}>
                Add selector label
              </Button>
            </StackItem>
            <StackItem>
              <FormHelperText>
                <HelperText>
                  <HelperTextItem>{OPENSHIFT_NODE_SELECTOR_HINT}</HelperTextItem>
                </HelperText>
              </FormHelperText>
            </StackItem>
          </Stack>
        </FormGroup>
      </FormSection>
    </>
  )
}
