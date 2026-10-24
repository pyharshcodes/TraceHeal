"""Remote GitHub REST API Integration.

Enables automated creation of branches, committed patch diffs, and Pull Requests
directly against upstream enterprise GitHub repositories.
Gracefully provides structured dry-run simulation when credentials are unconfigured.
"""

import base64
import os
from typing import Any, Dict, Optional
import httpx

from backend.app.core.config import settings
from backend.app.core.logging import logger


class GitHubApiClient:
    """Enterprise GitHub REST v3 API client."""

    def __init__(self, token: Optional[str] = None, repo: Optional[str] = None):
        self.token = token or settings.github_token
        self.repo = repo or settings.github_repo or "org/traceheal-services"
        self.api_base = "https://api.github.com"

    @property
    def is_configured(self) -> bool:
        """Checks if remote credentials are configured."""
        return bool(self.token and len(self.token.strip()) > 8)

    async def create_pull_request(
        self,
        branch_name: str,
        title: str,
        body: str,
        base_branch: str = "main",
        diff_patch: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatches an authenticated remote Pull Request or falls back to simulation."""
        if not self.is_configured:
            logger.info(f"GitHub token unconfigured. Simulating upstream PR for branch '{branch_name}'.")
            simulated_num = abs(hash(branch_name)) % 900 + 100
            return {
                "status": "SIMULATED",
                "pr_number": simulated_num,
                "pr_url": f"https://github.com/{self.repo}/pull/{simulated_num}",
                "branch": branch_name,
                "repo": self.repo,
                "message": "Local dry-run simulated PR (configure TRACEHEAL_GITHUB_TOKEN for live upstream PR).",
            }

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "TraceHeal-Autonomous-SRE",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                # 1. Ensure remote branch exists
                check_branch = await client.get(
                    f"{self.api_base}/repos/{self.repo}/git/ref/heads/{branch_name}",
                    headers=headers,
                )
                if check_branch.status_code == 404:
                    # Get base branch SHA
                    base_ref = await client.get(
                        f"{self.api_base}/repos/{self.repo}/git/ref/heads/{base_branch}",
                        headers=headers,
                    )
                    if base_ref.status_code == 200:
                        base_sha = base_ref.json().get("object", {}).get("sha")
                        if base_sha:
                            await client.post(
                                f"{self.api_base}/repos/{self.repo}/git/refs",
                                headers=headers,
                                json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
                            )
                            logger.info(f"Created remote GitHub branch '{branch_name}' at SHA {base_sha[:8]}")

                # 2. Commit diff patch if provided
                if diff_patch:
                    patch_path = f"patches/{branch_name}.patch"
                    b64_patch = base64.b64encode(diff_patch.encode("utf-8")).decode("utf-8")
                    await client.put(
                        f"{self.api_base}/repos/{self.repo}/contents/{patch_path}",
                        headers=headers,
                        json={
                            "message": f"fix: autonomous remediation patch for {branch_name}",
                            "content": b64_patch,
                            "branch": branch_name,
                        },
                    )

                # 3. Create or find existing PR
                payload = {
                    "title": title,
                    "head": branch_name,
                    "base": base_branch,
                    "body": body,
                    "maintainer_can_modify": True,
                }
                res = await client.post(
                    f"{self.api_base}/repos/{self.repo}/pulls",
                    headers=headers,
                    json=payload,
                )

                if res.status_code in (200, 201):
                    data = res.json()
                    logger.info(f"Successfully created remote GitHub PR #{data.get('number')}: {data.get('html_url')}")
                    return {
                        "status": "CREATED",
                        "pr_number": data.get("number"),
                        "pr_url": data.get("html_url"),
                        "branch": branch_name,
                        "repo": self.repo,
                        "data": data,
                    }
                elif res.status_code == 422 and "A pull request already exists" in res.text:
                    # Fetch existing pull request
                    existing_res = await client.get(
                        f"{self.api_base}/repos/{self.repo}/pulls?head={self.repo.split('/')[0]}:{branch_name}",
                        headers=headers,
                    )
                    if existing_res.status_code == 200 and existing_res.json():
                        existing_pr = existing_res.json()[0]
                        return {
                            "status": "EXISTING",
                            "pr_number": existing_pr.get("number"),
                            "pr_url": existing_pr.get("html_url"),
                            "branch": branch_name,
                            "repo": self.repo,
                            "data": existing_pr,
                        }

                logger.warning(f"GitHub PR creation response {res.status_code}: {res.text}")
                simulated_num = abs(hash(branch_name)) % 900 + 100
                return {
                    "status": "FALLBACK_SIMULATED",
                    "pr_number": simulated_num,
                    "pr_url": f"https://github.com/{self.repo}/pull/{simulated_num}",
                    "branch": branch_name,
                    "repo": self.repo,
                    "error": res.text,
                }

            except Exception as err:
                logger.error(f"Failed to communicate with GitHub API: {err}")
                simulated_num = abs(hash(branch_name)) % 900 + 100
                return {
                    "status": "FALLBACK_SIMULATED",
                    "pr_number": simulated_num,
                    "pr_url": f"https://github.com/{self.repo}/pull/{simulated_num}",
                    "branch": branch_name,
                    "repo": self.repo,
                    "error": str(err),
                }


github_client = GitHubApiClient()
