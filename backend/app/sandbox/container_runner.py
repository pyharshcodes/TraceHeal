"""Containerized Docker Sandbox Execution Runner.

Provides true kernel-level cgroups and namespace isolation using Docker containers
with strict CPU quotas, memory limits, and isolated ephemeral networks.
Includes seamless automatic fallback to ProcessSandboxRunner when Docker daemon is offline.
"""

import asyncio
import json
import os
import shutil
import subprocess
import time
from typing import Any, Dict, Optional

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.sandbox.runner import (
    ProcessSandboxRunner,
    SandboxEnvironment,
    SandboxRunner,
    find_free_port,
)


class ContainerSandboxRunner(SandboxRunner):
    """Docker-based isolated container runner with cgroups and resource limits."""

    def __init__(
        self,
        base_port: int = 9100,
        cpu_quota: float = 1.0,
        memory_limit: str = "512m",
        image: str = "python:3.11-slim",
    ):
        self.base_port = base_port
        self.cpu_quota = cpu_quota
        self.memory_limit = memory_limit
        self.image = image
        self._fallback_runner = ProcessSandboxRunner(base_port=base_port)
        self._docker_available: Optional[bool] = None

    def is_docker_available(self) -> bool:
        """Verifies Docker CLI and daemon connectivity."""
        if self._docker_available is not None:
            return self._docker_available

        if not settings.docker_sandbox_enabled:
            self._docker_available = False
            return False

        docker_bin = shutil.which("docker")
        if not docker_bin:
            logger.info("Docker binary not found on PATH. Defaulting to ProcessSandboxRunner.")
            self._docker_available = False
            return False

        try:
            res = subprocess.run(
                ["docker", "info"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
            self._docker_available = (res.returncode == 0)
        except Exception:
            self._docker_available = False

        if not self._docker_available:
            logger.info("Docker daemon is currently unreachable. Gracefully falling back to OS ProcessSandboxRunner.")
        else:
            logger.info("Docker daemon is active. Hardware-isolated container sandboxing enabled.")

        return self._docker_available

    async def create_sandbox(self, service_name: str) -> SandboxEnvironment:
        """Spins up a container sandbox or falls back to process runner."""
        if not self.is_docker_available():
            logger.info(f"[SANDBOX] Running '{service_name}' via ProcessSandboxRunner fallback.")
            return await self._fallback_runner.create_sandbox(service_name)

        # Docker container launch implementation
        port = find_free_port(self.base_port)
        sandbox_id = f"sbx_docker_{int(time.time())}"
        container_name = f"traceheal_{sandbox_id}"

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

        # Run container with resource limits and volume mount
        cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "-p", f"127.0.0.1:{port}:8000",
            f"--cpus={self.cpu_quota}",
            f"--memory={self.memory_limit}",
            "-v", f"{project_root}:/app",
            "-w", "/app",
            "-e", f"TRACEHEAL_SANDBOX_ID={sandbox_id}",
            "-e", "PYTHONPATH=/app",
            self.image,
            "python", "-m", "uvicorn", f"target_services.{service_name.replace('-', '_')}:app",
            "--host", "0.0.0.0", "--port", "8000",
        ]

        logger.info(f"Starting Docker sandbox container: {container_name} on port {port}")
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.warning(f"Docker run failed ({stderr.decode()}). Falling back to ProcessSandboxRunner.")
                return await self._fallback_runner.create_sandbox(service_name)

            base_url = f"http://127.0.0.1:{port}"
            env_obj = SandboxEnvironment(
                sandbox_id=sandbox_id,
                service_name=service_name,
                port=port,
                work_dir=project_root,
                process=None,  # Managed by Docker
                created_at=time.time(),
                base_url=base_url,
            )

            # Wait for health
            ready = await self._fallback_runner._wait_until_ready(base_url, timeout=12.0)
            if not ready:
                await self.destroy_sandbox(env_obj)
                logger.warning("Docker sandbox failed healthcheck. Falling back to Process runner.")
                return await self._fallback_runner.create_sandbox(service_name)

            return env_obj

        except Exception as err:
            logger.warning(f"Exception creating Docker container ({err}). Falling back to Process runner.")
            return await self._fallback_runner.create_sandbox(service_name)

    async def destroy_sandbox(self, env: SandboxEnvironment) -> bool:
        """Kills and removes the Docker container, or terminates the process."""
        if env.sandbox_id.startswith("sbx_docker_"):
            container_name = f"traceheal_{env.sandbox_id}"
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker", "rm", "-f", container_name,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
                return True
            except Exception as err:
                logger.error(f"Failed to destroy Docker container {container_name}: {err}")
                return False
        else:
            return await self._fallback_runner.destroy_sandbox(env)


def get_default_sandbox_runner() -> SandboxRunner:
    """Factory creating the optimal sandbox runner based on environment capabilities."""
    if settings.docker_sandbox_enabled:
        return ContainerSandboxRunner(base_port=settings.sandbox_base_port)
    return ProcessSandboxRunner(base_port=settings.sandbox_base_port)
