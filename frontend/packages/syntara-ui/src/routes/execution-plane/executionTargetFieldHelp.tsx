import { createFieldHelp } from '../../components/createFieldHelp'

/** Popover body for the OpenShift node selector field help (`?`) control. */
const OPENSHIFT_NODE_SELECTOR_TOOLTIP =
  'Labels that tell OpenShift which worker nodes in the selected cluster can run container pods for this target. Keys and values must match labels on cluster nodes—the scheduler uses them for pod placement. This controls where workloads run on the cluster, not how the orchestrator chooses an execution target for a workflow node.'

/** Helper text shown beneath the node selector key/value rows. */
export const OPENSHIFT_NODE_SELECTOR_HINT =
  'Match labels on OpenShift worker nodes in the selected cluster. Example: region=us-east.'

/** Helper text shown beneath the default execution target checkbox. */
export const DEFAULT_EXECUTION_TARGET_HINT =
  'Only one execution target can be default. Setting a default replaces the current default.'

/** Helper text when configuring the first execution target (auto-default). */
export const FIRST_DEFAULT_EXECUTION_TARGET_HINT =
  'Only one execution target can be default. Setting a default replaces the current default. The first target is automatically the default.'

/** Helper text when editing the current default (checkbox locked checked). */
export const CURRENT_DEFAULT_EXECUTION_TARGET_HINT =
  'Only one execution target can be default. This target is the current default and cannot be unmarked. To change the default, edit another target and mark it as default.'

/** Pre-built labelHelp elements for the configure execution target form. */
export const executionTargetHelp = {
  nodeSelector: createFieldHelp('OpenShift node selector', OPENSHIFT_NODE_SELECTOR_TOOLTIP),
} as const
