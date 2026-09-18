import { useQuery } from '@tanstack/react-query'

import { accessFetchClient } from '../access/accessClient'

export type NodeTypePermissionMap = Record<string, { read: boolean; write: boolean; execute: boolean }>
export type NodeTypePermission = NodeTypePermissionMap[string]

type CanINodeTypesResponse = {
  results: Array<{ node_type: string; allowed: boolean }>
}

const EMPTY: NodeTypePermissionMap = {}
const DENIED = { read: false, write: false, execute: false } as const

export function canModifyNodeType(permission: NodeTypePermission | undefined): boolean {
  return permission?.read === true && permission.write === true
}

function buildPermissionMap(
  nodeTypes: string[],
  action: 'read' | 'write' | 'execute',
  results: CanINodeTypesResponse['results']
): NodeTypePermissionMap {
  const allowedByType = new Map(results.map((entry) => [entry.node_type, entry.allowed]))
  const map: NodeTypePermissionMap = {}
  for (const nodeType of nodeTypes) {
    const allowed = allowedByType.get(nodeType) ?? false
    const existing = map[nodeType] ?? { ...DENIED }
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
    return Object.fromEntries(nodeTypes.map((id) => [id, { ...DENIED }]))
  }
  return buildPermissionMap(nodeTypes, action, data.results)
}

/**
 * Batch-resolves workflow node-type read/write/execute for the builder palette and inspector.
 * Fail closed: missing or loading entries are treated as denied.
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
  const loading = enabled && (readQuery.isLoading || writeQuery.isLoading || executeQuery.isLoading)
  for (const id of sortedIds) {
    permissions[id] = {
      read: loading ? false : (readQuery.data?.[id]?.read ?? false),
      write: loading ? false : (writeQuery.data?.[id]?.write ?? false),
      execute: loading ? false : (executeQuery.data?.[id]?.execute ?? false),
    }
  }

  return {
    permissions,
    isLoading: loading,
  }
}
