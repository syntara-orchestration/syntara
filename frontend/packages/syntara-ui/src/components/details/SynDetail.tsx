import { DescriptionListDescription, DescriptionListGroup, DescriptionListTerm } from '@patternfly/react-core'

/**
 * A single label/value row used inside detail pages (credentials, approvals, etc.).
 * Renders nothing when the value is absent, so optional fields can be passed unconditionally.
 */
export function SynDetail(props: { label: string; children?: React.ReactNode }) {
  if (!props.children || props.children === null) {
    return null
  }

  return (
    <DescriptionListGroup>
      <DescriptionListTerm>{props.label}</DescriptionListTerm>
      <DescriptionListDescription>{props.children}</DescriptionListDescription>
    </DescriptionListGroup>
  )
}
