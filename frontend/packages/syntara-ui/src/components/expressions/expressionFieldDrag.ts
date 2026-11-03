export const DRAG_TYPE_FIELD = 'syntara/input-field'
export const DRAG_TYPE_CONTEXT = 'syntara/context-variable'

export const EXPRESSION_FIELD_PLACEHOLDER = 'Enter or drag and drop value'

export type FieldDragData = {
  type: typeof DRAG_TYPE_FIELD
  nodeId: string
  fieldPath: string[]
}

export type ContextDragData = {
  type: typeof DRAG_TYPE_CONTEXT
  contextPath: string
}

export type DragData = FieldDragData | ContextDragData

export function isDragData(value: unknown): value is DragData {
  if (typeof value !== 'object' || value === null) return false
  const obj = value as Record<string, unknown>
  if (obj.type === DRAG_TYPE_FIELD) {
    return (
      typeof obj.nodeId === 'string' &&
      obj.nodeId.length > 0 &&
      Array.isArray(obj.fieldPath) &&
      obj.fieldPath.length > 0 &&
      obj.fieldPath.every((segment) => typeof segment === 'string' && segment.length > 0)
    )
  }
  if (obj.type === DRAG_TYPE_CONTEXT) {
    return typeof obj.contextPath === 'string' && obj.contextPath.length > 0
  }
  return false
}
