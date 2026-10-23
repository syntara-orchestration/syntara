# WebMCP workflow builder demo

The demo shows a browser agent working with Syntara's workflow builder. WebMCP tools create a draft graph in the canvas, check it with the builder's validators, save it through the existing save path, and open the existing run confirmation.

## Demo flow

1. Open a new, empty workflow in the builder and select a project.
2. Ask Codex what Syntara workflows can do. It can call `get_syntara_guide` for a concise overview, graph concepts, triggers, step types, configuration, or save/run guidance.
3. Ask it to create a workflow, for example: “Triage a maintenance request with an AI agent, get human approval, then summarize the decision.” It reads only the guide topics it needs.
4. The agent calls `create_workflow_draft` with a workflow name, trigger(s), graph nodes, and edges. It can also use the `steps` shortcut for a simple ordered chain. The graph appears in the normal canvas for review and editing.
5. Call `validate_workflow_draft` and fix any reported issues. Configure project-specific model, integration, credential, and job-template references in the node settings.
6. Call `save_workflow` to persist the workflow to the selected project.
7. Call `request_workflow_run`. Syntara opens the normal confirmation dialog. A person confirms the run and supplies trigger input when the workflow asks for it.

## Registered tools

| Tool                         | Purpose                                                                                                                                                                      |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `get_syntara_guide`          | Return one short application/workflow guide topic at a time to keep agent context focused.                                                                                   |
| `get_workflow_builder_state` | Read the open workflow, trigger and step names/types, graph connections, project selection, dirty state, and permissions. It does not return node parameters or credentials. |
| `create_workflow_draft`      | On a new empty builder, create a graph with any builder trigger or node type, including branches and loop connections.                                                       |
| `validate_workflow_draft`    | Return client-side and backend definition errors, warnings, and run readiness.                                                                                               |
| `save_workflow`              | Save through Syntara's existing project-scoped create/update path.                                                                                                           |
| `request_workflow_run`       | Check run readiness and open the normal run confirmation dialog. It does not start an execution directly.                                                                    |

Graph nodes support `script`, `http_request`, `agentic`, `aap_job_template`, `aap_workflow_job_template`, `approval`, `condition`, `switch`, `loop`, `wait`, and `converge`. Triggers support manual, scheduled, webhook, and EDA. Edges reference node IDs or trigger positions such as `trigger-0`; branch handles use the builder's `true`/`false`, `case_N`/`default`, `approved`/`rejected`, and `loop`/`done` ports. Use target handle `end` for loop feedback. The `steps` shortcut remains limited to ten simple ordered agentic, approval, AAP, and HTTP request steps. Generic placeholders and `internal_activity` are builder/system-managed. Parameters use backend names and credential references; never include secret values.

The guide content is a compact summary drawn from the workflow structure, trigger, approval, agentic, AAP, and frontend save-flow documentation. Each call returns only its requested topic instead of loading a full manual into the agent context.

## Access and confirmation

Tools are registered only while the workflow builder is open and the browser exposes `document.modelContext`. Guide, state, and validation tools are read-only. Edit and run tools are registered only when the current user has the corresponding Syntara permission. Draft creation refuses to overwrite a workflow that already has nodes. A run request always shows the confirmation dialog, including when the user's normal manual-run preference skips that dialog.

The browser integration follows Chrome's [WebMCP imperative API](https://developer.chrome.com/docs/ai/webmcp/imperative-api), including abort-based cleanup when the builder unmounts or permissions change.
