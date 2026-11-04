import { createContext } from 'react'

import type { KafkaSubscribeResources } from './useKafkaSubscribeResources'

export const KafkaSubscribeResourceContext = createContext<KafkaSubscribeResources | null>(null)
