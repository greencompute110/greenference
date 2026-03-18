"""Greenference CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from greenference.client import GreenferenceClient
from greenference.config import default_config_path, get_config, save_config
from greenference.loader import load_workload
from greenference.packaging import package_workload

app = typer.Typer(no_args_is_help=True, help="Greenference SDK and CLI")
console = Console()


def _client(
    ctx: typer.Context | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> GreenferenceClient:
    config = get_config()
    obj = ctx.obj if ctx and hasattr(ctx, "obj") and ctx.obj else {}
    return GreenferenceClient(
        base_url=base_url or obj.get("base_url") or config.api_base_url,
        api_key=api_key or obj.get("api_key") or config.api_key,
    )


def _emit(data: Any) -> None:
    console.print_json(json.dumps(data, default=str, indent=2))


def _render_build_log(entry: dict) -> str:
    if "message" in entry and "stage" in entry:
        return f"[{entry['stage']}] {entry['message']}"
    if "status" in entry:
        return f"[build] status={entry['status']}"
    return json.dumps(entry, default=str)


def _load_packaged(module_ref: str):
    loaded = load_workload(module_ref)
    packaged = package_workload(loaded.module_path, loaded.workload)
    return loaded, packaged


def _ensure_built(
    client: GreenferenceClient,
    module_ref: str,
    *,
    public: bool = False,
    wait: bool = False,
) -> dict:
    loaded, packaged = _load_packaged(module_ref)
    image_ref = loaded.workload.image_ref
    history = client.list_image_history(image_ref)
    published = next((item for item in history if item.get("status") == "published"), None)
    if published is not None:
        return published
    build = client.build(
        loaded.workload.to_build_payload(
            context_archive_b64=packaged.archive_b64,
            context_archive_name=packaged.archive_name,
            public=loaded.workload.public or public,
        )
    )
    if wait:
        for entry in client.stream_build_logs(build["build_id"], follow=True):
            console.print(_render_build_log(entry))
    return client.wait_for_build(build["build_id"])


@app.callback()
def main_callback(
    ctx: typer.Context,
    base_url: str | None = typer.Option(None, "--base-url", envvar="GREENFERENCE_API_URL"),
    api_key: str | None = typer.Option(None, "--api-key", envvar="GREENFERENCE_API_KEY"),
) -> None:
    """Greenference CLI - manage workloads, images, deployments, and inference."""
    ctx.obj = {"base_url": base_url, "api_key": api_key}


config_app = typer.Typer(help="Manage local SDK configuration")
app.add_typer(config_app, name="config")


@config_app.command("show", help="Show the resolved SDK configuration")
def config_show() -> None:
    config = get_config()
    _emit(
        {
            "config_path": str(default_config_path()),
            "base_url": config.api_base_url,
            "api_key": config.api_key,
        }
    )


@config_app.command("set", help="Persist SDK configuration to disk")
def config_set(
    base_url: str | None = typer.Option(None, help="Default Greenference API URL"),
    api_key: str | None = typer.Option(None, help="Default API key"),
) -> None:
    saved = save_config(api_base_url=base_url, api_key=api_key)
    _emit(
        {
            "config_path": str(default_config_path()),
            "base_url": saved.api_base_url,
            "api_key": saved.api_key,
        }
    )


# --- Register (no auth) ---
@app.command(help="Create an account")
def register(
    ctx: typer.Context,
    username: str = typer.Option(..., help="Username"),
    email: str | None = typer.Option(None, help="Email"),
) -> None:
    client = _client(ctx)
    _emit(client.register({"username": username, "email": email}))


# --- Workloads ---
workloads_app = typer.Typer(help="Manage workloads")
app.add_typer(workloads_app, name="workloads")


@workloads_app.command("list", help="List workloads")
def workloads_list(ctx: typer.Context) -> None:
    client = _client(ctx)
    items = client.list_workloads()
    if not items:
        console.print("No workloads found.")
        return
    table = Table(title="Workloads")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Image")
    table.add_column("Kind")
    for w in items:
        table.add_row(
            w.get("workload_id", ""),
            w.get("name", ""),
            w.get("image", ""),
            w.get("kind", ""),
        )
    console.print(table)


@workloads_app.command("get", help="Get a workload by ID")
def workloads_get(
    ctx: typer.Context,
    workload_id: str = typer.Argument(..., help="Workload ID"),
) -> None:
    client = _client(ctx)
    _emit(client.get_workload(workload_id))


@workloads_app.command("delete", help="Delete a workload")
def workloads_delete(
    ctx: typer.Context,
    workload_id: str = typer.Argument(..., help="Workload ID"),
) -> None:
    client = _client(ctx)
    _emit(client.delete_workload(workload_id))


@workloads_app.command("create-vllm", help="Create a VLLM workload from HuggingFace model")
def workloads_create_vllm(
    ctx: typer.Context,
    model: str = typer.Option(..., help="HuggingFace model (org/model)"),
    username: str = typer.Option("greenference", help="Image owner/namespace"),
    name: str | None = typer.Option(None, help="Workload name"),
) -> None:
    from greenference.templates import build_vllm_workload

    client = _client(ctx)
    workload = build_vllm_workload(
        username=username,
        name=name or model.rsplit("/", 1)[-1].replace(".", "-"),
        model_identifier=model,
    )
    _emit(client.create_workload(workload.workload.to_workload_payload()))


@workloads_app.command("create-diffusion", help="Create a diffusion workload")
def workloads_create_diffusion(
    ctx: typer.Context,
    model: str = typer.Option(..., help="Model identifier"),
    username: str = typer.Option("greenference", help="Image owner/namespace"),
    name: str = typer.Option(..., help="Workload name"),
) -> None:
    from greenference.templates import build_diffusion_workload

    client = _client(ctx)
    workload = build_diffusion_workload(username=username, name=name, model_identifier=model)
    _emit(client.create_workload(workload.workload.to_workload_payload()))


@workloads_app.command("guess", help="Guess GPU requirements for a HuggingFace model")
def workloads_guess(
    ctx: typer.Context,
    model: str = typer.Argument(..., help="HuggingFace model (org/model)"),
) -> None:
    client = _client(ctx)
    _emit(client.guess_vllm_config(model))


# --- Images ---
images_app = typer.Typer(help="Manage images")
app.add_typer(images_app, name="images")


@images_app.command("list", help="List images")
def images_list(ctx: typer.Context) -> None:
    client = _client(ctx)
    items = client.list_images()
    if not items:
        console.print("No images found.")
        return
    table = Table(title="Images")
    table.add_column("Build ID", style="cyan")
    table.add_column("Image")
    table.add_column("Status")
    for b in items:
        table.add_row(
            b.get("build_id", ""),
            b.get("image", ""),
            b.get("status", ""),
        )
    console.print(table)


@images_app.command("get", help="Get a build by ID")
def images_get(
    ctx: typer.Context,
    build_id: str = typer.Argument(..., help="Build ID"),
) -> None:
    client = _client(ctx)
    _emit(client.get_build(build_id))


# --- API Keys ---
keys_app = typer.Typer(help="Manage API keys")
app.add_typer(keys_app, name="keys")


@keys_app.command("create", help="Create an API key")
def keys_create(
    ctx: typer.Context,
    name: str = typer.Option(..., help="Key name"),
    user_id: str | None = typer.Option(None, help="User ID (admin only)"),
    admin: bool = typer.Option(False, help="Admin key"),
) -> None:
    client = _client(ctx)
    payload = {"name": name, "admin": admin}
    if user_id:
        payload["user_id"] = user_id
    _emit(client.create_api_key(payload))


@keys_app.command("list", help="List API keys")
def keys_list(ctx: typer.Context) -> None:
    client = _client(ctx)
    items = client.list_api_keys()
    if not items:
        console.print("No API keys found.")
        return
    table = Table(title="API Keys")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Admin")
    for k in items:
        table.add_row(
            k.get("key_id", ""),
            k.get("name", ""),
            "yes" if k.get("admin") else "no",
        )
    console.print(table)


@keys_app.command("get", help="Get an API key by ID")
def keys_get(
    ctx: typer.Context,
    key_id: str = typer.Argument(..., help="Key ID"),
) -> None:
    client = _client(ctx)
    _emit(client.get_api_key(key_id))


@keys_app.command("delete", help="Delete an API key")
def keys_delete(
    ctx: typer.Context,
    key_id: str = typer.Argument(..., help="Key ID"),
) -> None:
    client = _client(ctx)
    _emit(client.delete_api_key(key_id))


# --- Secrets ---
secrets_app = typer.Typer(help="Manage secrets")
app.add_typer(secrets_app, name="secrets")


@secrets_app.command("list", help="List secrets")
def secrets_list(ctx: typer.Context) -> None:
    client = _client(ctx)
    _emit(client.list_secrets())


@secrets_app.command("create", help="Create a secret")
def secrets_create(
    ctx: typer.Context,
    purpose: str = typer.Option(..., help="Purpose"),
    key: str = typer.Option(..., help="Key/value"),
) -> None:
    client = _client(ctx)
    _emit(client.create_secret({"purpose": purpose, "key": key}))


@secrets_app.command("delete", help="Delete a secret")
def secrets_delete(
    ctx: typer.Context,
    secret_id: str = typer.Argument(..., help="Secret ID"),
) -> None:
    client = _client(ctx)
    _emit(client.delete_secret(secret_id))


# --- Build ---
@app.command(help="Start an image build")
def build(
    ctx: typer.Context,
    module_ref: str | None = typer.Argument(None, help="Python ref like path/to/file.py:workload"),
    image: str | None = typer.Option(None, help="Image name"),
    context_uri: str | None = typer.Option(None, help="Context URI"),
    dockerfile_path: str = typer.Option("Dockerfile", help="Dockerfile path"),
    public: bool = typer.Option(False, help="Public image"),
    wait: bool = typer.Option(False, help="Wait for build completion"),
) -> None:
    client = _client(ctx)
    if module_ref is not None:
        loaded, packaged = _load_packaged(module_ref)
        result = client.build(
            loaded.workload.to_build_payload(
                context_archive_b64=packaged.archive_b64,
                context_archive_name=packaged.archive_name,
                public=loaded.workload.public or public,
            )
        )
        if wait:
            for entry in client.stream_build_logs(result["build_id"], follow=True):
                console.print(_render_build_log(entry))
            result = client.wait_for_build(result["build_id"])
        _emit(result)
        return
    if image is None or context_uri is None:
        raise typer.BadParameter("build requires <module_ref> or both --image and --context-uri")
    _emit(
        client.build(
            {
                "image": image,
                "context_uri": context_uri,
                "dockerfile_path": dockerfile_path,
                "public": public,
            }
        )
    )


# --- Deploy ---
@app.command(help="Deploy a workload")
def deploy(
    ctx: typer.Context,
    module_ref: str | None = typer.Argument(None, help="Python ref like path/to/file.py:workload"),
    workload_id: str | None = typer.Option(None, help="Workload ID"),
    name: str | None = typer.Option(None, help="Workload name (if creating new)"),
    image: str | None = typer.Option(None, help="Image (if creating new)"),
    gpu_count: int = typer.Option(1, help="GPU count"),
    min_vram_gb: int = typer.Option(16, help="Min VRAM per GPU"),
    requested_instances: int = typer.Option(1, help="Requested instances"),
    accept_fee: bool = typer.Option(False, help="Acknowledge and accept deployment fee"),
    public: bool = typer.Option(False, help="Build image as public if auto-building"),
    wait: bool = typer.Option(False, help="Wait for auto-build completion"),
) -> None:
    client = _client(ctx)
    if module_ref is not None:
        loaded = load_workload(module_ref)
        if not isinstance(loaded.workload.image, str):
            build = _ensure_built(client, module_ref, public=public, wait=wait)
            if build.get("status") != "published":
                console.print(f"image build did not publish successfully: {build.get('status')}")
                raise typer.Exit(code=1)
        workload = client.create_workload(loaded.workload.to_workload_payload())
        _emit(
            client.deploy(
                {
                    "workload_id": workload["workload_id"],
                    "requested_instances": requested_instances,
                    "accept_fee": accept_fee,
                }
            )
        )
        return
    if workload_id is None:
        if not name or not image:
            raise typer.BadParameter("deploy requires --workload-id or both --name and --image")
        workload = client.create_workload(
            {
                "name": name,
                "image": image,
                "requirements": {
                    "gpu_count": gpu_count,
                    "min_vram_gb_per_gpu": min_vram_gb,
                },
            }
        )
        workload_id = workload["workload_id"]
    _emit(
        client.deploy(
            {
                "workload_id": workload_id,
                "requested_instances": requested_instances,
                "accept_fee": accept_fee,
            }
        )
    )


# --- Invoke ---
@app.command(help="Invoke a deployed workload defined by a Python module ref")
def run(
    ctx: typer.Context,
    module_ref: str = typer.Argument(..., help="Python ref like path/to/file.py:workload"),
    message: str = typer.Option(..., help="User message"),
    stream: bool = typer.Option(False, help="Stream response"),
) -> None:
    loaded = load_workload(module_ref)
    payload = {
        "model": loaded.workload.invocation_model,
        "messages": [{"role": "user", "content": message}],
    }
    client = _client(ctx)
    if stream:
        for line in client.invoke_stream(payload):
            print(line)
    else:
        _emit(client.invoke(payload))


@app.command(help="Invoke chat completion")
def invoke(
    ctx: typer.Context,
    model: str = typer.Option(..., help="Model identifier"),
    message: str = typer.Option(..., help="User message"),
    stream: bool = typer.Option(False, help="Stream response"),
) -> None:
    client = _client(ctx)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
    }
    if stream:
        for line in client.invoke_stream(payload):
            print(line)
    else:
        _emit(client.invoke(payload))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
