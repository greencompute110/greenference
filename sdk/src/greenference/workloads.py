"""Compatibility wrappers for Greenference workload templates."""

from __future__ import annotations

from greenference.templates import build_diffusion_workload, build_vllm_workload, build_inference_workload


def create_vllm_workload(*args, **kwargs):
    return build_vllm_workload(*args, **kwargs)


def create_diffusion_workload(*args, **kwargs):
    return build_diffusion_workload(*args, **kwargs)


def create_inference_workload(*args, **kwargs):
    return build_inference_workload(*args, **kwargs)
