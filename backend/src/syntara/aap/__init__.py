"""AAP (Ansible Automation Platform) proxy domain.

Provides BFF proxy endpoints for browsing AAP Controller resources
(organizations, job templates, inventories) via the Syntara backend.

Auth is resolved from the AAP Gateway integration (URL/TLS) and an Orchestrator
credential. When ``integration_id`` and ``credential_id`` are omitted, the
unique visible enabled AAP integration and its management credential are used.
With more than one AAP integration, pass ``integration_id`` to select one.
"""
