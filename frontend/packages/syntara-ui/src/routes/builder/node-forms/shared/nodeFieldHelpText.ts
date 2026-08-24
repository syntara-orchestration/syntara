/** Help popover body text for workflow builder node form fields. */

export const SETTINGS_CONTINUE_ON_FAILURE_HELP =
  'Controls what happens when this step fails. System default uses the administrator setting. Continue on failure marks the step as failed but lets downstream steps continue. Stop workflow or branch on failure halts execution at this step.'

export const SETTINGS_TIMEOUT_HELP =
  'The maximum duration this step can run before it is marked as failed. If the step exceeds the limit, it is stopped and a timeout error is recorded. If you do not set a value, the step uses the global default timeout.'

export const SETTINGS_RETRY_TOGGLE_HELP =
  'When enabled, you can customize the retry behavior for this step. When disabled, the system default retry policy applies. Retries are available for HTTP request, AAP job template, and AAP workflow template steps.'

export const SETTINGS_MAX_RETRIES_HELP =
  'The number of retry attempts after the initial attempt. Set to 0 to disable retries. For non-idempotent operations such as POST or DELETE requests, disable retries to prevent duplicate side effects.'

export const SETTINGS_INITIAL_INTERVAL_HELP = 'The delay, in seconds, before the first retry.'

export const SETTINGS_MAX_INTERVAL_HELP = 'The maximum delay, in seconds, between retries.'

export const SETTINGS_BACKOFF_HELP =
  'The multiplier applied to the retry interval after each attempt. Use 1.0 for a fixed interval, or greater than 1.0 for exponential backoff.'

export const SCRIPT_LANGUAGE_HELP =
  'Select the scripting language for this step. Python and Bash are supported. The script runs in a sandboxed environment with access to workflow context variables.'

export const SCRIPT_CODE_HELP =
  'Enter the script code to execute. Access input data through the context object. The script must return a value that downstream steps can reference.'

export const SCRIPT_ENV_VARS_HELP =
  "Define input variables as key-value pairs that are passed to the script's execution context. Use expressions like ${previous_step.result} to pass data from earlier steps."

export const HTTP_METHOD_HELP =
  'Select the HTTP method for the request: GET retrieves data; POST creates data; PUT replaces data; PATCH updates data partially; DELETE removes data.'

export const HTTP_URL_HELP =
  'Enter the full URL for the HTTP request. You can include expressions like ${previous_step.endpoint} to build the URL dynamically.'

export const HTTP_HEADERS_HELP =
  'Add custom HTTP headers as key-value pairs. Use headers to pass metadata such as Content-Type, Accept, or custom API headers.'

export const HTTP_BODY_HELP =
  'Enter the request body as JSON or text. Used with POST, PUT, and PATCH methods. You can include expressions to insert dynamic values from previous steps.'

export const AI_MODEL_HELP =
  'Select the large language model (LLM) to use for this task agent step. Models are provided by integrations configured by your administrator.'

export const AI_CREDENTIAL_HELP =
  "The credential used to authenticate with the selected model's API. This is resolved automatically from the integration configuration."

export const AI_PROMPT_HELP =
  'Enter natural language instructions describing what the agent should do. Be specific about what to analyze or produce, the response format, and any constraints or boundaries.'

export const AI_TOOLS_HELP =
  'Select tools the agent can invoke during execution. Tools provide the agent with capabilities such as querying APIs, running searches, or executing commands.'

export const AI_INTEGRATION_CONNECTIONS_HELP =
  'Select integrations this agent can access. Connections provide access to external systems like Ansible Automation Platform or other configured services.'

export const AI_RESPONSE_SCHEMA_HELP =
  "Define a JSON schema for the agent's response. When set, the agent structures its final answer to match this schema, making the output predictable for downstream steps."

export const AI_CONTEXT_HELP =
  'Upload files to provide additional context for the agent. The agent can reference this content when generating its response.'

export const APPROVAL_APPROVER_USERS_HELP =
  'Select the users who can approve this request. Only users with the approval:decide permission appear in this list. If you do not specify any approver users or groups, any user with the approval:decide permission can approve the request.'

export const APPROVAL_APPROVER_GROUPS_HELP =
  'Select the groups whose members can approve this request. If you do not specify any approver users or groups, any user with the approval:decide permission can approve the request. Note: If you select a group with no members who have the approval:decide permission, no one from that group will be able to approve the request.'

export const APPROVAL_MESSAGE_HELP =
  'Enter a message for the approver describing the request. This message appears as part of the approval request when an approver reviews it.'

export const APPROVAL_FALLBACK_DECISION_HELP =
  'Select how to resolve the approval if the decision window expires: Reject (default) follows the rejected path; Approve follows the approved path. Requires Continue on failure to be enabled on the Settings tab — when the workflow is set to stop on failure, this setting has no effect.'

export const APPROVAL_FALLBACK_ENABLED_HELPER =
  'Determines the routing path when the approval cannot complete (decision window expired or send failure).'

export const APPROVAL_FALLBACK_DISABLED_SYSTEM_DEFAULT =
  'On failure behavior is System default (stop on failure), so this fallback will not be used.'

export const APPROVAL_FALLBACK_DISABLED_EXPLICIT_STOP =
  'On failure behavior is set to stop the workflow, so this fallback will not be used.'

export const APPROVAL_FALLBACK_ENABLE_LINK = 'Enable continue on failure'

export const APPROVAL_DECISION_WINDOW_HELP =
  'Enter the amount of time that approvers have to respond. If no approver responds within this window, the request expires and the approval step fails. Falls back to the system default if not set.'

export const LOOP_ITEMS_HELP =
  'Enter an expression that resolves to a list of items, for example ${previous_step.server_list}. The loop will iterate once for each item in the list.'

export const LOOP_ITEM_VARIABLE_HELP =
  'Enter a custom variable name for the current item in each iteration. The default is "item". Steps inside the loop body reference this value as ${loop.item}.'

export const LOOP_INDEX_VARIABLE_HELP =
  'Enter a custom variable name for the current iteration index. The default is "index". Steps inside the loop body reference this value as ${loop.index}.'

export const LOOP_MAX_ITERATIONS_HELP =
  'Set a maximum number of times the loop can repeat. This acts as a safety limit to prevent runaway loops if the exit condition is never met. If you do not set a value, the system applies a default limit.'

export const LOOP_WHILE_CONDITION_HELP =
  'Define the condition that determines whether the loop continues. After each iteration, the loop evaluates this condition and continues while it is true. Because the loop body always runs at least once before the first condition check, the condition must reference output from a step inside the loop body. You can use the visual expression builder or write a custom expression.'

export const CONVERGE_WAIT_DURATION_HELP =
  'Set a timeout to prevent the converge step from waiting indefinitely. The clock starts when the first step in the parallel section is scheduled. When it expires, the converge step fails and in-flight steps are reported as skipped.'

export const SWITCH_PATH_NAME_HELP =
  'Enter a descriptive name for this path. The name appears on the canvas and helps identify the branch during workflow design and execution monitoring.'

export const SWITCH_FALLBACK_HELP =
  'When no path expression evaluates to true, execution follows the fallback path. If no steps are connected to the fallback output, the workflow branch ends.'

export const WAIT_DURATION_HELP =
  'Enter the amount of time to pause execution, in days, hours, minutes, and seconds. A platform administrator can set a global maximum (default 30 days) — if this value exceeds it, the step fails at execution time.'

export const EDA_HTTP_METHOD_HELP =
  'The Event-Driven Ansible trigger accepts POST requests only. This value cannot be changed. POST is the industry standard for webhooks as it allows for large data payloads to be transmitted securely in the request body. If your EDA controller attempts to call this URL using a different method, it will receive a 405 Method Not Allowed error.'

export const EDA_URL_HELP =
  'This is the unique endpoint URL for this trigger. Event-Driven Ansible triggers use a different URL path (/api/v1/webhooks/eda/) than standard webhooks. Use this exact URL when configuring the rulebook activation in the webhook settings of your Event-Driven Ansible controller. Use the copy button to capture the full URL.'

export const EDA_INPUT_SCHEMA_HELP =
  'Define a structure that all incoming event payloads must follow. This acts as a quality gate for your workflow. If incoming data does not match the schema, the trigger rejects the request with a 400 Bad Request error and the workflow will not run. The default schema is a pass-through that allows all data — edit the properties block to enforce specific fields.'

export const MANUAL_INPUT_SCHEMA_HELP =
  'Define an input schema to allow users to input data when running the workflow manually. Use this to simulate or test workflow runs with specific parameters. Click Insert example to populate the field with a template schema.'

export const AAP_ORGANIZATION_HELP =
  'Select the Ansible Automation Platform organization that contains the job template you want to launch.'

export const AAP_JOB_TEMPLATE_HELP =
  'Select the AAP job template to launch when this step executes. The template determines which playbook runs and its default configuration.'

export const AAP_USE_EXPRESSIONS_HELP =
  'Toggle on to enter organization and template names as dynamic expressions instead of selecting from dropdowns. Use this when the target template is determined at runtime by an upstream step.'

export const AAP_JOB_TYPE_HELP =
  "Select the run type: Run executes the playbook normally; Check (Dry Run) validates the playbook without making changes. This overrides the template's default run type."

export const AAP_INVENTORY_HELP =
  'Override the default inventory for this job run. Select from inventories available in the selected organization.'

export const AAP_JOB_CREDENTIALS_HELP =
  'Override or add credentials for this job run. Select from credentials available in the selected organization.'

export const AAP_EXECUTION_ENVIRONMENT_HELP =
  'Override the execution environment for this job run. Execution environments are container images that include the dependencies needed to run your playbooks.'

export const AAP_LABELS_HELP =
  'Select or create labels for this job run. Labels help organize and filter job runs in AAP.'

export const AAP_VERBOSITY_HELP =
  'Control the detail level of the job output. Higher verbosity provides more information for debugging but increases log volume.'

export const AAP_FORKS_HELP =
  'Override the number of parallel processes to use for this job run. Higher values speed up execution across many hosts but increase resource usage.'

export const AAP_JOB_SLICE_COUNT_HELP =
  'Override the number of slices to divide this job into. Job slicing distributes the inventory across multiple job runs for parallel execution.'

export const AAP_DIFF_MODE_HELP =
  'When enabled, the job output includes a diff of changes made to managed hosts. Useful for reviewing what a playbook would change before applying.'

export const AAP_INSTANCE_GROUP_HELP =
  'Override the instance group for this job run. Instance groups determine which AAP execution nodes process the job.'

export const AAP_TAGS_HELP =
  'Enter tags to limit which tasks in the playbook are executed. Only tasks tagged with the specified values will run.'

export const AAP_SKIP_TAGS_HELP =
  'Enter tags to exclude specific tasks from the playbook run. Tasks tagged with the specified values will be skipped.'

export const AAP_LIMIT_HELP =
  'Restrict the job to a subset of the inventory hosts. Enter a host pattern to target specific hosts or groups.'

export const AAP_EXTRA_VARS_HELP =
  'Override or add variables for this job run as JSON or YAML. These variables take highest precedence and override any variables defined in the template.'

export const AAP_WORKFLOW_TEMPLATE_HELP =
  'Select the AAP workflow template to launch when this step executes. The template determines which workflow of playbooks and jobs runs.'

export const AAP_SCM_BRANCH_HELP =
  'Override the source control branch for this workflow run. This determines which version of the project is used.'

export const AAP_WF_TAGS_HELP = 'Enter tags to limit which tasks in the workflow are executed.'

export const AAP_WF_SKIP_TAGS_HELP = 'Enter tags to exclude specific tasks from the workflow run.'
