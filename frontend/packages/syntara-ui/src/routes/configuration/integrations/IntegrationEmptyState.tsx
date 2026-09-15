import { useNavigate } from '@tanstack/react-router'

import { AppRoute } from '../../../app/AppRoute'
import { SynEmptyStateNoData } from '../../../components/states/SynEmptyStateNoData'
import { detachPromise } from '../../../utils/detachPromise'

export function IntegrationEmptyState({ canCreate = true }: Readonly<{ canCreate?: boolean }>) {
  const navigate = useNavigate()
  return (
    <SynEmptyStateNoData
      title="No integrations yet"
      description="Configure integrations to connect external tools and services for use in workflows."
      buttonText={canCreate ? 'Configure integration' : undefined}
      addData={
        canCreate ? () => detachPromise(navigate({ to: AppRoute.Configuration.Integrations.Configure })) : undefined
      }
    />
  )
}
