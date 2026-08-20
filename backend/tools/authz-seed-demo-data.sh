#!/usr/bin/env bash
# authz-seed-demo-data.sh - Seed demo data to exercise all roles and features
#
# Prerequisites: Backend running on localhost:8000, `ao` CLI installed, `jq` installed
# Usage: ./tools/authz-seed-demo-data.sh [--clean] [--custom-policies]
#
# Creates:
#   Users:     20 users across engineering, product, QA, SRE, data, security, executive personas
#   Groups:    10 groups (functional teams + cross-functional)
#   Projects:  5 projects (storefront, payment-service, data-pipeline, mobile-app, internal-tools)
#   Workflows: 4-10 per project (~35 total, mix of simple + approval-gated)
#   Executions: sample runs by different users
#   Approvals:  pending approval requests for UI testing
#
# --custom-policies: Also creates project-scoped custom policies, custom roles
#   (with mixed builtin + custom policy references), and assigns them to users/groups.

set -euo pipefail

# -- Configuration --
CLI="uv run python tools/authz_cli.py"  # kept for --clean only (DB-direct ops)
AO="uv run orchestrator --base-url ${APP_CLI_URL:-http://localhost:8000}"
ADMIN_PASSWORD_PATH="${APP_ADMIN_PASSWORD_PATH:-.secrets/admin-password}"
ADMIN_PASSWORD=$(cat "$ADMIN_PASSWORD_PATH" 2>/dev/null || echo "admin1234")

info()  { echo "==> $*"; }
step()  { echo "  -> $*"; }
warn()  { echo "  !! $*"; }

# -- Associative arrays for ID tracking --
declare -A USER_IDS
declare -A GROUP_IDS
declare -A PROJECT_IDS
declare -A WF_IDS

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
if ! command -v jq &>/dev/null; then
    echo "ERROR: jq is required but not installed"
    echo "Install with: brew install jq (macOS) or apt install jq (Ubuntu)"
    exit 1
fi

if ! curl -sf "${APP_CLI_URL:-http://localhost:8000}/healthz/ready" > /dev/null 2>&1; then
    echo "ERROR: Backend not reachable at ${APP_CLI_URL:-http://localhost:8000}"
    echo "Start it with: make run"
    exit 1
fi

CUSTOM_POLICIES=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --clean)
            info "Cleaning existing demo data..."
            $CLI clean -y
            info "Re-seeding built-in policies and roles..."
            $CLI seed-builtin
            ;;
        --custom-policies)
            CUSTOM_POLICIES=true
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

create_user() {
    local username="$1" email="$2" fullname="$3"
    local id
    id=$($AO users create --username "$username" --email "$email" \
         --full-name "$fullname" --password "$ADMIN_PASSWORD" 2>/dev/null | jq -r '.id // empty')
    if [ -n "$id" ]; then
        USER_IDS["$username"]="$id"
        step "user: $username"
    else
        warn "Failed to create user: $username"
    fi
}

create_group() {
    local name="$1" desc="$2"
    local id
    id=$($AO groups create --name "$name" --description "$desc" 2>/dev/null | jq -r '.id // empty')
    if [ -n "$id" ]; then
        GROUP_IDS["$name"]="$id"
        step "group: $name"
    else
        warn "Failed to create group: $name"
    fi
}

add_member() {
    local group_name="$1" username="$2"
    local group_id="${GROUP_IDS[$group_name]:-}"
    local user_id="${USER_IDS[$username]:-}"
    if [ -z "$group_id" ] || [ -z "$user_id" ]; then
        warn "Cannot add $username to $group_name: missing ID"
        return
    fi
    $AO groups add-member "$group_id" --user-id "$user_id" > /dev/null 2>&1 \
        && step "$username -> $group_name" \
        || warn "Failed: $username -> $group_name"
}

create_project() {
    local name="$1" desc="$2"
    local id
    id=$($AO projects create --name "$name" --description "$desc" 2>/dev/null | jq -r '.id // empty')
    if [ -n "$id" ]; then
        PROJECT_IDS["$name"]="$id"
        step "project: $name"
    else
        warn "Failed to create project: $name"
    fi
}

assign_role() {
    local role="$1" principal_type="$2" principal_name="$3" project_name="${4:-}"
    local principal_id project_args=""

    if [ "$principal_type" = "user" ]; then
        principal_id="${USER_IDS[$principal_name]:-}"
    else
        principal_id="${GROUP_IDS[$principal_name]:-}"
    fi

    if [ -z "$principal_id" ]; then
        warn "Cannot assign $role: missing $principal_type ID for $principal_name"
        return
    fi

    if [ -n "$project_name" ]; then
        local project_id="${PROJECT_IDS[$project_name]:-}"
        if [ -z "$project_id" ]; then
            warn "Cannot assign $role: missing project ID for $project_name"
            return
        fi
        project_args="--project-id $project_id"
    fi

    # shellcheck disable=SC2086
    $AO role-assignments create \
        --principal-type "$principal_type" \
        --principal-id "$principal_id" \
        --role-name "$role" \
        $project_args > /dev/null 2>&1 \
        && step "$role -> $principal_type:$principal_name${project_name:+ in $project_name}" \
        || warn "Failed: $role -> $principal_type:$principal_name"
}

simple_wf() {
    local name="$1" project="$2"
    local project_id="${PROJECT_IDS[$project]:-}"
    local project_args=""
    if [ -n "$project_id" ]; then
        project_args="--project-id $project_id"
    fi

    local wf_def
    wf_def=$(jq -n --arg name "$name" '{
        schema_version: "2.0.0",
        name: $name,
        description: ("Sample workflow: " + $name),
        triggers: [{id: "trigger_manual", type: "manual_trigger"}],
        nodes: [{
            id: "step1", type: "script",
            name: ("Run " + $name),
            config: {language: "python", code: ("print(\"Running " + $name + "\")"), timeout: 300}
        }],
        edges: [{from: "trigger_manual", to: "step1"}]
    }')

    local result id
    # shellcheck disable=SC2086
    result=$($AO workflows create \
        --name "$name" \
        --description "Sample workflow: $name" \
        --workflow-definition "$wf_def" \
        $project_args 2>/dev/null) || true
    id=$(echo "$result" | jq -r '.id // empty')
    if [ -n "$id" ]; then
        WF_IDS["$name"]="$id"
        step "workflow: $name"
    else
        warn "Failed to create workflow: $name"
    fi
}

approval_wf() {
    local name="$1" desc="$2" project_id="$3"
    local wf_def
    wf_def=$(jq -n --arg name "$name" --arg desc "$desc" '{
        schema_version: "2.0.0",
        name: $name,
        description: $desc,
        triggers: [{id: "trigger_manual", type: "manual_trigger"}],
        nodes: [
            {id: "prepare", type: "script", name: "Prepare",
             config: {language: "python", code: ("print(\"Preparing " + $name + "...\")"), timeout: 300}},
            {id: "review", type: "approval", name: "Review and approve",
             config: {timeout: 3600}},
            {id: "execute", type: "script", name: "Execute",
             config: {language: "python", code: ("print(\"Executing " + $name + "\")"), timeout: 600}},
            {id: "rollback", type: "script", name: "Handle rejection",
             config: {language: "python", code: ("print(\"" + $name + " rejected\")"), timeout: 60}}
        ],
        edges: [
            {from: "trigger_manual", to: "prepare"},
            {from: "prepare", to: "review"},
            {from: "review", to: "execute", from_port: "approved"},
            {from: "review", to: "rollback", from_port: "rejected"}
        ]
    }')

    local result id
    result=$($AO workflows create \
        --name "$name" \
        --description "$desc" \
        --workflow-definition "$wf_def" \
        --project-id "$project_id" 2>/dev/null) || true
    id=$(echo "$result" | jq -r '.id // empty')
    if [ -n "$id" ]; then
        WF_IDS["$name"]="$id"
        step "approval workflow: $name"
    else
        warn "Failed to create approval workflow: $name"
    fi
}

create_credential() {
    local name="$1" type_id="$2" inputs="$3" project_id="${4:-}"
    # CredentialCreate requires project_id; org-level creds use the default project
    if [ -z "$project_id" ]; then
        project_id="${PROJECT_IDS[default]:-}"
    fi
    step "credential: $name"
    $AO credentials create \
        --name "$name" \
        --credential-type-id "$type_id" \
        --project-id "$project_id" \
        --inputs "$inputs" > /dev/null 2>&1 \
        || warn "  failed: $name"
}

run_wf() {
    local name="$1" user="$2"
    local wf_id="${WF_IDS[$name]:-}"

    if [ -z "$wf_id" ]; then
        wf_id=$($AO workflows list --limit 100 2>/dev/null | jq -r --arg n "$name" \
            '.resources[] | select(.name==$n) | .id // empty' | head -1)
    fi
    if [ -z "$wf_id" ]; then
        warn "Workflow $name not found"
        return
    fi

    step "$user runs $name"
    $AO executions create --workflow-id "$wf_id" --input-data '{}' > /dev/null 2>&1 \
        || warn "  execution failed"
}

create_approval() {
    local wf_name="$1" node_id="$2" approval_name="$3"
    local wf_id="${WF_IDS[$wf_name]:-}"

    if [ -z "$wf_id" ]; then
        wf_id=$($AO workflows list --limit 100 2>/dev/null | jq -r --arg n "$wf_name" \
            '.resources[] | select(.name==$n) | .id // empty' | head -1)
    fi
    [ -z "$wf_id" ] && return

    local wf_version_id
    wf_version_id=$($AO workflows list-versions "$wf_id" 2>/dev/null | jq -r \
        '(.versions // .resources // .) | if type == "array" then .[0].id // empty else empty end')
    [ -z "$wf_version_id" ] && return

    local exec_result exec_id
    exec_result=$($AO executions create --workflow-id "$wf_id" --input-data '{}' 2>/dev/null) || true
    exec_id=$(echo "$exec_result" | jq -r '.id // empty')
    [ -z "$exec_id" ] && return

    step "approval: $approval_name"

    local wf_context next_approved next_rejected
    wf_context=$(jq -n --arg vid "$wf_version_id" --arg wname "$wf_name" '{
        workflow_version_id: $vid,
        workflow_name: $wname,
        inputs: {}
    }')
    next_approved='{"id":"execute","name":"Execute","type":"task"}'
    next_rejected='{"id":"rollback","name":"Handle rejection","type":"task"}'

    $AO approvals create \
        --execution-id "$exec_id" \
        --approval-node-id "$node_id" \
        --name "$approval_name" \
        --workflow-context "$wf_context" \
        --next-step-approved "$next_approved" \
        --next-step-rejected "$next_rejected" > /dev/null 2>&1 \
        && step "  created" || warn "  failed"
}

create_project_policy() {
    local project_id="$1" name="$2" desc="$3" statements="$4"
    step "Policy: $name"
    $AO projects create-policy "$project_id" \
        --name "$name" \
        --description "$desc" \
        --statements "$statements" > /dev/null 2>&1 \
        && step "  created" || warn "  failed (may already exist)"
}

create_project_role() {
    local project_id="$1" name="$2" desc="$3" policies="$4"
    step "Role: $name"
    $AO projects create-role "$project_id" \
        --name "$name" \
        --description "$desc" \
        --policies "$policies" > /dev/null 2>&1 \
        && step "  created" || warn "  failed (may already exist)"
}

# ---------------------------------------------------------------------------
# Authenticate
# ---------------------------------------------------------------------------
info "Authenticating with ao CLI..."
$AO authentication login --username admin --password "$ADMIN_PASSWORD" > /dev/null 2>&1
step "authenticated as admin"

# Resolve pre-existing entity IDs
info "Resolving pre-existing entities..."
USER_IDS["admin"]=$($AO users list 2>/dev/null | jq -r '.resources[] | select(.username=="admin") | .id // empty' | head -1)
GROUP_IDS["admins"]=$($AO groups list 2>/dev/null | jq -r '.resources[] | select(.name=="admins") | .id // empty' | head -1)
PROJECT_IDS["default"]=$($AO projects list 2>/dev/null | jq -r '.resources[] | select(.name=="default") | .id // empty' | head -1)
step "admin=${USER_IDS[admin]:-?}  admins=${GROUP_IDS[admins]:-?}  default=${PROJECT_IDS[default]:-?}"

# ---------------------------------------------------------------------------
# 1. Users (20 users with varied personas)
# ---------------------------------------------------------------------------
info "Creating users..."

# Engineering leads
create_user alice   alice@example.com   "Alice Chen"
create_user bob     bob@example.com     "Bob Martinez"

# Backend engineers
create_user carol   carol@example.com   "Carol Williams"
create_user dave    dave@example.com    "Dave Patel"
create_user elena   elena@example.com   "Elena Novak"

# Frontend engineers
create_user frank   frank@example.com   "Frank Okafor"
create_user grace   grace@example.com   "Grace Kim"

# SRE / DevOps
create_user hector  hector@example.com  "Hector Reyes"
create_user iris    iris@example.com    "Iris Tanaka"

# QA engineers
create_user james   james@example.com   "James O'Brien"
create_user karen   karen@example.com   "Karen Liu"
create_user leo     leo@example.com     "Leo Andersen"

# Data engineers
create_user maya    maya@example.com    "Maya Gupta"
create_user nate    nate@example.com    "Nate Fischer"

# Product managers
create_user olivia  olivia@example.com  "Olivia Santos"
create_user paul    paul@example.com    "Paul Johansson"

# Security
create_user quinn   quinn@example.com   "Quinn Harper"

# Executive / read-only stakeholders
create_user rachel  rachel@example.com  "Rachel Nakamura"
create_user sam     sam@example.com     "Sam Dubois"
create_user tina    tina@example.com    "Tina Kowalski"

# ---------------------------------------------------------------------------
# 2. Groups (10 groups)
# ---------------------------------------------------------------------------
info "Creating groups..."

create_group backend-eng     "Backend engineering team"
create_group frontend-eng    "Frontend engineering team"
create_group sre             "Site reliability engineering"
create_group qa              "Quality assurance"
create_group data-eng        "Data engineering and analytics"
create_group product         "Product management"
create_group security        "Security team"
create_group leadership      "Engineering leadership and executives"
create_group on-call         "Current on-call rotation"
create_group release-managers "Release management (cross-functional)"

# ---------------------------------------------------------------------------
# 3. Group memberships
# ---------------------------------------------------------------------------
info "Adding users to groups..."

# admins group
add_member admins alice
add_member admins bob

# backend-eng
add_member backend-eng alice
add_member backend-eng carol
add_member backend-eng dave
add_member backend-eng elena

# frontend-eng
add_member frontend-eng bob
add_member frontend-eng frank
add_member frontend-eng grace

# sre
add_member sre hector
add_member sre iris

# qa
add_member qa james
add_member qa karen
add_member qa leo

# data-eng
add_member data-eng maya
add_member data-eng nate

# product
add_member product olivia
add_member product paul

# security
add_member security quinn

# leadership
add_member leadership rachel
add_member leadership sam
add_member leadership tina

# on-call (rotating - currently hector and carol)
add_member on-call hector
add_member on-call carol

# release-managers (cross-functional)
add_member release-managers alice
add_member release-managers bob
add_member release-managers hector
add_member release-managers olivia

# ---------------------------------------------------------------------------
# 4. Projects
# ---------------------------------------------------------------------------
info "Creating projects..."

create_project storefront      "Customer-facing web storefront"
create_project payment-service "Payment processing backend"
create_project data-pipeline   "Data ingestion and analytics pipeline"
create_project mobile-app      "iOS and Android mobile application"
create_project internal-tools  "Internal developer tooling and dashboards"

# Convenience aliases
STOREFRONT_ID="${PROJECT_IDS[storefront]:-}"
PAYMENT_ID="${PROJECT_IDS[payment-service]:-}"
PIPELINE_ID="${PROJECT_IDS[data-pipeline]:-}"
MOBILE_ID="${PROJECT_IDS[mobile-app]:-}"
TOOLS_ID="${PROJECT_IDS[internal-tools]:-}"

# ---------------------------------------------------------------------------
# 5. Project-level role assignments
# ---------------------------------------------------------------------------
info "Assigning project-level roles..."

# -- storefront: frontend-heavy, bob leads --
assign_role project-admin   user bob     storefront
assign_role project-user    user frank   storefront
assign_role project-user    user grace   storefront
assign_role project-user    user carol   storefront
assign_role project-auditor user james   storefront
assign_role project-auditor user olivia  storefront
assign_role project-auditor user rachel  storefront

# -- payment-service: backend-heavy, alice leads --
assign_role project-admin   user alice   payment-service
assign_role project-user    user carol   payment-service
assign_role project-user    user dave    payment-service
assign_role project-user    user elena   payment-service
assign_role project-auditor user quinn   payment-service
assign_role project-auditor user karen   payment-service
assign_role project-auditor user paul    payment-service

# -- data-pipeline: data team owns, SRE supports --
assign_role project-admin   user maya    data-pipeline
assign_role project-user    user nate    data-pipeline
assign_role project-user    user hector  data-pipeline
assign_role project-user    user iris    data-pipeline
assign_role project-auditor user leo     data-pipeline
assign_role project-auditor user sam     data-pipeline

# -- mobile-app: frontend + backend collaboration --
assign_role project-admin   user bob     mobile-app
assign_role project-admin   user alice   mobile-app
assign_role project-user    user frank   mobile-app
assign_role project-user    user grace   mobile-app
assign_role project-user    user dave    mobile-app
assign_role project-auditor user james   mobile-app
assign_role project-auditor user karen   mobile-app
assign_role project-auditor user olivia  mobile-app
assign_role project-auditor user tina    mobile-app

# -- internal-tools: SRE owns, everyone can read --
assign_role project-admin   user hector  internal-tools
assign_role project-user    user iris    internal-tools
assign_role project-user    user elena   internal-tools
assign_role project-user    user nate    internal-tools
assign_role project-auditor user quinn   internal-tools

# ---------------------------------------------------------------------------
# 6. Custom policies, roles & assignments (optional)
# ---------------------------------------------------------------------------
if [ "$CUSTOM_POLICIES" = true ]; then

info "Creating custom project policies..."

# -- data-pipeline policies --
create_project_policy "$PIPELINE_ID" "etl-operator" \
    "Run and monitor ETL workflows" \
    '[{"effect":"allow","actions":["workflow:read","execution:read","execution:run"],"scope":"project"}]'

create_project_policy "$PIPELINE_ID" "data-viewer" \
    "Read-only access to pipeline workflows and credentials" \
    '[{"effect":"allow","actions":["workflow:read","execution:read","credential:read"],"scope":"project"}]'

create_project_policy "$PIPELINE_ID" "data-quality-admin" \
    "Manage data quality workflows and approve pipeline runs" \
    '[{"effect":"allow","actions":["workflow:read","workflow:update","execution:read","execution:run","approval:read","approval:decide"],"scope":"project"}]'

# -- payment-service policies --
create_project_policy "$PAYMENT_ID" "pci-auditor" \
    "Read-only access with credential visibility for PCI compliance audits" \
    '[{"effect":"allow","actions":["workflow:read","execution:read","credential:read","approval:read"],"scope":"project"}]'

create_project_policy "$PAYMENT_ID" "deploy-approver" \
    "Approve production deployments but cannot modify workflows" \
    '[{"effect":"allow","actions":["workflow:read","execution:read","approval:read","approval:decide"],"scope":"project"}]'

# -- storefront policies --
create_project_policy "$STOREFRONT_ID" "feature-flag-manager" \
    "Manage feature flag workflows and run deployments" \
    '[{"effect":"allow","actions":["workflow:read","workflow:create","workflow:update","execution:read","execution:run"],"scope":"project"}]'

create_project_policy "$STOREFRONT_ID" "cdn-operator" \
    "Run CDN and cache-related workflows" \
    '[{"effect":"allow","actions":["workflow:read","execution:read","execution:run"],"scope":"project"}]'

# -- internal-tools policies --
create_project_policy "$TOOLS_ID" "infra-operator" \
    "Run infrastructure workflows and view credentials" \
    '[{"effect":"allow","actions":["workflow:read","execution:read","execution:run","credential:read"],"scope":"project"}]'

info "Creating custom project roles..."

# -- data-pipeline roles (mix of custom + builtin policies) --
create_project_role "$PIPELINE_ID" "etl-engineer" \
    "Run ETL workflows and view pipeline credentials" \
    '["etl-operator", "credential:read:project"]'

create_project_role "$PIPELINE_ID" "data-stakeholder" \
    "Read-only stakeholder view of data pipeline" \
    '["data-viewer"]'

create_project_role "$PIPELINE_ID" "data-quality-lead" \
    "Manage data quality checks and approve pipeline changes" \
    '["data-quality-admin", "credential:read:project", "role:read:project"]'

# -- payment-service roles --
create_project_role "$PAYMENT_ID" "compliance-reviewer" \
    "PCI compliance reviewer with deploy approval authority" \
    '["pci-auditor", "deploy-approver"]'

create_project_role "$PAYMENT_ID" "payment-deployer" \
    "Deploy payment services and manage credentials" \
    '["deploy-approver", "credential:read:project", "credential:update:project"]'

# -- storefront roles --
create_project_role "$STOREFRONT_ID" "frontend-lead" \
    "Manage feature flags and CDN for storefront" \
    '["feature-flag-manager", "cdn-operator", "credential:read:project"]'

create_project_role "$STOREFRONT_ID" "release-engineer" \
    "Run deployments and manage CDN cache" \
    '["cdn-operator", "execution:run:project"]'

# -- internal-tools roles --
create_project_role "$TOOLS_ID" "platform-engineer" \
    "Operate infrastructure workflows and manage tool credentials" \
    '["infra-operator", "credential:update:project"]'

info "Assigning custom roles..."

# -- data-pipeline: custom role assignments --
assign_role etl-engineer     user  nate    data-pipeline
assign_role data-stakeholder user  paul    data-pipeline
assign_role data-stakeholder user  rachel  data-pipeline
assign_role data-quality-lead user maya    data-pipeline
assign_role data-stakeholder group leadership data-pipeline

# -- payment-service: custom role assignments --
assign_role compliance-reviewer user  quinn    payment-service
assign_role payment-deployer    user  elena    payment-service
assign_role compliance-reviewer group security payment-service

# -- storefront: custom role assignments --
assign_role frontend-lead    user  bob    storefront
assign_role release-engineer user  hector storefront
assign_role release-engineer group on-call storefront

# -- internal-tools: custom role assignments --
assign_role platform-engineer user  iris   internal-tools
assign_role platform-engineer user  elena  internal-tools
assign_role platform-engineer group sre    internal-tools

fi

# ---------------------------------------------------------------------------
# 7. Workflows
# ---------------------------------------------------------------------------
info "Creating workflows..."

# -- storefront (6 workflows) --
simple_wf "build-storefront"     "storefront"
simple_wf "run-e2e-tests"        "storefront"
simple_wf "lighthouse-audit"     "storefront"
simple_wf "cdn-cache-purge"      "storefront"
approval_wf "deploy-storefront-prod" "Deploy storefront to production" "$STOREFRONT_ID"
approval_wf "feature-flag-toggle"    "Toggle feature flags in production" "$STOREFRONT_ID"

# -- payment-service (7 workflows) --
simple_wf "build-payment-svc"    "payment-service"
simple_wf "run-integration-tests" "payment-service"
simple_wf "pci-compliance-scan"  "payment-service"
simple_wf "rotate-api-keys"      "payment-service"
simple_wf "generate-txn-report"  "payment-service"
approval_wf "deploy-payment-prod"    "Deploy payment service to production" "$PAYMENT_ID"
approval_wf "db-schema-migration"    "Apply database schema migration" "$PAYMENT_ID"

# -- data-pipeline (5 workflows) --
simple_wf "run-etl-daily"        "data-pipeline"
simple_wf "validate-data-quality" "data-pipeline"
simple_wf "sync-data-warehouse"  "data-pipeline"
simple_wf "generate-analytics"   "data-pipeline"
approval_wf "backfill-historical"    "Run historical data backfill" "$PIPELINE_ID"

# -- mobile-app (6 workflows) --
simple_wf "build-ios"            "mobile-app"
simple_wf "build-android"        "mobile-app"
simple_wf "run-device-tests"     "mobile-app"
simple_wf "screenshot-diff"      "mobile-app"
approval_wf "submit-app-store"       "Submit to App Store / Play Store" "$MOBILE_ID"
approval_wf "push-notification-blast" "Send push notification to all users" "$MOBILE_ID"

# -- internal-tools (4 workflows) --
simple_wf "build-dev-portal"     "internal-tools"
simple_wf "update-docs-site"     "internal-tools"
simple_wf "rotate-service-creds" "internal-tools"
approval_wf "infra-terraform-apply"  "Apply Terraform infrastructure changes" "$TOOLS_ID"

# -- default project (2 workflows) --
simple_wf "hello-world"         "default"
simple_wf "smoke-test"          "default"

# ---------------------------------------------------------------------------
# 8. Credentials
# ---------------------------------------------------------------------------
info "Creating credentials..."

BEARER_TYPE=$($AO credentials list-types 2>/dev/null | jq -r '.resources[] | select(.name=="HTTP Bearer Token") | .id // empty' | head -1)
BASIC_TYPE=$($AO credentials list-types 2>/dev/null | jq -r '.resources[] | select(.name=="HTTP Basic Auth") | .id // empty' | head -1)
LLM_TYPE=$($AO credentials list-types 2>/dev/null | jq -r '.resources[] | select(.name=="LLM Provider") | .id // empty' | head -1)
AAP_TYPE=$($AO credentials list-types 2>/dev/null | jq -r '.resources[] | select(.name=="Ansible Automation Platform") | .id // empty' | head -1)
SSH_TYPE=$($AO credentials list-types 2>/dev/null | jq -r '.resources[] | select(.name=="SSH Key") | .id // empty' | head -1)

step "bearer=$BEARER_TYPE basic=$BASIC_TYPE llm=$LLM_TYPE aap=$AAP_TYPE ssh=$SSH_TYPE"

# -- Org-level credentials (use default project since project_id is required) --
create_credential "OpenRouter API Key" "$LLM_TYPE" \
    '{"api_key": "sk-or-v1-demo-openrouter-key", "provider": "openrouter"}' ""
create_credential "GitHub Actions Token" "$BEARER_TYPE" \
    '{"token": "ghp_demo_github_actions_token_2026"}' ""
create_credential "Shared SSH Deploy Key" "$SSH_TYPE" \
    '{"username": "deploy", "ssh_private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\ndemo-key-content\n-----END OPENSSH PRIVATE KEY-----"}' ""

# -- Storefront credentials --
create_credential "Storefront Stripe API Key" "$BEARER_TYPE" \
    '{"token": "sk_live_demo_stripe_storefront_key"}' "$STOREFRONT_ID"
create_credential "Storefront CDN Token" "$BEARER_TYPE" \
    '{"token": "cdn-demo-token-storefront-2026"}' "$STOREFRONT_ID"

# -- Payment service credentials --
create_credential "Payment DB Credentials" "$BASIC_TYPE" \
    '{"username": "payment_svc", "password": "demo-payment-db-password"}' "$PAYMENT_ID"
create_credential "Payment Gateway API Key" "$BEARER_TYPE" \
    '{"token": "pgw-demo-api-key-production"}' "$PAYMENT_ID"
create_credential "PCI Compliance Scanner" "$BASIC_TYPE" \
    '{"username": "pci-scanner", "password": "demo-pci-scanner-creds"}' "$PAYMENT_ID"

# -- Data pipeline credentials --
create_credential "Data Warehouse Credentials" "$BASIC_TYPE" \
    '{"username": "etl_pipeline", "password": "demo-warehouse-password"}' "$PIPELINE_ID"
create_credential "Analytics API Key" "$BEARER_TYPE" \
    '{"token": "analytics-demo-api-key-2026"}' "$PIPELINE_ID"

# -- Mobile app credentials --
create_credential "App Store Connect Key" "$BEARER_TYPE" \
    '{"token": "asc-demo-api-key-ios-2026"}' "$MOBILE_ID"
create_credential "Firebase Service Account" "$BEARER_TYPE" \
    '{"token": "firebase-demo-sa-token-2026"}' "$MOBILE_ID"

# -- Internal tools credentials --
create_credential "AAP Production Controller" "$AAP_TYPE" \
    '{"host": "https://aap.internal.example.com", "username": "syntara-svc", "password": "demo-aap-password", "verify_ssl": true}' "$TOOLS_ID"
create_credential "Internal Vault Token" "$BEARER_TYPE" \
    '{"token": "hvs.demo-vault-root-token-2026"}' "$TOOLS_ID"

# ---------------------------------------------------------------------------
# 9. Sample executions
# ---------------------------------------------------------------------------
info "Creating sample executions..."

run_wf "run-e2e-tests"         "frank"
run_wf "build-storefront"      "grace"
run_wf "lighthouse-audit"      "bob"
run_wf "run-integration-tests" "carol"
run_wf "pci-compliance-scan"   "alice"
run_wf "build-ios"             "frank"
run_wf "build-android"         "grace"
run_wf "run-etl-daily"         "maya"
run_wf "validate-data-quality" "nate"
run_wf "build-dev-portal"      "iris"
run_wf "hello-world"           "admin"
run_wf "smoke-test"            "hector"

# ---------------------------------------------------------------------------
# 10. Pending approval requests
# ---------------------------------------------------------------------------
info "Creating pending approval requests..."

create_approval "deploy-storefront-prod"  "review" "Deploy storefront v3.2 to production"
create_approval "deploy-payment-prod"     "review" "Deploy payment-service hotfix to production"
create_approval "db-schema-migration"     "review" "Add index on transactions.created_at"
create_approval "submit-app-store"        "review" "Submit mobile-app v2.0 to App Store"
create_approval "infra-terraform-apply"   "review" "Scale up payment-service to 8 replicas"
create_approval "push-notification-blast" "review" "Black Friday sale notification to all users"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
info "Demo data seeding complete!"
echo ""
echo "Users (20):    admin + alice, bob, carol, dave, elena, frank, grace,"
echo "               hector, iris, james, karen, leo, maya, nate,"
echo "               olivia, paul, quinn, rachel, sam, tina"
echo ""
echo "Groups (10):   admins, authenticated, backend-eng, frontend-eng, sre,"
echo "               qa, data-eng, product, security, leadership,"
echo "               on-call, release-managers"
echo ""
echo "Projects (5):  default, storefront, payment-service, data-pipeline,"
echo "               mobile-app, internal-tools"
echo ""
echo "Credentials:   15 (3 org-level + 12 project-scoped across 5 types)"
echo "Workflows:     ~35 (mix of simple + approval-gated)"
echo "Executions:    12 sample runs"
echo "Approvals:     6 pending approval requests"
if [ "$CUSTOM_POLICIES" = true ]; then
echo ""
echo "Custom policies (8): etl-operator, data-viewer, data-quality-admin,"
echo "               pci-auditor, deploy-approver, feature-flag-manager,"
echo "               cdn-operator, infra-operator"
echo ""
echo "Custom roles (8):  etl-engineer, data-stakeholder, data-quality-lead,"
echo "               compliance-reviewer, payment-deployer, frontend-lead,"
echo "               release-engineer, platform-engineer"
fi
echo ""
echo "Personas:"
echo "  alice, bob         -> eng leads, system admins"
echo "  carol, dave, elena -> backend engineers"
echo "  frank, grace       -> frontend engineers"
echo "  hector, iris       -> SRE / DevOps"
echo "  james, karen, leo  -> QA engineers"
echo "  maya, nate         -> data engineers"
echo "  olivia, paul       -> product managers"
echo "  quinn              -> security engineer"
echo "  rachel, sam, tina  -> leadership / executives (read-only)"
echo ""
echo "All users have password: (same as admin)"
echo "Pending approvals are waiting to be approved or rejected."
