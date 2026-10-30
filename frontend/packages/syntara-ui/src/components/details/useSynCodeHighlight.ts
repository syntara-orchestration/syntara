import { use, useEffect, useMemo, useState } from 'react'

import { detachPromise } from '../../utils/detachPromise'

import type { ShikiLanguage, ShikiTokenLines } from './shiki-service'
import { ShikiServiceLoaderContext } from './shiki-service-context'
import type { ShikiServiceLoader } from './shiki-service-context'

type ShikiService = typeof import('./shiki-service')

type HighlightState =
  | Readonly<{
      status: 'ready'
      highlightKey: string
      language: ShikiLanguage
      source: string
      tokens: ShikiTokenLines
    }>
  | Readonly<{
      status: 'error'
      highlightKey: string
      language: ShikiLanguage
      source: string
    }>

type HighlightRequest = Readonly<{
  enabled: boolean
  source: string | undefined
  language: ShikiLanguage | undefined
  highlightKey: string
}>

function hasSameIdentity(
  state: HighlightState | undefined,
  highlightKey: string,
  language: ShikiLanguage | undefined
): boolean {
  return state?.highlightKey === highlightKey && state.language === language
}

function isCurrentSource(
  state: HighlightState | undefined,
  highlightKey: string,
  language: ShikiLanguage | undefined,
  source: string | undefined
): boolean {
  return hasSameIdentity(state, highlightKey, language) && state?.source === source
}

function tokenizeNow(
  service: ShikiService,
  source: string,
  language: ShikiLanguage,
  highlightKey: string
): HighlightState {
  try {
    return { status: 'ready', highlightKey, language, source, tokens: service.highlightCodeSync(source, language) }
  } catch {
    return { status: 'error', highlightKey, language, source }
  }
}

function getInitialHighlight(request: HighlightRequest, serviceLoader: ShikiServiceLoader): HighlightState | undefined {
  if (!request.enabled || !request.language || request.source === undefined) return undefined
  const { highlightKey, language, source } = request
  const service = serviceLoader.getLoadedShikiService()
  if (!service?.isShikiReady(language)) return undefined
  return tokenizeNow(service, source, language, highlightKey)
}

function getImmediateHighlight(
  request: HighlightRequest,
  state: HighlightState | undefined,
  service: ShikiService | undefined
): HighlightState | undefined {
  if (!request.enabled || !request.language || request.source === undefined || !service?.isShikiReady(request.language))
    return undefined
  if (hasSameIdentity(state, request.highlightKey, request.language)) return undefined
  return tokenizeNow(service, request.source, request.language, request.highlightKey)
}

async function loadHighlight(
  source: string,
  language: ShikiLanguage,
  highlightKey: string,
  serviceLoader: ShikiServiceLoader
): Promise<HighlightState> {
  try {
    const service = await serviceLoader.loadShikiService()
    await service.preloadShiki(language)
    const tokens = await service.highlightCode(source, language)
    return { status: 'ready', highlightKey, language, source, tokens }
  } catch {
    return { status: 'error', highlightKey, language, source }
  }
}

function getDisplayedView(
  request: HighlightRequest,
  state: HighlightState | undefined,
  immediate: HighlightState | undefined
): HighlightedCodeView {
  if (!request.enabled || request.source === undefined) return { status: 'plain', source: request.source ?? '' }

  if (state?.status === 'ready' && hasSameIdentity(state, request.highlightKey, request.language)) {
    return { status: 'ready', source: state.source, tokens: state.tokens }
  }
  if (immediate?.status === 'ready') {
    return { status: 'ready', source: immediate.source, tokens: immediate.tokens }
  }
  if (immediate?.status === 'error') return { status: 'plain', source: request.source }
  if (state?.status === 'error' && isCurrentSource(state, request.highlightKey, request.language, request.source)) {
    return { status: 'plain', source: request.source }
  }
  return { status: 'plain', source: request.source }
}

export type HighlightedCodeView =
  Readonly<{ status: 'ready'; source: string; tokens: ShikiTokenLines }> | Readonly<{ status: 'plain'; source: string }>

/** Holds the current source and token stream together across async highlighting. */
export function useSynCodeHighlight(
  enabled: boolean,
  source: string | undefined,
  language: ShikiLanguage | undefined,
  highlightKey: string
): HighlightedCodeView {
  const serviceLoader = use(ShikiServiceLoaderContext)
  const request = useMemo(
    () => ({ enabled, source, language, highlightKey }),
    [enabled, highlightKey, language, source]
  )
  const [highlightState, setHighlightState] = useState<HighlightState | undefined>(() =>
    getInitialHighlight(request, serviceLoader)
  )
  const shikiService = serviceLoader.getLoadedShikiService()
  const immediateHighlight = useMemo(
    () => getImmediateHighlight(request, highlightState, shikiService),
    [highlightState, request, shikiService]
  )

  useEffect(() => {
    if (
      !enabled ||
      !language ||
      source === undefined ||
      isCurrentSource(highlightState, highlightKey, language, source)
    ) {
      return
    }
    if (immediateHighlight) return

    let isCurrentRequest = true
    detachPromise(
      loadHighlight(source, language, highlightKey, serviceLoader).then((result) => {
        if (isCurrentRequest) setHighlightState(result)
      })
    )
    return () => {
      isCurrentRequest = false
    }
  }, [enabled, highlightKey, highlightState, immediateHighlight, language, serviceLoader, source])

  return getDisplayedView(request, highlightState, immediateHighlight)
}
