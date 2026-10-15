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

import { AppRoute } from './AppRoute'

export type TNavigationItem = {
  label: string
  path: string
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
    path: AppRoute.WorkflowBuilder.New,
    // UX requirement: rotate the network icon 270° so it reads as a "builder" shape rather than a network diagram
    icon: <RhUiNetworkIcon style={{ transform: 'rotate(270deg)' }} />,
    matchPattern: '/workflow-builder/:workflowId',
  },
  {
    label: 'Workflows',
    path: AppRoute.Workflows.Root,
    icon: <RhUiListIcon />,
  },
  {
    label: 'Workflow Runs',
    path: AppRoute.Executions.Root,
    icon: <RhUiPlayCircleIcon />,
  },
  {
    label: 'Approvals',
    path: AppRoute.Approvals.Root,
    icon: <RhUiLikeIcon />,
    requiredPermissions: [
      { action: 'read', resourceType: 'approval' },
      { action: 'decide', resourceType: 'approval' },
    ],
  },
  {
    label: 'Configuration',
    path: AppRoute.Configuration.Integrations.Root,
    icon: <RhUiFolderIcon />,
    children: [
      {
        label: 'Integrations',
        path: AppRoute.Configuration.Integrations.Root,
        icon: <RhUiConnectedIcon />,
        requiredPermissions: [{ action: 'read', resourceType: 'integration' }],
        children: [
          {
            label: 'Configure',
            path: AppRoute.Configuration.Integrations.Configure,
            routePermission: { action: 'create', resourceType: 'integration' },
          },
          {
            label: 'Edit Integration',
            path: AppRoute.Configuration.Integrations.Edit,
            hidden: true,
            routePermission: { action: 'update', resourceType: 'integration' },
          },
          {
            label: 'Integration Detail',
            path: AppRoute.Configuration.Integrations.Detail,
            hidden: true,
          },
          {
            label: 'Integration Detail Tab',
            path: AppRoute.Configuration.Integrations.DetailTab,
            hidden: true,
          },
        ],
      },
      {
        label: 'Credentials',
        path: AppRoute.Configuration.Credentials.Root,
        icon: <RhUiKeyIcon />,
      },
    ],
  },
  {
    label: 'System Administration',
    path: AppRoute.SystemAdministration.Root,
    icon: <RhUiLanguageIcon />,
    children: [
      {
        label: 'Access Management',
        path: AppRoute.AccessManagement.Root,
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
            path: AppRoute.AccessManagement.Users,
            requiredPermissions: [{ action: 'read', resourceType: 'user' }],
          },
          {
            label: 'Groups',
            path: AppRoute.AccessManagement.Groups,
            requiredPermissions: [{ action: 'read', resourceType: 'group' }],
          },
          {
            label: 'Service Accounts',
            path: AppRoute.AccessManagement.ServiceAccounts,
            requiredPermissions: [{ action: 'read', resourceType: 'service_account' }],
          },
          {
            label: 'Service Account Detail',
            path: AppRoute.AccessManagement.ServiceAccountDetail,
            hidden: true,
          },
          {
            label: 'Service Account Detail Tab',
            path: AppRoute.AccessManagement.ServiceAccountDetailTab,
            hidden: true,
          },
          {
            label: 'Policies',
            path: AppRoute.AccessManagement.Policies,
          },
          {
            label: 'Roles',
            path: AppRoute.AccessManagement.Roles,
          },
          {
            label: 'Projects',
            path: AppRoute.AccessManagement.Projects,
          },
          {
            label: 'Project Detail',
            path: AppRoute.AccessManagement.ProjectDetail,
            hidden: true,
          },
          {
            label: 'Project Detail Tab',
            path: AppRoute.AccessManagement.ProjectDetailTab,
            hidden: true,
          },
          {
            label: 'Assignments',
            path: AppRoute.AccessManagement.Assignments,
          },
          {
            label: 'Check access',
            path: AppRoute.AccessManagement.CheckAccess,
          },
          {
            label: 'Token Revocation',
            path: AppRoute.AccessManagement.TokenRevocation,
          },
          {
            label: 'Group Detail',
            path: AppRoute.AccessManagement.GroupDetail,
            hidden: true,
          },
          {
            label: 'Group Detail Tab',
            path: AppRoute.AccessManagement.GroupDetailTab,
            hidden: true,
          },
          {
            label: 'Create User',
            path: AppRoute.AccessManagement.CreateUser,
            hidden: true,
            routePermission: { action: 'create', resourceType: 'user' },
          },
          {
            label: 'Edit User',
            path: AppRoute.AccessManagement.EditUser,
            hidden: true,
            routePermission: { action: 'update', resourceType: 'user' },
          },
          {
            label: 'Transfer Identity',
            path: AppRoute.AccessManagement.TransferIdentity,
            hidden: true,
          },
          {
            label: 'User Detail',
            path: AppRoute.AccessManagement.UserDetail,
            hidden: true,
          },
          {
            label: 'User Detail Tab',
            path: AppRoute.AccessManagement.UserDetailTab,
            hidden: true,
          },
        ],
      },
      {
        label: 'Identity Providers',
        path: AppRoute.SystemAdministration.Authentication.Root,
        icon: <RhUiSecuredIcon />,
        requiredPermissions: [{ action: 'read', resourceType: 'identity-provider' }],
        children: [
          {
            label: 'Add Identity Provider',
            path: AppRoute.SystemAdministration.Authentication.AddIdentityProvider,
            routePermission: { action: 'create', resourceType: 'identity-provider' },
          },
          {
            label: 'Edit Identity Provider',
            path: AppRoute.SystemAdministration.Authentication.EditIdentityProvider,
            routePermission: { action: 'update', resourceType: 'identity-provider' },
          },
          {
            label: 'Edit Group Mapping',
            path: AppRoute.SystemAdministration.Authentication.EditGroupMapping,
            hidden: true,
          },
          {
            label: 'Identity Provider Details',
            path: AppRoute.SystemAdministration.Authentication.IdentityProviderDetail,
          },
          {
            label: 'Identity Provider Details Tab',
            path: AppRoute.SystemAdministration.Authentication.IdentityProviderDetailTab,
            hidden: true,
          },
        ],
      },
      {
        label: 'Settings',
        path: AppRoute.SystemAdministration.Settings,
        icon: <RhUiSettingsIcon />,
        requiredPermissions: [{ action: 'read', resourceType: 'setting' }],
        children: [
          {
            label: 'Settings Tab',
            path: AppRoute.SystemAdministration.SettingsTab,
            hidden: true,
          },
        ],
      },
    ],
  },
  {
    label: 'Support',
    path: AppRoute.Support.Root,
    children: [
      {
        label: 'Documentation',
        path: AppRoute.Support.Documentation,
      },
      {
        label: 'FAQ',
        path: AppRoute.Support.FAQ,
      },
      {
        label: 'Glossary',
        path: AppRoute.Support.Glossary,
      },
    ],
  },
  // Hidden routes (not shown in navigation, but path needed for active-state matching)
  {
    label: 'Edit Workflow',
    path: AppRoute.WorkflowBuilder.Edit,
    hidden: true,
  },
  {
    label: 'Execution Detail',
    path: AppRoute.Executions.Execution,
    hidden: true,
  },
  {
    label: 'Credential Detail',
    path: AppRoute.Configuration.Credentials.Detail,
    hidden: true,
  },
  {
    label: 'Credential Detail Tab',
    path: AppRoute.Configuration.Credentials.DetailTab,
    hidden: true,
  },
  {
    label: 'My Profile',
    path: AppRoute.MyProfile.Root,
    hidden: true,
  },
  {
    label: 'My Profile Tab',
    path: AppRoute.MyProfile.Tab,
    hidden: true,
  },
] as const
