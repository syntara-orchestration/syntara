import { StackItem } from '@patternfly/react-core'
import { createContext, use, useLayoutEffect, useMemo, useSyncExternalStore, type ReactNode } from 'react'

import styles from '../FormPromptResponseContent.module.css'

type FormPromptRespondPanelFooterStore = Readonly<{
  getSnapshot: () => ReactNode | null
  setFooter: (footer: ReactNode | null) => void
  subscribe: (onStoreChange: () => void) => () => void
}>

function createFormPromptRespondPanelFooterStore(
  onFooterChange?: (footer: ReactNode | null) => void
): FormPromptRespondPanelFooterStore {
  let footer: ReactNode | null = null
  const listeners = new Set<() => void>()

  return {
    getSnapshot: () => footer,
    setFooter: (next) => {
      if (Object.is(footer, next)) {
        return
      }
      footer = next
      listeners.forEach((listener) => listener())
      onFooterChange?.(next)
    },
    subscribe: (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
  }
}

const FormPromptRespondPanelFooterStoreContext = createContext<FormPromptRespondPanelFooterStore | null>(null)

const emptyFormPromptRespondPanelFooterStore = createFormPromptRespondPanelFooterStore()

type FormPromptRespondPanelFooterProviderProps = Readonly<{
  children: ReactNode
  onFooterChange?: (footer: ReactNode | null) => void
}>

/** Bridges submit actions from `FormPromptResponseContent` to `SynPanel` `footer` in `FormPromptSidePanel`. */
export function FormPromptRespondPanelFooterProvider({
  children,
  onFooterChange,
}: FormPromptRespondPanelFooterProviderProps) {
  const store = useMemo(() => createFormPromptRespondPanelFooterStore(onFooterChange), [onFooterChange])

  return <FormPromptRespondPanelFooterStoreContext value={store}>{children}</FormPromptRespondPanelFooterStoreContext>
}

/** Projected footer content for `SynPanel` `footer` (omit prop when null to avoid an empty `PanelFooter`). */
// eslint-disable-next-line react-refresh/only-export-components -- footer snapshot hook for `SynPanel`
export function useFormPromptRespondPanelFooterSnapshot(): ReactNode | null {
  const store = use(FormPromptRespondPanelFooterStoreContext) ?? emptyFormPromptRespondPanelFooterStore
  return useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot)
}

/** Renders projected footer content (prefer `useFormPromptRespondPanelFooterSnapshot` for `SynPanel` `footer`). */
export function FormPromptRespondPanelFooterOutlet() {
  return useFormPromptRespondPanelFooterSnapshot()
}

type FormPromptRespondPanelFooterSlotProps = Readonly<{
  children: ReactNode
}>

/**
 * Renders into the side panel `SynPanel` footer when a provider is present.
 * Falls back to an inline footer when content is rendered outside the side panel (unit tests).
 */
export function FormPromptRespondPanelFooterSlot({ children }: FormPromptRespondPanelFooterSlotProps) {
  const store = use(FormPromptRespondPanelFooterStoreContext)

  useLayoutEffect(() => {
    if (!store) return undefined
    store.setFooter(children)
    return () => store.setFooter(null)
  }, [store, children])

  if (store) {
    return null
  }

  return <StackItem className={styles.footer}>{children}</StackItem>
}

/** Test helper: renders provider content plus projected footer in the document. */
export function FormPromptRespondPanelFooterTestHarness({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <FormPromptRespondPanelFooterProvider>
      {children}
      <FormPromptRespondPanelFooterTestHarnessFooter />
    </FormPromptRespondPanelFooterProvider>
  )
}

function FormPromptRespondPanelFooterTestHarnessFooter() {
  return <FormPromptRespondPanelFooterOutlet />
}
