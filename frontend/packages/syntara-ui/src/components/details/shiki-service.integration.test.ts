import { describe, expect, it } from 'vitest'

import { highlightCode, preloadShiki } from './shiki-service'

describe('Shiki JSON highlighter', () => {
  it('preserves the exact source and emits light and dark theme variables', async () => {
    const source = '{\n  "status": "failed"\n}\n'

    await Promise.all([preloadShiki(), preloadShiki()])
    const tokens = await highlightCode(source, 'json')
    const reconstructedSource = tokens.map((line) => line.map((token) => token.content).join('')).join('\n')
    const hasDualThemeStyle = tokens
      .flat()
      .some((token) => Boolean(token.style['--shiki-light']) && Boolean(token.style['--shiki-dark']))
    const statusToken = tokens.flat().find((token) => token.content.trim() === '"status"')

    expect(reconstructedSource).toBe(source)
    expect(hasDualThemeStyle).toBe(true)
    expect(statusToken?.style).toMatchObject({
      '--shiki-light': '#024C1A',
      '--shiki-dark': '#72F088',
    })
  })

  it('colors matching bracket pairs by nesting depth in both themes', async () => {
    const source = '{\n  "outer": [\n    {\n      "inner": {}\n    }\n  ]\n}'

    await preloadShiki()
    const tokens = await highlightCode(source, 'json')
    const bracketTokens = tokens
      .flat()
      .flatMap((token) =>
        [...token.content]
          .filter((content) => ['{', '}', '[', ']'].includes(content))
          .map((content) => ({ content, style: token.style }))
      )
    const lightColors = bracketTokens.map((token) => token.style['--shiki-light'])
    const darkColors = bracketTokens.map((token) => token.style['--shiki-dark'])

    expect(bracketTokens).toHaveLength(8)
    expect(lightColors.every((color) => typeof color === 'string')).toBe(true)
    expect(darkColors.every((color) => typeof color === 'string')).toBe(true)
    expect(lightColors[0]).toBe(lightColors[7])
    expect(lightColors[1]).toBe(lightColors[6])
    expect(lightColors[2]).toBe(lightColors[5])
    expect(lightColors[3]).toBe(lightColors[4])
    expect(darkColors[0]).toBe(darkColors[7])
    expect(darkColors[1]).toBe(darkColors[6])
    expect(darkColors[2]).toBe(darkColors[5])
    expect(darkColors[3]).toBe(darkColors[4])
    expect(new Set(lightColors).size).toBe(4)
    expect(new Set(darkColors).size).toBe(4)
  })

  it('loads Bash on demand and highlights shell command tokens in both themes', async () => {
    const source = "curl -X POST 'https://example.test/webhooks'"

    await preloadShiki('bash')
    const tokens = await highlightCode(source, 'bash')
    const reconstructedSource = tokens.map((line) => line.map((token) => token.content).join('')).join('\n')
    const curlToken = tokens.flat().find((token) => token.content === 'curl')

    expect(reconstructedSource).toBe(source)
    expect(curlToken?.style['--shiki-light']).toBeTruthy()
    expect(curlToken?.style['--shiki-dark']).toBeTruthy()
  })
})
