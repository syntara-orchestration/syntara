import { Content, ContentVariants, Tooltip } from '@patternfly/react-core'
import { RhUiInformationIcon } from '@patternfly/react-icons'

import { SynLabel } from '../../../components/labels/SynLabel'

import { computeRemainingGracePeriod } from './rotateDialogUtils'
import styles from './RotationGraceIndicator.module.css'

export function RotationGraceIndicator({
  oldSecretValidUntil,
}: Readonly<{ oldSecretValidUntil: string | null | undefined }>) {
  if (!oldSecretValidUntil) return null

  const gracePeriod = computeRemainingGracePeriod(oldSecretValidUntil)
  if (!gracePeriod) return null

  const tooltipContent = `The previous secret is still valid and will expire at ${gracePeriod.expiryFormatted}. Ensure all systems are updated to the new secret before then.`

  return (
    <div className={styles.container}>
      <Tooltip content={tooltipContent}>
        <SynLabel tabIndex={0} variant="outline" status="info" icon={<RhUiInformationIcon />}>
          Rotating — {gracePeriod.remainingLabel} left
        </SynLabel>
      </Tooltip>
      <Content component={ContentVariants.small} className={styles.expiryText}>
        Expires {gracePeriod.expiryShort}
      </Content>
    </div>
  )
}
