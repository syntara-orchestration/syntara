"""Context Manager module for Nexus agent orchestration.

Provides scaffolding for context retrieval, compression, and assembly
to support coordinated AI agent workflows.
"""

from .assembler_service import AssemblerService
from .compressor import CompressorService
from .model_profile_service import ModelProfileService, ModelTokenBudget
from .models import ContextPackage
from .planner import ContextManagerPlanner

__all__ = [
    "AssemblerService",
    "CompressorService",
    "ContextManagerPlanner",
    "ContextPackage",
    "ModelProfileService",
    "ModelTokenBudget",
]
