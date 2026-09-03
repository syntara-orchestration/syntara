/** Mock data for Access Management (RBAC) endpoints. */
import { mockDate } from './mockDates'

// ── Users (simplified for display) ────────────────────────────────────────

export interface MockUser {
  id: string
  username: string
  first_name: string
  last_name?: string | null
}

export const mockUsers: MockUser[] = [
  { id: 'u-001', username: 'alice', first_name: 'Alice', last_name: 'Johnson' },
  { id: 'u-002', username: 'bob', first_name: 'Bob', last_name: 'Smith' },
  { id: 'u-003', username: 'carol', first_name: 'Carol', last_name: 'Williams' },
  { id: 'u-004', username: 'admin', first_name: 'System', last_name: 'Admin' },
  { id: 'u-005', username: 'dave', first_name: 'Dave', last_name: 'Chen' },
]

// ── Groups ────────────────────────────────────────────────────────────────

export interface MockGroup {
  id: string
  name: string
  is_builtin: boolean
}

export const mockGroups: MockGroup[] = [
  { id: 'g-001', name: 'authenticated', is_builtin: true },
  { id: 'g-002', name: 'admins', is_builtin: true },
  { id: 'g-003', name: 'developers', is_builtin: false },
]

// ── Projects ──────────────────────────────────────────────────────────────

export interface MockProject {
  id: string
  name: string
  description: string | null
  labels: Record<string, string>
  is_default: boolean
  is_builtin: boolean
  created_at: string
  updated_at: string
}

export const mockProjects: MockProject[] = [
  {
    id: 'p-builtin',
    name: 'built-in',
    description: 'Built-in system project containing predefined workflows',
    labels: {},
    is_default: false,
    is_builtin: true,
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'p-001',
    name: 'default',
    description: 'Default project for all users',
    labels: {},
    is_default: true,
    is_builtin: false,
    created_at: '2024-01-15T19:00:00.000Z',
    updated_at: mockDate.daysAgo2,
  },
  {
    id: 'p-002',
    name: 'alice-sandbox',
    description: 'Alice sandbox project',
    labels: { team: 'platform' },
    is_default: false,
    is_builtin: false,
    created_at: '2024-02-01T19:00:00.000Z',
    updated_at: '2024-03-14T20:00:00.000Z',
  },
]

// ── Policies ─────────────────────────────────────────────────────────────

export interface MockPolicyStatement {
  effect: 'allow' | 'deny'
  scope: string
  actions: string[]
}

export interface MockPolicy {
  id: string
  name: string
  description: string | null
  is_builtin: boolean
  is_project_eligible: boolean
  /** Policy scope for list filtering (`any` | `self` | `project`), aligned with PolicyRead.scope */
  scope: 'any' | 'self' | 'project'
  project_id: string | null
  statements: MockPolicyStatement[]
  created_at: string
  updated_at: string
}

export const mockPolicies: MockPolicy[] = [
  // Project-scoped custom policies (shown first so they appear on page 1)
  {
    id: 'pol-013',
    name: 'deployment:approve:any',
    description: 'Approve deployment requests',
    is_builtin: false,
    is_project_eligible: true,
    scope: 'project',
    project_id: 'p-002',
    statements: [{ effect: 'allow', scope: 'project', actions: ['deployment:approve'] }],
    created_at: '2024-02-10T00:00:00.000Z',
    updated_at: '2024-02-10T00:00:00.000Z',
  },
  {
    id: 'pol-015',
    name: 'inventory:manage:any',
    description: 'Manage inventory resources',
    is_builtin: false,
    is_project_eligible: true,
    scope: 'project',
    project_id: 'p-001',
    statements: [
      {
        effect: 'allow',
        scope: 'project',
        actions: ['inventory:read', 'inventory:create', 'inventory:update', 'inventory:delete'],
      },
    ],
    created_at: '2024-01-20T00:00:00.000Z',
    updated_at: '2024-01-20T00:00:00.000Z',
  },
  // Global builtin policies
  {
    id: 'pol-001',
    name: 'admin:full:any',
    description: 'Full administrative access to all resources',
    is_builtin: true,
    is_project_eligible: false,
    scope: 'any',
    project_id: null,
    statements: [
      {
        effect: 'allow',
        scope: 'any',
        actions: [
          'workflow:create',
          'workflow:read',
          'workflow:update',
          'workflow:delete',
          'execution:read',
          'execution:run',
          'audit:read',
          'project:create',
          'user:read',
          'user:update',
        ],
      },
    ],
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'pol-002',
    name: 'workflow:create:any',
    description: 'Create workflows in any project',
    is_builtin: true,
    is_project_eligible: true,
    scope: 'any',
    project_id: null,
    statements: [{ effect: 'allow', scope: 'any', actions: ['workflow:create'] }],
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'pol-003',
    name: 'workflow:read:any',
    description: 'View workflows in any project',
    is_builtin: true,
    is_project_eligible: true,
    scope: 'any',
    project_id: null,
    statements: [{ effect: 'allow', scope: 'any', actions: ['workflow:read'] }],
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'pol-004',
    name: 'workflow:update:any',
    description: 'Edit workflows in any project',
    is_builtin: true,
    is_project_eligible: true,
    scope: 'any',
    project_id: null,
    statements: [{ effect: 'allow', scope: 'any', actions: ['workflow:update'] }],
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'pol-005',
    name: 'workflow:delete:any',
    description: 'Delete workflows in any project',
    is_builtin: true,
    is_project_eligible: true,
    scope: 'any',
    project_id: null,
    statements: [{ effect: 'allow', scope: 'any', actions: ['workflow:delete'] }],
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'pol-006',
    name: 'execution:read:any',
    description: 'View execution results',
    is_builtin: true,
    is_project_eligible: true,
    scope: 'any',
    project_id: null,
    statements: [{ effect: 'allow', scope: 'any', actions: ['execution:read'] }],
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'pol-007',
    name: 'execution:run:any',
    description: 'Run workflow executions',
    is_builtin: true,
    is_project_eligible: true,
    scope: 'any',
    project_id: null,
    statements: [{ effect: 'allow', scope: 'any', actions: ['execution:run'] }],
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'pol-008',
    name: 'audit:read:any',
    description: 'View audit data',
    is_builtin: true,
    is_project_eligible: true,
    scope: 'any',
    project_id: null,
    statements: [{ effect: 'allow', scope: 'any', actions: ['audit:read'] }],
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'pol-009',
    name: 'project-role:assign:any',
    description: 'Assign roles within projects',
    is_builtin: true,
    is_project_eligible: true,
    scope: 'any',
    project_id: null,
    statements: [{ effect: 'allow', scope: 'any', actions: ['project-role:assign'] }],
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'pol-010',
    name: 'user:read:self',
    description: 'Read own user information',
    is_builtin: true,
    is_project_eligible: false,
    scope: 'self',
    project_id: null,
    statements: [{ effect: 'allow', scope: 'self', actions: ['user:read'] }],
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'pol-011',
    name: 'user:update:self',
    description: 'Update own user information',
    is_builtin: true,
    is_project_eligible: false,
    scope: 'self',
    project_id: null,
    statements: [{ effect: 'allow', scope: 'self', actions: ['user:update'] }],
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'pol-012',
    name: 'project:create:any',
    description: 'Create new projects',
    is_builtin: true,
    is_project_eligible: false,
    scope: 'any',
    project_id: null,
    statements: [{ effect: 'allow', scope: 'any', actions: ['project:create'] }],
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  // Project-scoped policy (alice-sandbox, secret access)
  {
    id: 'pol-014',
    name: 'secret:read:any',
    description: 'Read project secrets and credentials',
    is_builtin: false,
    is_project_eligible: true,
    scope: 'project',
    project_id: 'p-002',
    statements: [{ effect: 'allow', scope: 'project', actions: ['secret:read'] }],
    created_at: '2024-02-10T00:00:00.000Z',
    updated_at: '2024-02-10T00:00:00.000Z',
  },
]

// ── Roles ─────────────────────────────────────────────────────────────────

export interface MockRole {
  id: string
  name: string
  description: string | null
  policies: string[]
  is_builtin: boolean
  project_id: string | null
  labels: Record<string, string>
  created_at: string
  updated_at: string
}

export const mockRoles: MockRole[] = [
  {
    id: 'r-001',
    name: 'admin',
    description: 'Full system access',
    policies: ['admin:full:any'],
    is_builtin: true,
    project_id: null,
    labels: {},
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'r-002',
    name: 'user',
    description: 'Standard user access',
    policies: [
      'workflow:create:any',
      'workflow:read:any',
      'workflow:update:any',
      'workflow:delete:any',
      'execution:read:any',
      'execution:run:any',
    ],
    is_builtin: true,
    project_id: null,
    labels: {},
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'r-003',
    name: 'auditor',
    description: 'Read-only access for auditing',
    policies: ['workflow:read:any', 'execution:read:any', 'audit:read:any'],
    is_builtin: true,
    project_id: null,
    labels: {},
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'r-004',
    name: 'project-admin',
    description: 'Full project access including role assignment',
    policies: [
      'workflow:create:any',
      'workflow:read:any',
      'workflow:update:any',
      'workflow:delete:any',
      'project-role:assign:any',
    ],
    is_builtin: true,
    project_id: null,
    labels: {},
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'r-005',
    name: 'project-user',
    description: 'Standard project member access',
    policies: [
      'workflow:create:any',
      'workflow:read:any',
      'workflow:update:any',
      'execution:read:any',
      'execution:run:any',
    ],
    is_builtin: true,
    project_id: null,
    labels: {},
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'r-006',
    name: 'project-auditor',
    description: 'Read-only access within a project',
    policies: ['workflow:read:any', 'execution:read:any'],
    is_builtin: true,
    project_id: null,
    labels: {},
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'r-007',
    name: 'default',
    description: 'Baseline for all authenticated users',
    policies: ['user:read:self', 'user:update:self', 'project:create:any'],
    is_builtin: true,
    project_id: null,
    labels: {},
    created_at: '2024-01-01T00:00:00.000Z',
    updated_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'r-008',
    name: 'deployer',
    description: 'Can approve and manage deployments',
    policies: ['deployment:approve:any', 'execution:run:any'],
    is_builtin: false,
    project_id: 'p-002',
    labels: {},
    created_at: '2024-02-10T00:00:00.000Z',
    updated_at: '2024-02-10T00:00:00.000Z',
  },
  {
    id: 'r-009',
    name: 'inventory-manager',
    description: 'Manage inventory and related resources',
    policies: ['inventory:manage:any', 'workflow:read:any'],
    is_builtin: false,
    project_id: 'p-001',
    labels: {},
    created_at: '2024-01-20T00:00:00.000Z',
    updated_at: '2024-01-20T00:00:00.000Z',
  },
]

// ── Project Role Assignments (user → role in project) ─────────────────────

export interface MockProjectRoleAssignment {
  id: string
  user_id: string
  username: string
  project_id: string
  role_id: string
  role_name: string
  created_at: string
}

export const mockProjectRoleAssignments: MockProjectRoleAssignment[] = [
  {
    id: 'pra-001',
    user_id: 'u-001',
    username: 'alice',
    project_id: 'p-002',
    role_id: 'r-004',
    role_name: 'project-admin',
    created_at: '2024-02-01T19:00:00.000Z',
  },
  {
    id: 'pra-002',
    user_id: 'u-002',
    username: 'bob',
    project_id: 'p-002',
    role_id: 'r-005',
    role_name: 'project-user',
    created_at: '2024-02-15T19:00:00.000Z',
  },
]

// ── Project Group Role Assignments (group → role in project) ──────────────

export interface MockProjectGroupRoleAssignment {
  id: string
  group_id: string
  group_name: string
  project_id: string
  role_id: string
  role_name: string
  created_at: string
}

export const mockProjectGroupRoleAssignments: MockProjectGroupRoleAssignment[] = [
  {
    id: 'pgra-001',
    group_id: 'g0-builtin-authenticated',
    group_name: 'authenticated',
    project_id: 'p-001',
    role_id: 'r-005',
    role_name: 'project-user',
    created_at: '2024-01-15T19:00:00.000Z',
  },
]

// ── System-level Group Role Assignments ───────────────────────────────────

export interface MockGroupRoleAssignment {
  id: string
  group_id: string
  group_name: string
  role_id: string
  role_name: string
  created_at: string
}

export const mockGroupRoleAssignments: MockGroupRoleAssignment[] = [
  {
    id: 'gra-001',
    group_id: 'g0-builtin-authenticated',
    group_name: 'authenticated',
    role_id: 'r-007',
    role_name: 'default',
    created_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'gra-002',
    group_id: 'g0-builtin-admins',
    group_name: 'admins',
    role_id: 'r-001',
    role_name: 'admin',
    created_at: '2024-01-01T00:00:00.000Z',
  },
]

// ── System-level User Role Assignments ───────────────────────────────────

export interface MockUserRoleAssignment {
  id: string
  user_id: string
  username: string
  role_id: string
  role_name: string
  created_at: string
}

export const mockUserRoleAssignments: MockUserRoleAssignment[] = [
  {
    id: 'ura-001',
    user_id: 'u-001',
    username: 'alice',
    role_id: 'r-001',
    role_name: 'admin',
    created_at: '2024-01-01T00:00:00.000Z',
  },
  {
    id: 'ura-002',
    user_id: 'b2c3d4e5-f6a7-8901-bcde-f12345678901',
    username: 'jdoe',
    role_id: 'r-001',
    role_name: 'admin',
    created_at: '2026-02-15T00:00:00.000Z',
  },
  {
    id: 'ura-003',
    user_id: 'b2c3d4e5-f6a7-8901-bcde-f12345678901',
    username: 'jdoe',
    role_id: 'r-002',
    role_name: 'viewer',
    created_at: '2026-03-01T00:00:00.000Z',
  },
]

// ── Service Account Role Assignments (SA → role in project) ─────────────

export interface MockServiceAccountRoleAssignment {
  id: string
  service_account_id: string
  service_account_name: string
  project_id: string
  role_id: string
  role_name: string
  created_at: string
}

export const mockServiceAccountRoleAssignments: MockServiceAccountRoleAssignment[] = [
  {
    id: 'sara-001',
    service_account_id: 'sa-001',
    service_account_name: 'ci-pipeline',
    project_id: 'p-001',
    role_id: 'r-005',
    role_name: 'project-user',
    created_at: '2024-03-10T00:00:00.000Z',
  },
]

// ── Service Accounts ─────────────────────────────────────────────────────

export type ServiceAccountStatus = 'active' | 'disabled'

export interface MockServiceAccount {
  id: string
  name: string
  description: string | null
  status: ServiceAccountStatus
  project_id: string
  project_name: string | null
  is_project_deleted: boolean
  last_authenticated_at: string | null
  created_by: { id: string; name: string }
  updated_by: { id: string; name: string } | null
  created_at: string
  updated_at: string
  labels: Record<string, string>
}

export const mockServiceAccounts: MockServiceAccount[] = [
  {
    id: 'sa-001',
    name: 'ci-pipeline',
    description: 'CI/CD pipeline service account for automated deployments',
    status: 'active',
    project_id: 'p-001',
    project_name: 'default',
    is_project_deleted: false,
    last_authenticated_at: mockDate.hoursAgo2,
    created_by: { id: 'u-001', name: 'alice' },
    updated_by: null,
    created_at: '2024-03-01T10:00:00.000Z',
    updated_at: '2024-03-01T10:00:00.000Z',
    labels: { environment: 'production' },
  },
  {
    id: 'sa-002',
    name: 'monitoring-agent',
    description: 'Monitoring and observability agent',
    status: 'active',
    project_id: 'p-001',
    project_name: 'default',
    is_project_deleted: false,
    last_authenticated_at: mockDate.minutesAgo30,
    created_by: { id: 'u-001', name: 'alice' },
    updated_by: null,
    created_at: '2024-03-15T14:00:00.000Z',
    updated_at: '2024-03-15T14:00:00.000Z',
    labels: {},
  },
  {
    id: 'sa-003',
    name: 'backup-agent',
    description: 'Automated backup service',
    status: 'disabled',
    project_id: 'p-002',
    project_name: 'alice-sandbox',
    is_project_deleted: false,
    last_authenticated_at: mockDate.daysAgo5,
    created_by: { id: 'u-002', name: 'bob' },
    updated_by: { id: 'u-001', name: 'alice' },
    created_at: '2024-02-20T09:00:00.000Z',
    updated_at: mockDate.daysAgo3,
    labels: {},
  },
  {
    id: 'sa-004',
    name: 'api-gateway',
    description: null,
    status: 'active',
    project_id: 'p-002',
    project_name: 'alice-sandbox',
    is_project_deleted: false,
    last_authenticated_at: null,
    created_by: { id: 'u-001', name: 'alice' },
    updated_by: null,
    created_at: mockDate.daysAgo1,
    updated_at: mockDate.daysAgo1,
    labels: { team: 'platform' },
  },
  {
    id: 'sa-005',
    name: 'legacy-sync',
    description: 'Sync agent from a project that has been removed',
    status: 'disabled',
    project_id: 'p-deleted-001',
    project_name: 'retired-infra',
    is_project_deleted: true,
    last_authenticated_at: mockDate.daysAgo5,
    created_by: { id: 'u-002', name: 'bob' },
    updated_by: null,
    created_at: '2024-01-10T08:00:00.000Z',
    updated_at: '2024-01-10T08:00:00.000Z',
    labels: {},
  },
]

// ── Service Account Credentials ─────────────────────────────────────────

export type ServiceAccountCredentialStatus = 'active' | 'disabled'

export interface MockServiceAccountCredential {
  id: string
  service_account_id: string
  credential_type: 'client_credentials'
  identifier: string
  status: ServiceAccountCredentialStatus
  grace_period_seconds: number
  expires_at: string | null
  last_used_at: string | null
  old_secret_valid_until?: string | null
  created_by: { id: string; name: string }
  updated_by: { id: string; name: string } | null
  created_at: string
  updated_at: string
}

export const mockServiceAccountCredentials: MockServiceAccountCredential[] = [
  {
    id: 'cred-001',
    service_account_id: 'sa-001',
    credential_type: 'client_credentials',
    identifier: 'nx_sa_ci_pipeline_a1b2c3',
    status: 'active',
    grace_period_seconds: 3600,
    expires_at: null,
    last_used_at: mockDate.hoursAgo2,
    old_secret_valid_until: mockDate.hoursFromNow2,
    created_by: { id: 'u-001', name: 'alice' },
    updated_by: null,
    created_at: '2024-03-01T10:00:00.000Z',
    updated_at: '2024-03-01T10:00:00.000Z',
  },
  {
    id: 'cred-002',
    service_account_id: 'sa-001',
    credential_type: 'client_credentials',
    identifier: 'nx_sa_ci_pipeline_d4e5f6',
    status: 'disabled',
    grace_period_seconds: 3600,
    expires_at: mockDate.daysAgo1,
    last_used_at: mockDate.daysAgo5,
    created_by: { id: 'u-001', name: 'alice' },
    updated_by: { id: 'u-001', name: 'alice' },
    created_at: '2024-02-15T08:00:00.000Z',
    updated_at: mockDate.daysAgo3,
  },
  {
    id: 'cred-003',
    service_account_id: 'sa-002',
    credential_type: 'client_credentials',
    identifier: 'nx_sa_monitoring_agent_g7h8i9',
    status: 'active',
    grace_period_seconds: 7200,
    expires_at: null,
    last_used_at: mockDate.minutesAgo30,
    created_by: { id: 'u-001', name: 'alice' },
    updated_by: null,
    created_at: '2024-03-15T14:00:00.000Z',
    updated_at: '2024-03-15T14:00:00.000Z',
  },
]

// ── Helpers ───────────────────────────────────────────────────────────────

export function getUserName(userId: string): string {
  const user = mockUsers.find((u) => u.id === userId)
  return user ? [user.first_name, user.last_name].filter(Boolean).join(' ') : userId
}

export function getGroupName(groupId: string): string {
  return mockGroups.find((g) => g.id === groupId)?.name ?? groupId
}

export function getRoleName(roleId: string): string {
  return mockRoles.find((r) => r.id === roleId)?.name ?? roleId
}
