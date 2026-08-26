import { type Request } from '@playwright/test'

import { type Page } from '../fixtures'

import { closeNodeEditorPanel } from './workflows'

export type WorkflowNode = {
  id: string
  type: string
  name?: string
  parameters: Record<string, unknown>
}

export type WorkflowPayload = {
  workflow_definition: {
    nodes: WorkflowNode[]
  }
}

export function getWorkflowPayload(request: Request): WorkflowPayload {
  return request.postDataJSON() as WorkflowPayload
}

export async function cancelAndCloseEditor(app: Page) {
  for (const label of ['Cancel step creation', 'Cancel without saving']) {
    const cancelBtn = app.getByRole('button', { name: label })
    if ((await cancelBtn.count()) > 0) {
      await cancelBtn.click()
      return
    }
  }
  await closeNodeEditorPanel(app)
}
