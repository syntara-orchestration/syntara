import { useQuery } from '@tanstack/react-query'

import { accessFetchClient } from '../access/accessClient'

export type NodeTypePermissionMap = Record<string, { read: boolean; write: boolean; execute: boolean }>

type CanINodeTypesResponse = {
  results: Array<{ node_type: string; allowed: boolean }>
}

const EMPTY: NodeTypePermissionMap = {}

function buildPermissionMap(
  nodeTypes: string[],
  action: 'read' | 'write' | 'execute',
  results: CanINodeTypesResponse['results']
): NodeTypePermissionMap {
  const allowedByType = new Map(results.map((entry) => [entry.node_type, entry.allowed]))
  const map: NodeTypePermissionMap = {}
  for (const nodeType of nodeTypes) {
    const allowed = allowedByType.get(nodeType) ?? false
    const existing = map[nodeType] ?? { read: true, write: true, execute: true }
    map[nodeType] = {
      ...existing,
      [action]: allowed,
    }
  }
  return map
}

async function fetchNodeTypeAction(
  projectId: string,
  nodeTypes: string[],
  action: 'read' | 'write' | 'execute'
): Promise<NodeTypePermissionMap> {
  if (!projectId || nodeTypes.length === 0) {
    return EMPTY
  }
  const { data, error } = await accessFetchClient.POST('/authz/can_i_node_types', {
    body: {
      action,
      resource_project: projectId,
      node_types: nodeTypes,
    },
  })
  if (error || !data) {
    return Object.fromEntries(nodeTypes.map((id) => [id, { read: false, write: false, execute: false }]))
  }
  return buildPermissionMap(nodeTypes, action, data.results)
}

/**
 * Batch-resolves workflow node-type read/write/execute for the builder palette and inspector.
 */
export function useNodeTypePermissions(projectId: string | undefined, nodeTypeIds: string[]) {
  const sortedIds = [...nodeTypeIds].sort()
  const enabled = Boolean(projectId) && sortedIds.length > 0

  const readQuery = useQuery({
    queryKey: ['authz', 'can_i_node_types', projectId, 'read', sortedIds],
    enabled,
    staleTime: Infinity,
    retry: false,
    queryFn: () => {
      if (!projectId) return Promise.resolve(EMPTY)
      return fetchNodeTypeAction(projectId, sortedIds, 'read')
    },
  })
  const writeQuery = useQuery({
    queryKey: ['authz', 'can_i_node_types', projectId, 'write', sortedIds],
    enabled,
    staleTime: Infinity,
    retry: false,
    queryFn: () => {
      if (!projectId) return Promise.resolve(EMPTY)
      return fetchNodeTypeAction(projectId, sortedIds, 'write')
    },
  })
  const executeQuery = useQuery({
    queryKey: ['authz', 'can_i_node_types', projectId, 'execute', sortedIds],
    enabled,
    staleTime: Infinity,
    retry: false,
    queryFn: () => {
      if (!projectId) return Promise.resolve(EMPTY)
      return fetchNodeTypeAction(projectId, sortedIds, 'execute')
    },
  })

  const permissions: NodeTypePermissionMap = {}
  const loading = readQuery.isLoading || writeQuery.isLoading || executeQuery.isLoading
  for (const id of sortedIds) {
    permissions[id] = {
      read: readQuery.data?.[id]?.read ?? loading,
      write: writeQuery.data?.[id]?.write ?? loading,
      execute: executeQuery.data?.[id]?.execute ?? loading,
    }
  }

  return {
    permissions,
    isLoading: loading,
  }
}
