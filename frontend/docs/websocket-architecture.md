# WebSocket Architecture

> **TL;DR:** We use a Zustand store for WebSocket connection management with a simple `useWebSocket()` hook for components. No Context needed - Zustand is global.

---

## Table of Contents

1. [Architecture Decision: Multiple Connections vs Singleton](#architecture-decision-multiple-connections-vs-singleton)
2. [Quick Start](#quick-start)
3. [Architecture](#architecture)
4. [API Reference](#api-reference)
5. [Connection States](#connection-states)
6. [Reconnection](#reconnection)
7. [Configuration](#configuration)
8. [Design Principles](#design-principles)

---

## Architecture Decision: Multiple Connections vs Singleton

### Why Multiple WebSocket Connections?

The frontend uses **one WebSocket connection per channel**, not a singleton WebSocket with multiplexing. This design was chosen to **match the backend architecture**.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                     MULTI-CONNECTION ARCHITECTURE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Frontend (Zustand Store)              Backend (FastAPI)                    │
│   ════════════════════════              ═══════════════════                  │
│                                                                              │
│   ┌──────────────────────┐              ┌──────────────────────┐            │
│   │  Singleton Store     │              │  Singleton Manager   │            │
│   │  (manages all)       │              │  (tracks all)        │            │
│   └──────────┬───────────┘              └──────────┬───────────┘            │
│              │                                     │                         │
│   ┌──────────┴───────────┐              ┌──────────┴───────────┐            │
│   │                      │              │                      │            │
│   ▼          ▼           ▼              ▼          ▼           ▼            │
│ Socket 1   Socket 2   Socket 3       Endpoint   Endpoint   Endpoint         │
│ /coffee    /chat      /tokens        /coffee    /chat      /tokens          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Backend Determines Frontend Pattern

The Nexus backend exposes **separate WebSocket endpoints per channel**:

| Backend Endpoint              | Handler                 | Purpose             |
| ----------------------------- | ----------------------- | ------------------- |
| `/ws/example/v1/coffee`       | `handle_coffee()`       | Coffee words demo   |
| `/ws/example/v1/chat`         | `handle_chat()`         | Bidirectional chat  |
| `/ws/example/v1/agent_events` | `handle_agent_events()` | Event subscriptions |
| `/ws/example/v1/tokens`       | `on_connect_tokens()`   | Token streaming     |

Each endpoint is defined via AsyncAPI specs (`websocket-*.yaml`) with its own message schemas. The frontend **must** create separate connections because:

1. **Different URLs** - Each channel has its own endpoint path
2. **Different protocols** - Each channel has its own request/response schemas
3. **Independent lifecycles** - Channels connect/disconnect independently
4. **Backend design** - The backend validates and routes per-endpoint, not per-message-type

### Alternative: Singleton with Multiplexing

A singleton pattern would require the backend to expose a **single endpoint** that routes messages by type:

```text
❌ NOT our architecture (would require backend changes)

Frontend                              Backend
════════                              ═══════
Single WebSocket ─────────────────►  /ws/v1 (single endpoint)
    │                                    │
    ├─ { channel: "coffee", ... }        ├─► route to coffee handler
    ├─ { channel: "chat", ... }          ├─► route to chat handler
    └─ { channel: "tokens", ... }        └─► route to tokens handler
```

This pattern was **not chosen** because:

- The backend already uses separate endpoints (FastAPI convention)
- Each channel has its own AsyncAPI schema validation
- Separate endpoints provide better isolation and debugging
- No additional complexity for message routing on the backend

### Summary

| Component                | Pattern                    | Reason                                     |
| ------------------------ | -------------------------- | ------------------------------------------ |
| **Frontend Store**       | Singleton Zustand          | Single source of truth for all connections |
| **Frontend Connections** | Multiple (one per channel) | Matches backend's separate endpoints       |
| **Backend Manager**      | Singleton                  | Tracks all connections across all channels |
| **Backend Endpoints**    | Multiple (one per channel) | FastAPI + AsyncAPI design pattern          |

The frontend architecture **mirrors the backend** - a singleton manager coordinating multiple independent connections.

---

## Quick Start

### Connect and Send Messages

```tsx
import { useWebSocket, WebSocketChannel } from '../lib/websocket'

function ChatComponent() {
  const { sendRaw, isConnected, connectionState, connect, disconnect } = useWebSocket(
    WebSocketChannel.Chat // Channel config with id and path
  )

  const handleSend = () => {
    if (isConnected) {
      // sendRaw() sends data as-is (matches backend format)
      sendRaw({ message: 'Hello!' })
    }
  }

  return (
    <div>
      <span>Status: {connectionState}</span>
      <button onClick={handleSend} disabled={!isConnected}>
        Send
      </button>
      <button onClick={isConnected ? disconnect : connect}>{isConnected ? 'Disconnect' : 'Connect'}</button>
    </div>
  )
}
```

### Receive Messages

```tsx
import { useState } from 'react'
import { useWebSocket, WebSocketChannel } from '../lib/websocket'

function NotificationsComponent() {
  const [notifications, setNotifications] = useState([])

  // Connect to channel and receive messages via onMessage callback
  const { isConnected } = useWebSocket(WebSocketChannel.AgentEvents, {
    onMessage: (msg) => {
      // Backend sends raw messages - access directly
      setNotifications((prev) => [...prev, msg])
    },
    messageTypes: ['notification'], // Optional filter
  })

  return <NotificationList items={notifications} />
}
```

### Custom Channels (not predefined)

```tsx
// For channels not in WebSocketChannel, pass a config object
const { sendRaw } = useWebSocket(
  { id: 'custom', path: '/ws/custom/endpoint' },
  { onMessage: (msg) => console.log(msg) }
)
```

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PURE ZUSTAND ARCHITECTURE                            │
└─────────────────────────────────────────────────────────────────────────────┘

   Component A              Component B              Component C
       │                        │                        │
       ▼                        ▼                        ▼
  useWebSocket()           useWebSocket()           useWebSocket()
  channelId: 'chat'        channelId: 'events'      channelId: 'tokens'
       │                        │                        │
       └────────────────────────┼────────────────────────┘
                                │
                                ▼
                   ┌─────────────────────────┐
                   │   useWebSocketStore     │
                   │   (Singleton Zustand)   │
                   │                         │
                   │  channels: Map<         │
                   │    'chat' → Socket 1    │
                   │    'events' → Socket 2  │
                   │    'tokens' → Socket 3  │
                   │  >                      │
                   └───────────┬─────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           ▼                   ▼                   ▼
      WebSocket 1         WebSocket 2         WebSocket 3
      /ws/.../chat        /ws/.../events      /ws/.../tokens
           │                   │                   │
           └───────────────────┼───────────────────┘
                               │
                               ▼
                    Backend Server (port 8000)
                    (separate endpoint per channel)
```

Each `channelId` creates its own WebSocket connection to its corresponding backend endpoint. The Zustand store acts as a **singleton coordinator** managing all connections.

### File Structure

```text
packages/syntara-ui/src/lib/websocket/
├── channels.ts       # Channel definitions (WebSocketChannel)
├── store.ts          # Zustand store with all connection logic
├── hooks.ts          # useWebSocket hook (single hook for all operations)
├── types.ts          # TypeScript type definitions
├── utils.ts          # UI helpers (getConnectionStateLabel, etc.)
├── index.ts          # Public API exports
└── __tests__/
    └── websocket.test.ts  # Unit tests
```

**Total: ~650 lines**

---

## API Reference

### `useWebSocket(channel, options?)`

Main hook for WebSocket connections.

```tsx
import { useWebSocket, WebSocketChannel } from '../lib/websocket'

const {
  sendWrapped, // (message) => boolean - wrapped format { type, payload, timestamp }
  sendRaw, // (data) => boolean - raw format (matches backend)
  connectionState, // 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 'failed'
  isConnected, // boolean
  connect, // () => void
  disconnect, // () => void
  error, // string | undefined
} = useWebSocket(WebSocketChannel.Chat, {
  autoConnect: true, // Default: true
  autoDisconnect: false, // Default: false
  onMessage: (msg) => {}, // Optional inline handler
  messageTypes: [], // Optional filter
  onStateChange: (state) => {}, // Optional
})
```

### `WebSocketChannel`

Predefined channel configurations:

```tsx
import { WebSocketChannel } from '../lib/websocket'

// Demo/example channels
WebSocketChannel.Coffee // { id: 'coffee', path: '/ws/example/v1/coffee' }
WebSocketChannel.Chat // { id: 'chat', path: '/ws/example/v1/chat' }
WebSocketChannel.AgentEvents // { id: 'agent_events', path: '/ws/example/v1/agent_events' }
WebSocketChannel.Tokens // { id: 'tokens', path: '/ws/example/v1/tokens' }

// Production channels
WebSocketChannel.ExecutionBase // { id: 'execution', path: '/ws/workflows/v1/executions' }
```

### Message Formats

```tsx
// sendWrapped() - Wrapped format (for custom protocols)
sendWrapped({ type: 'ChatMessage', payload: { text: 'Hello' } })
// Sends: { type: 'ChatMessage', payload: { text: 'Hello' }, timestamp: 1234567890 }

// sendRaw() - Raw format (matches backend expectations)
sendRaw({ message: 'Hello' })
// Sends: { message: 'Hello' }
```

### Execution Channels

For execution streaming, use the channel builder helper:

```tsx
import { buildExecutionChannelPath } from '../lib/websocket/channels'

// Build execution channel config with optional replay parameter
const channel = buildExecutionChannelPath('exec-123')
// Returns: { id: 'execution_exec-123', path: '/ws/workflows/v1/executions/exec-123' }

const channelWithReplay = buildExecutionChannelPath('exec-123', 'event-456')
// Returns: { id: 'execution_exec-123', path: '/ws/workflows/v1/executions/exec-123?replay=event-456' }

// Use with useWebSocket — pass the returned config directly
const { isConnected } = useWebSocket(buildExecutionChannelPath(executionId, lastEventId), {
  onMessage: handleExecutionMessage,
})
```

> 📚 **See [`docs/execution-visualizer-protocol.md`](./execution-visualizer-protocol.md) for the complete execution WebSocket protocol specification.**

### Internal Hooks (Not Exported from Public API)

These hooks exist in `lib/websocket/hooks.ts` but are **not exported** from the public `lib/websocket/index.ts` API. They are used internally by the WebSocket infrastructure.

#### `useWebSocketState(channelId)`

Returns the connection state as a `ConnectionState` string (not an object).

```tsx
import { useWebSocketState } from '../lib/websocket/hooks'

const connectionState = useWebSocketState('chat')
// Returns: ConnectionState ('connecting' | 'connected' | 'disconnected' | 'reconnecting' | 'failed')
```

#### `useIsWebSocketConnected(channelId)`

Returns only the connection boolean.

```tsx
import { useIsWebSocketConnected } from '../lib/websocket/hooks'

const isConnected = useIsWebSocketConnected('chat')
// Returns: boolean
```

### Utility Functions

Exported from the public API:

```tsx
import { getConnectionStateLabel, getConnectionStateColor } from '../lib/websocket'

// Display helpers
getConnectionStateLabel('connected') // 'Connected'
getConnectionStateColor('connected') // 'green'
```

Additional utilities exist in `lib/websocket/utils.ts` (not exported from the public API):

```tsx
import { isActiveState, isConnectingState, isFailedState } from '../lib/websocket/utils'

isActiveState('connected') // true - checks if state is 'connected'
isConnectingState('connecting') // true - checks if state is 'connecting' or 'reconnecting'
isFailedState('failed') // true - checks if state is 'failed'
```

### Store (Advanced Usage)

For advanced use cases, import the store directly (not part of the public API):

```tsx
import { useWebSocketStore, selectConnectionState, selectIsConnected, selectError } from '../lib/websocket/store'

// Actions
const { connect, disconnect, send, sendRaw, disconnectAll, reset, updateConfig } = useWebSocketStore.getState()

// State with selectors (minimal re-renders)
const connectionState = useWebSocketStore(selectConnectionState('chat'))
const isConnected = useWebSocketStore(selectIsConnected('chat'))
const error = useWebSocketStore(selectError('chat'))

// Disconnect all channels
useWebSocketStore.getState().disconnectAll()

// Reset store to initial state
useWebSocketStore.getState().reset()

// Update configuration
useWebSocketStore.getState().updateConfig({
  reconnection: { maxAttempts: 5 },
})
```

### Public API Summary

The `lib/websocket/index.ts` exports only what most consumers need:

| Export                    | Type       | Description                                                        |
| ------------------------- | ---------- | ------------------------------------------------------------------ |
| `useWebSocket`            | Hook       | Main hook for all WebSocket needs                                  |
| `WebSocketChannel`        | Constant   | Predefined channel configurations                                  |
| `getConnectionStateLabel` | Utility    | Human-readable state labels                                        |
| `getConnectionStateColor` | Utility    | Color for connection state badges                                  |
| Types                     | TypeScript | `ConnectionState`, `WebSocketMessage`, `UseWebSocketOptions`, etc. |

---

## Connection States

| State          | Description                           |
| -------------- | ------------------------------------- |
| `connecting`   | Initial connection attempt            |
| `connected`    | Successfully connected                |
| `disconnected` | Cleanly disconnected                  |
| `reconnecting` | Attempting to reconnect after failure |
| `failed`       | Max reconnection attempts reached     |

---

## Reconnection

Automatic reconnection with exponential backoff:

- **Initial delay:** 100ms
- **Max delay:** 30s
- **Backoff multiplier:** 2x
- **Max attempts:** 10

Custom configuration:

```tsx
import { useWebSocketStore } from '../lib/websocket/store'

useWebSocketStore.getState().updateConfig({
  reconnection: {
    initialDelay: 500,
    maxDelay: 60000,
    maxAttempts: 5,
  },
})
```

---

## Configuration

Default WebSocket base URL is derived from the page's origin (`ws://` or `wss://` + `location.host`). Override via environment variable:

```env
VITE_WS_URL=wss://api.example.com
```

> ⚠️ **Important:** WebSocket connections require the real backend server. The mock API (`npm run start:mock-api`) does not support WebSocket endpoints. Run the full backend to use WebSocket features.

---

## Design Principles

1. **Backend-Driven Architecture:** Multiple WebSocket connections (one per channel) to match backend's separate endpoints
2. **Singleton Store, Multiple Connections:** Zustand store is the single source of truth coordinating all channel connections
3. **No Context Required:** Zustand is global, no provider wrapper needed
4. **Simple API:** One hook (`useWebSocket`) for most use cases
5. **Independent Channel Lifecycles:** Channels connect/disconnect independently without affecting others
6. **Automatic Cleanup:** Hooks handle subscription lifecycle
7. **Type Safe:** Full TypeScript support
8. **Backend Compatible:** `sendRaw()` for direct backend communication matching AsyncAPI schemas

### Why Not a Singleton WebSocket?

We use **multiple connections** rather than a single multiplexed WebSocket because:

- **Backend architecture:** Nexus backend exposes separate endpoints per channel (FastAPI + AsyncAPI pattern)
- **Schema validation:** Each endpoint validates messages against its own AsyncAPI schema
- **Isolation:** Channel failures don't affect other channels
- **Debugging:** Easier to trace issues per-channel in network inspector
- **Flexibility:** Channels can have different reconnection strategies or configurations
