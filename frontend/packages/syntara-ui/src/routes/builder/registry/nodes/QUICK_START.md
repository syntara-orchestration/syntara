# Quick Start: Adding a New Step Type

This guide shows you how to quickly add a new workflow step type to the builder (user-facing **steps**; React Flow still uses **nodes** under the hood).

## Overview

Adding a new step type involves **just 2 simple steps**:

1. Create a form component
2. Create a registration file with **default export**

That's it! The **auto-discovery system** automatically finds and registers all `register*.ts` files.

## Step 1: Create Your Form Component

Create a form component in `packages/syntara-ui/src/routes/builder/node-forms/`:

```typescript
// MyNewNodeForm.tsx
import { useState } from 'react'
import type { BaseNodeFormProps } from '../registry/NodeRegistry'

export interface MyNewNodeFormData {
  name: string
  language: string
  code: string
  inputs?: string
}

export function MyNewNodeForm({ onSubmit, onCancel }: BaseNodeFormProps<MyNewNodeFormData>) {
  const [name, setName] = useState('')
  const [language, setLanguage] = useState('python')
  const [code, setCode] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit({ name, language, code })
  }

  return (
    <form onSubmit={handleSubmit}>
      {/* Your form fields here */}
      <button type="submit">Add Step</button>
      <button type="button" onClick={onCancel}>Cancel</button>
    </form>
  )
}
```

## Step 2: Create a Registration File

Choose the appropriate template based on your needs:

### Option A: Simple step type (direct registration)

```typescript
// registerMyNewNode.ts
import { RhUiRobotIcon } from '@patternfly/react-icons'
import { NodeRegistry } from '../NodeRegistry'
import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import { createScriptActivity } from '../../../../stores/workflowFactories'
import { MyNewNodeForm } from '../../node-forms/MyNewNodeForm'
import { buildNamedActivity } from '../../utils/nodeCreationHelpers'
import { getDefaultNodeBaseName } from '../../utils/nodeNaming'

// IMPORTANT: Must export as default for auto-discovery
export default function registerMyNewNode() {
  NodeRegistry.register({
    id: 'my-new-node',
    label: 'My New Step',
    icon: RhUiRobotIcon,
    category: 'action',
    description: 'Does something amazing',
    keywords: ['script', 'code', 'python'],
    order: 35,
    formComponent: MyNewNodeForm,
    onSubmit: (data, onSuccess, onError) => {
      try {
        const baseName = getDefaultNodeBaseName('my-new-node')
        const { activityId, activity } = buildNamedActivity(baseName, data.name, (id, name) =>
          createScriptActivity({
            id,
            name,
            language: data.language ?? 'python',
            code: data.code ?? '',
            inputs: data.inputs,
          })
        )
        useWorkflowStore.getState().addActivity(activity)
        onSuccess(activityId)
      } catch (error) {
        onError(error instanceof Error ? error.message : 'Failed to add step')
      }
    },
  })
}
```

### Option B: Custom step type (full implementation)

For step types that need to interact with the workflow store or perform complex logic:

```typescript
// registerMyNewNode.ts
import { RhUiRobotIcon } from '@patternfly/react-icons'
import { createCustomNode } from '../helpers/nodeTemplates'
import { NodeRegistry } from '../NodeRegistry'
import { useWorkflowStore } from '../../../../stores/useWorkflowStore'
import type { MyNewNodeFormData } from '../../node-forms/MyNewNodeForm'
import { MyNewNodeForm } from '../../node-forms/MyNewNodeForm'

// IMPORTANT: Must export as default for auto-discovery
export default function registerMyNewNode() {
  NodeRegistry.register(
    createCustomNode<MyNewNodeFormData>(
      {
        id: 'my-new-node',
        label: 'My New Step',
        icon: RhUiRobotIcon,
        category: 'action', // Type-safe category
        description: 'Does something amazing',
        keywords: ['api', 'http', 'request', 'web'],
        order: 35,
        formComponent: MyNewNodeForm,
      },
      (data, onSuccess, onError) => {
        try {
          // Your custom logic here
          const activity = createMyActivity(data)

          if (activity) {
            useWorkflowStore.getState().addActivity(activity)
            onSuccess()
          } else {
            onError('Invalid configuration. Please check your inputs.')
          }
        } catch (error) {
          onError(error instanceof Error ? error.message : 'Failed to add step')
        }
      }
    )
  )
}
```

**That's it!** Your step type is automatically discovered and registered. No need to manually edit `index.ts`.

## Categories

Choose the appropriate category for your step type:

| Category      | Use Case                      | Examples                               |
| ------------- | ----------------------------- | -------------------------------------- |
| `trigger`     | Starts workflow execution     | Manual trigger, Scheduled, Event-based |
| `action`      | Performs tasks or operations  | API calls, Script execution, Job runs  |
| `logic`       | Controls workflow flow        | Conditionals, Branches, Loops          |
| `integration` | External service integrations | Third-party APIs, Cloud services       |
| `approval`    | Human approval gates          | Manual approval, Review checkpoints    |

## Icons

Use [PatternFly React icons](https://patternfly.org/) for consistency:

```typescript
import {
  RhUiPlay,
  RhUiRobotIcon,
  RhUiElectricityIcon,
  RhUiBranchIcon,
  RhUiUserCheckIcon,
} from '@patternfly/react-icons'
```

Or use custom SVG icons (avoid as much as possible):

```typescript
// @ts-expect-error - SVG import as React component
import MyIcon from '../../../../assets/my-icon.svg?react'
```

## Best Practices

### 1. **Choose a Unique ID**

- Use lowercase with dashes: `my-service-action`
- Make it descriptive and unique
- Avoid generic names like `node1` or `test`

### 2. **Provide Good Keywords**

- Include related terms users might search for
- Think about what the step does and how users describe it
- Examples: `['api', 'http', 'rest', 'web', 'fetch']`

### 3. **Write Clear Descriptions**

- Describe what the step does, not what it is
- Keep it concise (one sentence)
- Good: "Execute HTTP API requests with custom headers"
- Bad: "An HTTP step type"

### 4. **Set Appropriate Order**

- Lower numbers appear first (default: 100)
- Group related step types together
- Common ranges:
  - Triggers: 10-20
  - AI/Agents: 20-30
  - Actions: 30-50
  - Logic: 50-60

### 5. **Error Handling**

- Always use try/catch in custom registrations
- Provide specific error messages
- Call `onError()` with helpful messages for users

## Testing your step type

1. **Start the dev server:**

   ```bash
   npm start
   ```

2. **Open the workflow builder:**
   Navigate to `/workflow-builder/new`

3. **Test the add panel:**
   - Click "Add Step"
   - Search for your step type using keywords
   - Verify it appears in the correct category
   - Click to open the form

4. **Test the form:**
   - Fill out the form fields
   - Submit and verify no errors
   - Check that the step appears on the canvas

## Example: Complete step registration

Here's a complete example for a webhook trigger step type:

```typescript
// registerWebhookNode.ts
import { RhStandardWebhooksIcon } from '@patternfly/react-icons'
import { createCustomNode } from '../helpers/nodeTemplates'
import { NodeRegistry } from '../NodeRegistry'
import { useWorkflowStore, createEventTrigger } from '../../../../stores/useWorkflowStore'
import type { WebhookFormData } from '../../node-forms/WebhookForm'
import { WebhookForm } from '../../node-forms/WebhookForm'

/**
 * Register the Webhook trigger step type
 * IMPORTANT: Must export as default for auto-discovery
 */
export default function registerWebhookNode() {
  NodeRegistry.register(
    createCustomNode<WebhookFormData>(
      {
        id: 'webhook-trigger',
        label: 'Webhook Trigger',
        icon: RhStandardWebhooksIcon,
        category: 'trigger',
        description: 'Trigger workflow from incoming webhook events',
        keywords: ['webhook', 'http', 'callback', 'event', 'api'],
        order: 15,
        formComponent: WebhookForm,
      },
      (data, onSuccess, onError) => {
        try {
          const trigger = createEventTrigger({ id: 'webhook', source: 'webhook', eventType: data.eventType })

          if (trigger) {
            useWorkflowStore.getState().addTrigger(trigger)
            onSuccess()
          } else {
            onError('Invalid webhook configuration')
          }
        } catch (error) {
          onError(error instanceof Error ? error.message : 'Failed to add webhook trigger')
        }
      }
    )
  )
}
```

## Troubleshooting

### Step type doesn't appear in the panel

- Ensure your registration file uses `export default function`
- Verify the file is named `register*.ts` (auto-discovered by glob pattern)
- Verify the category is valid
- Check browser console for errors

### Form doesn't submit

- Ensure `onSubmit` is called with proper data
- Check that all required fields are provided
- Verify `BaseNodeFormProps` interface is implemented correctly

### TypeScript errors

- Ensure form data interface matches what you're passing to `onSubmit`
- Use the generic type parameter: `createCustomNode<YourFormData>(...)`
- Check that the form component implements `BaseNodeFormProps<YourFormData>`

## Next Steps

- Review existing `register*.ts` files in this directory for patterns and examples
- Read the [Node Registry README](../README.md) for the full API reference
- See [docs/architecture.md](../../../../../../../docs/architecture.md) for the broader architectural overview
