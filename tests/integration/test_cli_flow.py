from __future__ import annotations

import io
import json
import sys
from urllib.error import HTTPError

import pytest

from greenference_sdk import client as client_module
from greenference_sdk.cli import main


class _FakeResponse:
    def __init__(self, payload: dict | list | str, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def read(self) -> bytes:
        if isinstance(self.payload, str):
            return self.payload.encode()
        return json.dumps(self.payload).encode()

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def _fake_urlopen(target):  # type: ignore[no-untyped-def]
    if isinstance(target, str):
        if target.endswith("/platform/workloads"):
            return _FakeResponse([{"workload_id": "wl-1", "name": "demo"}])
        raise HTTPError(target, 404, "not found", hdrs=None, fp=None)

    path = target.full_url
    payload = json.loads(target.data.decode()) if target.data else {}

    if path.endswith("/platform/register"):
        return _FakeResponse(
            {
                "user_id": "user-1",
                "username": payload["username"],
                "email": payload.get("email"),
            }
        )
    if path.endswith("/platform/api-keys"):
        return _FakeResponse(
            {
                "key_id": "key-1",
                "name": payload["name"],
                "user_id": payload.get("user_id"),
                "secret": "gk_demo",
            }
        )
    if path.endswith("/platform/images"):
        return _FakeResponse(
            {
                "build_id": "build-1",
                "image": payload["image"],
                "status": "published",
            }
        )
    if path.endswith("/platform/workloads"):
        return _FakeResponse(
            {
                "workload_id": "wl-1",
                "name": payload["name"],
                "image": payload["image"],
            }
        )
    if path.endswith("/platform/deployments"):
        return _FakeResponse(
            {
                "deployment_id": "dep-1",
                "workload_id": payload["workload_id"],
                "state": "scheduled",
            }
        )
    if path.endswith("/v1/chat/completions"):
        if payload.get("stream"):
            return _FakeResponse('data: {"content":"greenference-response: hi"}\n\ndata: [DONE]\n')
        return _FakeResponse(
            {
                "id": "resp-1",
                "model": payload["model"],
                "content": "greenference-response: hi",
                "deployment_id": "dep-1",
            }
        )

    raise HTTPError(path, 404, "not found", hdrs=None, fp=None)


@pytest.mark.usefixtures("monkeypatch")
def test_cli_happy_path_against_local_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module.request, "urlopen", _fake_urlopen)
    base_url = "http://greenference.test"

    commands = [
        ["greenference", "--base-url", base_url, "register", "--username", "alice", "--email", "alice@example.com"],
        ["greenference", "--base-url", base_url, "keys", "create", "--name", "default", "--user-id", "user-1"],
        ["greenference", "--base-url", base_url, "build", "--image", "greenference/echo:latest", "--context-uri", "s3://builds/echo.zip"],
        ["greenference", "--base-url", base_url, "deploy", "--name", "echo-model", "--image", "greenference/echo:latest"],
        ["greenference", "--base-url", base_url, "invoke", "--model", "wl-1", "--message", "hi"],
        ["greenference", "--base-url", base_url, "invoke", "--model", "wl-1", "--message", "hi", "--stream"],
        ["greenference", "--base-url", base_url, "workloads", "list"],
    ]

    for argv in commands:
        stdout = io.StringIO()
        old_stdout = sys.stdout
        old_argv = sys.argv
        sys.stdout = stdout
        sys.argv = argv
        try:
            main()
        finally:
            sys.stdout = old_stdout
            sys.argv = old_argv
        assert stdout.getvalue().strip()
