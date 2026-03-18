"""Greenference API client."""

from __future__ import annotations

import json
import socket
import time
from collections.abc import Iterator
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import quote


class GreenferenceError(Exception):
    """Base exception for Greenference client errors."""

    pass


class GreenferenceHTTPError(GreenferenceError):
    """HTTP error (4xx/5xx)."""

    def __init__(self, message: str, status_code: int | None = None, body: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class GreenferenceConnectionError(GreenferenceError):
    """Connection or network error."""

    pass


class GreenferenceTimeoutError(GreenferenceError):
    """Request timeout."""

    pass


class GreenferenceClient:
    """HTTP client for the Greenference API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"content-type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
            h["X-API-Key"] = self.api_key
        return h

    def _open(self, req: request.Request) -> object:
        last_exc: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return request.urlopen(req, timeout=self.timeout_seconds)
            except (TimeoutError, socket.timeout) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(0.5 * (2**attempt))
                    continue
                raise GreenferenceTimeoutError(str(exc)) from exc
            except HTTPError as exc:
                last_exc = exc
                if 500 <= exc.code < 600 and attempt < self.max_retries:
                    time.sleep(0.5 * (2**attempt))
                    continue
                body = exc.fp.read().decode() if exc.fp else None
                raise GreenferenceHTTPError(
                    f"HTTP {exc.code}: {exc.reason}",
                    status_code=exc.code,
                    body=body,
                ) from exc
            except URLError as exc:
                last_exc = exc
                if isinstance(exc.reason, (TimeoutError, OSError, socket.timeout)):
                    if attempt < self.max_retries:
                        time.sleep(0.5 * (2**attempt))
                        continue
                    raise GreenferenceTimeoutError(str(exc)) from exc
                raise GreenferenceConnectionError(str(exc)) from exc
        if last_exc:
            raise GreenferenceError(str(last_exc)) from last_exc
        raise GreenferenceError("request failed")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
    ) -> dict | list:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = request.Request(
            url=url,
            data=data,
            headers=self._headers(),
            method=method,
        )
        with self._open(req) as response:
            body = response.read().decode()
            return json.loads(body) if body else {}

    def _get(self, path: str) -> dict | list:
        req = request.Request(
            url=f"{self.base_url}{path}",
            headers=self._headers(),
            method="GET",
        )
        with self._open(req) as response:
            return json.loads(response.read().decode())

    def _post(self, path: str, payload: dict) -> dict | list:
        return self._request("POST", path, payload)

    def _patch(self, path: str, payload: dict) -> dict | list:
        return self._request("PATCH", path, payload)

    def _delete(self, path: str) -> dict | list:
        req = request.Request(
            url=f"{self.base_url}{path}",
            headers=self._headers(),
            method="DELETE",
        )
        with self._open(req) as response:
            body = response.read().decode()
            return json.loads(body) if body else {}

    def _post_stream(self, path: str, payload: dict) -> Iterator[str]:
        raw = json.dumps(payload).encode()
        req = request.Request(
            url=f"{self.base_url}{path}",
            data=raw,
            headers=self._headers(),
            method="POST",
        )
        with self._open(req) as response:
            for line in response.read().decode().splitlines():
                if not line.startswith("data: "):
                    continue
                yield line[6:]

    # --- Auth-free ---
    def register(self, payload: dict) -> dict:
        return self._post("/platform/register", payload)  # type: ignore[return-value]

    # --- API Keys ---
    def create_api_key(self, payload: dict) -> dict:
        return self._post("/platform/api-keys", payload)  # type: ignore[return-value]

    def list_api_keys(self) -> list[dict]:
        return self._get("/platform/api-keys")  # type: ignore[return-value]

    def get_api_key(self, key_id: str) -> dict:
        return self._get(f"/platform/api-keys/{key_id}")  # type: ignore[return-value]

    def delete_api_key(self, key_id: str) -> dict:
        return self._delete(f"/platform/api-keys/{key_id}")  # type: ignore[return-value]

    # --- Users ---
    def get_user(self, user_id: str) -> dict:
        return self._get(f"/platform/users/{user_id}")  # type: ignore[return-value]

    def get_user_balance(self, user_id: str) -> dict:
        return self._get(f"/platform/users/{user_id}/balance")  # type: ignore[return-value]

    # --- Images / Builds ---
    def build(self, payload: dict) -> dict:
        return self._post("/platform/images", payload)  # type: ignore[return-value]

    def list_images(self) -> list[dict]:
        return self._get("/platform/images")  # type: ignore[return-value]

    def list_image_history(self, image: str) -> list[dict]:
        return self._get(f"/platform/images/{quote(image, safe='')}/history")  # type: ignore[return-value]

    def list_builds(self) -> list[dict]:
        return self._get("/platform/builds")  # type: ignore[return-value]

    def get_build(self, build_id: str) -> dict:
        return self._get(f"/platform/builds/{build_id}")  # type: ignore[return-value]

    def stream_build_logs(self, build_id: str, *, follow: bool = False) -> Iterator[dict]:
        req = request.Request(
            url=f"{self.base_url}/platform/builds/{build_id}/logs/stream?follow={'true' if follow else 'false'}",
            headers=self._headers(),
            method="GET",
        )
        with self._open(req) as response:
            for line in response.read().decode().splitlines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload:
                    yield json.loads(payload)

    def wait_for_build(
        self,
        build_id: str,
        *,
        timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 1.0,
    ) -> dict:
        started = time.monotonic()
        while True:
            build = self.get_build(build_id)
            status = build.get("status")
            if status in {"published", "failed", "cancelled"}:
                return build
            if time.monotonic() - started > timeout_seconds:
                raise GreenferenceTimeoutError(f"timed out waiting for build {build_id}")
            time.sleep(poll_interval_seconds)

    # --- Workloads ---
    def create_workload(self, payload: dict) -> dict:
        return self._post("/platform/workloads", payload)  # type: ignore[return-value]

    def list_workloads(self) -> list[dict]:
        return self._get("/platform/workloads")  # type: ignore[return-value]

    def get_workload(self, workload_id: str) -> dict:
        return self._get(f"/platform/workloads/{workload_id}")  # type: ignore[return-value]

    def update_workload(self, workload_id: str, payload: dict) -> dict:
        return self._patch(f"/platform/workloads/{workload_id}", payload)  # type: ignore[return-value]

    def delete_workload(self, workload_id: str) -> dict:
        return self._delete(f"/platform/workloads/{workload_id}")  # type: ignore[return-value]

    def get_workload_utilization(self, workload_id: str) -> dict:
        return self._get(f"/platform/workloads/{workload_id}/utilization")  # type: ignore[return-value]

    def workload_warmup(self, workload_id: str) -> Iterator[dict]:
        """Stream warmup events (SSE) for a workload."""
        req = request.Request(
            url=f"{self.base_url}/platform/workloads/{workload_id}/warmup",
            headers=self._headers(),
            method="GET",
        )
        with self._open(req) as response:
            for line in response.read().decode().splitlines():
                if line.startswith("data: "):
                    payload = line[6:].strip()
                    if payload:
                        yield json.loads(payload)

    def guess_vllm_config(self, model: str) -> dict:
        """Analyze HuggingFace model and return GPU requirements (VRAM, GPU count, etc.)."""
        return self._get(f"/guess/vllm_config?model={quote(model, safe='')}")  # type: ignore[return-value]

    # --- Deployments ---
    def deploy(self, payload: dict) -> dict:
        return self._post("/platform/deployments", payload)  # type: ignore[return-value]

    def list_deployments(self) -> list[dict]:
        return self._get("/platform/deployments")  # type: ignore[return-value]

    def get_deployment(self, deployment_id: str) -> dict:
        return self._get(f"/platform/deployments/{deployment_id}")  # type: ignore[return-value]

    def update_deployment(self, deployment_id: str, payload: dict) -> dict:
        return self._patch(f"/platform/deployments/{deployment_id}", payload)  # type: ignore[return-value]

    # --- Secrets ---
    def create_secret(self, payload: dict) -> dict:
        return self._post("/platform/secrets", payload)  # type: ignore[return-value]

    def list_secrets(self) -> list[dict]:
        return self._get("/platform/secrets")  # type: ignore[return-value]

    def delete_secret(self, secret_id: str) -> dict:
        return self._delete(f"/platform/secrets/{secret_id}")  # type: ignore[return-value]

    # --- Inference ---
    def invoke(self, payload: dict) -> dict:
        return self._post("/v1/chat/completions", payload)  # type: ignore[return-value]

    def invoke_stream(self, payload: dict) -> Iterator[str]:
        stream_payload = dict(payload)
        stream_payload["stream"] = True
        return self._post_stream("/v1/chat/completions", stream_payload)

    def completions(self, payload: dict) -> dict:
        return self._post("/v1/completions", payload)  # type: ignore[return-value]

    def embeddings(self, payload: dict) -> dict:
        return self._post("/v1/embeddings", payload)  # type: ignore[return-value]

    # --- Aliases ---
    def workloads(self) -> list[dict]:
        return self.list_workloads()

    def register_miner(self, payload: dict) -> dict:
        return self._post("/agent/v1/register", payload)  # type: ignore[return-value]
