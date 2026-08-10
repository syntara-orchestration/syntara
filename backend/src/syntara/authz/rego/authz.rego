package nexus.authz
import rego.v1

default allow := false
default deny := false
default denial_reason := ""
default matched_policy := ""
default denied_by := ""

# Deny: any deny-effect policy that matches action+scope+conditions blocks the request
deny if {
    some policy in input.effective_policies
    policy.effect == "deny"
    _action_matches(policy)
    _scope_matches(policy)
    _conditions_match(policy)
}
denial_reason := "policy_deny" if { deny }

# Allow: any allow-effect policy that matches action+scope+conditions grants access
allow if {
    not deny
    some policy in input.effective_policies
    policy.effect == "allow"
    _action_matches(policy)
    _scope_matches(policy)
    _conditions_match(policy)
}

# Helpers
_action_matches(policy) if {
    requested := concat(":", [input.resource.type, input.action])
    some action in policy.actions
    action == requested
}
_action_matches(policy) if {
    wildcard := concat(":", [input.resource.type, "*"])
    some action in policy.actions
    action == wildcard
}

_scope_matches(policy) if { policy.scope == "any" }
_scope_matches(policy) if {
    policy.scope == "self"
    input.resource.type == "user"
    input.resource.id == input.user.id
}
_scope_matches(policy) if {
    policy.scope == "self"
    input.resource.type == "user_identity"
    input.resource.id == input.user.id
}
_scope_matches(policy) if {
    policy.scope == "self"
    input.resource.type == "group"
    some group in input.groups
    group.id == input.resource.id
}
_scope_matches(policy) if {
    policy.scope == "project"
    policy.project == input.resource.project
}
# Explicit any-project check (can_i check_any_project=true). Does NOT treat
# empty resource.project as a wildcard — that flag must be set.
_scope_matches(policy) if {
    policy.scope == "project"
    input.resource.any_project == true
    policy.project != ""
}

# Condition matching: no conditions key means unconditional match (backward compat)
_conditions_match(policy) if {
    not policy.conditions
}
_conditions_match(policy) if {
    policy.conditions
    not policy.conditions.__not_condition_failed__
    _resource_labels_match(policy)
    _resource_labels_not_match(policy)
    _user_labels_match(policy)
    _user_labels_not_match(policy)
    _resource_metadata_match(policy)
    _user_metadata_match(policy)
    _group_labels_match(policy)
}

# Sub-condition helpers: each passes if the key is absent OR all entries match
_resource_labels_match(policy) if {
    not policy.conditions.resource_labels
}
_resource_labels_match(policy) if {
    policy.conditions.resource_labels
    every key, val in policy.conditions.resource_labels {
        input.resource.labels[key] == val
    }
}

_resource_labels_not_match(policy) if {
    not policy.conditions.resource_labels_not
}
_resource_labels_not_match(policy) if {
    policy.conditions.resource_labels_not
    every key, val in policy.conditions.resource_labels_not {
        not input.resource.labels[key] == val
    }
}

_user_labels_match(policy) if {
    not policy.conditions.user_labels
}
_user_labels_match(policy) if {
    policy.conditions.user_labels
    every key, val in policy.conditions.user_labels {
        input.user.labels[key] == val
    }
}

_user_labels_not_match(policy) if {
    not policy.conditions.user_labels_not
}
# `not ... == val` (not `!=`): missing key → undefined → not true → passes.
# Closed-world: users who can't prove they hold a label are denied.
_user_labels_not_match(policy) if {
    policy.conditions.user_labels_not
    every key, val in policy.conditions.user_labels_not {
        not input.user.labels[key] == val
    }
}

_resource_metadata_match(policy) if {
    not policy.conditions.resource_metadata
}
_resource_metadata_match(policy) if {
    policy.conditions.resource_metadata
    every key, val in policy.conditions.resource_metadata {
        input.resource.metadata[key] == val
    }
}

_user_metadata_match(policy) if {
    not policy.conditions.user_metadata
}
_user_metadata_match(policy) if {
    policy.conditions.user_metadata
    every key, val in policy.conditions.user_metadata {
        input.user.metadata[key] == val
    }
}

_group_labels_match(policy) if {
    not policy.conditions.group_labels
}
_group_labels_match(policy) if {
    policy.conditions.group_labels
    some group in input.groups
    every key, val in policy.conditions.group_labels {
        group.labels[key] == val
    }
}

# Allowed projects: collect project names the user can access for the requested action
# Returns the set of project names, or ["*"] if any scope-"any" policy matches.
allowed_projects contains "*" if {
    not deny
    some policy in input.effective_policies
    policy.effect == "allow"
    _action_matches(policy)
    policy.scope == "any"
    _conditions_match(policy)
}
allowed_projects contains policy.project if {
    not deny
    some policy in input.effective_policies
    policy.effect == "allow"
    _action_matches(policy)
    policy.scope == "project"
    _conditions_match(policy)
}

# Track which policy allowed (collect all matching, return first)
_matched_policies contains policy.name if {
    not deny
    some policy in input.effective_policies
    policy.effect == "allow"
    _action_matches(policy)
    _scope_matches(policy)
    _conditions_match(policy)
}
matched_policy := _sorted[0] if {
    _sorted := sort(_matched_policies)
    count(_sorted) > 0
}

# Track which deny policy fired (collect all matching, return first)
_denied_by_policies contains policy.name if {
    some policy in input.effective_policies
    policy.effect == "deny"
    _action_matches(policy)
    _scope_matches(policy)
    _conditions_match(policy)
}
denied_by := _sorted[0] if {
    _sorted := sort(_denied_by_policies)
    count(_sorted) > 0
}
