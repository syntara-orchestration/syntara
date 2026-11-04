import { type ReactNode } from 'react'

import { KafkaSubscribeResourceContext } from './kafkaSubscribeResourceContext'
import { useKafkaSubscribeResources } from './useKafkaSubscribeResources'

export function KafkaSubscribeFormProvider({
  projectId,
  children,
}: Readonly<{ projectId?: string; children: ReactNode }>) {
  const resources = useKafkaSubscribeResources(projectId)
  return <KafkaSubscribeResourceContext value={resources}>{children}</KafkaSubscribeResourceContext>
}
