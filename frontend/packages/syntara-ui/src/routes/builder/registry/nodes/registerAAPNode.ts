import AnsibleIcon from '../../../../assets/ansible-automation-platform.svg?react'
import { RegistryNodeId } from '../../../../constants'
import {
  createAAPJobTemplateActivity,
  createAAPWorkflowTemplateActivity,
  useWorkflowStore,
} from '../../../../stores/useWorkflowStore'
import { AAPJobTemplateForm, type AAPJobTemplateFormData } from '../../node-forms/AAPJobTemplateForm'
import { AAPWorkflowTemplateForm, type AAPWorkflowTemplateFormData } from '../../node-forms/AAPWorkflowTemplateForm'
import {
  buildAAPConfig,
  buildAAPWorkflowTemplateConfig,
  buildExpressionModeActivity,
  buildWorkflowExpressionModeActivity,
  hasExpressionValue,
  isJobTemplateInputVariablesMode,
} from '../../utils/aapHelpers'
import { buildNamedActivity } from '../../utils/nodeCreationHelpers'
import { getDefaultNodeBaseName } from '../../utils/nodeNaming'
import { createCustomNode } from '../helpers/nodeTemplates'
import { NodeRegistry } from '../NodeRegistry'

/**
 * Register the AAP (Ansible Automation Platform) Execution category.
 * Includes Job Template and Workflow Template subtypes.
 */
export default function registerAAPNode() {
  NodeRegistry.register(
    createCustomNode<AAPJobTemplateFormData | AAPWorkflowTemplateFormData>(
      {
        id: RegistryNodeId.AAP_EXECUTION,
        label: 'AAP Execution',
        icon: AnsibleIcon,
        category: 'action',
        description: 'Execute Ansible Automation Platform jobs and workflows',
        keywords: ['ansible', 'aap', 'workflow', 'playbook', 'job', 'template'],
        order: 40,
        selectionTitle: 'Select an AAP execution node',
        // Category node with subtypes - form component not used, subtypes provide their own forms
        formComponent: AAPJobTemplateForm,
        subtypes: [
          {
            id: RegistryNodeId.AAP_JOB_TEMPLATE,
            label: 'Launch AAP job template',
            icon: AnsibleIcon,
            description: 'Execute an Ansible job template',
            formTitle: 'Configure AAP Job Template',
            formComponent: AAPJobTemplateForm,
          },
          {
            id: RegistryNodeId.AAP_WORKFLOW_TEMPLATE,
            label: 'Launch AAP workflow template',
            icon: AnsibleIcon,
            description: 'Execute an Ansible workflow template',
            formTitle: 'Configure AAP Workflow Template',
            formComponent: AAPWorkflowTemplateForm,
          },
        ],
      },
      (
        data: AAPJobTemplateFormData | AAPWorkflowTemplateFormData,
        onSuccess: (newNodeId?: string) => void,
        onError: (error: string) => void,
        subtypeId?: string
      ) => {
        try {
          const { addActivity } = useWorkflowStore.getState()

          // Job Template subtype
          if (subtypeId === RegistryNodeId.AAP_JOB_TEMPLATE) {
            const jobData = data as AAPJobTemplateFormData
            if (isJobTemplateInputVariablesMode(jobData)) {
              const baseName = getDefaultNodeBaseName({
                nodeTypeId: RegistryNodeId.AAP_JOB_TEMPLATE,
                label: 'AAP Job Template',
              })
              const { activityId, activity } = buildNamedActivity(baseName, jobData.name, (id, name) =>
                buildExpressionModeActivity(id, name, jobData)
              )
              addActivity(activity)
              onSuccess(activityId)
            } else {
              const config = buildAAPConfig(jobData)
              const baseName = getDefaultNodeBaseName({
                nodeTypeId: RegistryNodeId.AAP_JOB_TEMPLATE,
                label: 'AAP Job Template',
              })
              const { activityId, activity } = buildNamedActivity(baseName, jobData.name, (id, name) =>
                createAAPJobTemplateActivity(id, name, jobData.job_template_id, config)
              )
              addActivity(activity)
              onSuccess(activityId)
            }
            return
          }

          // Workflow Template subtype
          if (subtypeId === RegistryNodeId.AAP_WORKFLOW_TEMPLATE) {
            const workflowData = data as AAPWorkflowTemplateFormData
            if (hasExpressionValue(workflowData.workflow_job_template_name, workflowData.organization_name)) {
              const baseName = getDefaultNodeBaseName({
                nodeTypeId: RegistryNodeId.AAP_WORKFLOW_TEMPLATE,
                label: 'AAP Workflow Template',
              })
              const { activityId, activity } = buildNamedActivity(baseName, workflowData.name, (id, name) =>
                buildWorkflowExpressionModeActivity(id, name, workflowData)
              )
              addActivity(activity)
              onSuccess(activityId)
            } else {
              const config = buildAAPWorkflowTemplateConfig(workflowData)
              const baseName = getDefaultNodeBaseName({
                nodeTypeId: RegistryNodeId.AAP_WORKFLOW_TEMPLATE,
                label: 'AAP Workflow Template',
              })
              const { activityId, activity } = buildNamedActivity(baseName, workflowData.name, (id, name) =>
                createAAPWorkflowTemplateActivity(id, name, workflowData.workflow_job_template_id, config)
              )
              addActivity(activity)
              onSuccess(activityId)
            }
            return
          }

          onError('Invalid AAP execution type')
        } catch (error) {
          onError(error instanceof Error ? error.message : 'Failed to add AAP step')
        }
      }
    )
  )
}
