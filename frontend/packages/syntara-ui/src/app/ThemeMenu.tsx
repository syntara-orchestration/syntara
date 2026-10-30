import {
  Divider,
  MenuSearch,
  MenuSearchInput,
  MenuToggle,
  SelectGroup,
  ToggleGroup,
  ToggleGroupItem,
  Tooltip,
} from '@patternfly/react-core'
import type { MenuToggleElement } from '@patternfly/react-core'
import { RhUiAutoLightDarkModeIcon, RhUiDarkModeIcon, RhUiLightModeIcon } from '@patternfly/react-icons'
import { useRef, useState } from 'react'

import { SynSelect } from '../components/SynSelect'
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
 * Masthead theme menu modeled on the PatternFly documentation theme selector:
 * separate toggle groups for color scheme and contrast mode. Theme variant
 * (Default vs Project Felt) stays on the brand config, not this menu.
 */
export function ThemeMenu(props: Readonly<{ showTooltip: boolean }>) {
  const { colorSchemePreference, setColorScheme, contrastPreference, setContrastMode } = useColorScheme()
  const [isOpen, setIsOpen] = useState(false)
  const toggleRef = useRef<HTMLButtonElement | null>(null)
  const toggleName = themeToggleName(colorSchemePreference, contrastPreference)

  const toggle = (dropdownRef: React.Ref<MenuToggleElement>) => (
    <MenuToggle
      ref={(node) => {
        toggleRef.current = node instanceof HTMLButtonElement ? node : null
        if (typeof dropdownRef === 'function') {
          dropdownRef(node)
        } else if (dropdownRef) {
          dropdownRef.current = node
        }
      }}
      isExpanded={isOpen}
      variant="plain"
      icon={colorSchemeIcon(colorSchemePreference)}
      isDocked
      aria-label={toggleName}
      onClick={() => setIsOpen((open) => !open)}
    >
      Theme
    </MenuToggle>
  )

  return (
    <>
      <SynSelect
        isOpen={isOpen}
        onOpenChange={setIsOpen}
        onOpenChangeKeys={['Escape']}
        shouldFocusToggleOnSelect
        toggle={toggle}
        className={styles.themeMenu}
        isScrollable={false}
        popperProps={{
          placement: 'right-start',
          preventOverflow: true,
          enableFlip: true,
          width: 'max-content',
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
      </SynSelect>
      {props.showTooltip && (
        <Tooltip aria="none" aria-live="off" triggerRef={toggleRef} content={toggleName} position="right" />
      )}
    </>
  )
}
