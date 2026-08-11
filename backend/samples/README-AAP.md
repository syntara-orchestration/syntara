# AAP Job Template Workflow Sample

This directory contains sample files for testing the AAP (Ansible Automation Platform) Job Template executor in Nexus workflows.

## Files

- **playbooks/test-aap-parameters.yml** - Ansible playbook that demonstrates all AAP parameters
- **workflow-aap-job-template.yaml** - Nexus workflow that executes the AAP job template

## Setup Instructions

### 1. Configure AAP Connection

Add the following to your `.env` file:

```bash
# AAP URL
APP_AAP_BASE_URL=https://your-aap.example.com

# Authentication (choose one method)
# Option A: Token authentication (recommended)
APP_AAP_TOKEN=your_api_token_here

# Option B: Username/password authentication
# APP_AAP_USERNAME=your_username_here
# APP_AAP_PASSWORD=your_password_here

# Optional: Customize timeouts and polling
APP_AAP_TIMEOUT_SECONDS=3600
APP_AAP_POLL_INTERVAL_SECONDS=5.0
```

### 2. Create Job Template in AAP

1. **Upload the playbook** to your AAP Controller:
   - Copy `playbooks/test-aap-parameters.yml` to your project repository
   - Sync the project in AAP

2. **Create a Job Template**:
   - Name: `Nexus Test - AAP Parameters`
   - Project: Your project containing the playbook
   - Playbook: `test-aap-parameters.yml`
   - Inventory: Select a test inventory with at least one host
   - Credentials: Select appropriate credentials for the target hosts
   - Options: Check "Enable Provisioning Callbacks" if desired

3. **Note the Job Template ID**:
   - Go to Templates → Your template
   - The ID is in the URL: `https://aap.example.com/#/templates/job_template/42` (ID is 42)
   - Or use the AAP API: `curl https://aap.example.com/api/v2/job_templates/ -H "Authorization: Bearer $TOKEN"`

### 3. Execute the Workflow

#### Using the Nexus API

```bash
# Step 1: Read the workflow YAML file and create the workflow
WORKFLOW_CONTENT=$(cat samples/workflow-aap-job-template.yaml)
WORKFLOW_RESPONSE=$(curl -X POST http://localhost:8000/api/v1/workflows \
  -H "Content-Type: application/json" \
  -d "{
    \"definition\": $(echo "$WORKFLOW_CONTENT" | jq -Rs .)
  }")

# Extract workflow ID from response
WORKFLOW_ID=$(echo $WORKFLOW_RESPONSE | jq -r '.id')

# Step 2: Create an execution using the workflow ID
curl -X POST http://localhost:8000/api/v1/executions \
  -H "Content-Type: application/json" \
  -d "{
    \"workflow_id\": \"$WORKFLOW_ID\",
    \"inputs\": {
      \"job_template_id\": 42,
      \"app_name\": \"myapp\",
      \"app_version\": \"1.0.0\",
      \"deployment_env\": \"development\",
      \"operation\": \"status\"
    }
  }"
```
You can update samples/workflow-aap-job-template.yaml to use job template name and organization to identify the job template instead of reference by id

## Test Scenarios

### Scenario 1: Basic Execution (All Tasks)
```json
{
  "job_template_id": 42,
  "app_name": "myapp",
  "app_version": "1.0.0",
  "deployment_env": "development"
}
```

### Scenario 2: Monitoring Only
```json
{
  "job_template_id": 42,
  "tags": "monitoring"
}
```
Runs only tasks tagged with `monitoring` (disk, healthcheck).

### Scenario 3: System Info Only
```json
{
  "job_template_id": 42,
  "tags": "system,info"
}
```

### Scenario 4: Skip Deployment
```json
{
  "job_template_id": 42,
  "skip_tags": "deploy,backup"
}
```

### Scenario 5: Limit to Specific Hosts
```json
{
  "job_template_id": 42,
  "limit": "webservers"
}
```
or
```json
{
  "job_template_id": 42,
  "limit": "host1,host2,host3"
}
```

### Scenario 6: High Verbosity for Debugging
```json
{
  "job_template_id": 42,
  "verbosity": 3
}
```
Verbosity levels: 0 (normal), 1 (-v), 2 (-vv), 3 (-vvv), 4 (-vvvv), 5 (-vvvvv)

### Scenario 7: Production Deployment
```json
{
  "job_template_id": 42,
  "app_name": "prod-app",
  "app_version": "2.1.5",
  "deployment_env": "production",
  "operation": "deploy",
  "inventory": "production-servers",
  "limit": "web-prod-*",
  "tags": "deploy,config,healthcheck",
  "verbosity": 1
}
```

### Scenario 8: Custom Message
```json
{
  "job_template_id": 42,
  "custom_message": "Testing from CI/CD Pipeline - Build #1234",
  "tags": "custom,info"
}
```

### Scenario 9: Test with Different Credential
```json
{
  "job_template_id": 42,
  "job_credentials": [15],
  "tags": "credentials"
}
```
Uses a different AAP credential (ID 15) instead of the Job Template's default. The `job_credentials` parameter accepts an array of AAP credential IDs. Use `--tags credentials` to verify which user the job runs as.

## Playbook Features

The test playbook includes tasks organized by tags:

### Tag Categories

| Tag | Tasks | Purpose |
|-----|-------|---------|
| `always` | Info, Summary | Always run regardless of tag selection |
| `info` | Basic info, System info | Display general information |
| `system` | System info | OS, distribution, architecture details |
| `disk` | Disk usage | Check disk space |
| `monitoring` | Disk, Healthcheck | All monitoring tasks |
| `deploy` | Deployment simulation | Simulate app deployment |
| `config` | Configuration check | Check configuration status |
| `backup` | Backup simulation | Simulate backup operation |
| `healthcheck` | Health check | Application health status |
| `custom` | Custom message | Display custom message |
| `credentials` | Credential check | Shows which user/credential is being used |
| `fail_test` | Intentional failure | Test error handling (use with `--tags fail_test`) |

### Extra Variables

The playbook accepts these extra variables:

- `app_name` (default: "test-app") - Application name
- `app_version` (default: "1.0.0") - Version to deploy
- `deployment_env` (default: "development") - Target environment (note: renamed from 'environment' as that's reserved in Ansible)
- `operation` (default: "status") - Operation: deploy, config, status, backup
- `custom_message` (default: "Hello from Nexus Workflow!") - Custom message

## Troubleshooting

### Connection Issues

```bash
# Test AAP connectivity
curl -k https://your-aap.example.com/api/v2/ping \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Check Job Template Exists

```bash
# List all job templates
curl -k https://your-aap.example.com/api/v2/job_templates/ \
  -H "Authorization: Bearer YOUR_TOKEN"

# Get specific template
curl -k https://your-aap.example.com/api/v2/job_templates/42/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### View Job Output in AAP

1. Go to AAP UI → Jobs
2. Find the job by ID (returned in workflow output)
3. View full output, events, and artifacts

### Enable Debug Logging

In Nexus, set log level to DEBUG to see detailed AAP activity logs:

```bash
APP_FALLBACK_LOG_LEVEL=DEBUG
```

## Advanced Usage

### Testing with Different Credentials

AAP manages credentials centrally. To test a different credential:

#### 1. Find Credential IDs in AAP UI or API

**Via UI:**
- Go to Resources → Credentials
- Note the credential ID (shown in the URL or details)

**Via API:**
```bash
# List all credentials
curl -k https://aap.example.com/api/v2/credentials/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### 2. Use Credential in Workflow

```json
{
  "job_template_id": 42,
  "job_credentials": [15],
  "tags": "credentials"
}
```

This overrides the Job Template's default credential with credential ID 15.

#### 3. Verify Which User It Runs As

The `credentials` tag will show:
```
TASK [Display credential information]
ok: [hostname] => {
    "msg": [
        ">>> Credential Check",
        "Running as user: deploy_user",
        "On host: web-server-01",
        "Connection: ssh"
    ]
}
```

This confirms which credential/user account was used by AAP.

### Override Inventory

```json
{
  "job_template_id": 42,
  "inventory": "my-custom-inventory"
}
```
or by ID:
```json
{
  "job_template_id": 42,
  "inventory": "5"
}
```

## Next Steps

1. **Customize the playbook** for your actual use cases
2. **Create multiple job templates** in AAP for different purposes
3. **Build workflows** that chain multiple AAP job templates
4. **Use conditional logic** to run different templates based on results
5. **Integrate with other executors** (API, script, agentic) in the same workflow

## References

- [AAP Job Templates Documentation](https://docs.ansible.com/automation-controller/latest/html/userguide/job_templates.html)
- [Nexus Workflow Examples](../tests/integration/workflow/examples/README.md)
- [AAP REST API Guide](https://docs.ansible.com/automation-controller/latest/html/controllerapi/api_ref.html)
