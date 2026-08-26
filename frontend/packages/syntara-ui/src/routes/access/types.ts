/**
 * Shared types for the Access Management (RBAC) routes.
 *
 * Re-exported from auto-generated OpenAPI contracts so that consumer
 * imports stay unchanged while types stay in sync with the backend.
 */
import type { User } from '@syntara/contracts'
import type * as AuthzAPI from '@syntara/contracts/src/authz-api.js'
import type * as PoliciesAPI from '@syntara/contracts/src/policies-api.js'
import type * as ProjectsAPI from '@syntara/contracts/src/projects-api.js'
import type * as RoleAssignmentsAPI from '@syntara/contracts/src/role-assignments-api.js'
import type * as RolesAPI from '@syntara/contracts/src/roles-api.js'

import type { RolePrincipalType } from '../access-management/RoleAssignmentTypes'

// ── Project ───────────────────────────────────────────────────────────────

export type ProjectRead = ProjectsAPI.components['schemas']['ProjectRead']
export type ProjectCreate = ProjectsAPI.components['schemas']['ProjectCreate']
export type ProjectUpdate = ProjectsAPI.components['schemas']['ProjectUpdate']

// ── Role Assignment (unified) ────────────────────────────────────────────

export type RoleAssignmentRead = RoleAssignmentsAPI.components['schemas']['RoleAssignmentRead']
export type RoleAssignmentCreate = RoleAssignmentsAPI.components['schemas']['RoleAssignmentCreate']

// ── Policy ────────────────────────────────────────────────────────────────

export type PolicyStatement = PoliciesAPI.components['schemas']['PolicyStatementSchema']

// The generated PolicyRead.statements is `{ [key: string]: unknown }[]`
// which loses the strongly-typed PolicyStatementSchema. Override it.
/** Raw OpenAPI `PolicyRead` (statements are loosely typed in the generated schema). */
export type PolicyReadApi = PoliciesAPI.components['schemas']['PolicyRead']
export type PolicyRead = Omit<PolicyReadApi, 'statements'> & {
  statements: PolicyStatement[]
}

// ── Role ──────────────────────────────────────────────────────────────────

export type RoleRead = RolesAPI.components['schemas']['RoleRead']
export type RoleCreate = RolesAPI.components['schemas']['RoleCreate']
export type RoleUpdate = RolesAPI.components['schemas']['RoleUpdate']

// ── Project-scoped Policy ───────────────────────────────────────────────

export type ProjectPolicyRead = ProjectsAPI.components['schemas']['PolicyRead']
export type ProjectPolicyCreate = ProjectsAPI.components['schemas']['ProjectPolicyCreate']
export type ProjectPolicyUpdate = ProjectsAPI.components['schemas']['PolicyUpdate']

// ── User ─────────────────────────────────────────────────────────────────

export type UserRead = User

// ── Authorization query types ────────────────────────────────────────────

export type CanIRequest = AuthzAPI.components['schemas']['CanIRequest']
export type CanIResponse = AuthzAPI.components['schemas']['CanIResponse']
export type WhoCanRequest = AuthzAPI.components['schemas']['WhoCanRequest']
export type WhoCanUser = AuthzAPI.components['schemas']['WhoCanUser']
export type WhoCanResponse = AuthzAPI.components['schemas']['WhoCanResponse']

export type PermissionEntry = AuthzAPI.components['schemas']['PermissionEntry']

export type WhatCanIResponse = AuthzAPI.components['schemas']['WhatCanIResponse']

export type ResourceActionsResponse = AuthzAPI.components['schemas']['ResourceActionsResponse']

// ── Unified permission row for the Access Management table ───────────────

export type PermissionRow = {
  id: string
  principalType: RolePrincipalType
  principalId: string
  principalName: string
  assignmentType: 'role'
  assignmentName: string
  roleDescription: string | null
  rolePolicies: string[]
  roleId?: string
  scopeType: 'project' | 'system'
  scopeName: string
  projectId?: string
  sourceEndpoint: 'role-assignments' | 'project-role-assignments'
}
