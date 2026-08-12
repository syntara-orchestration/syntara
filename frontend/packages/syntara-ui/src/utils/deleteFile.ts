import { filesFetchClient } from '../client'

/**
 * Permanently delete a stored file by ID via DELETE /files/{file_id}.
 * Works for orphaned files whose project has been deleted.
 */
export async function deleteFileById(fileId: string): Promise<void> {
  const result = await filesFetchClient.DELETE('/files/{file_id}', {
    params: { path: { file_id: fileId } },
  })

  if (result.error || (result.response && !result.response.ok)) {
    throw new Error('Failed to delete file')
  }
}
