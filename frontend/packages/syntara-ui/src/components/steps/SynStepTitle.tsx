import { Content, ContentVariants, FlexItem, Title, TitleSizes, Tooltip } from '@patternfly/react-core'
import { useCallback, useRef, useState } from 'react'

import styles from './SynStepTitle.module.css'

function useTruncationTooltip() {
  const ref = useRef<HTMLDivElement>(null)
  const [isTruncated, setIsTruncated] = useState(false)
  const checkTruncation = useCallback(() => {
    const el = ref.current
    if (el) {
      setIsTruncated(el.scrollHeight > el.clientHeight || el.scrollWidth > el.clientWidth)
    }
  }, [])

  return { ref, isTruncated, onMouseEnter: checkTruncation }
}

function ClampedTitle(props: { text: string; isSubtitle?: boolean }) {
  const { ref, isTruncated, onMouseEnter } = useTruncationTooltip()

  const inner = (
    <div ref={ref} className={styles.clampWrapper}>
      {props.isSubtitle ? (
        <Content component={ContentVariants.small} className={styles.subtitleClamp} onMouseEnter={onMouseEnter}>
          {props.text}
        </Content>
      ) : (
        <Title headingLevel="h2" size={TitleSizes.md} className={styles.titleClamp} onMouseEnter={onMouseEnter}>
          {props.text}
        </Title>
      )}
    </div>
  )

  return isTruncated ? <Tooltip content={props.text}>{inner}</Tooltip> : inner
}

export function SynStepTitle(props: { title?: string; subTitle?: string }) {
  const headingText = props.title || props.subTitle || ''

  return (
    <FlexItem grow={{ default: 'grow' }} style={{ minWidth: 0 }}>
      <ClampedTitle text={headingText} />
      {props.title && props.subTitle ? <ClampedTitle text={props.subTitle} isSubtitle /> : null}
    </FlexItem>
  )
}
