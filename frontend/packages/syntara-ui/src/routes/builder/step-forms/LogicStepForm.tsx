import { ActivityTypeEnum, type NodeSettings } from '@syntara/contracts'
import type { ReactNode } from 'react'

import { ConditionStepForm, type ConditionFormData } from './ConditionStepForm'
import { ConvergeStepForm, type ConvergeFormData } from './ConvergeStepForm'
import { LoopStepForm, type LoopFormData } from './LoopStepForm'
import { SwitchStepForm, type SwitchFormData } from './SwitchStepForm'
import { WaitStepForm, type WaitFormData } from './WaitStepForm'

/** Converge strategy: when to continue after branches (re-exported from ConvergeStepForm) */
export type { ConvergeStrategy } from './ConvergeStepForm'

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
  // Settings (all logic step types)
  settings?: NodeSettings
}

type LogicStepFormProps = Readonly<{
  onSubmit: (data: LogicFormData) => void
  initialData?: Partial<LogicFormData>
  onHeaderContentChange?: (content: ReactNode | null) => void
}>

/**
 * LogicStepForm - A thin wrapper that delegates to specialized forms based on logicType.
 *
 * This form is used by registerLogicStep to present a unified "Logic" step with subtypes.
 * It delegates to the appropriate specialized form:
 * - ConditionStepForm for conditional logic
 * - LoopStepForm for loop logic
 * - ConvergeStepForm for converge logic
 *
 * Note: This wrapper exists to maintain the subtype pattern in registerLogicStep.
 * For editing existing steps, use the specialized forms directly via StepDetails components.
 */
// eslint-disable-next-line complexity -- dispatch function for 4 distinct logic node subtypes; each branch has its own data-shaping and submit handler; splitting further would scatter tightly-related logic
export function LogicStepForm({ onSubmit, initialData, onHeaderContentChange }: LogicStepFormProps) {
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
      <ConditionStepForm
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
      <LoopStepForm onSubmit={handleLoopSubmit} initialData={loopData} onHeaderContentChange={onHeaderContentChange} />
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
      <ConvergeStepForm
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
      <SwitchStepForm
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
      <WaitStepForm onSubmit={handleWaitSubmit} initialData={waitData} onHeaderContentChange={onHeaderContentChange} />
    )
  }

  // Fallback for unknown logic type
  return null
}
