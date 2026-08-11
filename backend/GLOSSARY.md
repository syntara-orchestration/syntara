# Nexus System Glossary - Alphabetical

## A

**Activity** - Individual task within a workflow that can be agentic (AI-driven), non-agentic (traditional), or human-interactive.

**Agent Orchestrator** - Central service that manages Nexus Agents, sub-agents, and automation workflows. Gathers context, guidance, applies policies, and decides actions.

**Agent Registry** - Catalog of available agents with their capabilities, requirements, and metadata for discovery and selection.

**Approval Manager** - Python container that coordinates approval checks for actions including both policy evaluation and human approvals.

**Approval Gate** - Human intervention point requiring user review and authorization before workflow execution proceeds.

**Approval Request** - Human-in-the-loop decision point including requestor, approver, context, deadline, and audit trail.

**Audit Log** - Immutable record of all system activities including timestamps, users, actions, and compliance metadata.

## B

## C

**Cache** - A store of data for improved system performance and response times.

**Chat Service** - Real-time conversational interface enabling human-AI collaboration and workflow intervention.

**Connector** - Synonym for "Integration"

**Context Aggregator** - Service collecting and organizing information from multiple sources for agent consumption.

**Context Loop** - Continuous cycle of context evaluation, refinement, and application within agent execution.

**Context Manager** - Service maintaining working memory, short-term patterns, and long-term historical data for decision making.

**Controlled Intermediary** - Zero-trust gateway managing secure credential access without exposing secrets to agents or LLMs.

**Conversation** - Interaction session between users and agents including message history, context, and outcomes.

**Core Agent** - Central workflow generation engine and top-level agent that interprets natural language requests, generates executable workflows, and coordinates multiple sub-agents to accomplish complex automation tasks through continuous loops.

**Credential Store** - Enterprise software system that manages secrets, credentials, and sensitive data.

## D

**Database** - A store of relational data for the Nexus system.

## E

**Execution** - Runtime instance of a workflow with current state, execution history, logs, and status information.

**Executor** - Determines what system runs the task and how it should be invoked - whether it's an AI agent, an API call, or other.

**External Systems** - Software systems that agents can perform actions against, including cloud infrastructure providers, CRM systems, team communication tools, IT ticketing systems, analytics platforms, content management systems, and infrastructure monitoring tools.

## F

## G

**Guidance Component** - Service providing contextual recommendations for tool selection and workflow generation based on policies and expertise.

**Guidance Repository** - Storage system for structured guidance documents, instructions, and policies with hierarchical precedence.

## H

**Human Interface Layer** - Web portal, APIs, observability dashboard, and real-time chat interface for user interactions.

## I

**Integration** - References to external agentic tool servers (MCP servers) defined in the MCP Server Integration and Tool Management feature, enabling workflow activities to invoke external tools and services.

## J

## L

**Large Language Models (LLMs)** - User-provided language models that use provided guidance and context to create automation plans.

**LLM Configuration** - Settings for language model providers including credentials, selection criteria, limits, and fallback options.

**LLM Usage Metrics** - Consumption data including tokens used, API calls made, execution time, and associated costs.

## M

**MCP Server** - External server implementing Model Context Protocol, providing tools and capabilities to agents.

**Memory Hierarchy** - Multi-tier storage system including working memory, short-term memory and long-term memory.

**Message Queue** - Asynchronous communication buffer for agent-to-agent and system-to-user messaging.

**Message Router** - System routing communications between agents, external systems, and human interfaces.

**Model Registry** - Catalog of available LLM models with provider details, capabilities, performance metrics, and cost information.

## N

**Nexus Automation System Boundary** - Software system boundary defining the scope and limits of the Nexus automation platform.

## O

**Object Store** - Container that stores file object data for the Nexus system.

**Orchestration and Scheduling** - Backend workflow system executing workflows and providing feedback to the Agent Orchestrator.

## P

**Persistent Storage** - Data storage layer including, for example, audit trails and working memory. See "Memory Hierarchy".

**Policy Engine** - External service evaluating tasks against organizational policies before and after execution.

**Policy Evaluation** - Result of policy engine assessment including context, response, violations, and required approvals.

## Q

## R

**REST API** - Container that provides Nexus automation functionality via JSON/HTTPS API, including interfaces for external system configuration management, approval management, and system administration.

## S

**Sandboxed Runtime Environment** - Container that provides a secure environment to run write/destructive actions on external systems.

**Security Event** - Record of authentication attempts, authorization decisions, and security-relevant actions.

**Sub-Agent** - Specialized agent with focused capabilities for specific domains like security, monitoring, or deployment.

## T

**Tool** - External service, application, or capability that can be invoked to perform specific automation tasks.

**Tool Manager** - Component handling tool discovery, selection, and execution coordination for agents.

**Tool Parameter** - Individual input requirement for tools including name, type, description, and validation rules.

**Tool Usage Metrics** - Tracking system maintaining consumption statistics per user, server, and tool with time window calculations.

## U

## V

**Vector Store** - Semantic memory system for context embeddings and similarity-based information retrieval.

## W

**Web Application** - The Syntara UI, including configuration, chat, and workflow management interfaces.

**Workflow** - Executable sequence of tool invocations with defined order, dependencies, approval gates, and error handling.

**Workflow Schedule Coordinator** - Component managing time-based triggers and event-driven workflow initiation.

**Workflow Server** - System executing and managing dynamic workflows comprised of agentic and non-agentic tasks.

**Workflow State Coordinator** - Component managing workflow state persistence and synchronization across system tiers.

**Workflow Workers** - Container that executes automation workflows activities with durability and automatic recovery capabilities.

## X

## Y

## Z

**Zero Trust** - Security architecture ensuring credentials never directly accessible to LLMs or agents, only through controlled intermediaries.
