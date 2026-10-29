import { AppRoute } from '../../../app/AppRoute'
import { SynEmptyStateNoData } from '../../../components/states/SynEmptyStateNoData'

export function IntegrationEmptyState({ canCreate = true }: Readonly<{ canCreate?: boolean }>) {
  return (
    <SynEmptyStateNoData
      title="No integrations yet"
      description="Configure integrations to connect external tools and services for use in workflows."
      buttonText={canCreate ? 'Configure integration' : undefined}
      linkTo={canCreate ? AppRoute.Configuration.Integrations.Configure : undefined}
    />
  )
}
