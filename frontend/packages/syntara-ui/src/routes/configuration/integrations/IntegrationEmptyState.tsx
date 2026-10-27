import { useNavigate } from '@tanstack/react-router'

import { AppRoute } from '../../../app/AppRoute'
import { SynEmptyStateNoData } from '../../../components/states/SynEmptyStateNoData'
import { detachPromise } from '../../../utils/detachPromise'

export function IntegrationEmptyState({ canCreate = true }: Readonly<{ canCreate?: boolean }>) {
  const navigate = useNavigate()
  return (
    <SynEmptyStateNoData
      title="No integrations in this view"
      description="Select Kafka in the Integration type filter to view Kafka connections, or configure a new integration."
      buttonText={canCreate ? 'Configure integration' : undefined}
      addData={
        canCreate ? () => detachPromise(navigate({ to: AppRoute.Configuration.Integrations.Configure })) : undefined
      }
    />
  )
}
