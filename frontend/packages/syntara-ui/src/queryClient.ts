// CI fork-coverage probe (DONT MERGE) - touches frontend to trigger UI pipelines.
import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({ defaultOptions: {} })
