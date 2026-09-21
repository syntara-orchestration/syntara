import { Button, Tooltip } from '@patternfly/react-core'
import { RhUiSearchIcon } from '@patternfly/react-icons'
import { useRef } from 'react'

import { commandPaletteShortcutLabel } from './commandPaletteShortcut'
import { useCommandPalette } from './useCommandPalette'

export type CommandPaletteNavButtonProps = {
  /** Extra classes for the docked PatternFly button. */
  className?: string
  /** Show a hover tooltip (icon-only collapsed dock). */
  showTooltip?: boolean
}

/**
 * Docked-nav trigger for the command palette. Accessible name includes the
 * platform shortcut (Ctrl/Cmd+K).
 */
export function CommandPaletteNavButton({ className, showTooltip = false }: CommandPaletteNavButtonProps) {
  const { open } = useCommandPalette()
  const searchRef = useRef<HTMLButtonElement>(null)
  const searchButtonLabel = `Search (${commandPaletteShortcutLabel()})`

  return (
    <>
      <Button
        variant="plain"
        isDocked
        className={className}
        icon={<RhUiSearchIcon />}
        aria-label={searchButtonLabel}
        ref={searchRef}
        onClick={open}
      >
        Search
      </Button>
      {showTooltip && (
        <Tooltip aria="none" aria-live="off" triggerRef={searchRef} content={searchButtonLabel} position="right" />
      )}
    </>
  )
}
