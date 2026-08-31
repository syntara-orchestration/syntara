import type * as AuthAPI from '@syntara/contracts/src/auth-api.js'

export type GroupRead = AuthAPI.components['schemas']['GroupRead']

/** Maps user IDs to the group IDs they belong to */
export const userGroupMemberships: Record<string, string[]> = {
  'a1b2c3d4-e5f6-7890-abcd-ef1234567890': [
    'g0-builtin-admins',
    'g0-builtin-authenticated',
    'g1a2b3c4-d5e6-7890-abcd-ef1234567890',
  ],
  'b2c3d4e5-f6a7-8901-bcde-f12345678901': ['g0-builtin-authenticated', 'g2b3c4d5-e6f7-8901-bcde-f12345678901'],
  'c3d4e5f6-a7b8-9012-cdef-123456789012': ['g0-builtin-authenticated'],
  'd4e5f6a7-b8c9-0123-defa-234567890123': ['g0-builtin-authenticated', 'g3c4d5e6-f7a8-9012-cdef-123456789012'],
  'e5f6a7b8-c9d0-1234-efab-345678901234': ['g0-builtin-authenticated'],
}

function computeMemberCount(groupId: string): number {
  return Object.values(userGroupMemberships).filter((ids) => ids.includes(groupId)).length
}

export const groups: GroupRead[] = [
  {
    id: 'g0-builtin-admins',
    name: 'admins',
    description: 'Built-in administrators group',
    is_builtin: true,
    created_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    source: 'local',
    member_count: computeMemberCount('g0-builtin-admins'),
  },
  {
    id: 'g0-builtin-authenticated',
    name: 'authenticated',
    description: 'Built-in group for all authenticated users',
    is_builtin: true,
    created_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    source: 'local',
    member_count: computeMemberCount('g0-builtin-authenticated'),
  },
  {
    id: 'g0-builtin-auditors',
    name: 'auditors',
    description: 'Read-only access for compliance review',
    is_builtin: true,
    created_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    source: 'local',
    member_count: computeMemberCount('g0-builtin-auditors'),
  },
  {
    id: 'g0-builtin-users',
    name: 'users',
    description: 'Standard users with access to create and manage own resources',
    is_builtin: true,
    created_by: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    source: 'local',
    member_count: computeMemberCount('g0-builtin-users'),
  },
  {
    id: 'g1a2b3c4-d5e6-7890-abcd-ef1234567890',
    name: 'platform-admins',
    description: 'Full platform administrators',
    is_builtin: false,
    created_by: { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', name: 'demo' },
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    source: 'local',
    member_count: computeMemberCount('g1a2b3c4-d5e6-7890-abcd-ef1234567890'),
  },
  {
    id: 'g2b3c4d5-e6f7-8901-bcde-f12345678901',
    name: 'developers',
    description: 'Workflow developers and creators',
    is_builtin: false,
    created_by: { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', name: 'demo' },
    created_at: '2026-01-15T00:00:00Z',
    updated_at: '2026-01-15T00:00:00Z',
    source: 'local',
    member_count: computeMemberCount('g2b3c4d5-e6f7-8901-bcde-f12345678901'),
  },
  {
    id: 'g3c4d5e6-f7a8-9012-cdef-123456789012',
    name: 'viewers',
    description: 'Read-only access group',
    is_builtin: false,
    created_by: { id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890', name: 'demo' },
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
    source: 'local',
    member_count: computeMemberCount('g3c4d5e6-f7a8-9012-cdef-123456789012'),
  },
]
