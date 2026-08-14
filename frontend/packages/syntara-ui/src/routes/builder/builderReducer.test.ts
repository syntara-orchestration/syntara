import type { Node } from '@xyflow/react'
import { describe, expect, it } from 'vitest'

import type { NodeType } from '../workflows/canvas/nodes/NodeType'

import { builderReducer, getInitialBuilderState, type BuilderAction, type BuilderState } from './builderReducer'

describe('builderReducer', () => {
  const initialState = getInitialBuilderState()

  describe('Dialog actions', () => {
    it('SET_CONFIRM_DIALOG sets confirmDialogOpen', () => {
      const action: BuilderAction = { type: 'SET_CONFIRM_DIALOG', payload: true }
      const result = builderReducer(initialState, action)
      expect(result.confirmDialogOpen).toBe(true)
    })

    it('SET_DELETE_DIALOG sets deleteDialogOpen', () => {
      const action: BuilderAction = { type: 'SET_DELETE_DIALOG', payload: true }
      const result = builderReducer(initialState, action)
      expect(result.deleteDialogOpen).toBe(true)
    })
  })

  describe('Panel toggle actions', () => {
    it('SET_DETAILS_OPEN sets detailsOpen', () => {
      const action: BuilderAction = { type: 'SET_DETAILS_OPEN', payload: true }
      const result = builderReducer(initialState, action)
      expect(result.detailsOpen).toBe(true)
    })

    it('TOGGLE_DETAILS toggles detailsOpen and closes other panels', () => {
      const stateWithPanelsOpen: BuilderState = {
        ...initialState,
        detailsOpen: false,
        addNodePanelOpen: true,
        historyCardOpen: true,
        selectedNode: { id: 'node-1' } as Node<NodeType['data']>,
        nodeEditorMode: 'edit',
        nodeEditorNodeTypeId: 'script',
        nodeEditorNodeSubtypeId: null,
      }

      const action: BuilderAction = { type: 'TOGGLE_DETAILS' }
      const result = builderReducer(stateWithPanelsOpen, action)

      expect(result.detailsOpen).toBe(true)
      expect(result.addNodePanelOpen).toBe(false)
      expect(result.historyCardOpen).toBe(false)
      expect(result.selectedNode).toBeNull()
      expect(result.nodeEditorMode).toBeNull()
      expect(result.nodeEditorNodeTypeId).toBeNull()
      expect(result.nodeEditorNodeSubtypeId).toBeNull()
    })

    it('TOGGLE_DETAILS when already open preserves panel state', () => {
      const stateWithDetailsOpen: BuilderState = {
        ...initialState,
        detailsOpen: true,
        addNodePanelOpen: true,
        historyCardOpen: true,
        selectedNode: { id: 'node-1' } as Node<NodeType['data']>,
        nodeEditorMode: 'edit',
        nodeEditorNodeTypeId: 'script',
        nodeEditorNodeSubtypeId: 'python',
      }

      const action: BuilderAction = { type: 'TOGGLE_DETAILS' }
      const result = builderReducer(stateWithDetailsOpen, action)

      expect(result.detailsOpen).toBe(false)
      // When closing, keep the other panel states
      expect(result.addNodePanelOpen).toBe(true)
      expect(result.historyCardOpen).toBe(true)
      expect(result.selectedNode).toEqual({ id: 'node-1' })
      expect(result.nodeEditorMode).toBe('edit')
      expect(result.nodeEditorNodeTypeId).toBe('script')
      expect(result.nodeEditorNodeSubtypeId).toBe('python')
    })

    it('SET_HISTORY_CARD_OPEN sets historyCardOpen', () => {
      const action: BuilderAction = { type: 'SET_HISTORY_CARD_OPEN', payload: true }
      const result = builderReducer(initialState, action)
      expect(result.historyCardOpen).toBe(true)
    })

    it('TOGGLE_HISTORY toggles historyCardOpen and closes other panels', () => {
      const stateWithPanelsOpen: BuilderState = {
        ...initialState,
        historyCardOpen: false,
        addNodePanelOpen: true,
        detailsOpen: true,
        selectedNode: { id: 'node-1' } as Node<NodeType['data']>,
        nodeEditorMode: 'edit',
        nodeEditorNodeTypeId: 'script',
        nodeEditorNodeSubtypeId: null,
      }

      const action: BuilderAction = { type: 'TOGGLE_HISTORY' }
      const result = builderReducer(stateWithPanelsOpen, action)

      expect(result.historyCardOpen).toBe(true)
      expect(result.addNodePanelOpen).toBe(false)
      expect(result.detailsOpen).toBe(false)
      expect(result.selectedNode).toBeNull()
      expect(result.nodeEditorMode).toBeNull()
    })

    it('TOGGLE_HISTORY when already open preserves panel state', () => {
      const stateWithHistoryOpen: BuilderState = {
        ...initialState,
        historyCardOpen: true,
        addNodePanelOpen: true,
        detailsOpen: true,
        selectedNode: { id: 'node-1' } as Node<NodeType['data']>,
        nodeEditorMode: 'edit',
        nodeEditorNodeTypeId: 'script',
        nodeEditorNodeSubtypeId: 'python',
      }

      const action: BuilderAction = { type: 'TOGGLE_HISTORY' }
      const result = builderReducer(stateWithHistoryOpen, action)

      expect(result.historyCardOpen).toBe(false)
      // When closing, keep the other panel states
      expect(result.addNodePanelOpen).toBe(true)
      expect(result.detailsOpen).toBe(true)
      expect(result.selectedNode).toEqual({ id: 'node-1' })
      expect(result.nodeEditorMode).toBe('edit')
    })
  })

  describe('Execution and UI state actions', () => {
    it('SET_KEBAB_OPEN sets isKebabOpen', () => {
      const action: BuilderAction = { type: 'SET_KEBAB_OPEN', payload: true }
      const result = builderReducer(initialState, action)
      expect(result.isKebabOpen).toBe(true)
    })

    it('SET_ADD_NODE_PANEL sets addNodePanelOpen', () => {
      const action: BuilderAction = { type: 'SET_ADD_NODE_PANEL', payload: true }
      const result = builderReducer(initialState, action)
      expect(result.addNodePanelOpen).toBe(true)
    })
  })

  describe('Node editor actions', () => {
    it('OPEN_NODE_EDITOR_ADD sets editor to add mode', () => {
      const action: BuilderAction = {
        type: 'OPEN_NODE_EDITOR_ADD',
        payload: { nodeTypeId: 'script', nodeSubtypeId: 'python' },
      }
      const result = builderReducer(initialState, action)

      expect(result.nodeEditorMode).toBe('add')
      expect(result.nodeEditorNodeTypeId).toBe('script')
      expect(result.nodeEditorNodeSubtypeId).toBe('python')
      expect(result.selectedNode).toBeNull()
      expect(result.addNodePanelOpen).toBe(false)
    })

    it('CLOSE_NODE_EDITOR clears editor state', () => {
      const stateWithEditor: BuilderState = {
        ...initialState,
        nodeEditorMode: 'edit',
        nodeEditorNodeTypeId: 'script',
        nodeEditorNodeSubtypeId: 'python',
        selectedNode: { id: 'node-1' } as Node<NodeType['data']>,
      }

      const action: BuilderAction = { type: 'CLOSE_NODE_EDITOR' }
      const result = builderReducer(stateWithEditor, action)

      expect(result.nodeEditorMode).toBeNull()
      expect(result.nodeEditorNodeTypeId).toBeNull()
      expect(result.nodeEditorNodeSubtypeId).toBeNull()
      expect(result.selectedNode).toBeNull()
    })

    it('SET_SELECTED_NODE sets selectedNode', () => {
      const node = { id: 'node-1', type: 'script' } as Node<NodeType['data']>
      const action: BuilderAction = { type: 'SET_SELECTED_NODE', payload: node }
      const result = builderReducer(initialState, action)

      expect(result.selectedNode).toBe(node)
    })
  })

  describe('Edge and node connection actions', () => {
    it('SET_SOURCE_NODE_ID sets sourceNodeId', () => {
      const action: BuilderAction = { type: 'SET_SOURCE_NODE_ID', payload: 'source-1' }
      const result = builderReducer(initialState, action)
      expect(result.sourceNodeId).toBe('source-1')
    })

    it('SET_TARGET_NODE_ID sets targetNodeId', () => {
      const action: BuilderAction = { type: 'SET_TARGET_NODE_ID', payload: 'target-1' }
      const result = builderReducer(initialState, action)
      expect(result.targetNodeId).toBe('target-1')
    })

    it('SET_EDGE_ID_TO_REPLACE sets edgeIdToReplace', () => {
      const action: BuilderAction = { type: 'SET_EDGE_ID_TO_REPLACE', payload: 'edge-1' }
      const result = builderReducer(initialState, action)
      expect(result.edgeIdToReplace).toBe('edge-1')
    })

    it('SET_SOURCE_HANDLE sets sourceHandle', () => {
      const action: BuilderAction = { type: 'SET_SOURCE_HANDLE', payload: 'loop' }
      const result = builderReducer(initialState, action)
      expect(result.sourceHandle).toBe('loop')
    })

    it('SET_TARGET_HANDLE sets targetHandle', () => {
      const action: BuilderAction = { type: 'SET_TARGET_HANDLE', payload: 'target' }
      const result = builderReducer(initialState, action)
      expect(result.targetHandle).toBe('target')
    })

    it('SET_REPLACEMENT_NODE_ID sets replacementNodeId', () => {
      const action: BuilderAction = { type: 'SET_REPLACEMENT_NODE_ID', payload: 'replacement-1' }
      const result = builderReducer(initialState, action)
      expect(result.replacementNodeId).toBe('replacement-1')
    })
  })

  describe('Workflow metadata actions', () => {
    it('SET_WORKFLOW_NAME sets workflowName', () => {
      const action: BuilderAction = { type: 'SET_WORKFLOW_NAME', payload: 'My Workflow' }
      const result = builderReducer(initialState, action)
      expect(result.workflowName).toBe('My Workflow')
    })

    it('SET_WORKFLOW_DESCRIPTION sets workflowDescription', () => {
      const action: BuilderAction = { type: 'SET_WORKFLOW_DESCRIPTION', payload: 'Description' }
      const result = builderReducer(initialState, action)
      expect(result.workflowDescription).toBe('Description')
    })
  })

  describe('Complex panel actions', () => {
    it('OPEN_ADD_NODE_FROM_EDGE sets up state for adding node from edge', () => {
      const action: BuilderAction = {
        type: 'OPEN_ADD_NODE_FROM_EDGE',
        payload: {
          sourceId: 'source-1',
          targetId: 'target-1',
          edgeId: 'edge-1',
          handle: 'loop',
          targetHandle: 'target',
          desiredPosition: { x: 100, y: 200 },
        },
      }
      const result = builderReducer(initialState, action)

      expect(result.sourceNodeId).toBe('source-1')
      expect(result.targetNodeId).toBe('target-1')
      expect(result.edgeIdToReplace).toBe('edge-1')
      expect(result.sourceHandle).toBe('loop')
      expect(result.targetHandle).toBe('target')
      expect(result.newNodeDesiredPosition).toEqual({ x: 100, y: 200 })
      expect(result.addNodePanelOpen).toBe(true)
      expect(result.detailsOpen).toBe(false)
      expect(result.historyCardOpen).toBe(false)
    })

    it('OPEN_ADD_NODE_FROM_EDGE with minimal payload uses defaults', () => {
      const action: BuilderAction = {
        type: 'OPEN_ADD_NODE_FROM_EDGE',
        payload: {
          sourceId: 'source-1',
        },
      }
      const result = builderReducer(initialState, action)

      expect(result.sourceNodeId).toBe('source-1')
      expect(result.targetNodeId).toBeNull() // undefined → null
      expect(result.edgeIdToReplace).toBeNull() // undefined → null
      expect(result.sourceHandle).toBeUndefined() // undefined → undefined
      expect(result.targetHandle).toBeUndefined()
      expect(result.newNodeDesiredPosition).toBeNull() // undefined → null
      expect(result.addNodePanelOpen).toBe(true)
    })

    it('CLEAR_NEW_NODE_DESIRED_POSITION clears newNodeDesiredPosition', () => {
      const stateWithPosition: BuilderState = {
        ...initialState,
        newNodeDesiredPosition: { x: 100, y: 200 },
      }

      const action: BuilderAction = { type: 'CLEAR_NEW_NODE_DESIRED_POSITION' }
      const result = builderReducer(stateWithPosition, action)

      expect(result.newNodeDesiredPosition).toBeNull()
    })

    it('SET_NEW_NODE_DESIRED_POSITION sets newNodeDesiredPosition', () => {
      const action: BuilderAction = { type: 'SET_NEW_NODE_DESIRED_POSITION', payload: { x: 150, y: 250 } }
      const result = builderReducer(initialState, action)

      expect(result.newNodeDesiredPosition).toEqual({ x: 150, y: 250 })
    })

    it('OPEN_ADD_NODE_PANEL opens panel with source and replacement nodes', () => {
      const action: BuilderAction = {
        type: 'OPEN_ADD_NODE_PANEL',
        payload: { sourceNodeId: 'source-1', replacementNodeId: 'replacement-1' },
      }
      const result = builderReducer(initialState, action)

      expect(result.addNodePanelOpen).toBe(true)
      expect(result.sourceNodeId).toBe('source-1')
      expect(result.replacementNodeId).toBe('replacement-1')
      expect(result.targetNodeId).toBeNull()
      expect(result.edgeIdToReplace).toBeNull()
      expect(result.detailsOpen).toBe(false)
      expect(result.historyCardOpen).toBe(false)
    })

    it('OPEN_ADD_NODE_PANEL opens panel with optional sourceHandle for branching nodes', () => {
      const action: BuilderAction = {
        type: 'OPEN_ADD_NODE_PANEL',
        payload: { sourceNodeId: 'condition-1', replacementNodeId: null, sourceHandle: 'true' },
      }
      const result = builderReducer(initialState, action)

      expect(result.addNodePanelOpen).toBe(true)
      expect(result.sourceNodeId).toBe('condition-1')
      expect(result.sourceHandle).toBe('true')
      expect(result.replacementNodeId).toBeNull()
      expect(result.targetNodeId).toBeNull()
      expect(result.edgeIdToReplace).toBeNull()
    })

    it('CLOSE_ADD_NODE_PANEL clears all panel-related state', () => {
      const stateWithPanel: BuilderState = {
        ...initialState,
        addNodePanelOpen: true,
        sourceNodeId: 'source-1',
        targetNodeId: 'target-1',
        edgeIdToReplace: 'edge-1',
        sourceHandle: 'loop',
        targetHandle: 'target',
        replacementNodeId: 'replacement-1',
        newNodeDesiredPosition: { x: 100, y: 200 },
      }

      const action: BuilderAction = { type: 'CLOSE_ADD_NODE_PANEL' }
      const result = builderReducer(stateWithPanel, action)

      expect(result.addNodePanelOpen).toBe(false)
      expect(result.sourceNodeId).toBeNull()
      expect(result.targetNodeId).toBeNull()
      expect(result.edgeIdToReplace).toBeNull()
      expect(result.sourceHandle).toBeUndefined()
      expect(result.targetHandle).toBeUndefined()
      expect(result.replacementNodeId).toBeNull()
      expect(result.newNodeDesiredPosition).toBeNull()
    })

    it('CLOSE_OTHER_PANELS closes details and history panels', () => {
      const stateWithPanels: BuilderState = {
        ...initialState,
        selectedNode: { id: 'node-1' } as Node<NodeType['data']>,
        detailsOpen: true,
        historyCardOpen: true,
      }

      const action: BuilderAction = { type: 'CLOSE_OTHER_PANELS' }
      const result = builderReducer(stateWithPanels, action)

      expect(result.selectedNode).toBeNull()
      expect(result.detailsOpen).toBe(false)
      expect(result.historyCardOpen).toBe(false)
    })
  })

  describe('NODE_CLICK action', () => {
    it('opens replacement panel for generic node clicks', () => {
      const node = { id: 'generic-node-1', type: 'generic' } as Node<NodeType['data']>
      const action: BuilderAction = { type: 'NODE_CLICK', payload: { node, isGeneric: true } }
      const result = builderReducer(initialState, action)

      expect(result.addNodePanelOpen).toBe(true)
      expect(result.replacementNodeId).toBe('generic-node-1')
      expect(result.selectedNode).toBeNull()
      expect(result.detailsOpen).toBe(false)
      expect(result.historyCardOpen).toBe(false)
    })

    it('clears edge insertion context when clicking generic node', () => {
      // Start with state that has edge insertion context from OPEN_ADD_NODE_FROM_EDGE
      const stateWithEdgeContext: BuilderState = {
        ...initialState,
        targetNodeId: 'target-1',
        edgeIdToReplace: 'edge-1',
        sourceHandle: 'loop',
        targetHandle: 'target',
        sourceNodeId: 'source-1',
      }

      const node = { id: 'generic-node-1', type: 'generic' } as Node<NodeType['data']>
      const action: BuilderAction = { type: 'NODE_CLICK', payload: { node, isGeneric: true } }
      const result = builderReducer(stateWithEdgeContext, action)

      // Should clear edge insertion context to prevent mixing with replacement mode
      expect(result.targetNodeId).toBeNull()
      expect(result.edgeIdToReplace).toBeNull()
      expect(result.sourceHandle).toBeUndefined()
      expect(result.targetHandle).toBeUndefined()
      expect(result.sourceNodeId).toBeNull()
      // But still set replacement mode
      expect(result.replacementNodeId).toBe('generic-node-1')
      expect(result.addNodePanelOpen).toBe(true)
    })

    it('opens editor for non-generic node clicks', () => {
      const node = { id: 'task-1', type: 'script' } as Node<NodeType['data']>
      const action: BuilderAction = { type: 'NODE_CLICK', payload: { node, isGeneric: false } }
      const result = builderReducer(initialState, action)

      expect(result.selectedNode).toBe(node)
      expect(result.nodeEditorMode).toBe('edit')
      expect(result.addNodePanelOpen).toBe(false)
      expect(result.detailsOpen).toBe(false)
      expect(result.historyCardOpen).toBe(false)
      expect(result.replacementNodeId).toBeNull()
    })

    it('opens node editor in edit mode when viewingVersion is set', () => {
      const stateViewing: BuilderState = { ...initialState, viewingVersion: 2, versionHistoryOpen: true }
      const node = { id: 'task-1', type: 'script' } as Node<NodeType['data']>
      const action: BuilderAction = { type: 'NODE_CLICK', payload: { node, isGeneric: false } }
      const result = builderReducer(stateViewing, action)

      expect(result.versionHistoryOpen).toBe(true)
      expect(result.viewingVersion).toBe(2)
      expect(result.nodeEditorMode).toBe('edit')
      expect(result.selectedNode).toBe(node)
    })
  })

  describe('CLEAR_SELECTED_IF_DELETED action', () => {
    it('clears selectedNode if its ID is in deleted list', () => {
      const stateWithNode: BuilderState = {
        ...initialState,
        selectedNode: { id: 'node-to-delete' } as Node<NodeType['data']>,
      }

      const action: BuilderAction = { type: 'CLEAR_SELECTED_IF_DELETED', payload: ['node-to-delete', 'other-node'] }
      const result = builderReducer(stateWithNode, action)

      expect(result.selectedNode).toBeNull()
    })

    it('keeps selectedNode if its ID is not in deleted list', () => {
      const node = { id: 'node-to-keep' } as Node<NodeType['data']>
      const stateWithNode: BuilderState = {
        ...initialState,
        selectedNode: node,
      }

      const action: BuilderAction = { type: 'CLEAR_SELECTED_IF_DELETED', payload: ['node-1', 'node-2'] }
      const result = builderReducer(stateWithNode, action)

      expect(result.selectedNode).toBe(node)
    })

    it('returns state unchanged if no node is selected', () => {
      const action: BuilderAction = { type: 'CLEAR_SELECTED_IF_DELETED', payload: ['node-1'] }
      const result = builderReducer(initialState, action)

      expect(result).toBe(initialState)
    })
  })

  describe('INIT_WORKFLOW action', () => {
    it('initializes workflow metadata', () => {
      const action: BuilderAction = {
        type: 'INIT_WORKFLOW',
        payload: {
          name: 'My Workflow',
          description: 'Test Description',
        },
      }
      const result = builderReducer(initialState, action)

      expect(result.workflowName).toBe('My Workflow')
      expect(result.workflowDescription).toBe('Test Description')
    })

    it('resets UI state to prevent stale state from previous workflow', () => {
      // Start with state that has UI selections from a previous workflow
      const stateWithSelections: BuilderState = {
        ...initialState,
        selectedNode: { id: 'node-1', type: 'task' } as Node<NodeType['data']>,
        nodeEditorMode: 'edit',
        addNodePanelOpen: true,
        detailsOpen: true,
        historyCardOpen: true,
        sourceNodeId: 'source-1',
        targetNodeId: 'target-1',
        edgeIdToReplace: 'edge-1',
        sourceHandle: 'out',
        targetHandle: 'in',
        replacementNodeId: 'replacement-1',
        newNodeDesiredPosition: { x: 100, y: 200 },
      }

      const action: BuilderAction = {
        type: 'INIT_WORKFLOW',
        payload: {
          name: 'New Workflow',
          description: 'Fresh Start',
        },
      }

      const result = builderReducer(stateWithSelections, action)

      // Workflow metadata should be updated
      expect(result.workflowName).toBe('New Workflow')
      expect(result.workflowDescription).toBe('Fresh Start')

      // UI state should be reset to initial values
      expect(result.selectedNode).toBeNull()
      expect(result.nodeEditorMode).toBeNull()
      expect(result.nodeEditorNodeTypeId).toBeNull()
      expect(result.nodeEditorNodeSubtypeId).toBeNull()
      expect(result.addNodePanelOpen).toBe(false)
      expect(result.detailsOpen).toBe(false)
      expect(result.historyCardOpen).toBe(false)
      expect(result.sourceNodeId).toBeNull()
      expect(result.targetNodeId).toBeNull()
      expect(result.edgeIdToReplace).toBeNull()
      expect(result.sourceHandle).toBeUndefined()
      expect(result.targetHandle).toBeUndefined()
      expect(result.replacementNodeId).toBeNull()
      expect(result.newNodeDesiredPosition).toBeNull()
    })

    it('sets viewingVersion and versionHistoryOpen when initialViewVersion is provided', () => {
      const action: BuilderAction = {
        type: 'INIT_WORKFLOW',
        payload: { name: 'Test', description: '', initialViewVersion: 3 },
      }
      const result = builderReducer(initialState, action)

      expect(result.viewingVersion).toBe(3)
      expect(result.versionHistoryOpen).toBe(true)
    })

    it('resets viewingVersion when initialViewVersion is not provided', () => {
      const stateViewing: BuilderState = { ...initialState, viewingVersion: 2, versionHistoryOpen: true }
      const action: BuilderAction = {
        type: 'INIT_WORKFLOW',
        payload: { name: 'Test', description: '' },
      }
      const result = builderReducer(stateViewing, action)

      expect(result.viewingVersion).toBeNull()
      expect(result.versionHistoryOpen).toBe(false)
    })
  })

  describe('Most recent run panel actions', () => {
    it('SET_MOST_RECENT_EXECUTION sets mostRecentExecutionId and opens the panel', () => {
      const action: BuilderAction = {
        type: 'SET_MOST_RECENT_EXECUTION',
        payload: { executionId: 'exec-42' },
      }
      const result = builderReducer(initialState, action)

      expect(result.mostRecentExecutionId).toBe('exec-42')
      expect(result.mostRecentRunPanelOpen).toBe(true)
      expect(result.copiedRunActivityIds).toBeNull()
    })

    it('SET_MOST_RECENT_EXECUTION stores copiedRunActivityIds allowlist when provided', () => {
      const action: BuilderAction = {
        type: 'SET_MOST_RECENT_EXECUTION',
        payload: { executionId: 'exec-42', copiedRunActivityIds: ['task-1', 'cond-1'] },
      }
      const result = builderReducer(initialState, action)

      expect(result.copiedRunActivityIds).toEqual(new Set(['task-1', 'cond-1']))
    })

    it('CLOSE_MOST_RECENT_RUN_PANEL sets mostRecentRunPanelOpen to false', () => {
      const stateWithPanelOpen: BuilderState = {
        ...initialState,
        mostRecentRunPanelOpen: true,
        mostRecentExecutionId: 'exec-1',
      }

      const action: BuilderAction = { type: 'CLOSE_MOST_RECENT_RUN_PANEL' }
      const result = builderReducer(stateWithPanelOpen, action)

      expect(result.mostRecentRunPanelOpen).toBe(false)
      // execution id is preserved — only the panel visibility changes
      expect(result.mostRecentExecutionId).toBe('exec-1')
    })

    it('INIT_WORKFLOW resets mostRecentExecutionId and mostRecentRunPanelOpen even when they were set', () => {
      const stateWithExecution: BuilderState = {
        ...initialState,
        mostRecentExecutionId: 'exec-old',
        mostRecentRunPanelOpen: true,
        copiedRunActivityIds: new Set(['task-1']),
      }

      const action: BuilderAction = {
        type: 'INIT_WORKFLOW',
        payload: { name: 'Fresh', description: '' },
      }
      const result = builderReducer(stateWithExecution, action)

      expect(result.mostRecentExecutionId).toBeNull()
      expect(result.mostRecentRunPanelOpen).toBe(false)
      expect(result.copiedRunActivityIds).toBeNull()
    })
  })

  describe('Version history actions', () => {
    it('TOGGLE_VERSION_HISTORY opens panel and closes other panels', () => {
      const stateWithDetails = { ...initialState, detailsOpen: true, historyCardOpen: true }
      const result = builderReducer(stateWithDetails, { type: 'TOGGLE_VERSION_HISTORY' })

      expect(result.versionHistoryOpen).toBe(true)
      expect(result.detailsOpen).toBe(false)
      expect(result.historyCardOpen).toBe(false)
      expect(result.addNodePanelOpen).toBe(false)
    })

    it('TOGGLE_VERSION_HISTORY closes panel when already open', () => {
      const stateWithPanel = { ...initialState, versionHistoryOpen: true }
      const result = builderReducer(stateWithPanel, { type: 'TOGGLE_VERSION_HISTORY' })

      expect(result.versionHistoryOpen).toBe(false)
    })

    it('SET_VERSION_HISTORY_OPEN sets versionHistoryOpen', () => {
      const result = builderReducer(initialState, { type: 'SET_VERSION_HISTORY_OPEN', payload: true })
      expect(result.versionHistoryOpen).toBe(true)
    })

    it('SET_VIEWING_VERSION sets viewingVersion', () => {
      const result = builderReducer(initialState, { type: 'SET_VIEWING_VERSION', payload: 3 })
      expect(result.viewingVersion).toBe(3)
    })

    it('EXIT_VERSION_VIEW resets viewingVersion to null', () => {
      const stateViewing = { ...initialState, viewingVersion: 2 }
      const result = builderReducer(stateViewing, { type: 'EXIT_VERSION_VIEW' })
      expect(result.viewingVersion).toBeNull()
    })
  })

  describe('getInitialBuilderState', () => {
    it('returns initial state with expected defaults', () => {
      const state = getInitialBuilderState()

      expect(state.confirmDialogOpen).toBe(false)
      expect(state.deleteDialogOpen).toBe(false)
      expect(state.detailsOpen).toBe(false)
      expect(state.historyCardOpen).toBe(false)
      expect(state.isKebabOpen).toBe(false)
      expect(state.addNodePanelOpen).toBe(false)
      expect(state.nodeEditorMode).toBeNull()
      expect(state.selectedNode).toBeNull()
      expect(state.workflowName).toBe('')
      expect(state.workflowDescription).toBe('')
    })
  })

  describe('Validation error actions', () => {
    it('SET_VALIDATION_ERRORS sets validation errors', () => {
      const errors = [
        { message: 'Node A is disconnected', nodeId: 'node-1' },
        { message: 'Missing trigger', nodeId: null },
      ]
      const action: BuilderAction = { type: 'SET_VALIDATION_ERRORS', payload: errors }
      const result = builderReducer(initialState, action)

      expect(result.validationErrors).toEqual(errors)
      expect(result.validationSource).toBe('verify')
    })

    it('SET_VALIDATION_ERRORS records save source', () => {
      const errors = [{ message: 'Missing interval', nodeId: 't1' }]
      const result = builderReducer(initialState, {
        type: 'SET_VALIDATION_ERRORS',
        payload: errors,
        source: 'save',
      })

      expect(result.validationSource).toBe('save')
    })

    it('SET_VALIDATION_ERRORS with empty payload clears source', () => {
      const stateWithErrors: BuilderState = {
        ...initialState,
        validationErrors: [{ message: 'Missing interval', nodeId: 't1' }],
        validationSource: 'save',
      }
      const result = builderReducer(stateWithErrors, { type: 'SET_VALIDATION_ERRORS', payload: [] })

      expect(result.validationErrors).toEqual([])
      expect(result.validationSource).toBeNull()
    })

    it('SET_VALIDATION_ERRORS preserves nodeName field', () => {
      const errors = [
        { message: 'MyNode: is disconnected', nodeId: 'node-1', nodeName: 'MyNode' },
        { message: 'Missing trigger', nodeId: null },
      ]
      const action: BuilderAction = { type: 'SET_VALIDATION_ERRORS', payload: errors }
      const result = builderReducer(initialState, action)

      expect(result.validationErrors).toEqual(errors)
    })

    it('CLEAR_VALIDATION_ERRORS resets to empty array', () => {
      const stateWithErrors: BuilderState = {
        ...initialState,
        validationErrors: [{ message: 'Some error', nodeId: 'node-1' }],
        validationSource: 'save',
      }
      const action: BuilderAction = { type: 'CLEAR_VALIDATION_ERRORS' }
      const result = builderReducer(stateWithErrors, action)

      expect(result.validationErrors).toEqual([])
      expect(result.validationSource).toBeNull()
    })

    it('INIT_WORKFLOW clears validation errors', () => {
      const stateWithErrors: BuilderState = {
        ...initialState,
        validationErrors: [{ message: 'Stale error', nodeId: null }],
        validationSource: 'save',
      }
      const action: BuilderAction = {
        type: 'INIT_WORKFLOW',
        payload: { name: 'New', description: '' },
      }
      const result = builderReducer(stateWithErrors, action)

      expect(result.validationErrors).toEqual([])
      expect(result.validationSource).toBeNull()
    })

    it('getInitialBuilderState has empty validationErrors', () => {
      expect(initialState.validationErrors).toEqual([])
      expect(initialState.validationSource).toBeNull()
    })
  })
})
