type ShikiService = typeof import('./shiki-service')

let shikiServiceModule: ShikiService | undefined
let shikiServicePromise: Promise<ShikiService> | undefined

/** Loads the heavy Shiki service only for views that opt into highlighting. */
export function loadShikiService(): Promise<ShikiService> {
  shikiServicePromise ??= import('./shiki-service')
    .then((service) => {
      shikiServiceModule = service
      return service
    })
    .catch((error: unknown) => {
      shikiServicePromise = undefined
      throw error
    })

  return shikiServicePromise
}

/** Returns the service module once its lazy import has completed. */
export function getLoadedShikiService(): ShikiService | undefined {
  return shikiServiceModule
}
