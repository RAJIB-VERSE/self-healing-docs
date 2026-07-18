"""Production GitHubBackend using PyGithub + git CLI, and loop-safety checks.

Constructed only inside the Action entrypoint — never at import time
(Rules.md §2). The git CLI handles branch/commit/push (the checkout already has
credentials in CI); PyGithub handles PRs and comments.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from dochealer.config import FIX_BRANCH_PREFIX, Settings

log = logging.getLogger(__name__)


def is_own_pr(head_branch: str, labels: list[str]) -> bool:
    """Loop safety (Rules.md §5): skip PRs dochealer itself created."""
    from dochealer.config import FIX_LABEL

    return head_branch.startswith(FIX_BRANCH_PREFIX) or FIX_LABEL in labels


class LiveGitHub:
    def __init__(self, settings: Settings) -> None:
        from github import Github  # deferred import

        self._settings = settings
        self._repo = Github(settings.github_token).get_repo(settings.github_repo)
        self._root = settings.repo_root

    def _git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self._root, check=True, timeout=120,
                       capture_output=True, text=True)

    def create_fix_branch(self, branch: str) -> None:
        self._git("checkout", "-B", branch)

    def commit_files(self, branch: str, files: dict[str, str], message: str) -> None:
        for rel_path, content in files.items():
            Path(self._root / rel_path).write_text(content, encoding="utf-8")
            self._git("add", rel_path)
        self._git("-c", "user.name=dochealer[bot]",
                  "-c", "user.email=dochealer[bot]@users.noreply.github.com",
                  "commit", "-m", message)
        self._git("push", "--force", "origin", branch)

    def open_pr(self, branch: str, title: str, body: str, label: str) -> str:
        base = self._repo.default_branch
        head = f"{self._repo.owner.login}:{branch}"
        existing = list(self._repo.get_pulls(state="open", head=head))
        if existing:
            pr = existing[0]
            pr.edit(title=title, body=body)
        else:
            pr = self._repo.create_pull(title=title, body=body, head=branch, base=base)
        try:
            pr.add_to_labels(label)
        except Exception as exc:  # noqa: BLE001 — label creation may need extra perms
            log.warning("[report] could not add label %r: %s", label, exc)
        return pr.html_url

    def upsert_comment(self, pr_number: int, marker: str, body: str) -> None:
        issue = self._repo.get_issue(pr_number)
        for comment in issue.get_comments():
            if marker in (comment.body or ""):
                comment.edit(body)
                return
        issue.create_comment(body)
