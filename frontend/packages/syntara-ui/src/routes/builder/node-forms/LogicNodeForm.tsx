import { ActivityTypeEnum, type NodeSettings } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { ConditionNodeForm, type ConditionFormData } from './ConditionNodeForm'
import { ConvergeNodeForm, type ConvergeFormData } from './ConvergeNodeForm'
import { LoopNodeForm, type LoopFormData } from './LoopNodeForm'
import { SwitchNodeForm, type SwitchFormData } from './SwitchNodeForm'
import { WaitNodeForm, type WaitFormData } from './WaitNodeForm'

/** Converge strategy: when to continue after branches (re-exported from ConvergeNodeForm) */
export type { ConvergeStrategy } from './ConvergeNodeForm'

/**
 * Combined form data type for logic nodes.
 * This is a union of all specialized form types plus the logicType discriminator.
 */
export type LogicFormData = {
  name: string
  logicType: string
  // Condition fields
  condition?: string
  // Loop fields
  type?: string
  items?: string
  maxIterations?: number
  indexVariable?: string
  itemVariable?: string
  // Switch fields
  cases?: Array<{
    caseId: string
    label?: string
    condition?: string
  }>
  // Converge fields
  strategy?: 'all' | 'any'
  requiredPathCount?: number
  // Wait node fields
  duration?: number
  // Converge fields
  wait_duration?: number
  // Settings (all logic node types)
  settings?: NodeSettings
}

type LogicNodeFormProps = Readonly<{
  onSubmit: (data: LogicFormData) => void
  initialData?: Partial<LogicFormData>
  onHeaderContentChange?: (content: ReactNode | null) => void
}>

/**
 * LogicNodeForm - A thin wrapper that delegates to specialized forms based on logicType.
 *
 * This form is used by registerLogicNode to present a unified "Logic" node with subtypes.
 * It delegates to the appropriate specialized form:
 * - ConditionNodeForm for conditional logic
 * - LoopNodeForm for loop logic
 * - ConvergeNodeForm for converge logic
 *
 * Note: This wrapper exists to maintain the subtype pattern in registerLogicNode.
 * For editing existing nodes, use the specialized forms directly via NodeDetails components.
 */
// eslint-disable-next-line complexity -- dispatch function for 4 distinct logic node subtypes; each branch has its own data-shaping and submit handler; splitting further would scatter tightly-related logic
export function LogicNodeForm({ onSubmit, initialData, onHeaderContentChange }: LogicNodeFormProps) {
  const logicType = initialData?.logicType

  // Handle Condition node
  if (logicType === ActivityTypeEnum.CONDITION) {
    const conditionData: Partial<ConditionFormData> = {
      name: initialData?.name,
      condition: initialData?.condition,
    }

    const handleConditionSubmit = (data: ConditionFormData) => {
      onSubmit({
        ...data,
        logicType: ActivityTypeEnum.CONDITION,
      })
    }

    return (
      <ConditionNodeForm
        onSubmit={handleConditionSubmit}
        initialData={conditionData}
        onHeaderContentChange={onHeaderContentChange}
      />
    )
  }

  // Handle Loop node
  if (logicType === ActivityTypeEnum.LOOP) {
    const loopData: Partial<LoopFormData> = {
      name: initialData?.name,
      type: (initialData?.type as 'forEach' | 'while') || 'while',
      items: initialData?.items,
      condition: initialData?.condition,
      maxIterations: initialData?.maxIterations,
      indexVariable: initialData?.indexVariable,
      itemVariable: initialData?.itemVariable,
    }

    const handleLoopSubmit = (data: LoopFormData) => {
      onSubmit({
        ...data,
        logicType: ActivityTypeEnum.LOOP,
      })
    }

    return (
      <LoopNodeForm onSubmit={handleLoopSubmit} initialData={loopData} onHeaderContentChange={onHeaderContentChange} />
    )
  }

  // Handle Converge node
  if (logicType === ActivityTypeEnum.CONVERGE) {
    const convergeSource = {
      name: initialData?.name,
      strategy: initialData?.strategy,
      requiredPathCount: initialData?.requiredPathCount,
      wait_duration: initialData?.wait_duration,
      settings: initialData?.settings,
    } satisfies Partial<ConvergeFormData>
    const convergeData: Partial<ConvergeFormData> = Object.fromEntries(
      Object.entries(convergeSource).filter(([, v]) => v !== undefined)
    )

    const handleConvergeSubmit = (data: ConvergeFormData) => {
      onSubmit({
        ...data,
        logicType: ActivityTypeEnum.CONVERGE,
      })
    }

    return (
      <ConvergeNodeForm
        onSubmit={handleConvergeSubmit}
        initialData={convergeData}
        onHeaderContentChange={onHeaderContentChange}
      />
    )
  }

  // Handle Switch node
  if (logicType === ActivityTypeEnum.SWITCH) {
    const switchData: Partial<SwitchFormData> = {
      name: initialData?.name,
      cases: initialData?.cases,
    }

    const handleSwitchSubmit = (data: SwitchFormData) => {
      onSubmit({
        ...data,
        logicType: ActivityTypeEnum.SWITCH,
      })
    }

    return (
      <SwitchNodeForm
        onSubmit={handleSwitchSubmit}
        initialData={switchData}
        onHeaderContentChange={onHeaderContentChange}
      />
    )
  }

  // Handle Wait node
  if (logicType === ActivityTypeEnum.WAIT) {
    const waitData: Partial<WaitFormData> = {
      name: initialData?.name,
      duration: initialData?.duration,
    }

    const handleWaitSubmit = (data: WaitFormData) => {
      onSubmit({
        name: data.name,
        duration: data.duration,
        logicType: ActivityTypeEnum.WAIT,
      })
    }

    return (
      <WaitNodeForm onSubmit={handleWaitSubmit} initialData={waitData} onHeaderContentChange={onHeaderContentChange} />
    )
  }

  // Fallback for unknown logic type
  return null
}
