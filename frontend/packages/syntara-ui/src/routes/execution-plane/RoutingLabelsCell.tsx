import { LabelGroup } from '@patternfly/react-core'

import { SynLabel } from '../../components/labels/SynLabel'

type RoutingLabelsCellProps = Readonly<{
  labels: Record<string, string>
}>

/** Renders execution-target routing labels as compact chips. */
export function RoutingLabelsCell({ labels }: RoutingLabelsCellProps) {
  const entries = Object.entries(labels)
  if (entries.length === 0) return <>—</>

  return (
    <LabelGroup numLabels={3} isCompact>
      {entries.map(([key, value]) => (
        <SynLabel key={key} variant="outline">
          {key}={value}
        </SynLabel>
      ))}
    </LabelGroup>
  )
}
