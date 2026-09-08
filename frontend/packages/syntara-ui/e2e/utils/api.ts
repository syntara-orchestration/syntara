/**
 * Barrel re-export for E2E API utilities.
 *
 * All domain-specific helpers live in their own modules (api-core, api-credentials,
 * etc.). This file re-exports everything so existing spec files can continue to
 * import from './utils/api' without changes.
 */
export { apiUrl, getAuthToken, apiRequest, ensureProject } from './api-core'
export { createCredentialViaApi, deleteCredentialViaApi, listCredentialsByName } from './api-credentials'
export {
  createWorkflowViaApi,
  publishWorkflowViaApi,
  createBasicWorkflowViaApi,
  findWorkflowIdByName,
  deleteWorkflowViaApi,
} from './api-workflows'
export {
  type GroupResource,
  listAllGroups,
  createGroupViaApi,
  deleteGroupViaApi,
  findBuiltinGroupByName,
  type IdentityProviderResource,
  createIdentityProviderViaApi,
  deleteIdentityProviderViaApi,
  findIdentityProviderByName,
  createUserViaApi,
  deleteUserViaApi,
  createPolicyViaApi,
  deletePolicyViaApi,
  createRoleViaApi,
  deleteRoleViaApi,
  createRoleAssignmentViaApi,
  deleteRoleAssignmentViaApi,
  createServiceAccountViaApi,
  deleteServiceAccountViaApi,
} from './api-rbac'
export { pollExecutionStatus, pollApprovalVisible } from './api-executions'
