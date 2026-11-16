import { editIntegrationNameSchema } from './editIntegrationNameSchema'

describe('editIntegrationNameSchema', () => {
  it('accepts a non-empty name', () => {
    const result = editIntegrationNameSchema.safeParse({ name: 'ocp-us-east' })
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.name).toBe('ocp-us-east')
    }
  })

  it('trims whitespace and accepts the trimmed value', () => {
    const result = editIntegrationNameSchema.safeParse({ name: '  renamed  ' })
    expect(result.success).toBe(true)
    if (result.success) {
      expect(result.data.name).toBe('renamed')
    }
  })

  it('rejects an empty name', () => {
    const result = editIntegrationNameSchema.safeParse({ name: '' })
    expect(result.success).toBe(false)
  })

  it('rejects a whitespace-only name', () => {
    const result = editIntegrationNameSchema.safeParse({ name: '   ' })
    expect(result.success).toBe(false)
  })
})
