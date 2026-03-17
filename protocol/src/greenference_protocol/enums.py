from enum import StrEnum


class WorkloadKind(StrEnum):
    INFERENCE = "inference"
    POD = "pod"
    VM = "vm"


class SecurityTier(StrEnum):
    STANDARD = "standard"
    CPU_TEE = "cpu_tee"
    CPU_GPU_ATTESTED = "cpu_gpu_attested"


class DeploymentState(StrEnum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    PULLING = "pulling"
    STARTING = "starting"
    READY = "ready"
    DRAINING = "draining"
    FAILED = "failed"
    TERMINATED = "terminated"

