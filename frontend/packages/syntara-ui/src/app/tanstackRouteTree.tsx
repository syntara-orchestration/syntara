import { rootRoute } from './routes/__root'
import { accessManagementRoutes } from './routes/access-management'
import { approvalsRoutes } from './routes/approvals'
import { authenticationRoutes } from './routes/authentication'
import { builderRoutes } from './routes/builder'
import { configurationRoutes } from './routes/configuration'
import { executionPlaneRoutes } from './routes/execution-plane'
import { executionsRoutes } from './routes/executions'
import { featureFlagDemoRoutes } from './routes/feature-flag-demo'
import { myProfileRoutes } from './routes/my-profile'
import { settingsRoutes } from './routes/settings'
import { workflowsRoutes } from './routes/workflows'

export const buildTanStackRouteTree = () =>
  rootRoute.addChildren([
    ...builderRoutes,
    ...workflowsRoutes,
    ...executionsRoutes,
    ...featureFlagDemoRoutes,
    ...approvalsRoutes,
    ...executionPlaneRoutes,
    ...configurationRoutes,
    ...settingsRoutes,
    ...authenticationRoutes,
    ...accessManagementRoutes,
    ...myProfileRoutes,
  ])
