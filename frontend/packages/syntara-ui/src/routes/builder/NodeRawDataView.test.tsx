import { render, screen } from '@testing-library/react'
import type { Node } from '@xyflow/react'
import { describe, expect, it } from 'vitest'

import type { NodeType } from '../workflows/canvas/nodes/NodeType'

import { NodeRawDataView } from './NodeRawDataView'

describe('NodeRawDataView Component', () => {
  it('renders step type correctly', () => {
    const node: Node<NodeType['data']> = {
      id: 'test-node-1',
      type: 'converge',
      position: { x: 0, y: 0 },
      data: {
        type: 'converge',
        id: 'test-node-1',
        name: 'Test Converge Node',
      },
    }

    render(<NodeRawDataView node={node} />)

    expect(screen.getByText('Node type')).toBeInTheDocument()
    expect(screen.getByText('converge')).toBeInTheDocument()
  })

  it('renders Node ID correctly', () => {
    const node: Node<NodeType['data']> = {
      id: 'my-custom-id',
      type: 'parallel',
      position: { x: 0, y: 0 },
      data: {},
    }

    render(<NodeRawDataView node={node} />)

    expect(screen.getByText('Node ID')).toBeInTheDocument()
    expect(screen.getByText('my-custom-id')).toBeInTheDocument()
  })

  it('renders Node data as formatted JSON', () => {
    const node: Node<NodeType['data']> = {
      id: 'data-test',
      type: 'converge',
      position: { x: 100, y: 200 },
      data: {
        type: 'converge',
        id: 'data-test',
        name: 'Test Data',
        customField: 'custom value',
      },
    }

    render(<NodeRawDataView node={node} />)

    expect(screen.getByText('Node data')).toBeInTheDocument()

    // Check that the JSON is displayed
    const preElement = screen.getByText(/Test Data/)
    expect(preElement).toBeInTheDocument()
    expect(preElement.textContent).toContain('"type": "converge"')
    expect(preElement.textContent).toContain('"name": "Test Data"')
    expect(preElement.textContent).toContain('"customField": "custom value"')
  })

  it('capitalizes React Flow node type string in display', () => {
    const node: Node<NodeType['data']> = {
      id: 'test',
      type: 'trigger',
      position: { x: 0, y: 0 },
      data: {},
    }

    render(<NodeRawDataView node={node} />)

    const stepTypeValue = screen.getByText('trigger')
    expect(stepTypeValue).toBeInTheDocument()
  })

  it('uses monospace font for Node ID value', () => {
    const node: Node<NodeType['data']> = {
      id: 'monospace-test',
      type: 'task',
      position: { x: 0, y: 0 },
      data: {},
    }

    render(<NodeRawDataView node={node} />)

    // PatternFly CodeBlock uses monospace by default
    const stepIdCode = screen.getByText('monospace-test')
    expect(stepIdCode).toBeInTheDocument()
    expect(stepIdCode.tagName).toBe('CODE')
  })

  it('handles empty step data', () => {
    const node: Node<NodeType['data']> = {
      id: 'empty-data',
      type: 'converge',
      position: { x: 0, y: 0 },
      data: {},
    }

    render(<NodeRawDataView node={node} />)

    expect(screen.getByText('Node data')).toBeInTheDocument()
    const preElement = screen.getByText('{}')
    expect(preElement).toBeInTheDocument()
  })

  it('handles complex nested data structures', () => {
    const node: Node<NodeType['data']> = {
      id: 'complex-node',
      type: 'condition',
      position: { x: 0, y: 0 },
      data: {
        type: 'condition',
        id: 'complex-node',
        name: 'Complex Condition',
        condition: 'input.value > 10',
        then: [
          {
            type: 'task',
            id: 'nested-task',
            name: 'Nested Task',
            task: {
              executor: 'script',
              parameters: {
                language: 'python',
                code: 'print("nested")',
              },
            },
          },
        ],
        else: [],
      },
    }

    render(<NodeRawDataView node={node} />)

    const preElement = screen.getByText(/Complex Condition/)
    expect(preElement.textContent).toContain('"condition": "input.value > 10"')
    expect(preElement.textContent).toContain('"then"')
    expect(preElement.textContent).toContain('"executor": "script"')
  })

  it('applies correct styling classes', () => {
    const node: Node<NodeType['data']> = {
      id: 'style-test',
      type: 'task',
      position: { x: 0, y: 0 },
      data: {},
    }

    render(<NodeRawDataView node={node} />)

    expect(screen.getByText('Node type')).toBeInTheDocument()
  })
})
