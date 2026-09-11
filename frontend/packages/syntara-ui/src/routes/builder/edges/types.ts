import type { EdgeProps } from '@xyflow/react'

import type { FlowPosition, OnAddNodeFromEdge } from '../types'

/**
 * Shared edge data interface used by all edge types
 */
export type EdgeData = {
  onAddNode?: OnAddNodeFromEdge
  isActive?: boolean
  isPending?: boolean
  executionStatus?: 'passed' | 'pending'
}

/**
 * Button edge data interface (different from regular edges)
 */
export type ButtonEdgeData = {
  /** Called when [+] is clicked; optional position is the [+] location in flow coordinates (for placing the new node) */
  onButtonClick?: (position?: FlowPosition) => void
  isActive?: boolean
  sourceHandle?: string
}

/**
 * Base edge props interface that all edge components extend
 */
export type BaseEdgeProps = {
  data?: EdgeData
} & Omit<EdgeProps, 'data'>

/**
 * Button edge props interface
 */
export type ButtonEdgeProps = {
  data?: ButtonEdgeData
} & Omit<EdgeProps, 'data'>
