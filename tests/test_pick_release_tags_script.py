import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "sandbox" / "pick-release-tags.sh"


def _init_git_repo(repo: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    (repo / "README.md").write_text("test\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)


def test_pick_release_tags_falls_back_when_repo_has_no_tags(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    proc = subprocess.run(
        ["bash", str(SCRIPT), "--repo", str(repo), "--count", "5", "--fallback-ref", "refs/heads/main"],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == ["refs/heads/main"]
    assert "falling back to refs/heads/main" in proc.stderr


def test_pick_release_tags_without_fallback_still_errors_on_empty_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    proc = subprocess.run(
        ["bash", str(SCRIPT), "--repo", str(repo), "--count", "5"],
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    assert "no release tags found" in proc.stderr


def test_pick_release_tags_prefers_real_tags_over_fallback(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    subprocess.run(["git", "tag", "v1.0.0"], cwd=repo, check=True)
    subprocess.run(["git", "tag", "v2.0.0"], cwd=repo, check=True)

    proc = subprocess.run(
        ["bash", str(SCRIPT), "--repo", str(repo), "--count", "2", "--fallback-ref", "refs/heads/main"],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == ["v1.0.0", "v2.0.0"]
