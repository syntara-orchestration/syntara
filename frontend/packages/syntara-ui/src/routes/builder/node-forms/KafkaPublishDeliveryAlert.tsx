import { Alert, Button, Content, ContentVariants, Title } from '@patternfly/react-core'
import { RhUiCaretDownIcon } from '@patternfly/react-icons'
import { useId, useState } from 'react'

import styles from './KafkaPublishMessageFields.module.css'

export function KafkaPublishDeliveryAlert() {
  const [expanded, setExpanded] = useState(true)
  const contentId = useId()
  return (
    <Alert
      variant="info"
      isInline
      component="div"
      role="region"
      aria-label="Message delivery behavior"
      className={styles.deliveryAlert}
      title={
        <>
          <Button
            type="button"
            variant="plain"
            className={`${styles.toggleButton} ${styles.deliveryToggle}`}
            aria-label="Message delivery behavior"
            aria-expanded={expanded}
            aria-controls={expanded ? contentId : undefined}
            onClick={() => setExpanded(!expanded)}
          >
            <RhUiCaretDownIcon className={styles.toggleIcon} aria-hidden />
          </Button>
          <Title headingLevel="h4" className={styles.deliveryTitle}>
            Message delivery behavior
          </Title>
        </>
      }
    >
      {expanded && (
        <Content id={contentId} component={ContentVariants.p} role="note" aria-label="Kafka Publish delivery details">
          Kafka acknowledgment confirms broker receipt. Retries and reruns can publish another copy. Timeout or
          cancellation may leave delivery unconfirmed.
        </Content>
      )}
    </Alert>
  )
}
