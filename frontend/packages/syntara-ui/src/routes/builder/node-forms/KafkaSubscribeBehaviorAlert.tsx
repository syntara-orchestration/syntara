import { Alert, Content, ContentVariants } from '@patternfly/react-core'

/** One expandable info alert for how a Kafka subscription is activated and kept. */
export function KafkaSubscribeBehaviorAlert() {
  return (
    <Alert variant="info" isInline isExpandable component="h4" title="Kafka Subscribe behavior">
      <Content component={ContentVariants.p}>
        Publishing activates the subscription; changes apply on the next publish. The runtime credential authenticates
        to Kafka, while workflow identity and message offsets are handled automatically.
      </Content>
    </Alert>
  )
}
