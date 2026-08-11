"""Assembler Service for context package assembly.

This module provides the AssemblerService for assembling RelevantDocuments
into ContextPackage objects with compression retry support.
"""

from syntara.agent_orchestrator.context_manager.assembler_service.service import (
    AssemblerService,
    ContextAssemblyError,
)

__all__ = ["AssemblerService", "ContextAssemblyError"]
