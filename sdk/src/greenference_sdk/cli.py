from __future__ import annotations

import argparse
import json
from typing import Any

from greenference_sdk.client import GreenferenceClient


def _emit(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="greenference")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    subparsers = parser.add_subparsers(dest="command", required=True)

    register = subparsers.add_parser("register")
    register.add_argument("--username", required=True)
    register.add_argument("--email")

    keys = subparsers.add_parser("keys")
    keys_sub = keys.add_subparsers(dest="keys_command", required=True)
    key_create = keys_sub.add_parser("create")
    key_create.add_argument("--name", required=True)
    key_create.add_argument("--user-id")
    key_create.add_argument("--admin", action="store_true")

    build = subparsers.add_parser("build")
    build.add_argument("--image", required=True)
    build.add_argument("--context-uri", required=True)
    build.add_argument("--dockerfile-path", default="Dockerfile")
    build.add_argument("--public", action="store_true")

    deploy = subparsers.add_parser("deploy")
    deploy.add_argument("--workload-id")
    deploy.add_argument("--name")
    deploy.add_argument("--image")
    deploy.add_argument("--gpu-count", type=int, default=1)
    deploy.add_argument("--min-vram-gb", type=int, default=16)
    deploy.add_argument("--requested-instances", type=int, default=1)

    invoke = subparsers.add_parser("invoke")
    invoke.add_argument("--model", required=True)
    invoke.add_argument("--message", required=True)
    invoke.add_argument("--stream", action="store_true")

    workloads = subparsers.add_parser("workloads")
    workloads_sub = workloads.add_subparsers(dest="workloads_command", required=True)
    workloads_sub.add_parser("list")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    client = GreenferenceClient(base_url=args.base_url)

    if args.command == "register":
        _emit(
            client.register(
                {
                    "username": args.username,
                    "email": args.email,
                }
            )
        )
        return

    if args.command == "keys" and args.keys_command == "create":
        _emit(
            client.create_api_key(
                {
                    "name": args.name,
                    "user_id": args.user_id,
                    "admin": args.admin,
                    "scopes": [],
                }
            )
        )
        return

    if args.command == "build":
        _emit(
            client.build(
                {
                    "image": args.image,
                    "context_uri": args.context_uri,
                    "dockerfile_path": args.dockerfile_path,
                    "public": args.public,
                }
            )
        )
        return

    if args.command == "deploy":
        workload_id = args.workload_id
        if workload_id is None:
            if not args.name or not args.image:
                parser.error("deploy requires --workload-id or both --name and --image")
            workload = client.create_workload(
                {
                    "name": args.name,
                    "image": args.image,
                    "requirements": {
                        "gpu_count": args.gpu_count,
                        "min_vram_gb_per_gpu": args.min_vram_gb,
                    },
                }
            )
            workload_id = workload["workload_id"]
        _emit(
            client.deploy(
                {
                    "workload_id": workload_id,
                    "requested_instances": args.requested_instances,
                }
            )
        )
        return

    if args.command == "invoke":
        payload = {
            "model": args.model,
            "messages": [{"role": "user", "content": args.message}],
        }
        if args.stream:
            for line in client.invoke_stream(payload):
                print(line)
        else:
            _emit(client.invoke(payload))
        return

    if args.command == "workloads" and args.workloads_command == "list":
        _emit(client.workloads())
