import { Content, ContentVariants, FlexItem, Title, TitleSizes, Tooltip } from '@patternfly/react-core'
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'

import styles from './SynStepTitle.module.css'

function useTruncated(text: string) {
  const ref = useRef<HTMLDivElement>(null)
  const [truncated, setTruncated] = useState(false)

  const measure = useCallback(() => {
    const el = ref.current?.firstElementChild
    if (!(el instanceof HTMLElement)) {
      setTruncated(false)
      return
    }
    setTruncated(el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1)
  }, [])

  useLayoutEffect(() => {
    measure()
    const el = ref.current?.firstElementChild
    if (!(el instanceof HTMLElement) || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => measure())
    observer.observe(el)
    return () => observer.disconnect()
  }, [measure, text])

  return { ref, truncated }
}

function useStepFocus(ref: RefObject<HTMLElement | null>) {
  const [focused, setFocused] = useState(false)

  useEffect(() => {
    const el = ref.current
    const root = el?.closest('.react-flow__node') ?? el?.closest('[data-syn-step-root]')
    if (!root) return

    const onFocusIn = (event: Event) => {
      const target = event.target
      if (!(target instanceof Element)) return
      setFocused(target.closest('[data-syn-step-actions]') == null)
    }
    const onFocusOut = (event: Event) => {
      const next = 'relatedTarget' in event ? event.relatedTarget : null
      if (!(next instanceof Node) || !root.contains(next)) {
        setFocused(false)
      }
    }

    root.addEventListener('focusin', onFocusIn)
    root.addEventListener('focusout', onFocusOut)
    return () => {
      root.removeEventListener('focusin', onFocusIn)
      root.removeEventListener('focusout', onFocusOut)
    }
  }, [ref])

  return focused
}

function ClampedLine(props: { text: string; isSubtitle?: boolean }) {
  const { ref, truncated } = useTruncated(props.text)
  const stepFocused = useStepFocus(ref)
  const className = props.isSubtitle ? styles.subtitleText : styles.titleText

  const inner = (
    <div ref={ref} className={styles.textWrapper}>
      {props.isSubtitle ? (
        <Content component={ContentVariants.small} className={className}>
          {props.text}
        </Content>
      ) : (
        <Title headingLevel="h2" size={TitleSizes.md} className={className}>
          {props.text}
        </Title>
      )}
    </div>
  )

  if (!props.text || !truncated) {
    return inner
  }

  if (stepFocused) {
    return (
      <Tooltip content={props.text} trigger="manual" isVisible>
        {inner}
      </Tooltip>
    )
  }

  return (
    <Tooltip content={props.text} trigger="mouseenter" entryDelay={300}>
      {inner}
    </Tooltip>
  )
}

export function SynStepTitle(props: { title?: string; subTitle?: string }) {
  const headingText = props.title || props.subTitle || ''

  return (
    <FlexItem grow={{ default: 'grow' }} style={{ minWidth: 0, width: '100%' }}>
      <ClampedLine text={headingText} />
      {props.title && props.subTitle ? <ClampedLine text={props.subTitle} isSubtitle /> : null}
    </FlexItem>
  )
}
