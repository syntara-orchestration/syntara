import { ExpressionHelpPopover } from './ExpressionHelpPopover'

export function ConditionalExpressionHelp() {
  return (
    <ExpressionHelpPopover
      headerContent="Conditional expression"
      description="The condition that determines which branch the workflow takes. If the expression evaluates to true, the True branch runs; otherwise, the False branch runs."
    />
  )
}
