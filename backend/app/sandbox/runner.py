"""Isolated Sandbox Execution Runner.

Provides OS-level process isolation, dynamic port bindings, stripped environment variables,
and captured I/O streams for empirical incident reproduction.
"""

import asyncio
import os
import secrets
import shutil
import socket
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional
import httpx

SERVICE_APP_MAP = {
    "payment-service": "target_services.payment_service:app",
    "order-service": "target_services.order_service:app",
    "inventory-service": "target_services.inventory_service:app",
    "gateway-service": "target_services.gateway_service:app",
    "auth-service": "target_services.auth_service:app",
    "notification-service": "target_services.notification_service:app",
}


_last_allocated_port = 9100


def find_free_port(start_port: int = 9100) -> int:
    """Finds an available TCP port for ephemeral sandbox binding with dynamic rolling offset."""
    global _last_allocated_port
    port = max(start_port, _last_allocated_port + 1)
    if port > 9900:
        port = start_port

    while port < 9999:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                _last_allocated_port = port
                return port
            except OSError:
                port += 1
    raise RuntimeError("No free port available in sandbox port range.")


@dataclass
class SandboxEnvironment:
    """Represents an active isolated sandbox environment."""
    sandbox_id: str
    service_name: str
    port: int
    work_dir: str
    process: Optional[asyncio.subprocess.Process]
    created_at: float
    base_url: str

    @property
    def is_alive(self) -> bool:
        return self.process is not None and self.process.returncode is None


@dataclass
class SandboxExecutionResult:
    """Outcome of replaying a failure reproduction recipe inside the sandbox."""
    sandbox_id: str
    exit_code: Optional[int]
    stdout: str
    stderr: str
    observed_signature: Optional[str]
    reproduction_verified: bool
    duration_ms: float
    details: Dict[str, Any]


class SandboxRunner(ABC):
    """Abstract interface for execution runners (Process, Docker, MicroVM)."""

    @abstractmethod
    async def create_sandbox(self, service_name: str) -> SandboxEnvironment:
        pass

    @abstractmethod
    async def destroy_sandbox(self, env: SandboxEnvironment) -> bool:
        pass


class ProcessSandboxRunner(SandboxRunner):
    """OS-native process sandbox runner providing lightweight, reproducible isolation."""

    def __init__(self, base_port: int = 9100):
        self.base_port = base_port

    async def create_sandbox(self, service_name: str) -> SandboxEnvironment:
        """Spins up an isolated microservice process in a sandbox directory on a dedicated port."""
        if service_name not in SERVICE_APP_MAP:
            raise ValueError(f"Unknown service '{service_name}' for sandbox execution.")

        sandbox_id = f"sbx_{secrets.token_hex(4)}"
        port = find_free_port(self.base_port)
        work_dir = tempfile.mkdtemp(prefix=f"traceheal_sbx_{sandbox_id}_")

        # Copy minimal environment, strictly stripping sensitive tokens and keys
        env = os.environ.copy()
        sensitive_prefixes = (
            "TRACEHEAL_GITHUB_",
            "TRACEHEAL_GEMINI_",
            "TRACEHEAL_OPENAI_",
            "TRACEHEAL_ANTHROPIC_",
            "TRACEHEAL_JWT_",
            "TRACEHEAL_SLACK_",
            "TRACEHEAL_SUPABASE_",
        )
        sensitive_exact = ("GITHUB_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY")
        for k in list(env.keys()):
            if any(k.startswith(pfx) for pfx in sensitive_prefixes) or k in sensitive_exact:
                env.pop(k, None)

        env["TRACEHEAL_SANDBOX_ID"] = sandbox_id
        env["TRACEHEAL_PORT"] = str(port)
        env["PYTHONUNBUFFERED"] = "1"
        # Ensure project root is in PYTHONPATH so target_services can be imported
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        env["PYTHONPATH"] = project_root

        app_target = SERVICE_APP_MAP[service_name]
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            app_target,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
            env=env,
        )

        base_url = f"http://127.0.0.1:{port}"
        env_obj = SandboxEnvironment(
            sandbox_id=sandbox_id,
            service_name=service_name,
            port=port,
            work_dir=work_dir,
            process=proc,
            created_at=time.time(),
            base_url=base_url,
        )

        # Wait until health check responds
        ready = await self._wait_until_ready(base_url, timeout=10.0)
        if not ready:
            await self.destroy_sandbox(env_obj)
            raise RuntimeError(f"Sandbox '{sandbox_id}' for {service_name} failed to become healthy on port {port}.")

        return env_obj

    async def _wait_until_ready(self, base_url: str, timeout: float = 10.0) -> bool:
        start_time = time.time()
        async with httpx.AsyncClient(timeout=1.0) as client:
            while time.time() - start_time < timeout:
                try:
                    resp = await client.get(f"{base_url}/health")
                    if resp.status_code == 200:
                        await asyncio.sleep(0.15)
                        return True
                except Exception:
                    pass
                await asyncio.sleep(0.2)
        return False

    async def destroy_sandbox(self, env: SandboxEnvironment) -> bool:
        """Terminates the sandbox process and cleans up temporary working directories."""
        if env.process and env.process.returncode is None:
            try:
                env.process.terminate()
                try:
                    await asyncio.wait_for(env.process.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    env.process.kill()
                    await env.process.wait()
            except Exception:
                pass

        if os.path.exists(env.work_dir):
            try:
                shutil.rmtree(env.work_dir, ignore_errors=True)
            except Exception:
                pass

        return True
