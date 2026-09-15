import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { axe } from 'vitest-axe'

import { TestSignInCallback } from './TestSignInCallback'

describe('TestSignInCallback', () => {
  const mockClose = vi.fn()
  let originalClose: typeof globalThis.close

  beforeEach(() => {
    originalClose = globalThis.close
    globalThis.close = mockClose
    mockClose.mockClear()
    localStorage.clear()
  })

  afterEach(() => {
    globalThis.close = originalClose
    localStorage.clear()
    globalThis.location.hash = ''
  })

  it('renders completion message', () => {
    render(<TestSignInCallback />)
    expect(screen.getByText('Sign-in complete. This window should close automatically.')).toBeInTheDocument()
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<TestSignInCallback />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('decodes base64url claims from URL hash and stores in localStorage with nonce', () => {
    const claims = { sub: 'user-123', groups: ['admin', 'users'] }
    const json = JSON.stringify(claims)
    const base64 = btoa(json).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
    const nonce = 'test-nonce-123'
    localStorage.setItem('syntara-test-signin-nonce', nonce)
    globalThis.location.hash = `#${base64}`

    render(<TestSignInCallback />)

    const stored = localStorage.getItem('syntara-test-signin')
    expect(stored).not.toBeNull()
    const parsed = JSON.parse(stored!) as { type: string; nonce: string; claims: Record<string, unknown> }
    expect(parsed.type).toBe('test-signin')
    expect(parsed.nonce).toBe(nonce)
    expect(parsed.claims).toEqual(claims)
  })

  it('leaves the nonce in localStorage for the parent to clean up', () => {
    const claims = { sub: 'user-123' }
    const base64 = btoa(JSON.stringify(claims))
    localStorage.setItem('syntara-test-signin-nonce', 'some-nonce')
    globalThis.location.hash = `#${base64}`

    render(<TestSignInCallback />)

    expect(localStorage.getItem('syntara-test-signin-nonce')).toBe('some-nonce')
  })

  it('discards payload when no nonce is present in localStorage', () => {
    const claims = { sub: 'user-123' }
    const base64 = btoa(JSON.stringify(claims))
    globalThis.location.hash = `#${base64}`

    render(<TestSignInCallback />)

    expect(localStorage.getItem('syntara-test-signin')).toBeNull()
  })

  it('rejects non-object claims (array)', () => {
    localStorage.setItem('syntara-test-signin-nonce', 'nonce')
    globalThis.location.hash = `#${btoa(JSON.stringify(['not', 'an', 'object']))}`

    render(<TestSignInCallback />)

    expect(localStorage.getItem('syntara-test-signin')).toBeNull()
  })

  it('rejects non-object claims (primitive)', () => {
    localStorage.setItem('syntara-test-signin-nonce', 'nonce')
    globalThis.location.hash = `#${btoa(JSON.stringify('just a string'))}`

    render(<TestSignInCallback />)

    expect(localStorage.getItem('syntara-test-signin')).toBeNull()
  })

  it('closes the window after processing', () => {
    render(<TestSignInCallback />)
    expect(mockClose).toHaveBeenCalled()
  })

  it('closes the window even when hash is empty', () => {
    globalThis.location.hash = ''
    render(<TestSignInCallback />)
    expect(mockClose).toHaveBeenCalled()
  })

  it('handles invalid base64 gracefully and still closes', () => {
    localStorage.setItem('syntara-test-signin-nonce', 'nonce')
    globalThis.location.hash = '#not-valid-base64!!!'
    render(<TestSignInCallback />)

    expect(localStorage.getItem('syntara-test-signin')).toBeNull()
    expect(mockClose).toHaveBeenCalled()
  })

  it('handles invalid JSON in decoded base64 gracefully', () => {
    localStorage.setItem('syntara-test-signin-nonce', 'nonce')
    const base64 = btoa('not-json')
    globalThis.location.hash = `#${base64}`

    render(<TestSignInCallback />)

    expect(localStorage.getItem('syntara-test-signin')).toBeNull()
    expect(mockClose).toHaveBeenCalled()
  })
})
