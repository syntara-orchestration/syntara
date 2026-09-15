import {
  CodeBlock as PFCodeBlock,
  CodeBlockCode,
  DescriptionList,
  DescriptionListDescription,
  DescriptionListGroup,
  DescriptionListTerm,
} from '@patternfly/react-core'
import type { Node } from '@xyflow/react'

import { SynCodeBlock } from '../../components/details/SynCodeBlock'
import type { NodeType } from '../workflows/canvas/nodes/NodeType'

type NodeRawDataViewProps = {
  node: Node<NodeType['data']>
}

export function NodeRawDataView({ node }: NodeRawDataViewProps) {
  return (
    <DescriptionList>
      <DescriptionListGroup>
        <DescriptionListTerm>Node type</DescriptionListTerm>
        <DescriptionListDescription>{node.type}</DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Node ID</DescriptionListTerm>
        <DescriptionListDescription>
          <PFCodeBlock>
            <CodeBlockCode>{node.id}</CodeBlockCode>
          </PFCodeBlock>
        </DescriptionListDescription>
      </DescriptionListGroup>
      <DescriptionListGroup>
        <DescriptionListTerm>Node data</DescriptionListTerm>
        <DescriptionListDescription>
          <SynCodeBlock jsonObject={node.data} />
        </DescriptionListDescription>
      </DescriptionListGroup>
    </DescriptionList>
  )
}
