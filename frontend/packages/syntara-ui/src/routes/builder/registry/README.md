# Node Registry System

A plugin-based architecture for registering and managing **workflow step types** (what users add from the **Add step** panel). Code still uses React Flow **nodes** on the canvas; `NodeRegistry` holds metadata, forms, and submit handlers per step type.

## Architecture Overview

```text
registry/
├── NodeRegistry.ts          # Core registry singleton
├── helpers/                 # Node template helpers
│   └── nodeTemplates.ts
├── nodes/                   # Step type registrations (register*.ts)
│   ├── index.ts            # Auto-discovery entry point
│   ├── registerAAPNode.ts
│   ├── registerActionNode.ts
│   ├── registerAIAgentNode.ts
│   ├── registerApprovalNode.ts
│   ├── registerHumanTasksNode.ts
│   ├── registerGenericNode.ts
│   ├── registerLogicNode.ts
│   └── registerTriggerNode.ts
└── README.md               # This file
```

## Key Concepts

### 1. Node Registry

- **Singleton pattern** - Single source of truth for all step types in the Add panel
- **Type-safe** - Full TypeScript support
- **Extensible** - Add new step types without modifying existing code
- **Searchable** - Built-in search by label, keywords, category

### 2. Step type definition

Each registered step type consists of:

- **id**: Unique identifier
- **label**: Display name in UI
- **icon**: Icon component (PatternFly or custom)
- **category**: Optional grouping (trigger, action, logic, etc.)
- **description**: Help text for users
- **keywords**: Search terms
- **formComponent**: React component for configuration
- **onSubmit**: Handler function when form is submitted
- **order**: Display order (lower = earlier)
- **enabled**: Whether the step type is available in the Add step panel

### 3. Subtypes

Step types can optionally define **subtypes** (e.g. Logic → Conditional/Loop/Converge).
Subtype options are rendered by `order` when provided (lower = earlier). If `order` is
not set, declaration order is preserved.

Note: the `order` default of `100` applies to top-level step types only, not subtypes.

## How to Add a New Step Type

### Step 1: Create Your Form Component

```typescript
// routes/builder/node-forms/MyCustomForm.tsx
import type { BaseNodeFormProps } from '../registry/NodeRegistry'

export interface MyCustomFormData {
  name: string
  // ... your fields
}

export function MyCustomForm({
  onSubmit,
  onCancel,
  initialData
}: BaseNodeFormProps<MyCustomFormData>) {
  // Your form implementation
  return <form>...</form>
}
```

### Step 2: Create Registration File

```typescript
// routes/builder/registry/nodes/registerMyNode.ts
import { RhUiMyIcon } from '@patternfly/react-icons'
import { NodeRegistry } from '../NodeRegistry'
import { MyCustomForm } from '../../node-forms/MyCustomForm'
import type { MyCustomFormData } from '../../node-forms/MyCustomForm'

export default function registerMyNode() {
  NodeRegistry.register<MyCustomFormData>({
    id: 'my-node',
    label: 'My Custom Step',
    icon: RhUiMyIcon,
    category: 'action',
    description: 'Does something custom',
    keywords: ['custom', 'special'],
    formComponent: MyCustomForm,
    onSubmit: (data, onSuccess) => {
      // Handle submission
      // Add to workflow store
      onSuccess()
    },
  })
}
```

### Step 3: That's It! (Auto-Discovery)

The registration system uses **auto-discovery** via Vite's `import.meta.glob`. Any file matching `register*.ts` in `routes/builder/registry/nodes/` with a **default export** is automatically discovered and registered at app startup.

**No manual imports needed** — just create the file with the correct naming pattern and export your registration function as `default`.

```typescript
// routes/builder/registry/nodes/index.ts (auto-discovery implementation)
const modules = import.meta.glob('./register*.ts', { eager: true })
for (const path in modules) {
  const module = modules[path] as { default: () => void }
  module.default() // Calls each registration function
}
```

### How It Works at App Startup

```typescript
// In main.tsx - called once before React renders
import { registerAllNodes } from './routes/builder/registry/nodes'

registerAllNodes() // Auto-discovers and registers all step types
```

## Benefits of This Architecture

### ✅ **Open/Closed Principle**

- Open for extension (add new step types)
- Closed for modification (don't change existing code)

### ✅ **Single Responsibility**

- Each registration handles one step type
- Registry handles storage and retrieval
- UI components handle display

### ✅ **Easy Testing**

```typescript
import { NodeRegistry } from './registry/NodeRegistry'

describe('MyNode', () => {
  beforeEach(() => {
    NodeRegistry.clear()
    registerMyNode()
  })

  it('should be registered', () => {
    expect(NodeRegistry.get('my-node')).toBeDefined()
  })
})
```

### ✅ **Plugin System**

- Third-party plugins can register step types
- No code changes to core required
- Dynamic loading possible

### ✅ **Type Safety**

- Full TypeScript support
- Form data types are enforced
- Compile-time errors for mismatches

## API Reference

### NodeRegistry

#### `register<TFormData>(definition: NodeTypeDefinition<TFormData>): void`

Register a new workflow step type.

#### `unregister(id: string): boolean`

Remove a step type from the registry.

#### `get(id: string): NodeTypeDefinition | undefined`

Get a specific step type by ID.

#### `getAll(): NodeTypeDefinition[]`

Get all enabled step types, sorted by order.

#### `getByCategory(category): NodeTypeDefinition[]`

Get all step types in a specific category.

#### `search(query: string): NodeTypeDefinition[]`

Search step types by label, keywords, or ID.

#### `clear(): void`

Remove all registrations (testing only).

## Migration from Old System

### Before (Hard-coded)

```typescript
// AddNodePanel.tsx - tightly coupled
const nodeTypes = [
  { id: 'trigger', label: 'Triggers', icon: TriggerIcon },
  // ... hard-coded list
]

const renderForm = () => {
  switch (selectedNodeType) {
    case 'trigger': return <TriggerNodeForm ... />
    case 'action': return <ActionNodeForm ... />
    // ... switch statement grows with each step type
  }
}
```

### After (Registry-based)

```typescript
// AddNodePanel.tsx - decoupled
const allNodeTypes = NodeRegistry.getAll()

const selectedNode = NodeRegistry.get(selectedNodeType)
const FormComponent = selectedNode.formComponent
return <FormComponent ... />
```

## Examples

See the existing `register*.ts` files in `nodes/` for working examples (e.g., `registerApprovalNode.ts`, `registerActionNode.ts`).

## Future Enhancements

Possible future improvements:

- **Lazy loading**: Load registration modules on demand
- **Conditional rendering**: Show/hide step types based on user permissions
- **Step dependencies**: Require certain step types before others
- **Validation hooks**: Validate step configurations before adding
- **Transformation hooks**: Transform data before submission
