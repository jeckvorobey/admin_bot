#!/usr/bin/env python3
"""Точка входа для локального запуска FastAPI backend."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import uvicorn  # noqa: F401
    from dotenv import load_dotenv
except ImportError:
    print("uvicorn или python-dotenv не установлены")
    print("Установите зависимости: uv sync")
    sys.exit(1)


def _build_uvicorn_command(config: dict[str, Any]) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        config["app"],
        "--host",
        config["host"],
        "--port",
        str(config["port"]),
        "--log-level",
        config["log_level"],
    ]
    if config["reload"]:
        cmd.append("--reload")
    return cmd


def _start_server(cmd: list[str], workdir: Path) -> subprocess.Popen[str]:
    popen_kwargs: dict[str, Any] = {"cwd": str(workdir), "text": True}
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **popen_kwargs)


def _terminate_process_tree(proc: subprocess.Popen[str], timeout: float = 10.0) -> None:
    if proc.poll() is not None:
        return

    if os.name == "nt":
        proc.terminate()
    else:
        try:
            os.killpg(proc.pid, signal.SIGINT)
        except ProcessLookupError:
            return

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> None:
    """Запускает `app.main:app` через uvicorn."""
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(env_path)

    config = {
        "app": "app.main:app",
        "host": os.getenv("APP_HOST", "127.0.0.1"),
        "port": int(os.getenv("APP_PORT", "8000")),
        "reload": "--no-reload" not in sys.argv,
        "log_level": os.getenv("LOG_LEVEL", "info"),
    }

    cmd = _build_uvicorn_command(config)
    workdir = Path(__file__).resolve().parent
    proc = _start_server(cmd, workdir)

    def _handle_signal(_signum: int, _frame: object | None) -> None:
        _terminate_process_tree(proc)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    sys.exit(proc.wait())


if __name__ == "__main__":
    main()
