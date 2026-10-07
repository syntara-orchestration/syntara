export type FormResponsesAction =
  | { type: 'TOGGLE_ROW'; payload: string }
  | { type: 'SET_EXPANDED_ROWS'; payload: Set<string> }

export function formResponsesReducer(state: { expandedRows: Set<string> }, action: FormResponsesAction) {
  switch (action.type) {
    case 'TOGGLE_ROW': {
      const next = new Set(state.expandedRows)
      if (next.has(action.payload)) next.delete(action.payload)
      else next.add(action.payload)
      return { expandedRows: next }
    }
    case 'SET_EXPANDED_ROWS':
      return { expandedRows: action.payload }
    default:
      return state
  }
}
