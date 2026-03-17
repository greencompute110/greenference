from __future__ import annotations

import json
from collections.abc import Iterator
from urllib import request


class GreenferenceClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self.base_url = base_url.rstrip("/")

    def _post(self, path: str, payload: dict) -> dict:
        raw = json.dumps(payload).encode()
        http_request = request.Request(
            url=f"{self.base_url}{path}",
            data=raw,
            headers={"content-type": "application/json"},
            method="POST",
        )
        with request.urlopen(http_request) as response:  # noqa: S310
            return json.loads(response.read().decode())

    def _post_stream(self, path: str, payload: dict) -> Iterator[str]:
        raw = json.dumps(payload).encode()
        http_request = request.Request(
            url=f"{self.base_url}{path}",
            data=raw,
            headers={"content-type": "application/json"},
            method="POST",
        )
        with request.urlopen(http_request) as response:  # noqa: S310
            for line in response.read().decode().splitlines():
                if not line.startswith("data: "):
                    continue
                yield line[6:]

    def _get(self, path: str) -> dict | list:
        with request.urlopen(f"{self.base_url}{path}") as response:  # noqa: S310
            return json.loads(response.read().decode())

    def register(self, payload: dict) -> dict:
        return self._post("/platform/register", payload)

    def register_miner(self, payload: dict) -> dict:
        return self._post("/agent/v1/register", payload)

    def create_api_key(self, payload: dict) -> dict:
        return self._post("/platform/api-keys", payload)

    def build(self, payload: dict) -> dict:
        return self._post("/platform/images", payload)

    def create_workload(self, payload: dict) -> dict:
        return self._post("/platform/workloads", payload)

    def deploy(self, payload: dict) -> dict:
        return self._post("/platform/deployments", payload)

    def invoke(self, payload: dict) -> dict:
        return self._post("/v1/chat/completions", payload)

    def invoke_stream(self, payload: dict) -> Iterator[str]:
        stream_payload = dict(payload)
        stream_payload["stream"] = True
        return self._post_stream("/v1/chat/completions", stream_payload)

    def workloads(self) -> list[dict]:
        return self._get("/platform/workloads")  # type: ignore[return-value]
