import { useNavigate } from '@tanstack/react-router'

import { AppRoute } from '../../app/AppRoute'
import { SynEmptyStateNoData } from '../../components/states/SynEmptyStateNoData'
import { detachPromise } from '../../utils/detachPromise'

export function ExecutionPlaneEmptyState({ canConfigure = true }: Readonly<{ canConfigure?: boolean }>) {
  const navigate = useNavigate()
  return (
    <SynEmptyStateNoData
      title="No execution targets yet"
      description="Configure an execution target to register compute capacity on the installed OpenShift cluster."
      buttonText={canConfigure ? 'Configure execution target' : undefined}
      addData={canConfigure ? () => detachPromise(navigate({ to: AppRoute.ExecutionPlane.Create })) : undefined}
    />
  )
}
