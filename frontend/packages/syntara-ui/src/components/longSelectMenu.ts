/**
 * Shared constraints for long PatternFly Select menus (credentials, SA create, builder).
 *
 * Caps at 25rem (~400px) on tall displays; the 40vh leg keeps the menu inside short
 * viewports so it does not clip the screen edge. Pair with `longSelectMenuPopperProps`
 * and `longSelectMenu.module.css` so overflow stays on the menu (no page scroll chaining).
 *
 * Prefer `SynSelect` for app selects; it closes on outer scroll automatically.
 */
export const LONG_SELECT_MAX_MENU_HEIGHT = 'min(40vh, 25rem)'

export const longSelectMenuPopperProps = { preventOverflow: true } as const
