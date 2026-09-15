import type { CredentialsAPI } from '@syntara/contracts'

type CredentialRead = CredentialsAPI.components['schemas']['CredentialRead']
type CredentialTypeRead = CredentialsAPI.components['schemas']['CredentialTypeRead']
type CredentialWorkflowRef = CredentialsAPI.components['schemas']['CredentialWorkflowRef']

// Type assertion needed because the contract types `inputs` as Record<string, never>,
// but the runtime JSON contains field schema objects. The UI casts with `as Record<string, unknown>`.
type FieldDef = {
  id: string
  label: string
  type: string
  secret?: boolean
  help_text?: string
  choices?: string[]
  default?: unknown
  multiline?: boolean
}

type FieldConstraints = {
  mutually_exclusive?: string[][]
  mutually_exclusive_labels?: string[]
  mutually_exclusive_help?: string
  required_one_of?: string[][]
  required_together?: string[][]
}

function typeInputs(fields: FieldDef[], required: string[] = [], constraints?: FieldConstraints) {
  return { fields, required, ...constraints } as CredentialTypeRead['inputs']
}

function typeInjectors(extra_vars: Record<string, string>) {
  return { env: {}, file: {}, extra_vars } as CredentialTypeRead['injectors']
}

export const credentialTypes: CredentialTypeRead[] = [
  {
    id: 'ctype-bearer',
    name: 'HTTP Bearer Token',
    description: 'Bearer token authentication for HTTP APIs',
    inputs: typeInputs(
      [{ id: 'token', type: 'string', label: 'Token', secret: true, help_text: 'Bearer token value' }],
      ['token']
    ),
    injectors: typeInjectors({ auth_type: 'bearer', bearer_token: '{{token}}' }),
    managed: true,
    credential_count: 1,
    created_at: '2025-06-01T09:00:00Z',
    updated_at: '2025-06-01T09:00:00Z',
    labels: {},
  },
  {
    id: 'ctype-basic',
    name: 'HTTP Basic Auth',
    description: 'Username and password authentication for HTTP APIs',
    inputs: typeInputs(
      [
        { id: 'username', type: 'string', label: 'Username', secret: false, help_text: 'Username for authentication' },
        { id: 'password', type: 'string', label: 'Password', secret: true, help_text: 'Password for authentication' },
      ],
      ['username', 'password']
    ),
    injectors: typeInjectors({ auth_type: 'basic', basic_username: '{{username}}', basic_password: '{{password}}' }),
    managed: true,
    credential_count: 2,
    created_at: '2025-06-01T09:00:00Z',
    updated_at: '2025-06-01T09:00:00Z',
    labels: {},
  },
  {
    id: 'ctype-aap',
    name: 'Ansible Automation Platform',
    description: 'Authentication for Ansible Automation Platform Controller API',
    inputs: typeInputs(
      [
        {
          id: 'username',
          type: 'string',
          label: 'Username',
          secret: false,
          help_text: 'AAP username (optional if using token)',
        },
        {
          id: 'password',
          type: 'string',
          label: 'Password',
          secret: true,
          help_text: 'AAP password (optional if using token)',
        },
        {
          id: 'oauth_token',
          type: 'string',
          label: 'OAuth Token',
          secret: true,
          help_text: 'AAP OAuth2 token (preferred over username/password)',
        },
      ],
      [],
      {
        mutually_exclusive: [['oauth_token'], ['username', 'password']],
        mutually_exclusive_labels: ['OAuth2 Token', 'Basic Auth'],
        mutually_exclusive_help:
          'Basic Auth authenticates with an Ansible Automation Platform username and password. OAuth2 Token authenticates with a personal access token, which can be scoped and revoked independently of a user account.',
        required_one_of: [['oauth_token'], ['username', 'password']],
        required_together: [['username', 'password']],
      }
    ),
    injectors: typeInjectors({
      auth_type: 'aap',
      aap_username: '{{username}}',
      aap_password: '{{password}}',
      aap_oauth_token: '{{oauth_token}}',
    }),
    managed: true,
    credential_count: 0,
    created_at: '2025-06-01T09:00:00Z',
    updated_at: '2025-06-01T09:00:00Z',
    labels: {},
  },
  {
    id: 'ctype-llm',
    name: 'LLM Provider',
    description: 'API key authentication for LLM providers (OpenAI, Anthropic, etc.)',
    inputs: typeInputs(
      [{ id: 'api_key', type: 'string', label: 'API Key', secret: true, help_text: 'API key for the LLM provider' }],
      ['api_key']
    ),
    injectors: typeInjectors({
      auth_type: 'api_key',
      llm_api_key: '{{api_key}}',
    }),
    managed: true,
    credential_count: 0,
    created_at: '2025-06-01T09:00:00Z',
    updated_at: '2025-06-01T09:00:00Z',
    labels: {},
  },
  {
    id: 'ctype-ssh',
    name: 'SSH Key',
    description: 'SSH private key authentication without passphrase',
    inputs: typeInputs(
      [
        { id: 'username', type: 'string', label: 'Username', secret: false, help_text: 'SSH username' },
        {
          id: 'ssh_private_key',
          type: 'string',
          label: 'Private key',
          secret: true,
          help_text: 'Paste private key contents (OpenSSH format, no passphrase)',
          multiline: true,
        },
      ],
      ['username', 'ssh_private_key']
    ),
    injectors: typeInjectors({
      auth_type: 'ssh',
      ssh_username: '{{username}}',
      ssh_private_key: '{{ssh_private_key}}',
    }),
    managed: true,
    credential_count: 0,
    created_at: '2025-06-01T09:00:00Z',
    updated_at: '2025-06-01T09:00:00Z',
    labels: {},
  },
]

// Workflow references for credential detail pages
export const credentialWorkflows: Record<string, CredentialWorkflowRef[]> = {
  'cred-001': [
    {
      id: 'wf-001',
      name: 'Production Deployment Pipeline',
      created_by: 'user-001',
      created_at: '2025-07-10T14:30:00Z',
    },
    { id: 'wf-002', name: 'Nightly Health Check', created_by: 'user-001', created_at: '2025-07-12T10:00:00Z' },
  ],
}

/** TODO: Revert to CredentialRead[] once project_id is added to the OpenAPI spec */
export const credentials: (CredentialRead & { project_id?: string })[] = [
  {
    id: 'cred-001',
    name: 'Production API Auth',
    description: 'Basic auth for production API access',
    credential_type_id: 'ctype-basic',
    inputs: { username: 'admin', password: '$encrypted$' },
    enabled: true,
    created_at: '2025-07-10T14:30:00Z',
    updated_at: '2025-07-10T14:30:00Z',
    created_by: { id: '550e8400-e29b-41d4-a716-446655440001', name: 'user-001' },
    labels: {},
    deleted_at: null,
    deleted_by: null,
    project_id: 'p-001',
  },
  {
    id: 'cred-002',
    name: 'Staging API Auth',
    description: 'Basic auth for staging environment',
    credential_type_id: 'ctype-basic',
    inputs: { username: 'deploy', password: '$encrypted$' },
    enabled: true,
    created_at: '2025-07-12T10:00:00Z',
    updated_at: '2025-07-12T10:00:00Z',
    created_by: { id: '550e8400-e29b-41d4-a716-446655440001', name: 'user-001' },
    labels: {},
    deleted_at: null,
    deleted_by: null,
    project_id: 'p-001',
  },
  {
    id: 'cred-003',
    name: 'GitHub API Token',
    description: 'Bearer token for GitHub API access',
    credential_type_id: 'ctype-bearer',
    inputs: { token: '$encrypted$' },
    enabled: false,
    created_at: '2025-08-01T08:00:00Z',
    updated_at: '2025-08-05T16:45:00Z',
    created_by: { id: '550e8400-e29b-41d4-a716-446655440002', name: 'user-002' },
    labels: {},
    deleted_at: null,
    deleted_by: null,
    project_id: 'p-002',
  },
  {
    id: 'cred-004',
    name: 'MCP Integration Token',
    description: 'Bearer token for MCP server integration',
    credential_type_id: 'ctype-bearer',
    inputs: { token: '$encrypted$' },
    enabled: true,
    created_at: '2025-09-01T10:00:00Z',
    updated_at: '2025-09-01T10:00:00Z',
    created_by: { id: '550e8400-e29b-41d4-a716-446655440001', name: 'user-001' },
    labels: {},
    deleted_at: null,
    deleted_by: null,
    project_id: null,
  },
  {
    id: 'cred-005',
    name: 'OpenAI API Key',
    description: 'API key for OpenAI LLM provider',
    credential_type_id: 'ctype-llm',
    inputs: { api_key: '$encrypted$' },
    enabled: true,
    created_at: '2025-09-15T09:00:00Z',
    updated_at: '2025-09-15T09:00:00Z',
    created_by: { id: '550e8400-e29b-41d4-a716-446655440001', name: 'user-001' },
    labels: {},
    deleted_at: null,
    deleted_by: null,
    project_id: 'p-001',
  },
  {
    id: 'cred-006',
    name: 'Azure OpenAI Key',
    description: 'API key for Azure-hosted OpenAI models',
    credential_type_id: 'ctype-llm',
    inputs: { api_key: '$encrypted$' },
    enabled: true,
    created_at: '2025-09-16T11:00:00Z',
    updated_at: '2025-09-16T11:00:00Z',
    created_by: { id: '550e8400-e29b-41d4-a716-446655440001', name: 'user-001' },
    labels: {},
    deleted_at: null,
    deleted_by: null,
    project_id: 'p-001',
  },
]
