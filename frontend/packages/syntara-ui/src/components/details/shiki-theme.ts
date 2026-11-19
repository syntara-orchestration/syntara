export const SHIKI_THEME_LIGHT = 'github-light-high-contrast'
export const SHIKI_THEME_DARK = 'github-dark-high-contrast'

export type ShikiThemeName = typeof SHIKI_THEME_LIGHT | typeof SHIKI_THEME_DARK

export function getShikiTheme(isDark: boolean): ShikiThemeName {
  return isDark ? SHIKI_THEME_DARK : SHIKI_THEME_LIGHT
}
