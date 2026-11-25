import { test, expect } from './fixtures'
import {
  buildUniqueName,
  createBasicWorkflowViaApi,
  openWorkflowInBuilder,
  publishWorkflowViaApi,
  verifyNodeVisible,
} from './helpers/workflows'
import { createWorkflowViaApi, deleteWorkflowViaApi } from './utils/api'

/**
 * Full embed-with-reference flow (AAP-91236): a published source workflow whose steps
 * include a sub-workflow reference is embedded into another workflow. The copied steps —
 * including the preserved sub-workflow reference — must land on the target canvas, and the
 * dialog must surface that the copy keeps calling the same child workflow.
 */
test.describe('Embed published workflow', () => {
  test('embeds a published source whose steps include a sub-workflow reference', async ({ app }) => {
    test.setTimeout(120_000)

    const childName = buildUniqueName('e2e-embed-child')
    const sourceName = buildUniqueName('e2e-embed-source')
    const targetName = buildUniqueName('e2e-embed-target')
    let childId: string | undefined
    let sourceId: string | undefined
    let targetId: string | undefined

    try {
      // The child the reference points at: a published workflow with a sub-workflow trigger.
      const child = await createWorkflowViaApi({
        app,
        name: childName,
        triggers: [
          {
            id: 'child_subworkflow_trigger',
            type: 'subworkflow_trigger',
            name: 'Child invocation',
            parameters: { input_schema: { type: 'object', properties: {} } },
          },
        ],
        nodes: [
          {
            id: 'child_script',
            type: 'script',
            name: 'Child echo',
            parameters: { language: 'python', code: 'print("child")' },
          },
        ],
        edges: [{ from: 'child_subworkflow_trigger', to: 'child_script' }],
      })
      childId = child.id
      await publishWorkflowViaApi(app, child.id, child.versionNumber)

      // The source to embed: a trigger (excluded on embed), a plain step, and a sub-workflow
      // reference step pointing at the published child. Published so it is embeddable.
      const source = await createWorkflowViaApi({
        app,
        name: sourceName,
        triggers: [{ id: 'source_manual_trigger', type: 'manual_trigger', name: 'Start', parameters: {} }],
        nodes: [
          {
            id: 'source_prep',
            type: 'script',
            name: 'Source prep',
            parameters: { language: 'python', code: 'print("prep")' },
          },
          {
            id: 'source_call_child',
            type: 'sub_workflow',
            name: 'Call child',
            parameters: { workflow_id: child.id, trigger_node_id: 'child_subworkflow_trigger', input_mapping: {} },
          },
        ],
        edges: [
          { from: 'source_manual_trigger', to: 'source_prep' },
          { from: 'source_prep', to: 'source_call_child' },
        ],
      })
      sourceId = source.id
      await publishWorkflowViaApi(app, source.id, source.versionNumber)

      // The target we embed into.
      const target = await createBasicWorkflowViaApi(app, targetName, 'Target step')
      targetId = target.id
      await openWorkflowInBuilder(app, targetName, target.id)

      // Open the kebab and launch the Embed dialog.
      await app.getByRole('button', { name: 'Workflow actions' }).click()
      await app.getByRole('menuitem', { name: /Embed published workflow/i }).click()

      const dialog = app.getByRole('dialog')
      await expect(dialog).toBeVisible()

      // Pick the published source.
      await dialog.getByRole('button', { name: 'Select a published workflow' }).click()
      // PatternFly renders the select menu in a portal outside the dialog, so locate the
      // option at page level rather than scoping it to the dialog.
      await app.getByRole('option', { name: new RegExp(sourceName) }).click()

      // Preview: the copy summary plus the sub-workflow reference note (the source has a
      // sub_workflow step, so the copy keeps calling the same child workflow). The trigger
      // is excluded, so only the two non-trigger steps are counted.
      await expect(dialog.getByText(/will be copied/i)).toBeVisible()
      await expect(dialog.getByText(/call the same child workflows/i)).toBeVisible()

      // Embed; the dialog closes and the copied steps — including the preserved sub-workflow
      // reference — land on the canvas alongside the target's own step.
      await dialog.getByRole('button', { name: 'Embed workflow' }).click()
      await expect(dialog).not.toBeVisible({ timeout: 10_000 })

      // The copied steps are visible immediately — BEFORE any Reset layout. A layout reset would
      // separate the cards and hide the placement regression this assertion is here to catch.
      await verifyNodeVisible(app, 'Source prep')
      await verifyNodeVisible(app, 'Call child')
      await verifyNodeVisible(app, 'Target step')

      // The two copied cards must not land on top of each other (the stacking bug).
      const node = (name: string) =>
        app.locator('[role="group"][aria-roledescription="node"]').filter({ hasText: name })
      const sourceBox = await node('Source prep').boundingBox()
      const childBox = await node('Call child').boundingBox()
      expect(sourceBox).not.toBeNull()
      expect(childBox).not.toBeNull()
      const overlaps =
        !!sourceBox &&
        !!childBox &&
        sourceBox.x < childBox.x + childBox.width &&
        sourceBox.x + sourceBox.width > childBox.x &&
        sourceBox.y < childBox.y + childBox.height &&
        sourceBox.y + sourceBox.height > childBox.y
      expect(overlaps).toBe(false)
    } finally {
      // Delete the source first so the child is no longer referenced, then the child and target.
      if (sourceId) await deleteWorkflowViaApi(app, sourceId)
      if (childId) await deleteWorkflowViaApi(app, childId)
      if (targetId) await deleteWorkflowViaApi(app, targetId)
    }
  })
})
