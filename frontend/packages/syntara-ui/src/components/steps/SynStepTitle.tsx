import { Content, ContentVariants, FlexItem, Title, TitleSizes, Tooltip } from '@patternfly/react-core'
import { useCallback, useLayoutEffect, useRef, useState } from 'react'

import styles from './SynStepTitle.module.css'

function useOverflowTooltip(text: string) {
  const ref = useRef<HTMLDivElement>(null)
  const [showTooltip, setShowTooltip] = useState(false)

  const measure = useCallback(() => {
    const el = ref.current
    if (!el) {
      setShowTooltip(false)
      return
    }
    setShowTooltip(el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1)
  }, [])

  useLayoutEffect(() => {
    measure()
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => measure())
    observer.observe(el)
    return () => observer.disconnect()
  }, [measure, text])

  return { ref, showTooltip }
}

function TitleLine(props: { text: string; isSubtitle?: boolean }) {
  const { ref, showTooltip } = useOverflowTooltip(props.text)

  const inner = (
    <div ref={ref} className={styles.textWrapper}>
      {props.isSubtitle ? (
        <Content component={ContentVariants.small} className={styles.subtitleText}>
          {props.text}
        </Content>
      ) : (
        <Title headingLevel="h2" size={TitleSizes.md} className={styles.titleText}>
          {props.text}
        </Title>
      )}
    </div>
  )

  if (!props.text) {
    return inner
  }

  return showTooltip ? (
    <Tooltip content={props.text} trigger="mouseenter" entryDelay={300}>
      {inner}
    </Tooltip>
  ) : (
    inner
  )
}

export function SynStepTitle(props: { title?: string; subTitle?: string }) {
  const headingText = props.title || props.subTitle || ''

  return (
    <FlexItem grow={{ default: 'grow' }} style={{ minWidth: 0, width: '100%' }}>
      <TitleLine text={headingText} />
      {props.title && props.subTitle ? <TitleLine text={props.subTitle} isSubtitle /> : null}
    </FlexItem>
  )
}
