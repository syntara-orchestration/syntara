/**
 * Shared constraints for long PatternFly Select menus.
 *
 * Caps at 25rem (~400px) on tall displays; the 40vh leg keeps the menu inside short
 * viewports so it does not clip the screen edge. `SynSelect` applies these as defaults
 * along with `longSelectMenu.module.css` scroll containment. Override `maxMenuHeight`
 * or `popperProps` on `SynSelect` only when a control needs different bounds.
 */
export const LONG_SELECT_MAX_MENU_HEIGHT = 'min(40vh, 25rem)'

export const longSelectMenuPopperProps = { preventOverflow: true } as const
