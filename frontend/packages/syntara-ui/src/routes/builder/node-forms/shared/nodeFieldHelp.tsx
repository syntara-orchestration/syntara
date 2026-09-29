import { createFieldHelp } from '../../../../components/createFieldHelp'
import { APPROVER_GROUPS_LABEL, APPROVER_USERS_LABEL } from '../approverConstants'

import * as T from './nodeFieldHelpText'

/** Pre-built labelHelp elements for node forms. */
export const nodeHelp = {
  // Settings
  onFailureBehavior: createFieldHelp('On failure behavior', T.SETTINGS_CONTINUE_ON_FAILURE_HELP),
  timeout: createFieldHelp('Timeout', T.SETTINGS_TIMEOUT_HELP),
  retryToggle: createFieldHelp('Override retry policy', T.SETTINGS_RETRY_TOGGLE_HELP),
  maxRetries: createFieldHelp('Max retries', T.SETTINGS_MAX_RETRIES_HELP),
  initialInterval: createFieldHelp('Initial interval', T.SETTINGS_INITIAL_INTERVAL_HELP),
  maxInterval: createFieldHelp('Max interval', T.SETTINGS_MAX_INTERVAL_HELP),
  backoffCoefficient: createFieldHelp('Backoff coefficient', T.SETTINGS_BACKOFF_HELP),

  // Script / HTTP
  scriptLanguage: createFieldHelp('Language', T.SCRIPT_LANGUAGE_HELP),
  scriptCode: createFieldHelp('Script', T.SCRIPT_CODE_HELP),
  scriptEnvVars: createFieldHelp('Environment variables', T.SCRIPT_ENV_VARS_HELP),
  httpMethod: createFieldHelp('HTTP Method', T.HTTP_METHOD_HELP),
  httpUrl: createFieldHelp('URL', T.HTTP_URL_HELP),
  httpHeaders: createFieldHelp('Headers', T.HTTP_HEADERS_HELP),
  httpBody: createFieldHelp('Body', T.HTTP_BODY_HELP),

  // AI agent
  aiModel: createFieldHelp('Model', T.AI_MODEL_HELP),
  aiCredential: createFieldHelp('Credential', T.AI_CREDENTIAL_HELP),
  aiPrompt: createFieldHelp('Prompt', T.AI_PROMPT_HELP),
  aiTools: createFieldHelp('Tools', T.AI_TOOLS_HELP),
  aiConnections: createFieldHelp('Connections', T.AI_INTEGRATION_CONNECTIONS_HELP),
  aiResponseSchema: createFieldHelp('Response schema', T.AI_RESPONSE_SCHEMA_HELP),
  aiContext: createFieldHelp('Context file upload', T.AI_CONTEXT_HELP),

  // Approval
  approverUsers: createFieldHelp(APPROVER_USERS_LABEL, T.APPROVAL_APPROVER_USERS_HELP),
  approverGroups: createFieldHelp(APPROVER_GROUPS_LABEL, T.APPROVAL_APPROVER_GROUPS_HELP),
  approvalMessage: createFieldHelp('Message', T.APPROVAL_MESSAGE_HELP),
  approvalFallback: createFieldHelp('Fallback decision', T.APPROVAL_FALLBACK_DECISION_HELP),
  approvalDecisionWindow: createFieldHelp('Decision window', T.APPROVAL_DECISION_WINDOW_HELP),

  // Loop / logic
  loopItems: createFieldHelp('Items expression', T.LOOP_ITEMS_HELP),
  loopItemVariable: createFieldHelp('Item variable', T.LOOP_ITEM_VARIABLE_HELP),
  loopIndexVariable: createFieldHelp('Index variable', T.LOOP_INDEX_VARIABLE_HELP),
  maxIterations: createFieldHelp('Max iterations', T.LOOP_MAX_ITERATIONS_HELP),
  convergeWaitDuration: createFieldHelp('Wait duration', T.CONVERGE_WAIT_DURATION_HELP),
  switchPathName: createFieldHelp('Path name', T.SWITCH_PATH_NAME_HELP),
  switchFallback: createFieldHelp('Fallback path', T.SWITCH_FALLBACK_HELP),
  waitDuration: createFieldHelp('Wait duration', T.WAIT_DURATION_HELP),

  // Triggers
  manualInputSchema: createFieldHelp('Input schema', T.MANUAL_INPUT_SCHEMA_HELP),
  edaHttpMethod: createFieldHelp('HTTP method', T.EDA_HTTP_METHOD_HELP),
  edaUrl: createFieldHelp('URL', T.EDA_URL_HELP),
  edaInputSchema: createFieldHelp('JSON schema validation', T.EDA_INPUT_SCHEMA_HELP),

  // AAP
  aapOrganization: createFieldHelp('Organization', T.AAP_ORGANIZATION_HELP),
  aapJobTemplate: createFieldHelp('Job template', T.AAP_JOB_TEMPLATE_HELP),
  aapWorkflowTemplate: createFieldHelp('Workflow template', T.AAP_WORKFLOW_TEMPLATE_HELP),
  aapUseExpressions: createFieldHelp('Use input variables', T.AAP_USE_EXPRESSIONS_HELP),
  aapJobType: createFieldHelp('Run type', T.AAP_JOB_TYPE_HELP),
  aapInventory: createFieldHelp('Inventory', T.AAP_INVENTORY_HELP),
  aapJobCredentials: createFieldHelp('Credentials', T.AAP_JOB_CREDENTIALS_HELP),
  aapExecutionEnvironment: createFieldHelp('Execution environment', T.AAP_EXECUTION_ENVIRONMENT_HELP),
  aapLabels: createFieldHelp('Labels', T.AAP_LABELS_HELP),
  aapVerbosity: createFieldHelp('Verbosity', T.AAP_VERBOSITY_HELP),
  aapForks: createFieldHelp('Forks', T.AAP_FORKS_HELP),
  aapJobSliceCount: createFieldHelp('Job slices', T.AAP_JOB_SLICE_COUNT_HELP),
  aapDiffMode: createFieldHelp('Show changes', T.AAP_DIFF_MODE_HELP),
  aapInstanceGroup: createFieldHelp('Instance group', T.AAP_INSTANCE_GROUP_HELP),
  aapTags: createFieldHelp('Job tags', T.AAP_TAGS_HELP),
  aapSkipTags: createFieldHelp('Skip tags', T.AAP_SKIP_TAGS_HELP),
  aapLimit: createFieldHelp('Limit', T.AAP_LIMIT_HELP),
  aapExtraVars: createFieldHelp('Extra variables', T.AAP_EXTRA_VARS_HELP),
  aapScmBranch: createFieldHelp('Source control branch', T.AAP_SCM_BRANCH_HELP),
  aapWfTags: createFieldHelp('Job tags', T.AAP_WF_TAGS_HELP),
  aapWfSkipTags: createFieldHelp('Skip tags', T.AAP_WF_SKIP_TAGS_HELP),
} as const
