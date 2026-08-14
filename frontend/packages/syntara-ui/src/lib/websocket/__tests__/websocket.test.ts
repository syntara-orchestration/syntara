import { renderHook, act } from '@testing-library/react'
import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'

import { useAuthStore } from '../../../stores/useAuthStore'
import { WebSocketChannel, type WebSocketChannelConfig } from '../channels'
import { useWebSocket, useWebSocketState, useIsWebSocketConnected } from '../hooks'
import { useWebSocketStore } from '../store'
import { getConnectionStateLabel, getConnectionStateColor } from '../utils'

// ============================================================================
// Mock WebSocket
// ============================================================================

let mockWebSocketInstances: MockWebSocket[] = []

class MockWebSocket {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3

  url: string
  readyState: number = MockWebSocket.CONNECTING

  onopen: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  private sentMessages: string[] = []

  constructor(url: string) {
    this.url = url
    mockWebSocketInstances.push(this)
  }

  send(data: string): void {
    if (this.readyState !== MockWebSocket.OPEN) {
      throw new Error('WebSocket is not open')
    }
    this.sentMessages.push(data)
  }

  close(code?: number): void {
    this.readyState = MockWebSocket.CLOSED
    if (this.onclose) {
      this.onclose({ code: code ?? 1000 } as CloseEvent)
    }
  }

  simulateOpen(): void {
    this.readyState = MockWebSocket.OPEN
    if (this.onopen) {
      this.onopen(new Event('open'))
    }
  }

  simulateMessage(data: unknown): void {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) } as MessageEvent)
    }
  }

  simulateClose(code = 1006): void {
    this.readyState = MockWebSocket.CLOSED
    if (this.onclose) {
      this.onclose({ code } as CloseEvent)
    }
  }

  getSentMessages(): string[] {
    return this.sentMessages
  }
}

// ============================================================================
// Test Setup
// ============================================================================

describe('WebSocket Store', () => {
  beforeEach(() => {
    mockWebSocketInstances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.useFakeTimers()
    useWebSocketStore.getState().reset()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  // ============================================================================
  // Connection Tests
  // ============================================================================

  describe('connect', () => {
    it('creates a WebSocket connection', () => {
      useWebSocketStore.getState().connect('test', '/ws/test')

      expect(mockWebSocketInstances).toHaveLength(1)
      expect(mockWebSocketInstances[0].url).toBe('ws://localhost:3000/ws/test')
    })

    it('handles full URLs', () => {
      useWebSocketStore.getState().connect('test', 'wss://other.server.com/ws')

      expect(mockWebSocketInstances[0].url).toBe('wss://other.server.com/ws')
    })

    it('does not create duplicate connections', () => {
      useWebSocketStore.getState().connect('test', '/ws/test')
      mockWebSocketInstances[0].simulateOpen()

      useWebSocketStore.getState().connect('test', '/ws/test')

      expect(mockWebSocketInstances).toHaveLength(1)
    })

    it('tracks connection state', () => {
      useWebSocketStore.getState().connect('test', '/ws/test')
      expect(useWebSocketStore.getState().getConnectionState('test')).toBe('connecting')

      mockWebSocketInstances[0].simulateOpen()
      expect(useWebSocketStore.getState().getConnectionState('test')).toBe('connected')
      expect(useWebSocketStore.getState().isConnected('test')).toBe(true)
    })
  })

  // ============================================================================
  // Disconnect Tests
  // ============================================================================

  describe('disconnect', () => {
    it('closes the connection', () => {
      useWebSocketStore.getState().connect('test', '/ws/test')
      mockWebSocketInstances[0].simulateOpen()

      useWebSocketStore.getState().disconnect('test')

      expect(useWebSocketStore.getState().getConnectionState('test')).toBe('disconnected')
    })

    it('disconnects all channels', () => {
      useWebSocketStore.getState().connect('ch1', '/ws/ch1')
      useWebSocketStore.getState().connect('ch2', '/ws/ch2')
      mockWebSocketInstances.forEach((ws) => ws.simulateOpen())

      useWebSocketStore.getState().disconnectAll()

      expect(useWebSocketStore.getState().isConnected('ch1')).toBe(false)
      expect(useWebSocketStore.getState().isConnected('ch2')).toBe(false)
    })
  })

  // ============================================================================
  // Send Tests
  // ============================================================================

  describe('send', () => {
    it('sends messages when connected', () => {
      useWebSocketStore.getState().connect('test', '/ws/test')
      mockWebSocketInstances[0].simulateOpen()

      const result = useWebSocketStore.getState().send('test', { type: 'Test', payload: { data: 'hello' } })

      expect(result).toBe(true)
      expect(mockWebSocketInstances[0].getSentMessages()).toHaveLength(1)
    })

    it('returns false when not connected', () => {
      useWebSocketStore.getState().connect('test', '/ws/test')

      const result = useWebSocketStore.getState().send('test', { type: 'Test', payload: {} })

      expect(result).toBe(false)
    })
  })

  // ============================================================================
  // SendRaw Tests
  // ============================================================================

  describe('sendRaw', () => {
    it('sends raw data without wrapping when connected', () => {
      useWebSocketStore.getState().connect('test', '/ws/test')
      mockWebSocketInstances[0].simulateOpen()

      const result = useWebSocketStore.getState().sendRaw('test', { input: 'hello' })

      expect(result).toBe(true)
      const sent: unknown = JSON.parse(mockWebSocketInstances[0].getSentMessages()[0])
      expect(sent).toEqual({ input: 'hello' })
    })

    it('returns false when not connected', () => {
      useWebSocketStore.getState().connect('test', '/ws/test')

      const result = useWebSocketStore.getState().sendRaw('test', { input: 'hello' })

      expect(result).toBe(false)
    })

    it('sends data without adding timestamp', () => {
      useWebSocketStore.getState().connect('test', '/ws/test')
      mockWebSocketInstances[0].simulateOpen()

      useWebSocketStore.getState().sendRaw('test', { message: 'test' })

      const sent = JSON.parse(mockWebSocketInstances[0].getSentMessages()[0]) as Record<string, unknown>
      expect(sent).toEqual({ message: 'test' })
      expect(sent.timestamp).toBeUndefined()
    })
  })

  // ============================================================================
  // Subscription Tests
  // ============================================================================

  describe('subscribe', () => {
    it('receives messages', () => {
      const messages: unknown[] = []
      useWebSocketStore.getState().subscribe('test', {
        onMessage: (msg) => messages.push(msg),
      })

      useWebSocketStore.getState().connect('test', '/ws/test')
      mockWebSocketInstances[0].simulateOpen()
      mockWebSocketInstances[0].simulateMessage({ type: 'Event', payload: { value: 42 } })

      expect(messages).toHaveLength(1)
    })

    it('filters by message type', () => {
      const messages: unknown[] = []
      useWebSocketStore.getState().subscribe('test', {
        onMessage: (msg) => messages.push(msg),
        messageTypes: ['Wanted'],
      })

      useWebSocketStore.getState().connect('test', '/ws/test')
      mockWebSocketInstances[0].simulateOpen()
      mockWebSocketInstances[0].simulateMessage({ type: 'Unwanted', payload: {} })
      mockWebSocketInstances[0].simulateMessage({ type: 'Wanted', payload: {} })

      expect(messages).toHaveLength(1)
    })

    it('unsubscribes correctly', () => {
      const messages: unknown[] = []
      const unsubscribe = useWebSocketStore.getState().subscribe('test', {
        onMessage: (msg) => messages.push(msg),
      })

      useWebSocketStore.getState().connect('test', '/ws/test')
      mockWebSocketInstances[0].simulateOpen()
      mockWebSocketInstances[0].simulateMessage({ type: 'Event1', payload: {} })

      unsubscribe()

      mockWebSocketInstances[0].simulateMessage({ type: 'Event2', payload: {} })

      expect(messages).toHaveLength(1)
    })
  })

  // ============================================================================
  // Reconnection Tests
  // ============================================================================

  describe('reconnection', () => {
    it('reconnects on non-clean close', () => {
      useWebSocketStore.getState().connect('test', '/ws/test')
      mockWebSocketInstances[0].simulateOpen()
      mockWebSocketInstances[0].simulateClose(1006)

      expect(useWebSocketStore.getState().getConnectionState('test')).toBe('reconnecting')

      vi.advanceTimersByTime(100)

      expect(mockWebSocketInstances).toHaveLength(2)
    })

    it('does not reconnect on clean close', () => {
      useWebSocketStore.getState().connect('test', '/ws/test')
      mockWebSocketInstances[0].simulateOpen()
      mockWebSocketInstances[0].simulateClose(1000)

      vi.advanceTimersByTime(1000)

      expect(mockWebSocketInstances).toHaveLength(1)
    })

    it('fails after max attempts', () => {
      useWebSocketStore.getState().updateConfig({
        reconnection: { initialDelay: 100, maxDelay: 1000, backoffMultiplier: 2, maxAttempts: 3 },
      })

      useWebSocketStore.getState().connect('test', '/ws/test')
      mockWebSocketInstances[0].simulateOpen()

      for (let i = 0; i < 3; i++) {
        mockWebSocketInstances[i].simulateClose(1006)
        vi.advanceTimersByTime(1000)
      }

      mockWebSocketInstances[3].simulateClose(1006)

      expect(useWebSocketStore.getState().getConnectionState('test')).toBe('failed')
    })
  })

  // ============================================================================
  // Utility Tests
  // ============================================================================

  describe('utilities', () => {
    it('getConnectionStateLabel returns correct labels', () => {
      expect(getConnectionStateLabel('connected')).toBe('Connected')
      expect(getConnectionStateLabel('disconnected')).toBe('Disconnected')
      expect(getConnectionStateLabel('failed')).toBe('Connection Failed')
    })

    it('getConnectionStateColor returns correct colors', () => {
      expect(getConnectionStateColor('connected')).toBe('green')
      expect(getConnectionStateColor('disconnected')).toBe('gray')
      expect(getConnectionStateColor('failed')).toBe('red')
    })
  })
})

// ============================================================================
// Hook Tests
// ============================================================================

describe('useWebSocket hook', () => {
  beforeEach(() => {
    mockWebSocketInstances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    useWebSocketStore.getState().reset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('auto-connects on mount with predefined channel', () => {
    renderHook(() => useWebSocket(WebSocketChannel.Chat))

    expect(mockWebSocketInstances).toHaveLength(1)
    expect(mockWebSocketInstances[0].url).toContain('/ws/example/v1/chat')
  })

  it('does not auto-connect when autoConnect is false', () => {
    renderHook(() => useWebSocket(WebSocketChannel.Chat, { autoConnect: false }))

    expect(mockWebSocketInstances).toHaveLength(0)
  })

  it('returns correct connection state', () => {
    const { result, rerender } = renderHook(() => useWebSocket(WebSocketChannel.Chat))

    expect(result.current.connectionState).toBe('connecting')
    expect(result.current.isConnected).toBe(false)

    act(() => {
      mockWebSocketInstances[0].simulateOpen()
    })

    rerender()

    expect(result.current.connectionState).toBe('connected')
    expect(result.current.isConnected).toBe(true)
  })

  it('calls onMessage callback when message received', () => {
    const onMessage = vi.fn()
    renderHook(() => useWebSocket(WebSocketChannel.Chat, { onMessage }))

    act(() => {
      mockWebSocketInstances[0].simulateOpen()
    })

    act(() => {
      mockWebSocketInstances[0].simulateMessage({ type: 'test', payload: { data: 'hello' } })
    })

    expect(onMessage).toHaveBeenCalledTimes(1)
  })

  it('sendRaw sends data when connected', () => {
    const { result } = renderHook(() => useWebSocket(WebSocketChannel.Chat))

    act(() => {
      mockWebSocketInstances[0].simulateOpen()
    })

    let sendResult: boolean
    act(() => {
      sendResult = result.current.sendRaw({ message: 'hello' })
    })

    expect(sendResult!).toBe(true)
    expect(mockWebSocketInstances[0].getSentMessages()).toHaveLength(1)
  })

  it('sendRaw returns false when not connected', () => {
    const { result } = renderHook(() => useWebSocket(WebSocketChannel.Chat))

    const sendResult = result.current.sendRaw({ message: 'hello' })

    expect(sendResult).toBe(false)
  })

  it('manual connect/disconnect works', () => {
    const { result, rerender } = renderHook(() => useWebSocket(WebSocketChannel.Coffee, { autoConnect: false }))

    expect(mockWebSocketInstances).toHaveLength(0)

    act(() => {
      result.current.connect()
    })

    expect(mockWebSocketInstances).toHaveLength(1)

    act(() => {
      mockWebSocketInstances[0].simulateOpen()
    })

    rerender()
    expect(result.current.isConnected).toBe(true)

    act(() => {
      result.current.disconnect()
    })

    rerender()
    expect(result.current.isConnected).toBe(false)
  })

  it('disconnects on unmount when autoDisconnect is true', () => {
    const { result, unmount, rerender } = renderHook(() =>
      useWebSocket(WebSocketChannel.Chat, { autoDisconnect: true })
    )

    act(() => {
      mockWebSocketInstances[0].simulateOpen()
    })

    rerender()
    expect(result.current.isConnected).toBe(true)

    unmount()

    expect(useWebSocketStore.getState().getConnectionState('chat')).toBe('disconnected')
  })

  it('works with custom channel config', () => {
    const customChannel = { id: 'custom', path: '/ws/custom/endpoint' } as unknown as WebSocketChannelConfig
    renderHook(() => useWebSocket(customChannel))

    expect(mockWebSocketInstances).toHaveLength(1)
    expect(mockWebSocketInstances[0].url).toContain('/ws/custom/endpoint')
  })
})

// ============================================================================
// Simple Hook Tests
// ============================================================================

describe('useWebSocketState hook', () => {
  beforeEach(() => {
    mockWebSocketInstances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    useWebSocketStore.getState().reset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns connection state for channel', () => {
    useWebSocketStore.getState().connect('test', '/ws/test')

    const { result } = renderHook(() => useWebSocketState('test'))

    expect(result.current).toBe('connecting')
  })

  it('returns disconnected for unknown channel', () => {
    const { result } = renderHook(() => useWebSocketState('unknown'))

    expect(result.current).toBe('disconnected')
  })
})

describe('useIsWebSocketConnected hook', () => {
  beforeEach(() => {
    mockWebSocketInstances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    useWebSocketStore.getState().reset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns false when not connected', () => {
    const { result } = renderHook(() => useIsWebSocketConnected('test'))

    expect(result.current).toBe(false)
  })

  it('returns true when connected', () => {
    useWebSocketStore.getState().connect('test', '/ws/test')

    const { result, rerender } = renderHook(() => useIsWebSocketConnected('test'))

    expect(result.current).toBe(false)

    act(() => {
      mockWebSocketInstances[0].simulateOpen()
    })

    rerender()
    expect(result.current).toBe(true)
  })
})

// ============================================================================
// Ticket Auth Tests
// ============================================================================

vi.mock('../../../client', () => ({
  authFetchClient: {
    POST: vi.fn(),
  },
}))

describe('WebSocket ticket auth', () => {
  const setAuthState = (authenticated: boolean) => {
    useAuthStore.setState({
      isAuthenticated: authenticated,
      accessToken: authenticated ? 'fake-jwt' : null,
      ensureValidToken: vi.fn().mockResolvedValue(undefined),
    })
  }

  beforeEach(() => {
    mockWebSocketInstances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.useFakeTimers()
    useWebSocketStore.getState().reset()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    setAuthState(false)
  })

  it('fetches a ticket before connecting when authenticated', async () => {
    const { authFetchClient } = await import('../../../client')
    const mockPost = vi.mocked(authFetchClient.POST)
    mockPost.mockResolvedValue({ data: { ticket: 'test-ticket-123', expires_in: 30 }, error: undefined } as never)

    setAuthState(true)

    useWebSocketStore.getState().connect('test', '/ws/test/v1/channel')

    await vi.advanceTimersByTimeAsync(0)

    expect(mockPost).toHaveBeenCalledWith('/auth/ws_ticket')
    expect(mockWebSocketInstances).toHaveLength(1)
    expect(mockWebSocketInstances[0].url).toContain('ticket=test-ticket-123')
  })

  it('appends ticket with & when URL already has query params', async () => {
    const { authFetchClient } = await import('../../../client')
    const mockPost = vi.mocked(authFetchClient.POST)
    mockPost.mockResolvedValue({ data: { ticket: 'abc', expires_in: 30 }, error: undefined } as never)

    setAuthState(true)

    useWebSocketStore.getState().connect('test', '/ws/test/v1/channel?replay=0')

    await vi.advanceTimersByTimeAsync(0)

    expect(mockWebSocketInstances[0].url).toContain('?replay=0&ticket=abc')
  })

  it('connects without ticket when not authenticated', () => {
    setAuthState(false)

    useWebSocketStore.getState().connect('test', '/ws/test/v1/channel')

    expect(mockWebSocketInstances).toHaveLength(1)
    expect(mockWebSocketInstances[0].url).not.toContain('ticket')
  })

  it('connects without ticket when ticket fetch fails', async () => {
    const { authFetchClient } = await import('../../../client')
    const mockPost = vi.mocked(authFetchClient.POST)
    mockPost.mockResolvedValue({ data: undefined, error: { status: 401 } } as never)

    setAuthState(true)

    useWebSocketStore.getState().connect('test', '/ws/test/v1/channel')

    await vi.advanceTimersByTimeAsync(0)

    expect(mockWebSocketInstances).toHaveLength(1)
    expect(mockWebSocketInstances[0].url).not.toContain('ticket')
  })

  it('skips ticket fetch for non-WebSocket paths', () => {
    setAuthState(true)

    useWebSocketStore.getState().connect('test', '/api/v1/something')

    expect(mockWebSocketInstances).toHaveLength(1)
    expect(mockWebSocketInstances[0].url).not.toContain('ticket')
  })

  it('fetches a fresh ticket on reconnection', async () => {
    const { authFetchClient } = await import('../../../client')
    const mockPost = vi.mocked(authFetchClient.POST)
    mockPost
      .mockResolvedValueOnce({ data: { ticket: 'ticket-1', expires_in: 30 }, error: undefined } as never)
      .mockResolvedValueOnce({ data: { ticket: 'ticket-2', expires_in: 30 }, error: undefined } as never)

    setAuthState(true)

    useWebSocketStore.getState().connect('test', '/ws/test/v1/channel')
    await vi.advanceTimersByTimeAsync(0)

    expect(mockWebSocketInstances[0].url).toContain('ticket=ticket-1')

    mockWebSocketInstances[0].simulateOpen()
    mockWebSocketInstances[0].simulateClose(1006)

    // Advance past reconnect delay
    await vi.advanceTimersByTimeAsync(200)

    expect(mockPost).toHaveBeenCalledTimes(2)
    expect(mockWebSocketInstances).toHaveLength(2)
    expect(mockWebSocketInstances[1].url).toContain('ticket=ticket-2')
  })
})
