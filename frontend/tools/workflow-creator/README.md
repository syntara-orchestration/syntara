# Workflow Creator

Create workflows from JSON using the Syntara API.

**Use case**: During PR reviews, test workflow definitions locally without manually creating them in the UI.

## PR Review Workflow

When reviewing a PR that includes a workflow JSON:

1. **Copy the JSON** from the PR

2. **Save it to the workflows directory** (this folder is git-ignored):

   ```bash
   # Create a file in the workflows/ directory
   # Example: tools/workflow-creator/workflows/pr-123.json
   ```

3. **Run the script**:

   ```bash
   npm run create-workflow -- tools/workflow-creator/workflows/pr-123.json
   ```

4. **Open the UI** at `http://localhost:5173` and verify the workflow

> **Note:** The `workflows/` directory is git-ignored, so your review files won't be accidentally committed.

## Quick Start

```bash
# Default example (no args)
npm run create-workflow

# From a file
npm run create-workflow -- tools/workflow-creator/workflows/my-workflow.json

# From stdin (paste JSON, then Ctrl+D)
npm run create-workflow -- -

# Dry run (preview without creating)
npm run create-workflow -- workflow.json --dry-run
```

## Directory Structure

```
workflow-creator/
├── create_workflow.py    # The script
├── examples/             # Example JSON files
├── workflows/            # Drop PR files here (git-ignored)
└── README.md
```

## Options

```bash
python3 create_workflow.py <json_file> [options]

  --name NAME      Override workflow name
  --api-url URL    API URL (default: http://localhost:8000)
  --dry-run        Preview without creating
```

## Supported JSON Formats

### 1. API Response (exported from UI)

```json
{
  "name": "workflow-name",
  "version": {
    "workflow_definition": { ... }
  }
}
```

### 2. Simple Format

```json
{
  "name": "workflow-name",
  "workflow_definition": { ... }
}
```

### 3. Direct Definition

```json
{
  "version": 1,
  "schemaVersion": "1.0.0",
  "metadata": { "name": "workflow-name" },
  "triggers": [...],
  "workflow": { "activities": [...] }
}
```

## Requirements

- Python 3.6+
- No dependencies (uses built-in `urllib`)
- Syntara API running locally
