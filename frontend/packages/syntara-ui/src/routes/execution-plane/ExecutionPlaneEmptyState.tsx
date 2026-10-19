import { useNavigate } from '@tanstack/react-router'

import { AppRoute } from '../../app/AppRoute'
import { SynEmptyStateNoData } from '../../components/states/SynEmptyStateNoData'
import { detachPromise } from '../../utils/detachPromise'

export function ExecutionPlaneEmptyState({ canConfigure = true }: Readonly<{ canConfigure?: boolean }>) {
  const navigate = useNavigate()
  return (
    <SynEmptyStateNoData
      title="No execution targets yet"
      description="Configure an OpenShift integration to register an execution target on the Execution Plane."
      buttonText={canConfigure ? 'Configure integration' : undefined}
      addData={
        canConfigure ? () => detachPromise(navigate({ to: AppRoute.Configuration.Integrations.Configure })) : undefined
      }
    />
  )
}
