import { LabelGroup } from '@patternfly/react-core'

import { SynLabel } from '../../components/labels/SynLabel'

type NodeSelectorsCellProps = Readonly<{
  /** Kubernetes/OpenShift node selector strings (`key=value`). */
  selectors: readonly string[]
}>

/** Renders execution-target node selectors as compact chips. */
export function NodeSelectorsCell({ selectors }: NodeSelectorsCellProps) {
  if (selectors.length === 0) return <>—</>

  return (
    <LabelGroup numLabels={3} isCompact>
      {selectors.map((selector) => (
        <SynLabel key={selector} variant="outline">
          {selector}
        </SynLabel>
      ))}
    </LabelGroup>
  )
}
