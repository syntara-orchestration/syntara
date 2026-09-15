import {
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
} from '@patternfly/react-core'
import { ExpandableRowContent } from '@patternfly/react-table'

/** Expandable row body for related-resource tables: description only, matching the credentials list. */
export function DescriptionExpandableContent({ description }: Readonly<{ description: string }>) {
  return (
    <ExpandableRowContent>
      <DescriptionList>
        <DescriptionListGroup>
          <DescriptionListTerm>Description</DescriptionListTerm>
          <DescriptionListDescription>{description}</DescriptionListDescription>
        </DescriptionListGroup>
      </DescriptionList>
    </ExpandableRowContent>
  )
}
