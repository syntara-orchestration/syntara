import { ActivityTypeEnum } from '@syntara/contracts'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { RegistryNodeId } from '../../constants'

import { AddNodePanel } from './AddNodePanel'
import { NodeRegistry } from './registry/NodeRegistry'
import registerActionNode from './registry/nodes/registerActionNode'
import registerKafkaPublishNode from './registry/nodes/registerKafkaPublishNode'

describe('Kafka Publish action selection', () => {
  beforeEach(() => {
    NodeRegistry.clear()
    registerActionNode()
    registerKafkaPublishNode()
  })

  afterEach(() => {
    NodeRegistry.clear()
  })

  it('shows Kafka Publish inside Action before REST API and Script', async () => {
    const user = userEvent.setup()
    const { container } = render(<AddNodePanel onClose={vi.fn()} onSelectNode={vi.fn()} />)

    expect(screen.queryByRole('button', { name: 'Kafka Publish' })).not.toBeInTheDocument()
    expect(
      screen.getByText('Run scripts, make API calls, invoke another published workflow, or publish messages to Kafka.')
    ).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()

    await user.click(screen.getByRole('button', { name: 'Action' }))

    expect(screen.getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent)).toEqual([
      'Kafka Publish',
      'REST API',
      'Script',
    ])
    const kafkaOption = screen.getByRole('button', { name: 'Kafka Publish' })
    expect(within(kafkaOption).getByText('Publish a structured message to a Kafka topic.')).toBeInTheDocument()
    expect(screen.getByText('Developer Preview')).toBeInTheDocument()
    expect(await axe(container)).toHaveNoViolations()
  })

  it('routes keyboard selection to the registered Kafka Publish step', async () => {
    const user = userEvent.setup()
    const onSelectNode = vi.fn()
    render(<AddNodePanel onClose={vi.fn()} onSelectNode={onSelectNode} />)

    await user.click(screen.getByRole('button', { name: 'Action' }))
    screen.getByRole('button', { name: 'Kafka Publish' }).focus()
    await user.keyboard('{Enter}')

    expect(onSelectNode).toHaveBeenCalledTimes(1)
    expect(onSelectNode).toHaveBeenCalledWith(ActivityTypeEnum.KAFKA_PUBLISH, null)
    expect(screen.queryByRole('button', { name: 'Kafka Publish' })).not.toBeInTheDocument()
  })

  it('keeps the REST API and Script forms routed through Action', async () => {
    const user = userEvent.setup()
    const onSelectNode = vi.fn()
    render(<AddNodePanel onClose={vi.fn()} onSelectNode={onSelectNode} sourceNodeId="trigger-0" />)

    await user.click(screen.getByRole('button', { name: 'Action' }))
    await user.click(screen.getByRole('button', { name: 'REST API' }))
    expect(onSelectNode).toHaveBeenLastCalledWith(RegistryNodeId.ACTION, RegistryNodeId.ACTION_API)

    await user.click(screen.getByRole('button', { name: 'Action' }))
    await user.click(screen.getByRole('button', { name: 'Script' }))
    expect(onSelectNode).toHaveBeenLastCalledWith(RegistryNodeId.ACTION, RegistryNodeId.ACTION_SCRIPT)
  })
})
