# Manual form-prompt options walkthrough

This copy-and-paste guide creates one workflow with static and dynamic dropdown/multi-select fields. Dynamic expressions must resolve to arrays of option records; flat scalar lists such as `[10, 20]` are rejected. It checks the resolved options, submits invalid and valid answers, and exercises malformed upstream data and invalid authored definitions.

The manual trigger supplies the upstream values, so the dynamic options test does not need an external HTTP service or script execution. Keep one Bash terminal open so the variables set in one step are available to the next. The workflow and executions remain in the database for inspection.

Before starting, make sure the API, Temporal service and workflow worker, and PostgreSQL are running. The login must be allowed to create and run workflows in PROJECT_ID.

## 1. Set the API, project, and login settings

Run this from the repository root. Use a project where your user has permission to create and run workflows.

```bash
export API_BASE_URL="https://localhost:8000/api/v1"
export PROJECT_ID="ce3582d3-ddd3-4499-8172-a77289e6cf1c" # Edit for another project.
export LOGIN_USERNAME="admin"
export ADMIN_PASSWORD_FILE="backend/.secrets/admin-password"
export WALKTHROUGH_DIR="/tmp/form-prompt-options-walkthrough"
mkdir -p "$WALKTHROUGH_DIR"
: "${PROJECT_ID:?Set PROJECT_ID to a project UUID}"
```

The local dev server uses HTTPS with a self-signed certificate, so the commands below include --insecure. Remove that option when using a trusted certificate.

## 2. Log in and save the bearer token

If you already have an API token, set API_TOKEN yourself and skip this entire section.

```bash
jq -n --arg username "$LOGIN_USERNAME" --rawfile password "$ADMIN_PASSWORD_FILE" '{username: $username, password: ($password | rtrimstr("\n") | rtrimstr("\r"))}' > "$WALKTHROUGH_DIR/login.json"
```

```bash
curl --silent --show-error --insecure --request POST "$API_BASE_URL/auth/login" --header 'Content-Type: application/json' --data-binary "@$WALKTHROUGH_DIR/login.json" --output "$WALKTHROUGH_DIR/login-response.json" --write-out '\nHTTP %{http_code}\n'
jq . "$WALKTHROUGH_DIR/login-response.json"
```

```bash
export API_TOKEN="$(jq -er '.access_token' "$WALKTHROUGH_DIR/login-response.json")"
```

## 3. Build a workflow with static and dynamic options

The workflow has a static dropdown (environment), a static multi-select (risk_tags), and two record-backed dynamic fields (region_id and team_ids). Each dynamic field must specify `label_key` and `value_key`; every upstream record needs a string label and scalar value at those keys. The manual trigger declares the input properties; `region_records` is intentionally left unconstrained so negative runs can exercise the runtime resolver.

```bash
export WORKFLOW_NAME="form-options-walkthrough-$(date -u +%Y%m%dT%H%M%SZ)"
jq -n --arg name "$WORKFLOW_NAME" --arg project_id "$PROJECT_ID" '{
  name: $name,
  description: "Manual walkthrough for static and dynamic form options",
  project_id: $project_id,
  workflow_definition: {
    schema_version: "2.0.0",
    name: $name,
    description: "Exercises static options and options resolved from trigger output.",
    triggers: [{
      id: "trigger_manual",
      type: "manual_trigger",
      parameters: {
        input_schema: {
          type: "object",
          properties: {
            region_records: {description: "Upstream records for the dynamic region dropdown."},
            team_ids: {
              type: "array",
              items: {
                type: "object",
                required: ["display_label", "value"],
                properties: {
                  display_label: {type: "string"},
                  value: {type: "integer"}
                },
                additionalProperties: false
              }
            }
          },
          required: ["region_records", "team_ids"],
          additionalProperties: false
        }
      }
    }],
    nodes: [
      {
        id: "collect_options",
        name: "Choose deployment options",
        type: "form_prompt",
        settings: {continue_on_failure: true},
        parameters: {
          message: "Choose the deployment options.",
          response_window: 600,
          fallback_decision: "fallback",
          form_definition: {fields: [
            {
              value_name: "environment",
              type: "dropdown",
              label: "Environment",
              required: true,
              options: {source: "static", values: [
                {display_label: "Development", value: "development"},
                {display_label: "Staging", value: "staging"}
              ]}
            },
            {
              value_name: "risk_tags",
              type: "multi_select",
              label: "Risk tags",
              options: {source: "static", values: [
                {display_label: "Security review", value: "security-review"},
                {display_label: "Customer impact", value: "customer-impact"}
              ]}
            },
            {
              value_name: "region_id",
              type: "dropdown",
              label: "Region",
              required: true,
              options: {
                source: "dynamic",
                expression: "${trigger.region_records}",
                label_key: "name",
                value_key: "id"
              }
            },
            {
              value_name: "team_ids",
              type: "multi_select",
              label: "Teams",
              options: {
                source: "dynamic",
                expression: "${trigger.team_ids}",
                label_key: "display_label",
                value_key: "value"
              }
            }
          ]}
        }
      },
      {id: "after_submit", type: "wait", parameters: {duration: 1}},
      {id: "after_fallback", type: "wait", parameters: {duration: 1}}
    ],
    edges: [
      {from: "trigger_manual", to: "collect_options"},
      {from: "collect_options", from_port: "submitted", to: "after_submit"},
      {from: "collect_options", from_port: "fallback", to: "after_fallback"}
    ]
  }
}' > "$WALKTHROUGH_DIR/workflow.json"
jq . "$WALKTHROUGH_DIR/workflow.json"
```

## 4. Check invalid authored definitions

Workflow drafts can be saved with invalid definitions. Each invalid draft below should return HTTP 201 with `has_validation_issues: true` and a `validation_result` containing the form field error. Verification through `/workflows/validate` should return HTTP 422, and publishing an invalid draft should return HTTP 409.

Restart the backend after updating workflow JSON schemas before running these checks; the validator caches schemas for the lifetime of the process.

Static option values must be strings. Change one to a number and save the draft:

```bash
BAD_STATIC_NAME="$WORKFLOW_NAME-bad-static-$(date -u +%Y%m%dT%H%M%SZ)"
jq --arg name "$BAD_STATIC_NAME" '.name = $name | .workflow_definition.name = $name | .workflow_definition.nodes[0].parameters.form_definition.fields[0].options.values[0].value = 7' "$WALKTHROUGH_DIR/workflow.json" > "$WALKTHROUGH_DIR/bad-static.json"
curl --silent --show-error --insecure --request POST "$API_BASE_URL/workflows" --header "Authorization: Bearer $API_TOKEN" --header 'Content-Type: application/json' --data-binary "@$WALKTHROUGH_DIR/bad-static.json" --output "$WALKTHROUGH_DIR/bad-static-response.json" --write-out '\nHTTP %{http_code}\n'
jq . "$WALKTHROUGH_DIR/bad-static-response.json"
```

Expect a finding on `collect_options` at `parameters.form_definition.fields.0.options.values.0.value`, stating that `7` is not a string. Verify the same definition; this request should return HTTP 422:

```bash
jq '{workflow_definition}' "$WALKTHROUGH_DIR/bad-static.json" > "$WALKTHROUGH_DIR/bad-static-validate.json"
curl --silent --show-error --insecure --request POST "$API_BASE_URL/workflows/validate" --header "Authorization: Bearer $API_TOKEN" --header 'Content-Type: application/json' --data-binary "@$WALKTHROUGH_DIR/bad-static-validate.json" --output "$WALKTHROUGH_DIR/bad-static-validate-response.json" --write-out '\nHTTP %{http_code}\n'
jq . "$WALKTHROUGH_DIR/bad-static-validate-response.json"
```

Dynamic option definitions must include non-empty `label_key` and `value_key` fields. Remove the label key from the region field and save the draft:

```bash
BAD_DYNAMIC_KEYS_NAME="$WORKFLOW_NAME-bad-dynamic-keys-$(date -u +%Y%m%dT%H%M%SZ)"
jq --arg name "$BAD_DYNAMIC_KEYS_NAME" '.name = $name | .workflow_definition.name = $name | del(.workflow_definition.nodes[0].parameters.form_definition.fields[2].options.label_key)' "$WALKTHROUGH_DIR/workflow.json" > "$WALKTHROUGH_DIR/bad-dynamic-keys.json"
curl --silent --show-error --insecure --request POST "$API_BASE_URL/workflows" --header "Authorization: Bearer $API_TOKEN" --header 'Content-Type: application/json' --data-binary "@$WALKTHROUGH_DIR/bad-dynamic-keys.json" --output "$WALKTHROUGH_DIR/bad-dynamic-keys-response.json" --write-out '\nHTTP %{http_code}\n'
jq . "$WALKTHROUGH_DIR/bad-dynamic-keys-response.json"
```

Expect HTTP 201 with a validation finding on `collect_options` at `parameters.form_definition.fields.2.options.label_key`. The invalid draft is saved with the finding, while `/workflows/validate` returns HTTP 422 and publishing is blocked:

```bash
jq '{workflow_definition}' "$WALKTHROUGH_DIR/bad-dynamic-keys.json" > "$WALKTHROUGH_DIR/bad-dynamic-keys-validate.json"
curl --silent --show-error --insecure --request POST "$API_BASE_URL/workflows/validate" --header "Authorization: Bearer $API_TOKEN" --header 'Content-Type: application/json' --data-binary "@$WALKTHROUGH_DIR/bad-dynamic-keys-validate.json" --output "$WALKTHROUGH_DIR/bad-dynamic-keys-validate-response.json" --write-out '\nHTTP %{http_code}\n'
jq . "$WALKTHROUGH_DIR/bad-dynamic-keys-validate-response.json"
```

The workflow engine owns the `dynamic_resolved` source. Save a draft with an author-supplied option using that source:

```bash
BAD_RESOLVED_NAME="$WORKFLOW_NAME-bad-resolved-$(date -u +%Y%m%dT%H%M%SZ)"
jq --arg name "$BAD_RESOLVED_NAME" '.name = $name | .workflow_definition.name = $name | .workflow_definition.nodes[0].parameters.form_definition.fields[2].options = {source: "dynamic_resolved", values: [{display_label: "US East", value: 1}]}' "$WALKTHROUGH_DIR/workflow.json" > "$WALKTHROUGH_DIR/bad-resolved.json"
curl --silent --show-error --insecure --request POST "$API_BASE_URL/workflows" --header "Authorization: Bearer $API_TOKEN" --header 'Content-Type: application/json' --data-binary "@$WALKTHROUGH_DIR/bad-resolved.json" --output "$WALKTHROUGH_DIR/bad-resolved-response.json" --write-out '\nHTTP %{http_code}\n'
jq . "$WALKTHROUGH_DIR/bad-resolved-response.json"
```

Expect HTTP 201 with a finding at `parameters.form_definition.fields.2.options.source`, stating that `dynamic_resolved` is not one of the allowed values (`static`, `dynamic`). Verify the definition; this request should return HTTP 422:

```bash
jq '{workflow_definition}' "$WALKTHROUGH_DIR/bad-resolved.json" > "$WALKTHROUGH_DIR/bad-resolved-validate.json"
curl --silent --show-error --insecure --request POST "$API_BASE_URL/workflows/validate" --header "Authorization: Bearer $API_TOKEN" --header 'Content-Type: application/json' --data-binary "@$WALKTHROUGH_DIR/bad-resolved-validate.json" --output "$WALKTHROUGH_DIR/bad-resolved-validate-response.json" --write-out '\nHTTP %{http_code}\n'
jq . "$WALKTHROUGH_DIR/bad-resolved-validate-response.json"
```

Finally, try publishing that invalid draft. It should return HTTP 409 with `WORKFLOW_PUBLISH_VALIDATION_ERROR` and the same source finding:

```bash
BAD_RESOLVED_WORKFLOW_ID="$(jq -er '.id' "$WALKTHROUGH_DIR/bad-resolved-response.json")"
BAD_RESOLVED_WORKFLOW_VERSION="$(jq -er '.current_version' "$WALKTHROUGH_DIR/bad-resolved-response.json")"
curl --silent --show-error --insecure --request POST "$API_BASE_URL/workflows/$BAD_RESOLVED_WORKFLOW_ID/versions/$BAD_RESOLVED_WORKFLOW_VERSION/publish" --header "Authorization: Bearer $API_TOKEN" --header 'Content-Type: application/json' --data '{}' --output "$WALKTHROUGH_DIR/bad-resolved-publish-response.json" --write-out '\nHTTP %{http_code}\n'
jq . "$WALKTHROUGH_DIR/bad-resolved-publish-response.json"
```

## 5. Create and publish the valid workflow

```bash
curl --silent --show-error --insecure --request POST "$API_BASE_URL/workflows" --header "Authorization: Bearer $API_TOKEN" --header 'Content-Type: application/json' --data-binary "@$WALKTHROUGH_DIR/workflow.json" --output "$WALKTHROUGH_DIR/workflow-create.json" --write-out '\nHTTP %{http_code}\n'
jq . "$WALKTHROUGH_DIR/workflow-create.json"
```

The response should return 201:

```bash
export WORKFLOW_ID="$(jq -er '.id' "$WALKTHROUGH_DIR/workflow-create.json")"
export WORKFLOW_VERSION="$(jq -er '.current_version' "$WALKTHROUGH_DIR/workflow-create.json")"
jq -n --arg name "$WORKFLOW_NAME" '{name: $name, change_description: "Publish form options walkthrough"}' > "$WALKTHROUGH_DIR/publish.json"
curl --silent --show-error --insecure --request POST "$API_BASE_URL/workflows/$WORKFLOW_ID/versions/$WORKFLOW_VERSION/publish" --header "Authorization: Bearer $API_TOKEN" --header 'Content-Type: application/json' --data-binary "@$WALKTHROUGH_DIR/publish.json" | jq .
```

## 6. Start a valid run with upstream options

The manual trigger is the preceding workflow node. Its output contains region and team records; each record provides a display label and a typed value.

```bash
jq -n --arg workflow_id "$WORKFLOW_ID" '{workflow_id: $workflow_id, trigger_node_id: "trigger_manual", use_published: true, input_data: {region_records: [{name: "US East", id: 1, region: "us-east"}, {name: "EU West", id: 2, region: "eu-west"}], team_ids: [{display_label: "Platform", value: 10}, {display_label: "Data", value: 20}]}}' > "$WALKTHROUGH_DIR/execution.json"
curl --silent --show-error --insecure --request POST "$API_BASE_URL/executions" --header "Authorization: Bearer $API_TOKEN" --header 'Content-Type: application/json' --data-binary "@$WALKTHROUGH_DIR/execution.json" --output "$WALKTHROUGH_DIR/execution-create.json" --write-out '\nHTTP %{http_code}\n'
jq . "$WALKTHROUGH_DIR/execution-create.json"
export EXECUTION_ID="$(jq -er '.id' "$WALKTHROUGH_DIR/execution-create.json")"
```

## 7. Find and inspect the pending prompt

Starting an execution returns before its workflow reaches the form node. Poll for up to 60 seconds (2 seconds between requests):

```bash
PROMPT_ID=""
for attempt in {1..30}; do
  curl --silent --show-error --insecure "$API_BASE_URL/form_prompts?execution_id=$EXECUTION_ID&status=pending&limit=100" --header "Authorization: Bearer $API_TOKEN" --header 'Accept: application/json' --output "$WALKTHROUGH_DIR/prompts.json"
  PROMPT_ID="$(jq -r '.resources[]? | select(.prompt_node_id == "collect_options") | .id' "$WALKTHROUGH_DIR/prompts.json" | head -n 1)"
  if [ -n "$PROMPT_ID" ]; then
    break
  fi
  sleep 2
done

if [ -n "$PROMPT_ID" ]; then
  export PROMPT_ID
  jq '.resources[] | select(.prompt_node_id == "collect_options")' "$WALKTHROUGH_DIR/prompts.json"
  curl --silent --show-error --insecure "$API_BASE_URL/form_prompts/$PROMPT_ID" --header "Authorization: Bearer $API_TOKEN" --header 'Accept: application/json' | jq '.form_definition.fields[] | {value_name, type, options}'
else
  echo "No pending form prompt appeared after 60 seconds. Execution status:"
  curl --silent --show-error --insecure "$API_BASE_URL/executions/$EXECUTION_ID?include=activities" --header "Authorization: Bearer $API_TOKEN" --header 'Accept: application/json' | jq '{status, current_activities, activities, error_details}'
fi
```

If no prompt appears after 60 seconds, inspect the execution status and resolve any workflow error before continuing to the submission steps.

If `error_details` says `Server disconnected without sending a response`, check the workflow worker's `APP_FORMS_API_BASE_URL`. The worker must use an API URL reachable from its network; the Podman Compose default is `https://syntara:8000/api/v1`.

Expect environment and risk_tags to remain source static. Expect region_id and team_ids to have source `dynamic_resolved`. Region values should still be integers, and the extra region property on each upstream record should be ignored.

## 8. Try invalid selections

This request tests four failures together: static dropdown membership, static multi-select membership, a string "2" where the resolved dropdown value is integer 2, and a team ID outside the resolved multi-select list. It should return HTTP 422; the prompt should remain pending.

```bash
jq -n '{response_data: {environment: "production", risk_tags: ["not-listed"], region_id: "2", team_ids: [999]}}' > "$WALKTHROUGH_DIR/invalid-submit.json"
curl --silent --show-error --insecure --request POST "$API_BASE_URL/form_prompts/$PROMPT_ID/submit" --header "Authorization: Bearer $API_TOKEN" --header 'Content-Type: application/json' --data-binary "@$WALKTHROUGH_DIR/invalid-submit.json" --output "$WALKTHROUGH_DIR/invalid-submit-response.json" --write-out '\nHTTP %{http_code}\n'
jq . "$WALKTHROUGH_DIR/invalid-submit-response.json"
curl --silent --show-error --insecure "$API_BASE_URL/form_prompts/$PROMPT_ID" --header "Authorization: Bearer $API_TOKEN" --header 'Accept: application/json' | jq '{status, response_data, responded_at}'
```

## 9. Submit valid static and dynamic values

The resolved dropdown receives an integer, and the resolved multi-select receives integers, matching the upstream options.

```bash
jq -n '{response_data: {environment: "staging", risk_tags: ["security-review"], region_id: 2, team_ids: [10, 20]}}' > "$WALKTHROUGH_DIR/valid-submit.json"
curl --silent --show-error --insecure --request POST "$API_BASE_URL/form_prompts/$PROMPT_ID/submit" --header "Authorization: Bearer $API_TOKEN" --header 'Content-Type: application/json' --data-binary "@$WALKTHROUGH_DIR/valid-submit.json" --output "$WALKTHROUGH_DIR/submit-response.json" --write-out '\nHTTP %{http_code}\n'
jq . "$WALKTHROUGH_DIR/submit-response.json"
```

The response should return 200 with status submitted. Check that region_id and the team_ids entries are JSON numbers, not strings. The prompt stores the selections under `response_data` using each field's `value_name`; downstream nodes can read the selected team values with `${collect_options.response_data.team_ids}`. Repeat the execution GET until it completes; the submitted branch should run.

```bash
jq '{status, response_data}' "$WALKTHROUGH_DIR/submit-response.json"
curl --silent --show-error --insecure "$API_BASE_URL/executions/$EXECUTION_ID?include=activities" --header "Authorization: Bearer $API_TOKEN" --header 'Accept: application/json' | jq '{status, activities}'
```

## 10. Confirm flat scalar lists are rejected

Start another run with a flat list for `region_records`. The trigger schema accepts this value, so the options resolver should reject its first item because the field expects records with `name` and `id` keys. Because continue_on_failure is enabled, the workflow should complete with errors via the fallback edge. The prompt activity should not create a form-prompt row.

```bash
jq -n --arg workflow_id "$WORKFLOW_ID" '{workflow_id: $workflow_id, trigger_node_id: "trigger_manual", use_published: true, input_data: {region_records: [90, 98], team_ids: [{display_label: "Platform", value: 10}]}}' > "$WALKTHROUGH_DIR/bad-upstream-execution.json"
curl --silent --show-error --insecure --request POST "$API_BASE_URL/executions" --header "Authorization: Bearer $API_TOKEN" --header 'Content-Type: application/json' --data-binary "@$WALKTHROUGH_DIR/bad-upstream-execution.json" --output "$WALKTHROUGH_DIR/bad-upstream-execution-create.json" --write-out '\nHTTP %{http_code}\n'
jq . "$WALKTHROUGH_DIR/bad-upstream-execution-create.json"
export BAD_EXECUTION_ID="$(jq -er '.id' "$WALKTHROUGH_DIR/bad-upstream-execution-create.json")"
```

Repeat the execution GET until it reaches completed_with_errors. Inspect the failed form node's field-specific error and confirm the fallback wait node completed. Then confirm no prompt was created for the malformed run; the expected count is 0.

```bash
curl --silent --show-error --insecure "$API_BASE_URL/executions/$BAD_EXECUTION_ID?include=activities" --header "Authorization: Bearer $API_TOKEN" --header 'Accept: application/json' | jq '{status, activities}'
curl --silent --show-error --insecure "$API_BASE_URL/form_prompts?execution_id=$BAD_EXECUTION_ID&limit=100" --header "Authorization: Bearer $API_TOKEN" --header 'Accept: application/json' | jq '.resources | length'
```

The resolver also rejects a non-list result and an empty array. Repeat the malformed run with `region_records` set to `"not-a-list"` to see the expected-list error, or `[]` to see the empty-list error.
