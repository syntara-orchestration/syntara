import { EdgeHandleEnum, type SwitchActivity, type SwitchConfig } from '@syntara/contracts'
import { type ReactNode, useMemo } from 'react'
import { z } from 'zod'

import { useAlerts } from '../../../providers/alerts'
import { useWorkflowStoreActions } from '../../../stores/useWorkflowStore'
import type { Expression } from '../../../utils/expressions/types'
import { SwitchStepForm, type SwitchFormData } from '../step-forms/SwitchStepForm'
import { buildSwitchCasePort } from '../utils/switchCaseHelpers'

const expressionTreesSchema = z.record(z.string(), z.custom<Expression>())
const editorModesSchema = z.record(z.string(), z.enum(['visual', 'raw']))

function getExpressionTrees(params: Record<string, unknown>): Record<string, Expression> | undefined {
  const result = expressionTreesSchema.safeParse(params._expressionTrees)
  return result.success ? result.data : undefined
}

function getEditorModes(params: Record<string, unknown>): Record<string, 'visual' | 'raw'> | undefined {
  const result = editorModesSchema.safeParse(params._editorModes)
  return result.success ? result.data : undefined
}

type SwitchStepDetailsProps = {
  switchData: SwitchActivity
  nodeId: string
  onClose: () => void
  onHeaderContentChange?: (content: ReactNode | null) => void
}

export function SwitchStepDetails({ switchData, nodeId, onClose, onHeaderContentChange }: SwitchStepDetailsProps) {
  const { showError } = useAlerts()
  const { updateSwitchActivity } = useWorkflowStoreActions()

  const switchConfig = (switchData.parameters ?? { cases: [] }) as SwitchConfig
  const uiState = (switchData.parameters as Record<string, unknown> | undefined) ?? {}
  const expressionTrees = getExpressionTrees(uiState)
  const editorModes = getEditorModes(uiState)

  const { initialCases, oldCaseIdToPort } = useMemo(() => {
    const portMap = new Map<string, string>()
    const cases =
      switchConfig.cases?.map((c, i) => {
        portMap.set(c.port, c.port)
        return {
          caseId: c.port,
          label: c.label || `Path ${i + 1}`,
          condition: c.condition,
          expressionTree: expressionTrees?.[c.port],
          editorMode: editorModes?.[c.port],
        }
      }) ?? []
    return { initialCases: cases, oldCaseIdToPort: portMap }
  }, [switchConfig.cases, expressionTrees, editorModes])

  const initialData: Partial<SwitchFormData> = {
    name: switchData.name,
    cases: initialCases,
  }

  const handleSubmit = (data: SwitchFormData) => {
    try {
      const trees: Record<string, Expression> = {}
      const modes: Record<string, 'visual' | 'raw'> = {}
      const newCases = data.cases.map((c, i) => {
        const port = buildSwitchCasePort(i)
        if (c.expressionTree) {
          trees[port] = c.expressionTree
        }
        if (c.editorMode) {
          modes[port] = c.editorMode
        }
        return {
          port,
          label: c.label || `Path ${i + 1}`,
          condition: c.condition,
        }
      })

      const updatedActivity: SwitchActivity = {
        ...switchData,
        name: data.name,
        parameters: {
          cases: newCases,
          default_port: EdgeHandleEnum.DEFAULT,
          _expressionTrees: trees,
          _editorModes: modes,
        },
      } as SwitchActivity

      const portMapping = new Map<string, string>()
      data.cases.forEach((formCase, newIdx) => {
        const oldPort = oldCaseIdToPort.get(formCase.caseId)
        if (oldPort) {
          portMapping.set(oldPort, buildSwitchCasePort(newIdx))
        }
      })

      updateSwitchActivity(nodeId, updatedActivity, portMapping)

      onClose()
    } catch (error) {
      showError({
        title: 'Update failed',
        description: error instanceof Error ? error.message : 'Failed to update step',
      })
    }
  }

  return (
    <SwitchStepForm initialData={initialData} onSubmit={handleSubmit} onHeaderContentChange={onHeaderContentChange} />
  )
}
