import { ExpressionHelpPopover } from './ExpressionHelpPopover'

export function PathExpressionHelp() {
  return (
    <ExpressionHelpPopover
      headerContent="Path expression"
      description="The condition that determines if this path is taken. The workflow routes to the first path whose condition evaluates to true."
    />
  )
}
