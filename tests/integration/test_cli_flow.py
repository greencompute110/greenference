from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from urllib.error import HTTPError

import pytest

from greenference import client as client_module
from greenference.cli import main


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


def _fake_urlopen(target, timeout=None):  # type: ignore[no-untyped-def]
    if isinstance(target, str):
        if target.endswith("/platform/workloads"):
            return _FakeResponse([{"workload_id": "wl-1", "name": "demo"}])
        raise HTTPError(target, 404, "not found", hdrs=None, fp=None)

    path = target.full_url
    method = target.get_method()
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
    if path.endswith("/platform/images") and method == "GET":
        return _FakeResponse(
            [
                {
                    "build_id": "build-1",
                    "image": "demo/echo:latest",
                    "status": "published",
                }
            ]
        )
    if path.endswith("/platform/images"):
        return _FakeResponse(
            {
                "build_id": "build-1",
                "image": payload["image"],
                "status": "published",
            }
        )
    if "/platform/images/" in path and path.endswith("/history"):
        return _FakeResponse(
            [
                {
                    "build_id": "build-1",
                    "image": "demo/echo:latest",
                    "status": "published",
                }
            ]
        )
    if path.endswith("/platform/workloads") and method == "GET":
        return _FakeResponse([{"workload_id": "wl-1", "name": "demo", "image": "demo/echo:latest"}])
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
def test_cli_happy_path_against_local_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(client_module.request, "urlopen", _fake_urlopen)
    base_url = "http://greenference.test"
    module_root = tmp_path / "sdk"
    module_root.mkdir()
    monkeypatch.chdir(module_root)
    workload_file = module_root / "cli_workload.py"
    data_file = module_root / "cli_data.txt"
    data_file.write_text("hello", encoding="utf-8")
    workload_file.write_text(
        """
from greenference import Image, NodeSelector, Workload

image = (
    Image(username="demo", name="echo", tag="latest")
    .from_base("python:3.12-slim")
    .add("cli_data.txt", "/app/cli_data.txt")
    .run_command("echo build")
)

workload = Workload(
    name="echo-model",
    image=image,
    node_selector=NodeSelector(gpu_count=1),
    model_identifier="demo/echo-model",
)
""",
        encoding="utf-8",
    )
    module_ref = f"{workload_file}:workload"

    monkeypatch.setenv("GREENFERENCE_API_URL", base_url)
    commands = [
        ["greenference", "--base-url", base_url, "register", "--username", "alice", "--email", "alice@example.com"],
        ["greenference", "--base-url", base_url, "keys", "create", "--name", "default", "--user-id", "user-1"],
        ["greenference", "--base-url", base_url, "build", module_ref],
        ["greenference", "--base-url", base_url, "deploy", module_ref, "--accept-fee"],
        ["greenference", "--base-url", base_url, "run", module_ref, "--message", "hi"],
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
            try:
                main()
            except SystemExit as exc:
                assert exc.code == 0
        finally:
            sys.stdout = old_stdout
            sys.argv = old_argv
        assert stdout.getvalue().strip()
