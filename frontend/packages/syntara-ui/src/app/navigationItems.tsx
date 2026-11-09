import {
  RhUiConnectedIcon,
  RhUiFolderIcon,
  RhUiKeyIcon,
  RhUiLanguageIcon,
  RhUiLikeIcon,
  RhUiListIcon,
  RhUiNetworkIcon,
  RhUiPlayCircleIcon,
  RhUiSecuredIcon,
  RhUiSettingsIcon,
  RhUiUsersIcon,
} from '@patternfly/react-icons'

import type { PermissionRequirement } from '../hooks/permissionUtils'

import type { AppRouteNavigationOptions } from './routeNavigationOptions'
import * as routeRefs from './routes/routeReferences'

export type TNavigationItem = {
  id?: string
  label: string
  destination?: AppRouteNavigationOptions
  matchPath?: string
  matchPrefix?: string
  children?: TNavigationItem[]
  hidden?: boolean
  matchPattern?: string
  separatorBefore?: boolean
  icon?: React.ReactNode
  /**
   * If set, the item is visible only when the user has **at least one** of
   * these permissions (OR logic). Hidden when every check is denied.
   * Omit to keep the item always visible.
   */
  requiredPermissions?: PermissionRequirement[]
  /**
   * If set, the route is wrapped in a `ProtectedRoute` guard that blocks
   * access when the user lacks this permission. Shows an access-denied
   * empty state instead of the page component.
   */
  routePermission?: PermissionRequirement
}

export const NAV_ITEMS: TNavigationItem[] = [
  {
    label: 'Workflow Builder',
    destination: { to: routeRefs.builderNewRoute.fullPath },
    matchPath: routeRefs.builderNewRoute.fullPath,
    // UX requirement: rotate the network icon 270° so it reads as a "builder" shape rather than a network diagram
    icon: <RhUiNetworkIcon style={{ transform: 'rotate(270deg)' }} />,
    matchPattern: routeRefs.builderEditRoute.fullPath,
  },
  {
    label: 'Workflows',
    destination: { to: routeRefs.workflowsRoute.fullPath },
    matchPath: routeRefs.workflowsRoute.fullPath,
    icon: <RhUiListIcon />,
  },
  {
    label: 'Workflow Runs',
    destination: { to: routeRefs.executionsListRoute.fullPath },
    matchPath: routeRefs.executionsListRoute.fullPath,
    icon: <RhUiPlayCircleIcon />,
  },
  {
    label: 'Approvals',
    destination: { to: routeRefs.approvalsRoute.fullPath },
    matchPath: routeRefs.approvalsRoute.fullPath,
    icon: <RhUiLikeIcon />,
    requiredPermissions: [
      { action: 'read', resourceType: 'approval' },
      { action: 'decide', resourceType: 'approval' },
    ],
  },
  {
    label: 'Configuration',
    destination: { to: routeRefs.integrationsRoute.fullPath },
    matchPath: routeRefs.integrationsRoute.fullPath,
    icon: <RhUiFolderIcon />,
    children: [
      {
        label: 'Integrations',
        destination: { to: routeRefs.integrationsRoute.fullPath },
        matchPath: routeRefs.integrationsRoute.fullPath,
        icon: <RhUiConnectedIcon />,
        requiredPermissions: [{ action: 'read', resourceType: 'integration' }],
        children: [
          {
            label: 'Configure',
            destination: { to: routeRefs.configureIntegrationRoute.fullPath },
            matchPath: routeRefs.configureIntegrationRoute.fullPath,
            routePermission: { action: 'create', resourceType: 'integration' },
          },
          {
            label: 'Edit Integration',
            matchPath: routeRefs.editIntegrationRoute.fullPath,
            hidden: true,
            routePermission: { action: 'update', resourceType: 'integration' },
          },
          {
            label: 'Integration Detail',
            matchPath: routeRefs.integrationDetailRoute.fullPath,
            hidden: true,
          },
          {
            label: 'Integration Detail Tab',
            matchPath: routeRefs.integrationDetailTabRoute.fullPath,
            hidden: true,
          },
        ],
      },
      {
        label: 'Credentials',
        destination: { to: routeRefs.credentialsRoute.fullPath },
        matchPath: routeRefs.credentialsRoute.fullPath,
        icon: <RhUiKeyIcon />,
      },
    ],
  },
  {
    label: 'System Administration',
    id: '/system-administration',
    matchPrefix: '/system-administration',
    icon: <RhUiLanguageIcon />,
    children: [
      {
        label: 'Access Management',
        destination: { to: routeRefs.accessManagementRoute.fullPath },
        matchPath: routeRefs.accessManagementRoute.fullPath,
        icon: <RhUiUsersIcon />,
        // Admin-worthy grants only. Do not include project:read or service_account:read —
        // those are shared with project-user / project-auditor and would over-show the hub.
        // Project-admins unlock via role-assignment:* through can_i check_any_project.
        requiredPermissions: [
          { action: 'read', resourceType: 'user' },
          { action: 'read', resourceType: 'group' },
          { action: 'read', resourceType: 'role-assignment' },
          { action: 'assign', resourceType: 'role-assignment' },
        ],
        children: [
          {
            label: 'Users',
            destination: { to: routeRefs.accessManagementUsersRoute.fullPath },
            matchPath: routeRefs.accessManagementUsersRoute.fullPath,
            requiredPermissions: [{ action: 'read', resourceType: 'user' }],
          },
          {
            label: 'Groups',
            destination: { to: routeRefs.accessManagementGroupsRoute.fullPath },
            matchPath: routeRefs.accessManagementGroupsRoute.fullPath,
            requiredPermissions: [{ action: 'read', resourceType: 'group' }],
          },
          {
            label: 'Service Accounts',
            destination: { to: routeRefs.accessManagementServiceAccountsRoute.fullPath },
            matchPath: routeRefs.accessManagementServiceAccountsRoute.fullPath,
            requiredPermissions: [{ action: 'read', resourceType: 'service_account' }],
          },
          {
            label: 'Service Account Detail',
            matchPath: routeRefs.serviceAccountDetailRoute.fullPath,
            hidden: true,
          },
          {
            label: 'Service Account Detail Tab',
            matchPath: routeRefs.serviceAccountDetailCredentialsRoute.fullPath,
            hidden: true,
          },
          {
            label: 'Policies',
            destination: { to: routeRefs.accessManagementPoliciesRoute.fullPath },
            matchPath: routeRefs.accessManagementPoliciesRoute.fullPath,
          },
          {
            label: 'Roles',
            destination: { to: routeRefs.accessManagementRolesRoute.fullPath },
            matchPath: routeRefs.accessManagementRolesRoute.fullPath,
          },
          {
            label: 'Projects',
            destination: { to: routeRefs.accessManagementProjectsRoute.fullPath },
            matchPath: routeRefs.accessManagementProjectsRoute.fullPath,
          },
          {
            label: 'Project Detail',
            matchPath: routeRefs.projectDetailRoute.fullPath,
            hidden: true,
          },
          {
            label: 'Project Detail Tab',
            matchPath: routeRefs.projectDetailWorkflowsRoute.fullPath,
            hidden: true,
          },
          {
            label: 'Assignments',
            destination: { to: routeRefs.accessManagementAssignmentsRoute.fullPath },
            matchPath: routeRefs.accessManagementAssignmentsRoute.fullPath,
          },
          {
            label: 'Check access',
            destination: { to: routeRefs.accessManagementCheckAccessRoute.fullPath },
            matchPath: routeRefs.accessManagementCheckAccessRoute.fullPath,
          },
          {
            label: 'Token Revocation',
            destination: { to: routeRefs.accessManagementTokenRevocationRoute.fullPath },
            matchPath: routeRefs.accessManagementTokenRevocationRoute.fullPath,
          },
          {
            label: 'Group Detail',
            matchPath: routeRefs.groupDetailRoute.fullPath,
            hidden: true,
          },
          {
            label: 'Group Detail Tab',
            matchPath: routeRefs.groupDetailMembersRoute.fullPath,
            hidden: true,
          },
          {
            label: 'Create User',
            destination: { to: routeRefs.createUserRoute.fullPath },
            matchPath: routeRefs.createUserRoute.fullPath,
            hidden: true,
            routePermission: { action: 'create', resourceType: 'user' },
          },
          {
            label: 'Edit User',
            matchPath: routeRefs.editUserRoute.fullPath,
            hidden: true,
            routePermission: { action: 'update', resourceType: 'user' },
          },
          {
            label: 'Transfer Identity',
            matchPath: routeRefs.transferIdentityRoute.fullPath,
            hidden: true,
          },
          {
            label: 'User Detail',
            matchPath: routeRefs.userDetailRoute.fullPath,
            hidden: true,
          },
          {
            label: 'User Detail Tab',
            matchPath: routeRefs.userDetailDetailsRoute.fullPath,
            hidden: true,
          },
        ],
      },
      {
        label: 'Identity Providers',
        destination: { to: routeRefs.authenticationRootRoute.fullPath },
        matchPath: routeRefs.authenticationRootRoute.fullPath,
        icon: <RhUiSecuredIcon />,
        requiredPermissions: [{ action: 'read', resourceType: 'identity-provider' }],
        children: [
          {
            label: 'Add Identity Provider',
            destination: { to: routeRefs.addIdentityProviderRoute.fullPath },
            matchPath: routeRefs.addIdentityProviderRoute.fullPath,
            routePermission: { action: 'create', resourceType: 'identity-provider' },
          },
          {
            label: 'Edit Identity Provider',
            matchPath: routeRefs.editIdentityProviderRoute.fullPath,
            routePermission: { action: 'update', resourceType: 'identity-provider' },
          },
          {
            label: 'Edit Group Mapping',
            matchPath: routeRefs.editIdentityProviderGroupMappingRoute.fullPath,
            hidden: true,
          },
          {
            label: 'Identity Provider Details',
            matchPath: routeRefs.identityProviderDetailRoute.fullPath,
          },
          {
            label: 'Identity Provider Details Tab',
            matchPath: routeRefs.identityProviderGroupMappingRoute.fullPath,
            hidden: true,
          },
        ],
      },
      {
        label: 'Settings',
        destination: { to: routeRefs.settingsRoute.fullPath },
        matchPath: routeRefs.settingsRoute.fullPath,
        icon: <RhUiSettingsIcon />,
        requiredPermissions: [{ action: 'read', resourceType: 'setting' }],
        children: [
          {
            label: 'Settings Tab',
            matchPath: routeRefs.settingsCategoryRoute.fullPath,
            hidden: true,
          },
        ],
      },
    ],
  },
  // Hidden routes (not shown in navigation, but path needed for active-state matching)
  {
    label: 'Edit Workflow',
    matchPath: routeRefs.builderEditRoute.fullPath,
    hidden: true,
  },
  {
    label: 'Execution Detail',
    matchPath: routeRefs.executionDetailRoute.fullPath,
    hidden: true,
  },
  {
    label: 'Credential Detail',
    matchPath: routeRefs.credentialDetailRoute.fullPath,
    hidden: true,
  },
  {
    label: 'Credential Detail Tab',
    matchPath: routeRefs.credentialDetailsRoute.fullPath,
    hidden: true,
  },
  {
    label: 'My Profile',
    destination: { to: routeRefs.myProfileRootRoute.fullPath },
    matchPath: routeRefs.myProfileRootRoute.fullPath,
    hidden: true,
  },
  {
    label: 'My Profile Tab',
    matchPath: routeRefs.myProfileTabRoute.fullPath,
    hidden: true,
  },
] as const
