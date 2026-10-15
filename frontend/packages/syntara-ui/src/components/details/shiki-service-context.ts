import { createContext } from 'react'

import { getLoadedShikiService, loadShikiService } from './shiki-service-loader'

export type ShikiServiceLoader = Readonly<{
  getLoadedShikiService: typeof getLoadedShikiService
  loadShikiService: typeof loadShikiService
}>

export const ShikiServiceLoaderContext = createContext<ShikiServiceLoader>({
  getLoadedShikiService,
  loadShikiService,
})
