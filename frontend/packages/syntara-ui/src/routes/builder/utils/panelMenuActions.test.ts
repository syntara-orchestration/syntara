import type { Node } from '@xyflow/react'
import { describe, expect, it, vi } from 'vitest'

import type { NodeType } from '../../workflows/canvas/nodes/NodeType'

import { buildPanelMenuActions } from './panelMenuActions'

describe('buildPanelMenuActions', () => {
  it('returns empty actions in add mode', () => {
    const actions = buildPanelMenuActions('add', undefined, [], vi.fn())
    expect(actions).toEqual([])
  })

  it('filters out the view-details action', () => {
    const node: Node<NodeType['data']> = {
      id: 'task-1',
      type: 'task',
      position: { x: 0, y: 0 },
      data: { id: 'task-1', type: 'task', name: 'Task' },
    }

    const actions = buildPanelMenuActions(
      'edit',
      node,
      [
        { id: 'view-details', label: 'View step details', onClick: vi.fn() },
        { id: 'delete', label: 'Delete', onClick: vi.fn(), variant: 'danger' },
      ],
      vi.fn()
    )

    expect(actions.find((a) => a.id === 'view-details')).toBeUndefined()
    expect(actions.find((a) => a.id === 'delete')).toBeDefined()
  })

  it('wraps delete action to close panel', () => {
    const onClose = vi.fn()
    const onDelete = vi.fn()
    const node: Node<NodeType['data']> = {
      id: 'task-1',
      type: 'task',
      position: { x: 0, y: 0 },
      data: { id: 'task-1', type: 'task', name: 'Task' },
    }

    const actions = buildPanelMenuActions(
      'edit',
      node,
      [
        {
          id: 'delete',
          label: 'Delete',
          onClick: onDelete,
          variant: 'danger',
        },
      ],
      onClose
    )

    expect(actions).toHaveLength(1)
    actions[0].onClick()
    expect(onDelete).toHaveBeenCalledTimes(1)
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
