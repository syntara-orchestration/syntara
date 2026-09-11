export type ApprovalsAction =
  | { type: 'SET_EXPANDED_ROWS'; payload: Set<string> }
  | { type: 'TOGGLE_ROW'; payload: string }

export function approvalsReducer(state: { expandedRows: Set<string> }, action: ApprovalsAction) {
  switch (action.type) {
    case 'SET_EXPANDED_ROWS':
      return { ...state, expandedRows: action.payload }
    case 'TOGGLE_ROW': {
      const next = new Set(state.expandedRows)
      if (next.has(action.payload)) {
        next.delete(action.payload)
      } else {
        next.add(action.payload)
      }
      return { ...state, expandedRows: next }
    }
    default:
      return state
  }
}
