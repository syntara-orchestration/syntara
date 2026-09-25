from execution_plane.models.execution_target import BackendType, ExecutionTarget
from execution_plane.worker_manager.base import WorkerManager
from execution_plane.worker_manager.kubernetes import KubernetesWorkerManager


def create_worker_manager(target: ExecutionTarget) -> WorkerManager:
    """Create the backend implementation configured by an execution target."""
    if target.backend_type == BackendType.VANILLA_K8S:
        return KubernetesWorkerManager(target)
    msg = f"Unsupported execution target backend: {target.backend_type}"
    raise ValueError(msg)


__all__ = ["KubernetesWorkerManager", "WorkerManager", "create_worker_manager"]
