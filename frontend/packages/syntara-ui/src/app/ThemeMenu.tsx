import {
  Button,
  Divider,
  MenuSearch,
  MenuSearchInput,
  Popover,
  SelectGroup,
  ToggleGroup,
  ToggleGroupItem,
  Tooltip,
} from '@patternfly/react-core'
import { RhUiAutoLightDarkModeIcon, RhUiDarkModeIcon, RhUiLightModeIcon } from '@patternfly/react-icons'
import { useRef, useState } from 'react'

import type { ColorSchemePreference } from '../providers/theme/colorScheme'
import type { ContrastPreference } from '../providers/theme/contrastMode'
import { useColorScheme } from '../providers/theme/useColorScheme'

import styles from './ThemeMenu.module.css'

const COLOR_SCHEME_TITLE_ID = 'theme-menu-color-scheme'
const CONTRAST_MODE_TITLE_ID = 'theme-menu-contrast'

const COLOR_SCHEME_OPTIONS = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
] as const satisfies readonly { value: ColorSchemePreference; label: string }[]

const CONTRAST_OPTIONS = [
  { value: 'system', label: 'System' },
  { value: 'default', label: 'Default' },
  { value: 'high-contrast', label: 'High contrast' },
  { value: 'glass', label: 'Glass' },
] as const satisfies readonly { value: ContrastPreference; label: string }[]

function colorSchemeLabel(preference: ColorSchemePreference): string {
  return COLOR_SCHEME_OPTIONS.find((option) => option.value === preference)?.label ?? 'System'
}

function contrastLabel(preference: ContrastPreference): string {
  return CONTRAST_OPTIONS.find((option) => option.value === preference)?.label ?? 'System'
}

function themeToggleName(colorPreference: ColorSchemePreference, contrastPreference: ContrastPreference): string {
  return `Theme, color scheme ${colorSchemeLabel(colorPreference)}, contrast ${contrastLabel(contrastPreference)}`
}

function colorSchemeIcon(preference: ColorSchemePreference) {
  if (preference === 'light') {
    return <RhUiLightModeIcon />
  }
  if (preference === 'dark') {
    return <RhUiDarkModeIcon />
  }
  return <RhUiAutoLightDarkModeIcon />
}

function colorSchemeButtonId(value: ColorSchemePreference): string {
  return `theme-color-${value}`
}

function contrastButtonId(value: ContrastPreference): string {
  return `theme-contrast-${value}`
}

/**
 * Theme preferences open in a PatternFly popover dialog. The segmented toggle
 * groups mirror the PatternFly documentation theme selector. Theme variant
 * (Default vs Project Felt) stays on the brand config, not this panel.
 */
export function ThemeMenu(props: Readonly<{ showTooltip: boolean }>) {
  const { colorSchemePreference, setColorScheme, contrastPreference, setContrastMode } = useColorScheme()
  const [isOpen, setIsOpen] = useState(false)
  const toggleRef = useRef<HTMLButtonElement | null>(null)
  const toggleName = themeToggleName(colorSchemePreference, contrastPreference)

  return (
    <>
      <Button
        ref={toggleRef}
        isExpanded={isOpen}
        isDocked
        variant="plain"
        icon={colorSchemeIcon(colorSchemePreference)}
        aria-label={toggleName}
        aria-haspopup="dialog"
        onClick={() => setIsOpen((open) => !open)}
      >
        Theme
      </Button>
      <Popover
        isVisible={isOpen}
        triggerRef={toggleRef}
        shouldClose={() => setIsOpen(false)}
        aria-label="Theme settings"
        showClose={false}
        withFocusTrap
        position="right-end"
        distance={8}
        hasNoPadding
        hasAutoWidth
        className={styles.themeMenu}
        bodyContent={
          <div
            className={styles.themeContent}
            role="presentation"
            onMouseDown={(event) => {
              // PatternFly's Popover disables its trap on bubbled mousedown; keep this
              // presentational wrapper from disabling the modal dialog's focus trap.
              event.stopPropagation()
            }}
          >
            <SelectGroup
              label={
                <div className="pf-v6-c-menu__group-title" id={COLOR_SCHEME_TITLE_ID}>
                  Color scheme
                </div>
              }
            >
              <MenuSearch>
                <MenuSearchInput>
                  <ToggleGroup aria-labelledby={COLOR_SCHEME_TITLE_ID}>
                    {COLOR_SCHEME_OPTIONS.map((option) => (
                      <ToggleGroupItem
                        key={option.value}
                        text={option.label}
                        buttonId={colorSchemeButtonId(option.value)}
                        isSelected={colorSchemePreference === option.value}
                        onChange={() => {
                          setColorScheme(option.value)
                        }}
                      />
                    ))}
                  </ToggleGroup>
                </MenuSearchInput>
              </MenuSearch>
            </SelectGroup>
            <Divider />
            <SelectGroup
              label={
                <div className="pf-v6-c-menu__group-title" id={CONTRAST_MODE_TITLE_ID}>
                  Contrast mode
                </div>
              }
            >
              <MenuSearch>
                <MenuSearchInput>
                  <ToggleGroup aria-labelledby={CONTRAST_MODE_TITLE_ID}>
                    {CONTRAST_OPTIONS.map((option) => (
                      <ToggleGroupItem
                        key={option.value}
                        text={option.label}
                        buttonId={contrastButtonId(option.value)}
                        isSelected={contrastPreference === option.value}
                        onChange={() => {
                          setContrastMode(option.value)
                        }}
                      />
                    ))}
                  </ToggleGroup>
                </MenuSearchInput>
              </MenuSearch>
            </SelectGroup>
          </div>
        }
      />
      {props.showTooltip && !isOpen && (
        <Tooltip aria="none" aria-live="off" triggerRef={toggleRef} content={toggleName} position="right" />
      )}
    </>
  )
}
