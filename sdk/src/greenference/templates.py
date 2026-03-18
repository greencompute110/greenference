"""Workload template builders."""

from __future__ import annotations

from greenference.image import Image
from greenference.workload import NodeSelector, Workload, WorkloadPack


def build_inference_workload(
    *,
    username: str,
    name: str,
    model_identifier: str,
    runtime_kind: str = "local-cpu-textgen",
    image: Image | str | None = None,
    node_selector: NodeSelector | None = None,
    readme: str = "",
    public: bool = False,
    tags: list[str] | None = None,
    warmup_enabled: bool = False,
    warmup_path: str | None = None,
    scaling_threshold: float = 0.75,
    shutdown_after_seconds: int = 300,
) -> WorkloadPack:
    resolved_image = image or Image(username=username, name=name, tag="latest", readme=readme)
    workload = Workload(
        name=name,
        image=resolved_image,
        readme=readme,
        public=public,
        tags=tags or [],
        node_selector=node_selector or NodeSelector(),
        runtime_kind=runtime_kind,
        model_identifier=model_identifier,
        warmup_enabled=warmup_enabled,
        warmup_path=warmup_path,
        scaling_threshold=scaling_threshold,
        shutdown_after_seconds=shutdown_after_seconds,
    )
    return WorkloadPack(workload=workload, template="inference")


def build_vllm_workload(
    *,
    username: str,
    name: str,
    model_identifier: str,
    image: Image | str | None = None,
    node_selector: NodeSelector | None = None,
    readme: str = "",
    public: bool = False,
) -> WorkloadPack:
    resolved_selector = node_selector or NodeSelector(gpu_count=1, min_vram_gb_per_gpu=24, concurrency=8)
    return build_inference_workload(
        username=username,
        name=name,
        model_identifier=model_identifier,
        runtime_kind="vllm",
        image=image,
        node_selector=resolved_selector,
        readme=readme,
        public=public,
        warmup_enabled=True,
        warmup_path="/healthz",
    )


def build_diffusion_workload(
    *,
    username: str,
    name: str,
    model_identifier: str,
    image: Image | str | None = None,
    node_selector: NodeSelector | None = None,
    readme: str = "",
    public: bool = False,
) -> WorkloadPack:
    resolved_selector = node_selector or NodeSelector(gpu_count=1, min_vram_gb_per_gpu=16, concurrency=1)
    return build_inference_workload(
        username=username,
        name=name,
        model_identifier=model_identifier,
        runtime_kind="diffusion",
        image=image,
        node_selector=resolved_selector,
        readme=readme,
        public=public,
    )
