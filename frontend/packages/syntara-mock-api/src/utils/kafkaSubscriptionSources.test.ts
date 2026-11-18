import { describe, expect, it } from 'vitest'

import { projectKafkaSources } from './kafkaSubscriptionSources'

const source = {
  trigger_node_id: 'subscribe',
  source_id: 'source-1',
  generation: 1,
  configuration_revision: 1,
  integration_id: 'integration-1',
  topic: 'orders',
  group_id: 'published-A',
}
const definition = (topic = 'orders', groupId: string | null = null) => ({
  triggers: [
    {
      id: 'subscribe',
      type: 'event_subscribe_trigger',
      parameters: { integration_id: 'integration-1', topic, group_id: groupId },
    },
  ],
})

describe('mock Kafka projection', () => {
  it('retains the established group and source generation when the next definition omits it', () => {
    expect(projectKafkaSources('workflow-1', definition(), [source])).toEqual([
      { ...source, configuration_revision: 2 },
    ])
  })
  it('rejects a stale explicit override like the backend', () => {
    expect(() => projectKafkaSources('workflow-1', definition('orders', 'draft-B'), [source])).toThrow(
      'fixed after the first successful publication'
    )
  })
  it('allocates a new source and group for a replacement topic', () => {
    const [replacement] = projectKafkaSources('workflow-1', definition('replacement'), [source])
    expect(replacement?.generation).toBe(2)
    expect(replacement?.topic).toBe('replacement')
    expect(replacement?.source_id).not.toBe(source.source_id)
    expect(replacement?.group_id).not.toBe(source.group_id)
  })
  it('does not expose retired subscriptions after a trigger is removed', () => {
    expect(projectKafkaSources('workflow-1', { triggers: [] }, [source])).toEqual([])
  })
})
