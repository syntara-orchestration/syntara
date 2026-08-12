import { beforeEach, describe, expect, it, vi } from 'vitest'

import { filesFetchClient } from '../client'

import { deleteFileById } from './deleteFile'

vi.mock('../client', () => ({
  filesFetchClient: {
    DELETE: vi.fn(),
  },
}))

describe('deleteFileById', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('deletes a file by ID', async () => {
    vi.mocked(filesFetchClient.DELETE).mockResolvedValue({
      data: undefined,
      error: undefined,
      response: new Response(null, { status: 204 }),
    } as never)

    await deleteFileById('file-1')

    expect(filesFetchClient.DELETE).toHaveBeenCalledWith('/files/{file_id}', {
      params: { path: { file_id: 'file-1' } },
    })
  })

  it('throws when the API returns an error payload', async () => {
    vi.mocked(filesFetchClient.DELETE).mockResolvedValue({
      data: undefined,
      error: { detail: 'not found' },
      response: new Response(null, { status: 404 }),
    } as never)

    await expect(deleteFileById('missing')).rejects.toThrow('Failed to delete file')
  })

  it('throws when the response is not ok', async () => {
    vi.mocked(filesFetchClient.DELETE).mockResolvedValue({
      data: undefined,
      error: undefined,
      response: new Response(null, { status: 500 }),
    } as never)

    await expect(deleteFileById('file-1')).rejects.toThrow('Failed to delete file')
  })
})
