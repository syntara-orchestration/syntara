import { createFieldHelp } from '../../components/createFieldHelp'

/** Popover body for the OpenShift node selector field help (`?`) control. */
export const OPENSHIFT_NODE_SELECTOR_TOOLTIP =
  'Labels that tell OpenShift which worker nodes in the selected cluster can run container pods for this target. Keys and values must match labels on cluster nodes—the scheduler uses them for pod placement. This controls where workloads run on the cluster, not how the orchestrator chooses an execution target for a workflow node.'

/** Helper text shown beneath the node selector key/value rows. */
export const OPENSHIFT_NODE_SELECTOR_HINT =
  'Match labels on OpenShift worker nodes in the selected cluster. Example: region=us-east.'

/** Pre-built labelHelp elements for the configure execution target form. */
export const executionTargetHelp = {
  nodeSelector: createFieldHelp('OpenShift node selector', OPENSHIFT_NODE_SELECTOR_TOOLTIP),
} as const
