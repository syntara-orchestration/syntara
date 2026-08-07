/**
 * WebSocket Store
 *
 * Pure Zustand store with all WebSocket connection logic.
 * Single source of truth - no external state to sync.
 */

import { create } from 'zustand'

import { authFetchClient } from '../../client'
import { useAuthStore } from '../../stores/useAuthStore'
import { detachPromise } from '../../utils/detachPromise'

import type { ChannelState, ConnectionState, WebSocketConfig, WebSocketMessage, SubscriberOptions } from './types'
import { DEFAULT_CONFIG } from './types'

// ============================================================================
// Store Types
// ============================================================================

type WebSocketStore = {
  // State
  channels: Map<string, ChannelState>
  config: WebSocketConfig

  // Actions
  connect: (channelId: string, path: string, isFullUrl?: boolean) => void
  disconnect: (channelId: string) => void
  disconnectAll: () => void
  send: <T = unknown>(channelId: string, message: WebSocketMessage<T>) => boolean
  sendRaw: <T = unknown>(channelId: string, data: T) => boolean
  subscribe: <T = unknown>(channelId: string, options: SubscriberOptions<T>) => () => void

  // Getters
  getConnectionState: (channelId: string) => ConnectionState
  isConnected: (channelId: string) => boolean

  // Config
  updateConfig: (config: Partial<WebSocketConfig>) => void

  // Reset
  reset: () => void
}

// ============================================================================
// Subscribers (stored outside Zustand)
// ============================================================================

// Stored outside Zustand to:
// 1. Avoid serialization issues (callback functions can't be serialized)
// 2. Prevent unnecessary re-renders when subscribers change
// 3. Allow direct mutation without triggering store updates
const subscribers = new Map<string, Map<string, SubscriberOptions>>()
let subscriberId = 0

function notifyMessage(channelId: string, message: WebSocketMessage): void {
  subscribers.get(channelId)?.forEach((sub) => {
    if (!sub.onMessage) return
    // Note: messageTypes filtering only works when the message has a 'type' field.
    // Raw backend messages without 'type' will bypass this filter.
    if (sub.messageTypes?.length && !sub.messageTypes.includes(message.type)) return
    try {
      sub.onMessage(message)
    } catch {
      // Ignore subscriber errors
    }
  })
}

function notifyStateChange(channelId: string, state: ConnectionState): void {
  subscribers.get(channelId)?.forEach((sub) => {
    if (sub.onStateChange) {
      try {
        sub.onStateChange(state, channelId)
      } catch {
        // Ignore subscriber errors
      }
    }
  })
}

// ============================================================================
// Helper Functions
// ============================================================================

function buildUrl(baseUrl: string, path: string): string {
  if (path.startsWith('ws://') || path.startsWith('wss://')) {
    return path
  }
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${baseUrl}${normalizedPath}`
}

function appendTicketToUrl(url: string, ticket: string): string {
  const separator = url.includes('?') ? '&' : '?'
  return `${url}${separator}ticket=${encodeURIComponent(ticket)}`
}

async function fetchWebSocketTicket(): Promise<string | null> {
  const store = useAuthStore.getState()
  try {
    await store.ensureValidToken()
  } catch {
    return null
  }

  const { data, error } = await authFetchClient.POST('/auth/ws_ticket')
  if (error || !data) return null
  return data.ticket
}

// ============================================================================
// Store Implementation
// ============================================================================

export const useWebSocketStore = create<WebSocketStore>((set, get) => {
  // Helper to update a channel
  const updateChannel = (channelId: string, updates: Partial<ChannelState>) => {
    set((state) => {
      const channels = new Map(state.channels)
      const existing = channels.get(channelId)
      if (existing) {
        channels.set(channelId, { ...existing, ...updates })
      }
      return { channels }
    })
  }

  // Schedule reconnection with exponential backoff
  const scheduleReconnect = (channelId: string) => {
    const { channels, config } = get()
    const channel = channels.get(channelId)
    if (!channel) return

    const { maxAttempts, initialDelay, maxDelay, backoffMultiplier } = config.reconnection

    if (channel.reconnectAttempts >= maxAttempts) {
      updateChannel(channelId, { state: 'failed', error: 'Max reconnection attempts reached' })
      notifyStateChange(channelId, 'failed')
      return
    }

    const attempts = channel.reconnectAttempts + 1
    updateChannel(channelId, { reconnectAttempts: attempts, state: 'reconnecting' })
    notifyStateChange(channelId, 'reconnecting')

    const delay = Math.min(initialDelay * Math.pow(backoffMultiplier, attempts - 1), maxDelay)

    const timeout = setTimeout(() => {
      const ch = get().channels.get(channelId)
      // Use basePath for reconnection so connect() fetches a fresh single-use ticket
      if (ch) {
        const reconnectPath = ch.basePath ?? ch.url
        get().connect(channelId, reconnectPath, !ch.basePath)
      }
    }, delay)

    updateChannel(channelId, { reconnectTimeout: timeout })
  }

  return {
    channels: new Map(),
    config: { ...DEFAULT_CONFIG },

    connect: (channelId, path, isFullUrl = false) => {
      const { channels, config } = get()
      const existing = channels.get(channelId)

      // Don't reconnect if already connected/connecting
      if (existing && (existing.state === 'connected' || existing.state === 'connecting')) {
        return
      }

      // Skip buildUrl if already a full URL (used during reconnection)
      const url = isFullUrl ? path : buildUrl(config.baseUrl, path)

      // Initialize channel immediately (synchronous)
      const channel: ChannelState = {
        socket: null,
        url,
        basePath: isFullUrl ? existing?.basePath : path,
        state: 'connecting',
        reconnectAttempts: existing?.reconnectAttempts ?? 0,
      }

      set((state) => {
        const channels = new Map(state.channels)
        channels.set(channelId, channel)
        return { channels }
      })

      const createSocket = (socketUrl: string) => {
        try {
          const socket = new WebSocket(socketUrl)

          socket.onopen = () => {
            updateChannel(channelId, { state: 'connected', reconnectAttempts: 0, error: undefined })
            notifyStateChange(channelId, 'connected')
          }

          socket.onclose = (event) => {
            updateChannel(channelId, { socket: null })

            if (event.code === 1000) {
              // Clean disconnect - clear any pending reconnect timeout
              const channel = get().channels.get(channelId)
              if (channel?.reconnectTimeout) {
                clearTimeout(channel.reconnectTimeout)
              }
              updateChannel(channelId, { state: 'disconnected', reconnectTimeout: undefined })
              notifyStateChange(channelId, 'disconnected')
              return
            }

            scheduleReconnect(channelId)
          }

          socket.onerror = () => {
            // onclose will follow
          }

          socket.onmessage = (event) => {
            try {
              if (typeof event.data !== 'string') return
              const raw: unknown = JSON.parse(event.data)
              if (typeof raw !== 'object' || raw === null) return
              const message = raw as WebSocketMessage
              message.timestamp = message.timestamp ?? Date.now()
              message.channel = channelId
              notifyMessage(channelId, message)
            } catch {
              // Ignore parse errors
            }
          }

          updateChannel(channelId, { socket, url: socketUrl })
        } catch (error) {
          updateChannel(channelId, { state: 'failed', error: String(error) })
          notifyStateChange(channelId, 'failed')
        }
      }

      // Fetch a ticket, then open the WebSocket with the ticket appended
      const isAuthenticated = useAuthStore.getState().isAuthenticated
      if (isAuthenticated && url.includes('/ws/')) {
        detachPromise(
          fetchWebSocketTicket().then((ticket) => {
            // Bail out if the channel was disconnected while we were fetching
            const current = get().channels.get(channelId)
            if (current?.state !== 'connecting') return

            if (ticket) {
              createSocket(appendTicketToUrl(url, ticket))
            } else {
              createSocket(url)
            }
          })
        )
      } else {
        createSocket(url)
      }
    },

    disconnect: (channelId) => {
      const channel = get().channels.get(channelId)
      if (!channel) return

      if (channel.reconnectTimeout) {
        clearTimeout(channel.reconnectTimeout)
      }

      if (channel.socket) {
        channel.socket.close(1000, 'Client disconnect')
      }

      updateChannel(channelId, { socket: null, state: 'disconnected', reconnectTimeout: undefined })
      notifyStateChange(channelId, 'disconnected')
    },

    disconnectAll: () => {
      const { channels, disconnect } = get()
      channels.forEach((_, id) => disconnect(id))
      set({ channels: new Map() })
      subscribers.clear()
    },

    send: (channelId, message) => {
      const channel = get().channels.get(channelId)
      if (channel?.state !== 'connected' || !channel.socket) {
        return false
      }

      try {
        channel.socket.send(JSON.stringify({ ...message, timestamp: message.timestamp ?? Date.now() }))
        return true
      } catch {
        return false
      }
    },

    sendRaw: (channelId, data) => {
      const channel = get().channels.get(channelId)
      if (channel?.state !== 'connected' || !channel.socket) {
        return false
      }

      try {
        channel.socket.send(JSON.stringify(data))
        return true
      } catch {
        return false
      }
    },

    subscribe: (channelId, options) => {
      const id = `sub_${++subscriberId}`

      if (!subscribers.has(channelId)) {
        subscribers.set(channelId, new Map())
      }
      subscribers.get(channelId)!.set(id, options as SubscriberOptions)

      return () => {
        subscribers.get(channelId)?.delete(id)
      }
    },

    getConnectionState: (channelId) => {
      return get().channels.get(channelId)?.state ?? 'disconnected'
    },

    isConnected: (channelId) => {
      return get().channels.get(channelId)?.state === 'connected'
    },

    updateConfig: (newConfig) => {
      set((state) => ({
        config: {
          ...state.config,
          ...newConfig,
          reconnection: { ...state.config.reconnection, ...newConfig.reconnection },
        },
      }))
    },

    reset: () => {
      // Clear all reconnection timeouts first to prevent race conditions
      const { channels } = get()
      channels.forEach((channel) => {
        if (channel.reconnectTimeout) {
          clearTimeout(channel.reconnectTimeout)
        }
      })
      get().disconnectAll()
      set({ channels: new Map(), config: { ...DEFAULT_CONFIG } })
    },
  }
})

// ============================================================================
// Selectors
// ============================================================================

export const selectConnectionState = (channelId: string) => (state: WebSocketStore) =>
  state.channels.get(channelId)?.state ?? 'disconnected'

export const selectIsConnected = (channelId: string) => (state: WebSocketStore) =>
  state.channels.get(channelId)?.state === 'connected'

export const selectError = (channelId: string) => (state: WebSocketStore) => state.channels.get(channelId)?.error
