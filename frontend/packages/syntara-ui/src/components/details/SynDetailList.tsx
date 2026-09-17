import { DescriptionList } from '@patternfly/react-core'

/**
 * Wraps `SynDetail` rows inside workflow canvas steps (task, condition, approval, converge).
 * Renders a compact description list that fits within the constrained space of a step card.
 */
export function SynDetailList(props: { children: React.ReactNode; isHorizontal?: boolean; 'data-testid'?: string }) {
  return (
    <DescriptionList
      data-testid={props['data-testid'] ?? 'description-list'}
      className="details"
      isCompact
      isHorizontal={props.isHorizontal}
    >
      {props.children}
    </DescriptionList>
  )
}
