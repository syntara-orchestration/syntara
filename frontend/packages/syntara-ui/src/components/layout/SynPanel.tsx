import { Panel, PanelFooter, PanelMain, PanelMainBody, type PanelProps } from '@patternfly/react-core'
import type { ComponentProps, CSSProperties, ReactNode, Ref } from 'react'

import styles from './SynPanel.module.css'

/** Solid panel fill under glass theme without `variant="raised"` chrome (shadow / smaller radius). */
const OPAQUE_FLOATING_PANEL_FILL_STYLE = {
  '--pf-v6-c-panel--BackgroundColor': 'var(--pf-t--global--background--color--floating--default)',
} as CSSProperties

type PanelMainProps = Omit<ComponentProps<typeof PanelMain>, 'children'>
type PanelMainBodyProps = Omit<ComponentProps<typeof PanelMainBody>, 'children'>

/**
 * Convenience wrapper around `Panel -> PanelMain -> PanelMainBody` per the PatternFly
 * [panel composition spec](https://github.com/patternfly/patternfly-react/pull/12372).
 *
 * Inherited prop overrides: `isGlass` defaults **on** unless `isGlass={false}`, `isPill`, or
 * `variant="raised"` is set. `isScrollable + isFullHeight` auto-enables `isAutoHeight` (pass
 * `isAutoHeight={false}` to opt out). Avoid `overflow: hidden` between sibling `variant="raised"`
 * panels - it clips the box-shadow; use `SynPageBody` / `minHeight: 0` instead.
 */
export type SynPanelProps = Omit<PanelProps, 'children'> & {
  /** Rendered inside `PanelMainBody`. */
  children?: ReactNode
  /**
   * Content rendered inside a `PanelFooter` sibling to `PanelMain`.
   * When the panel is `isScrollable`, PanelMain scrolls while the footer stays pinned
   * with PatternFly's built-in border, shadow, and padding.
   */
  footer?: ReactNode
  /** Removes padding from `PanelMainBody`. */
  hasNoPadding?: boolean
  /**
   * Solid floating-token fill (opaque under `pf-v6-theme-glass`) without `variant="raised"` chrome.
   * Prefer `variant="raised"` when you want the full raised look (shadow + smaller radius).
   */
  opaqueFloatingFill?: boolean
  /** Props forwarded to the inner `PanelMain` element. */
  panelMainProps?: PanelMainProps
  /** Props forwarded to the inner `PanelMainBody` element. */
  panelMainBodyProps?: Omit<PanelMainBodyProps, 'children'>
  /** React 19: `ref` is a regular prop (no `forwardRef`). */
  ref?: Ref<HTMLDivElement>
}

function defaultIsGlass(
  isPill: boolean | undefined,
  variant: PanelProps['variant'],
  isGlass: boolean | undefined
): boolean {
  if (isGlass === true) return true
  if (isGlass === false || isPill === true || variant === 'raised') return false
  return true
}

export function SynPanel({
  ref,
  hasNoPadding,
  children,
  footer,
  panelMainProps,
  panelMainBodyProps,
  isScrollable,
  isFullHeight,
  isAutoHeight,
  style: panelStyle,
  className,
  isPill,
  variant,
  isGlass,
  opaqueFloatingFill,
  ...panelProps
}: SynPanelProps) {
  const { style: mainStyle, ...restPanelMain } = panelMainProps ?? {}
  const { style: bodyStyle, className: bodyClassName, ...restBody } = panelMainBodyProps ?? {}

  let mergedBodyStyle: CSSProperties = { ...bodyStyle }
  if (hasNoPadding === true) {
    mergedBodyStyle = { ...mergedBodyStyle, padding: 0 }
  }
  if (isFullHeight === true) {
    if (footer != null) {
      // flex-shrink:0 + flex-basis:auto sizes PanelMainBody to its content so bottom
      // padding is preserved when PanelMain (overflow:auto) scrolls. flex-grow:1 still
      // fills available space when content is shorter than the panel.
      mergedBodyStyle = {
        flex: '1 0 auto',
        display: 'flex',
        flexDirection: 'column',
        ...mergedBodyStyle,
      }
    } else {
      mergedBodyStyle = {
        flex: 1,
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
        ...mergedBodyStyle,
      }
    }
  }
  const bodyStyleProp = Object.keys(mergedBodyStyle).length > 0 ? mergedBodyStyle : undefined

  let mergedMainStyle: CSSProperties = { ...mainStyle }
  if (isFullHeight === true) {
    mergedMainStyle = { flex: 1, minHeight: 0, ...mergedMainStyle }
  }
  const mainStyleProp = Object.keys(mergedMainStyle).length > 0 ? mergedMainStyle : undefined

  const useAutoHeight =
    isAutoHeight === true || (isAutoHeight !== false && isScrollable === true && isFullHeight === true)

  const mergedPanelStyle: CSSProperties = {
    ...(isFullHeight === true ? { flex: 1, minHeight: 0, minWidth: 0 } : {}),
    ...(opaqueFloatingFill === true ? OPAQUE_FLOATING_PANEL_FILL_STYLE : {}),
    ...panelStyle,
  }
  const panelStyleProp = Object.keys(mergedPanelStyle).length > 0 ? mergedPanelStyle : undefined

  return (
    <Panel
      ref={ref}
      className={className}
      style={panelStyleProp}
      isScrollable={isScrollable}
      isFullHeight={isFullHeight}
      isAutoHeight={useAutoHeight ? true : undefined}
      isPill={isPill}
      variant={variant}
      {...panelProps}
      isGlass={defaultIsGlass(isPill, variant, isGlass)}
    >
      <PanelMain {...restPanelMain} style={mainStyleProp}>
        <PanelMainBody {...restBody} className={bodyClassName} style={bodyStyleProp}>
          {children}
        </PanelMainBody>
      </PanelMain>
      {footer != null && <PanelFooter className={styles.footer}>{footer}</PanelFooter>}
    </Panel>
  )
}
