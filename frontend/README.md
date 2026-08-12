# Syntara UI

## Overview

Syntara UI is a cutting-edge React application designed for building and managing complex automation workflows. It provides a robust, type-safe, and performant solution for creating, visualizing, and managing automated processes.

### Key Features

- 🚀 Modern React 19 with TypeScript
- 🎨 Responsive UI with PatternFly 6
- 🔀 Advanced workflow canvas and step-based automation
- 🔒 Type-safe API integrations
- 🧪 Comprehensive testing infrastructure
- 🚢 Docker/Podman containerization

## Quick Start

### Prerequisites

- Node.js 22+ (recommended)
- npm 10+

### Installation

```bash
# Clone the repository
git clone https://github.com/syntara-orchestration/syntara.git
cd syntara/frontend

# Install dependencies
npm ci

# Set up git hooks (Husky)
npm run prepare
```

### Development Server

```bash
# Start all services (UI + mock API)
npm start
```

### Connecting to Real Backend

To use the real Nexus backend instead of the mock API:

1. The backend is available at `../backend/` in this monorepo
2. Follow the backend README (`../backend/README.md`) to start the API server
3. Export the backend URL and start the UI:

```bash
export VITE_API_URL=http://localhost:8000
npm start
```

### Access Applications

- **UI**: <http://localhost:5173>
- **Mock API**: <http://localhost:3000>

The UI loads with demo workflows from the mock API. No backend setup needed for initial exploration!

### Your First Change (5 minutes)

Get familiar with the hot reload workflow:

1. **Open the UI** in your browser: <http://localhost:5173>
2. **Navigate to** the Workflows page
3. **Open the code** in your editor: `packages/syntara-ui/src/routes/workflows/Workflows.tsx`
4. **Find the `NxPageHeader`** component and change the title text
5. **Watch it reload** automatically in your browser - no refresh needed!
6. **Revert the change** - you're ready to start real development

**What's next?** See [docs/architecture.md](docs/architecture.md) → "Your First Day" section for a guided tour.

### Common Commands

```bash
# Run all static analysis checks (tsc, lint, format, knip) concurrently
npm run check

# Run tests
npm test

# Build for production
npm run build

# Generate API contracts
npm run gen
```

### Troubleshooting

- Ensure you're using Node.js 22+
- Run `npm ci` instead of `npm install`
- Check that all dependencies are installed correctly
- Refer to [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines
- Check out [CLAUDE.md](CLAUDE.md) for comprehensive development information

## Project Documentation

- [Contributing Guidelines](CONTRIBUTING.md)
- [Developer Guide](DEVELOPER_GUIDE.md)
- [Architecture Overview](docs/architecture.md)
- [Data Flow & API Contracts](docs/data-flow.md)
- [Zustand State Management](docs/zustand-architecture.md)
- [WebSocket Architecture](docs/websocket-architecture.md)
- [Workflow Loading & Saving](docs/workflow-loading-saving.md)
- [Execution Visualizer Protocol](docs/execution-visualizer-protocol.md)
- [Error Handling](docs/error-handling.md)
- [Developer Quick Reference](CLAUDE.md)

## Project Structure

The frontend uses npm workspaces to organize its packages:

```text
frontend/
├── packages/
│   ├── syntara-ui/              # Main React 19 application
│   ├── syntara-contracts/       # OpenAPI TypeScript types
│   └── syntara-mock-api/        # MSW-based mock API server
├── docs/                      # Architecture and design documentation
├── tools/                     # Developer utilities (workflow creator, CI scripts)
├── package.json               # Root workspace configuration
├── packages/syntara-ui/Containerfile        # UI container image
└── packages/syntara-mock-api/Containerfile  # Mock API container image
```

## Development

### Tooling

- Node.js 22+ (see package.json for exact requirements)
- npm (comes with Node.js)

### Available Commands

```bash
# Development
npm start                          # Start all services (UI + mock API)
npm run start:ui                   # Start UI only
npm run start:mock-api             # Start mock API server only

# Building
npm run build                      # Build UI package

# Static Analysis (mirrors CI "Checks" job — tsc, lint, format, knip, mermaid)
npm run check                      # Run all checks concurrently

# Testing & Linting
npm test                           # Run all tests (format check + ESLint + TypeScript)
npm run format                     # Format code with Prettier
npm run format:check               # Check code formatting

# Playwright integration tests
npm run e2e                        # Run Playwright tests
npm run e2e:ui                     # Run Playwright UI mode

# E2E environment
# Tests run against the mock backend by default.
# UI runs on port 4173 and mock API on port 3300.
# Override ports with NEXUS_E2E_PORT and NEXUS_E2E_API_PORT.
# Real backend mode: see packages/syntara-ui/TESTING.md for setup.


# API Contracts
npm run gen                        # Regenerate TypeScript types from OpenAPI specs

# Deployment
npm run podman:build               # Build all container images
npm run podman:build:ui            # Build UI image only
npm run podman:build:mock-api      # Build mock API image only
npm run podman:run                 # Run all containers (UI on 4000, API on 3000)
npm run podman:run:ui              # Run UI container only
npm run podman:run:mock-api        # Run mock API container only

# Multi-architecture builds (AMD64 + ARM64)
./build-multiarch.sh               # Build multi-arch images with Podman
./build-multiarch.sh push          # Build and push to registry
```

## Multi-Architecture Container Builds

The project uses **Podman** for local container builds and supports multiple architectures (AMD64 and ARM64).

### Local Development (Podman)

All local container operations use Podman:

```bash
# Multi-architecture builds (AMD64 + ARM64)
./build-multiarch.sh               # Build for both architectures
./build-multiarch.sh push          # Build and push to registry

# Single-architecture builds (faster for development)
podman build -f packages/syntara-ui/Containerfile -t syntara-ui:latest .
podman build -f packages/syntara-mock-api/Containerfile -t syntara-mock-api:latest .

# Run containers
podman run -p 4000:80 syntara-ui:latest
podman run -p 3000:3000 syntara-mock-api:latest
```

### Custom Registry Configuration

```bash
# Build and push to custom registry
REGISTRY=ghcr.io REPOSITORY_OWNER=your-org ./build-multiarch.sh push
```

### CI/CD (Docker Buildx)

GitHub Actions uses Docker Buildx for automated builds. When you push to `main`:

- Builds images for both `linux/amd64` and `linux/arm64`
- Pushes multi-arch manifests to GitHub Container Registry
- Creates a single image that works on both architectures

### Supported Platforms

- **linux/amd64** - Intel/AMD x86_64 processors
- **linux/arm64** - ARM64/AArch64 processors (Apple Silicon, ARM servers, Raspberry Pi 4+)

Multi-arch images automatically select the correct architecture when pulled.

## Code Quality

Code quality and coverage are tracked via SonarCloud. SonarCloud analysis runs automatically on all PRs with coverage reports from unit and integration tests.

## Contributing

We welcome contributions! Please read our [Contributing Guidelines](CONTRIBUTING.md) for details on how to get started, our development process, and how you can contribute.

## Technology Stack

### Syntara UI (Application)

- React 19 with TypeScript
- Vite build tool
- PatternFly 6
- Wouter (routing)
- TanStack Query (data fetching)
- openapi-fetch + openapi-react-query (type-safe API client)
- Fuse.js (fuzzy search)
- ReactFlow/XYFlow (workflow diagrams)
- MSW (API mocking)

### Syntara Contracts (Type Definitions)

- openapi-typescript (type generation)
- Generated from the backend OpenAPI specs at `../backend/src/syntara/schemas/`
- Shared types for UI and mock API

### Syntara Mock API (Development Server)

- MSW (Mock Service Worker)
- @mswjs/http-middleware (Node.js server)
- tsx (TypeScript execution)
- Serves mock responses for API contracts

### Build & Deployment

- npm workspaces
- Vite
- TypeScript 5.9
- ESLint 9 + Prettier
- Vitest + React Testing Library
- Podman/Docker with Nginx
