import { Compass, CompassContent } from '@patternfly/react-core'
import { useRef } from 'react'

import { SessionTimeoutWarning } from '../components/session/SessionTimeoutWarning'
import { useRouteChangeFocus } from '../hooks/useRouteChangeFocus'
import { UnsavedChangesProvider } from '../providers/unsaved-changes/UnsavedChangesProvider'

import { AppDockedNav } from './AppDockedNav'
import { AppLogin } from './AppLogin'
import { AppMobileMasthead } from './AppMobileMasthead'
import styles from './AppShell.module.css'
import { DockStateContext, useDockStateProvider } from './useDockState'

/**
 * App chrome: authentication gate, top-level navigation, and the main content area.
 *
 * Rendered as the root layout route component inside TanStack Router's RouterProvider.
 * `UnsavedChangesProvider` lives here so it is always inside a router context.
 */
export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const dockState = useDockStateProvider()
  const mainRef = useRef<HTMLDivElement>(null)
  useRouteChangeFocus(mainRef)

  /* v8 ignore start -- phantom branches from compiled JSX props */
  return (
    <UnsavedChangesProvider>
      <AppLogin>
        <SessionTimeoutWarning />
        <DockStateContext.Provider value={dockState}>
          <Compass
            className="pf-m-no-screen-warning"
            isDockExpanded={dockState.isDockExpanded}
            isDockTextExpanded={dockState.isDockTextExpanded}
            masthead={<AppMobileMasthead />}
            dock={<AppDockedNav />}
            main={
              <CompassContent ref={mainRef} role="main" tabIndex={-1} className={styles.mainContent}>
                {children}
              </CompassContent>
            }
          />
        </DockStateContext.Provider>
      </AppLogin>
    </UnsavedChangesProvider>
  )
  /* v8 ignore stop */
}
