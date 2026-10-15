import { createContext } from 'react'

import type { FileContextType } from './useFileUploadState'

export const AIAgentFileContext = createContext<FileContextType | null>(null)
