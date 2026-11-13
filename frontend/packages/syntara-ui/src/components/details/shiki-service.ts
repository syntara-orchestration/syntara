import { transformerColorizedBrackets } from '@shikijs/colorized-brackets'
import { shikiToMonaco, textmateThemeToMonacoTheme } from '@shikijs/monaco'
import type * as monacoEditorCore from 'monaco-editor-core'
import { createHighlighterCore } from 'shiki/core'
import { createJavaScriptRegexEngine } from 'shiki/engine/javascript'

import { SHIKI_THEME_DARK, SHIKI_THEME_LIGHT } from './shiki-theme'
import type { ShikiThemeName } from './shiki-theme'

type Highlighter = Awaited<ReturnType<typeof createHighlighterCore>>
type Monaco = typeof monacoEditorCore
type HastRoot = ReturnType<Highlighter['codeToHast']>
type HastElement = Extract<HastRoot['children'][number], { type: 'element' }>
type HastContent = HastElement['children'][number]

export type ShikiLanguage = 'bash' | 'json' | 'python'

export type ShikiToken = Readonly<{
  content: string
  style: Readonly<Record<string, string>>
}>

export type ShikiTokenLines = ReadonlyArray<ReadonlyArray<ShikiToken>>

let highlighterPromise: Promise<Highlighter> | undefined
let highlighter: Highlighter | undefined
let bashLanguagePromise: Promise<void> | undefined
let isBashLanguageLoaded = false
let pythonLanguagePromise: Promise<void> | undefined
let isPythonLanguageLoaded = false
const monacoInitializationByInstance = new WeakMap<Monaco, Promise<void>>()
const bracketColorizer = transformerColorizedBrackets()

function getHighlighter(): Promise<Highlighter> {
  highlighterPromise ??= createHighlighterCore({
    themes: [import('@shikijs/themes/github-light-high-contrast'), import('@shikijs/themes/github-dark-high-contrast')],
    langs: [import('@shikijs/langs/json')],
    engine: createJavaScriptRegexEngine(),
  })
    .then((initializedHighlighter) => {
      highlighter = initializedHighlighter
      return initializedHighlighter
    })
    .catch((error: unknown) => {
      highlighterPromise = undefined
      throw error
    })

  return highlighterPromise
}

function loadLanguage(initializedHighlighter: Highlighter, language: ShikiLanguage): Promise<void> {
  switch (language) {
    case 'json':
      return Promise.resolve()
    case 'bash':
      if (isBashLanguageLoaded) return Promise.resolve()
      bashLanguagePromise ??= import('@shikijs/langs/bash')
        .then(({ default: bashLanguage }) => initializedHighlighter.loadLanguage(bashLanguage))
        .then(() => {
          isBashLanguageLoaded = true
        })
        .catch((error: unknown) => {
          bashLanguagePromise = undefined
          throw error
        })
      return bashLanguagePromise
    case 'python':
      if (isPythonLanguageLoaded) return Promise.resolve()
      pythonLanguagePromise ??= import('@shikijs/langs/python')
        .then(({ default: pythonLanguage }) => initializedHighlighter.loadLanguage(pythonLanguage))
        .then(() => {
          isPythonLanguageLoaded = true
        })
        .catch((error: unknown) => {
          pythonLanguagePromise = undefined
          throw error
        })
      return pythonLanguagePromise
  }
}

/** Loads the highlighter, selected grammar, and both color schemes before a code block needs them. */
export async function preloadShiki(language: ShikiLanguage = 'json'): Promise<void> {
  const initializedHighlighter = await getHighlighter()
  await loadLanguage(initializedHighlighter, language)
}

/** Reports whether a component can render tokens without waiting for initialization. */
export function isShikiReady(language: ShikiLanguage = 'json'): boolean {
  return (
    highlighter !== undefined &&
    (language === 'json' ||
      (language === 'bash' && isBashLanguageLoaded) ||
      (language === 'python' && isPythonLanguageLoaded))
  )
}

/** Registers the shared Shiki grammars and themes with a Monaco instance once it mounts. */
export function setupMonacoShiki(monaco: Monaco, themeName: ShikiThemeName): Promise<void> {
  const existingSetup = monacoInitializationByInstance.get(monaco)
  if (existingSetup) return existingSetup.then(() => monaco.editor.setTheme(themeName))

  const setup = Promise.all([preloadShiki('bash'), preloadShiki('json'), preloadShiki('python')])
    .then(async () => {
      const initializedHighlighter = await getHighlighter()
      shikiToMonaco(initializedHighlighter, monaco)

      const lightTheme = textmateThemeToMonacoTheme(initializedHighlighter.getTheme(SHIKI_THEME_LIGHT))
      monaco.editor.defineTheme(SHIKI_THEME_LIGHT, { ...lightTheme, base: 'hc-light', inherit: true })

      const darkTheme = textmateThemeToMonacoTheme(initializedHighlighter.getTheme(SHIKI_THEME_DARK))
      monaco.editor.defineTheme(SHIKI_THEME_DARK, { ...darkTheme, base: 'hc-black', inherit: true })
    })
    .catch((error: unknown) => {
      monacoInitializationByInstance.delete(monaco)
      throw error
    })

  monacoInitializationByInstance.set(monaco, setup)
  return setup.then(() => monaco.editor.setTheme(themeName))
}

/** Highlights source synchronously after the cached highlighter has initialized. */
export function highlightCodeSync(source: string, language: ShikiLanguage): ShikiTokenLines {
  if (!isShikiReady(language) || !highlighter) throw new Error(`Shiki has not been initialized for ${language}`)

  const hast = highlighter.codeToHast(source, {
    lang: language,
    themes: { light: SHIKI_THEME_LIGHT, dark: SHIKI_THEME_DARK },
    defaultColor: false,
    structure: 'classic',
    transformers: [bracketColorizer],
  })
  const preElement = hast.children.find(
    (node): node is HastElement => node.type === 'element' && node.tagName === 'pre'
  )
  const codeElement = preElement?.children.find(
    (node): node is HastElement => node.type === 'element' && node.tagName === 'code'
  )
  if (!codeElement) throw new Error('Shiki did not return a code element')

  const lineElements = codeElement.children.filter(
    (node): node is HastElement => node.type === 'element' && node.tagName === 'span'
  )
  const tokens = lineElements.map((line) =>
    line.children.flatMap((node) => {
      const content = readHastText(node)
      if (content.length === 0) return []

      return [
        {
          content,
          style: node.type === 'element' ? parseInlineStyle(node.properties.style) : {},
        },
      ]
    })
  )

  const tokenizedSource = tokens.map((line) => line.map((token) => token.content).join('')).join('\n')
  if (tokenizedSource !== source) {
    throw new Error('Shiki token output did not preserve the source string')
  }

  return tokens
}

function readHastText(node: HastContent): string {
  if (node.type === 'text') return node.value
  if (node.type === 'element') return node.children.map(readHastText).join('')
  return ''
}

function parseInlineStyle(style: unknown): Readonly<Record<string, string>> {
  if (typeof style !== 'string') return {}

  const styles: Record<string, string> = {}
  for (const declaration of style.split(';')) {
    const separatorIndex = declaration.indexOf(':')
    if (separatorIndex < 0) continue

    const property = declaration.slice(0, separatorIndex).trim()
    const value = declaration.slice(separatorIndex + 1).trim()
    if (property.length > 0 && value.length > 0) styles[property] = value
  }

  return styles
}

/** Loads Shiki if needed, then returns tokens using its synchronous highlighter. */
export async function highlightCode(source: string, language: ShikiLanguage): Promise<ShikiTokenLines> {
  const initializedHighlighter = await getHighlighter()
  await loadLanguage(initializedHighlighter, language)
  return highlightCodeSync(source, language)
}
