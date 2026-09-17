import { filesFetchClient } from '../client'

function fileDeleteMessage(status: number): string {
  if (status === 403) return 'You do not have permission to delete this file.'
  if (status === 404) return 'This file has already been deleted or does not exist.'
  return 'Failed to delete file. Please try again.'
}

class FileDeleteError extends Error {
  readonly status: number

  constructor(status: number) {
    super(fileDeleteMessage(status))
    this.name = 'FileDeleteError'
    this.status = status
  }
}

export async function deleteFileById(fileId: string): Promise<void> {
  const result = await filesFetchClient.DELETE('/files/{file_id}', {
    params: { path: { file_id: fileId } },
  })

  if (result.error || (result.response && !result.response.ok)) {
    throw new FileDeleteError(result.response?.status ?? 500)
  }
}
