import { useQuery } from '@tanstack/react-query'

import { filesFetchClient } from '../../../client'
import type { UploadedFile } from '../components/file-upload'

export function useFilesMetadata(fileIds: string[] | undefined): {
  data: UploadedFile[]
  isLoading: boolean
  isError: boolean
} {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['files', 'metadata', fileIds],
    queryFn: () =>
      filesFetchClient.GET('/files/metadata', {
        params: { query: { file_ids: fileIds ?? [] } },
      }),
    enabled: !!fileIds && fileIds.length > 0,
    select: (res) =>
      res.data?.files.map((f) => ({
        id: f.file_id,
        file: new File([], f.filename, { type: f.mime_type }),
        fileSize: f.size_bytes,
        progress: 100,
        status: 'success' as const,
      })) ?? [],
    staleTime: Infinity,
  })

  return { data: data ?? [], isLoading, isError }
}
