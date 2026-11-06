import { workflowFetchClient } from '../client'

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function sanitizeFilename(name: string): string {
  return name.replaceAll(/[^\w.-]/g, '_').toLowerCase()
}

async function fetchExportBlob(workflowId: string, version: number): Promise<{ blob: Blob; filename: string }> {
  const result = await workflowFetchClient.GET('/workflows/{workflow_id}/versions/{version}/export', {
    params: { path: { workflow_id: workflowId, version } },
    parseAs: 'blob',
  })

  if (result.error || !result.data) {
    throw new Error('Failed to export workflow')
  }

  const disposition = result.response.headers.get('content-disposition')
  const match = disposition?.match(/filename="?([^"]+)"?/)
  const filename = match?.[1] ?? `workflow-v${String(version)}.json`
  return { blob: result.data, filename }
}

export async function downloadWorkflowExportById(workflowId: string, version?: number): Promise<void> {
  let exportVersion = version
  if (exportVersion == null) {
    const { data, error } = await workflowFetchClient.GET('/workflows/{workflow_id}', {
      params: { path: { workflow_id: workflowId } },
    })
    if (error || !data) {
      throw new Error('Failed to fetch workflow details for export')
    }
    exportVersion = data.current_version ?? data.version?.version
    if (exportVersion == null) {
      throw new Error('Workflow has no version to export')
    }
  }

  const { blob, filename } = await fetchExportBlob(workflowId, exportVersion)
  triggerDownload(blob, filename)
}

export async function downloadVersionExport(workflowId: string, version: number): Promise<void> {
  const { blob, filename } = await fetchExportBlob(workflowId, version)
  triggerDownload(blob, filename)
}

export function downloadWorkflowDefinition(definition: Record<string, unknown>, workflowName: string): void {
  const content = JSON.stringify(definition, null, 2)
  const blob = new Blob([content], { type: 'application/json' })
  triggerDownload(blob, `${sanitizeFilename(workflowName)}.json`)
}

export const MAX_WORKFLOW_IMPORT_FILE_SIZE_BYTES = 10 * 1024 * 1024 // 10 MB

export const WORKFLOW_IMPORT_FILE_TOO_LARGE_MESSAGE = 'File is too large. Maximum size is 10 MB.'

export function validateFileSize(file: File): void {
  if (file.size > MAX_WORKFLOW_IMPORT_FILE_SIZE_BYTES) {
    throw new Error(WORKFLOW_IMPORT_FILE_TOO_LARGE_MESSAGE)
  }
}

function validateElements(items: unknown[], requiredKeys: string[], label: string): void {
  for (const item of items) {
    if (!item || typeof item !== 'object') {
      throw new Error(`Each ${label} must be an object`)
    }
    for (const key of requiredKeys) {
      if (!(key in item)) {
        const fieldNames = requiredKeys.map((k) => '"' + k + '"').join(' and ')
        const suffix = requiredKeys.length > 1 ? 's' : ''
        throw new Error(`Each ${label} must have ${fieldNames} field${suffix}`)
      }
    }
  }
}

export function parseWorkflowFile(content: string, filename: string): Record<string, unknown> {
  const isJson = filename.toLowerCase().endsWith('.json')

  if (!isJson) {
    throw new Error('Only JSON files are supported')
  }

  const parsed: unknown = JSON.parse(content)

  if (!parsed || typeof parsed !== 'object') {
    throw new TypeError('File does not contain a valid workflow definition')
  }

  const definition = parsed as Record<string, unknown>

  if (definition.schema_version && definition.schema_version !== '2.0.0') {
    throw new Error(`Unsupported schema version: ${JSON.stringify(definition.schema_version)}. Expected 2.0.0`)
  }

  if (!Array.isArray(definition.triggers) || !Array.isArray(definition.nodes) || !Array.isArray(definition.edges)) {
    throw new TypeError('File is missing required workflow definition fields (triggers, nodes, edges must be arrays)')
  }

  validateElements(definition.nodes as unknown[], ['id', 'type'], 'node')
  validateElements(definition.triggers as unknown[], ['type'], 'trigger')
  validateElements(definition.edges as unknown[], ['from', 'to'], 'edge')

  return definition
}
