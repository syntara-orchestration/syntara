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

  it('throws with permission message on 403', async () => {
    vi.mocked(filesFetchClient.DELETE).mockResolvedValue({
      data: undefined,
      error: { detail: 'forbidden' },
      response: new Response(null, { status: 403 }),
    } as never)

    await expect(deleteFileById('file-1')).rejects.toThrow('You do not have permission to delete this file.')
  })

  it('throws with not-found message on 404', async () => {
    vi.mocked(filesFetchClient.DELETE).mockResolvedValue({
      data: undefined,
      error: { detail: 'not found' },
      response: new Response(null, { status: 404 }),
    } as never)

    await expect(deleteFileById('missing')).rejects.toThrow('already been deleted or does not exist')
  })

  it('throws with retry message on 500', async () => {
    vi.mocked(filesFetchClient.DELETE).mockResolvedValue({
      data: undefined,
      error: undefined,
      response: new Response(null, { status: 500 }),
    } as never)

    await expect(deleteFileById('file-1')).rejects.toThrow('Failed to delete file. Please try again.')
  })
})
