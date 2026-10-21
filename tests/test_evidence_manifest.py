"""Story 005 regression tests — consumer-visible CLI boundary only.

Every test exercises the shipped CLI (`paper-writing-skill/tools/evidence_manifest.py`)
the way a consumer does: real subprocess, real git repository, real bytes. No
source-text or wiring checks. Run with the project Python:

    python -m pytest tests/test_evidence_manifest.py -q
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL = REPO_ROOT / "paper-writing-skill" / "tools" / "evidence_manifest.py"


def run_cli(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
    )


def write_manifest(directory: Path, body: str) -> Path:
    manifest = directory / "evidence-manifest.yaml"
    manifest.write_text(body, encoding="utf-8")
    return manifest


VALID_BODY = """\
edition: "smoke-edition-1"
artifacts:
  - id: "committed-run"
    sha256: "{git_sha}"
    locator:
      kind: git
      repo: "{repo}"
      commit: "{commit}"
      path: "runs/42/out.dat"
  - id: "snapshot-note"
    sha256: "{snap_sha}"
    locator:
      kind: snapshot
      path: "{snapshot}"
  - id: "retained-pack"
    sha256: "{ret_sha}"
    locator:
      kind: retained
      path: "{retained}"
claims:
  - id: "claim-a"
    statement: "The pinned run shows the reported feature."
    artifacts: ["committed-run"]
    intent: "Carries the paper's main result."
    judgment: support
    reason: "Bytes match the adopted edition."
  - id: "claim-b"
    statement: "A recorded contrary run did not reproduce the feature."
    artifacts: ["retained-pack"]
    intent: "Bounds the claim's scope."
    judgment: refute
    reason: "Refuting evidence is admissible for a statement that reports it."
"""


def make_git_repo(base: Path) -> tuple[Path, str, bytes]:
    """Two commits: out.dat changes between them; later-only file added last."""
    repo = base / "repo"
    (repo / "runs" / "42").mkdir(parents=True)
    run_git(repo.parent, "init", "-q", str(repo))
    historical = b"historical adopted bytes v1\n"
    (repo / "runs" / "42" / "out.dat").write_bytes(historical)
    run_git(repo, "add", "-A")
    run_git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "historical")
    commit = run_git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    (repo / "runs" / "only-later.dat").write_bytes(b"current-only\n")
    (repo / "runs" / "42" / "out.dat").write_bytes(b"current changed bytes v2\n")
    run_git(repo, "add", "-A")
    run_git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "current")
    return repo, commit, historical


def run_git(cwd: Path, *arguments: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *arguments], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert result.returncode == 0, result.stderr
    return result


@pytest.fixture()
def workspace(tmp_path: Path) -> dict:
    repo, commit, historical = make_git_repo(tmp_path)
    snapshot = tmp_path / "snapshots" / "note.dat"
    snapshot.parent.mkdir(exist_ok=True)
    snapshot.write_bytes(b"snapshot bytes\n")
    retained = tmp_path / "retained" / "pack.bin"
    retained.parent.mkdir(exist_ok=True)
    retained.write_bytes(b"retained bytes\n")
    manifest = write_manifest(tmp_path, VALID_BODY.format(
        git_sha=hashlib.sha256(historical).hexdigest(),
        repo=str(repo),
        commit=commit,
        snap_sha=hashlib.sha256(b"snapshot bytes\n").hexdigest(),
        snapshot=str(snapshot),
        ret_sha=hashlib.sha256(b"retained bytes\n").hexdigest(),
        retained=str(retained),
    ))
    return {"manifest": manifest, "repo": repo, "commit": commit, "historical": historical,
            "snapshot": snapshot, "retained": retained}


# -- validate: pass case and echo of retrieval paths ---------------------------

def test_validate_accepts_three_locators_and_echoes_paths(workspace):
    result = run_cli("validate", str(workspace["manifest"]))
    assert result.returncode == 0, result.stderr.decode()
    out = result.stdout.decode()
    assert f"artifact committed-run: git {workspace['repo']}@{workspace['commit']}:runs/42/out.dat" in out
    assert f"artifact snapshot-note: snapshot {workspace['snapshot']}" in out
    assert f"artifact retained-pack: retained {workspace['retained']}" in out
    assert "valid; 3 artifacts, 2 claims" in out


# -- validate: hash-only entry, unknown kind, missing commit, duplicate id, bad ref

def test_hash_only_entry_rejected_as_not_retrievable(tmp_path):
    manifest = write_manifest(tmp_path, """\
edition: "e"
artifacts:
  - id: "x"
    sha256: "%s"
claims:
  - id: "c"
    statement: "s"
    artifacts: ["x"]
    intent: "i"
    judgment: support
    reason: "r"
""" % ("a" * 64))
    result = run_cli("validate", str(manifest))
    assert result.returncode != 0
    err = result.stderr.decode()
    assert "not a retrieval method" in err and "x" in err


def test_unknown_locator_kind_rejected_with_field(tmp_path):
    manifest = write_manifest(tmp_path, """\
edition: "e"
artifacts:
  - id: "x"
    sha256: "%s"
    locator:
      kind: teleport
      path: "p"
claims:
  - id: "c"
    statement: "s"
    artifacts: ["x"]
    intent: "i"
    judgment: support
    reason: "r"
""" % ("a" * 64))
    result = run_cli("validate", str(manifest))
    assert result.returncode == 2
    assert "locator.kind" in result.stderr.decode() and "teleport" in result.stderr.decode()


def test_git_locator_missing_commit_rejected(tmp_path):
    manifest = write_manifest(tmp_path, """\
edition: "e"
artifacts:
  - id: "x"
    sha256: "%s"
    locator:
      kind: git
      repo: "/tmp/repo"
      path: "p"
claims:
  - id: "c"
    statement: "s"
    artifacts: ["x"]
    intent: "i"
    judgment: support
    reason: "r"
""" % ("a" * 64))
    result = run_cli("validate", str(manifest))
    assert result.returncode == 2
    assert "locator.commit" in result.stderr.decode()


def test_git_locator_branch_reference_rejected(tmp_path):
    manifest = write_manifest(tmp_path, """\
edition: "e"
artifacts:
  - id: "x"
    sha256: "%s"
    locator:
      kind: git
      repo: "/tmp/repo"
      commit: "main"
      path: "p"
claims:
  - id: "c"
    statement: "s"
    artifacts: ["x"]
    intent: "i"
    judgment: support
    reason: "r"
""" % ("a" * 64))
    result = run_cli("validate", str(manifest))
    assert result.returncode == 2
    assert "locator.commit" in result.stderr.decode()


def test_duplicate_artifact_id_rejected(tmp_path):
    manifest = write_manifest(tmp_path, """\
edition: "e"
artifacts:
  - id: "x"
    sha256: "%s"
    locator: {kind: retained, path: "p1"}
  - id: "x"
    sha256: "%s"
    locator: {kind: retained, path: "p2"}
claims:
  - id: "c"
    statement: "s"
    artifacts: ["x"]
    intent: "i"
    judgment: support
    reason: "r"
""" % ("a" * 64, "b" * 64))
    result = run_cli("validate", str(manifest))
    assert result.returncode == 2
    assert "duplicate artifact id 'x'" in result.stderr.decode()


def test_claim_unknown_artifact_reference_rejected(tmp_path):
    manifest = write_manifest(tmp_path, """\
edition: "e"
artifacts:
  - id: "x"
    sha256: "%s"
    locator: {kind: retained, path: "p"}
claims:
  - id: "c"
    statement: "s"
    artifacts: ["ghost"]
    intent: "i"
    judgment: support
    reason: "r"
""" % ("a" * 64))
    result = run_cli("validate", str(manifest))
    assert result.returncode == 2
    assert "unknown artifact id 'ghost'" in result.stderr.decode()


def test_refute_and_insufficient_judgments_accepted(tmp_path):
    manifest = write_manifest(tmp_path, """\
edition: "e"
artifacts:
  - id: "x"
    sha256: "%s"
    locator: {kind: retained, path: "p"}
claims:
  - id: "c1"
    statement: "s"
    artifacts: ["x"]
    intent: "i"
    judgment: refute
    reason: "r"
  - id: "c2"
    statement: "s"
    artifacts: ["x"]
    intent: "i"
    judgment: insufficient
    reason: "r"
""" % ("a" * 64))
    result = run_cli("validate", str(manifest))
    assert result.returncode == 0, result.stderr.decode()


def test_invalid_judgment_rejected(tmp_path):
    manifest = write_manifest(tmp_path, """\
edition: "e"
artifacts:
  - id: "x"
    sha256: "%s"
    locator: {kind: retained, path: "p"}
claims:
  - id: "c"
    statement: "s"
    artifacts: ["x"]
    intent: "i"
    judgment: probably
    reason: "r"
""" % ("a" * 64))
    result = run_cli("validate", str(manifest))
    assert result.returncode == 2
    assert "judgment" in result.stderr.decode()


# -- retrieve: real historical git bytes ---------------------------------------

def test_retrieve_git_returns_historical_bytes_not_current(workspace, tmp_path):
    output = tmp_path / "out.dat"
    result = run_cli("retrieve", str(workspace["manifest"]), "committed-run", "--output", str(output))
    assert result.returncode == 0, result.stderr.decode()
    assert output.read_bytes() == workspace["historical"]
    assert output.read_bytes() != (workspace["repo"] / "runs" / "42" / "out.dat").read_bytes()


def test_retrieve_snapshot_and_retained_bytes(workspace, tmp_path):
    out1 = tmp_path / "s.bin"
    out2 = tmp_path / "r.bin"
    assert run_cli("retrieve", str(workspace["manifest"]), "snapshot-note", "--output", str(out1)).returncode == 0
    assert run_cli("retrieve", str(workspace["manifest"]), "retained-pack", "--output", str(out2)).returncode == 0
    assert out1.read_bytes() == workspace["snapshot"].read_bytes()
    assert out2.read_bytes() == workspace["retained"].read_bytes()


def test_retrieve_missing_historical_path_fails_without_current_fallback(workspace, tmp_path):
    """A path added after the pinned commit must fail even though it exists now."""
    body = VALID_BODY.format(
        git_sha=hashlib.sha256(b"current-only\n").hexdigest(),
        repo=str(workspace["repo"]),
        commit=workspace["commit"],
        snap_sha=hashlib.sha256(b"snapshot bytes\n").hexdigest(),
        snapshot=str(workspace["snapshot"]),
        ret_sha=hashlib.sha256(b"retained bytes\n").hexdigest(),
        retained=str(workspace["retained"]),
    )
    body = body.replace("path: \"runs/42/out.dat\"", "path: \"runs/only-later.dat\"")
    manifest = write_manifest(workspace["manifest"].parent, body)
    output = tmp_path / "out.dat"
    result = run_cli("retrieve", str(manifest), "committed-run", "--output", str(output))
    assert result.returncode == 2
    assert "not retrievable at commit" in result.stderr.decode()
    assert not output.exists()


def test_retrieve_unknown_commit_fails_visibly(workspace, tmp_path):
    body = VALID_BODY.format(
        git_sha=hashlib.sha256(workspace["historical"]).hexdigest(),
        repo=str(workspace["repo"]),
        commit="f" * 40,
        snap_sha=hashlib.sha256(b"snapshot bytes\n").hexdigest(),
        snapshot=str(workspace["snapshot"]),
        ret_sha=hashlib.sha256(b"retained bytes\n").hexdigest(),
        retained=str(workspace["retained"]),
    )
    manifest = write_manifest(workspace["manifest"].parent, body)
    result = run_cli("retrieve", str(manifest), "committed-run")
    assert result.returncode == 2
    assert "not found in repo" in result.stderr.decode()


def test_retrieve_hash_mismatch_fails_without_emitting_bytes(workspace, tmp_path):
    body = VALID_BODY.format(
        git_sha="0" * 64,
        repo=str(workspace["repo"]),
        commit=workspace["commit"],
        snap_sha=hashlib.sha256(b"snapshot bytes\n").hexdigest(),
        snapshot=str(workspace["snapshot"]),
        ret_sha=hashlib.sha256(b"retained bytes\n").hexdigest(),
        retained=str(workspace["retained"]),
    )
    manifest = write_manifest(workspace["manifest"].parent, body)
    output = tmp_path / "out.dat"
    result = run_cli("retrieve", str(manifest), "committed-run", "--output", str(output))
    assert result.returncode == 2
    assert "sha256 mismatch" in result.stderr.decode()
    assert not output.exists()


def test_retrieve_unknown_artifact_id_fails(workspace):
    result = run_cli("retrieve", str(workspace["manifest"]), "ghost")
    assert result.returncode == 2
    assert "not in manifest" in result.stderr.decode()


# -- round-1 review regressions (Standards/Spec axes, 2026-10-18) --------------

def test_relative_snapshot_path_resolves_against_manifest_directory(workspace, tmp_path, monkeypatch):
    """Documented relative snapshot paths must resolve from the manifest location, not the caller cwd."""
    import os

    body = VALID_BODY.format(
        git_sha=hashlib.sha256(workspace["historical"]).hexdigest(),
        repo=str(workspace["repo"]),
        commit=workspace["commit"],
        snap_sha=hashlib.sha256(b"snapshot bytes\n").hexdigest(),
        snapshot="snapshots/note.dat",
        ret_sha=hashlib.sha256(b"retained bytes\n").hexdigest(),
        retained=str(workspace["retained"]),
    )
    manifest = write_manifest(workspace["manifest"].parent, body)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    result = subprocess.run(
        [sys.executable, str(TOOL), "retrieve", os.path.relpath(manifest, elsewhere), "snapshot-note",
         "--output", str(tmp_path / "rel-out.bin")],
        cwd=elsewhere, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={**os.environ},
    )
    assert result.returncode == 0, result.stderr.decode()
    assert (tmp_path / "rel-out.bin").read_bytes() == b"snapshot bytes\n"


def test_non_string_claim_artifact_reference_rejected_readably(tmp_path):
    manifest = write_manifest(tmp_path, """\
edition: "e"
artifacts:
  - id: "x"
    sha256: "%s"
    locator: {kind: retained, path: "p"}
claims:
  - id: "c"
    statement: "s"
    artifacts: [{bad: structure}]
    intent: "i"
    judgment: support
    reason: "r"
""" % ("a" * 64))
    result = run_cli("validate", str(manifest))
    assert result.returncode == 2
    err = result.stderr.decode()
    assert err.startswith("evidence-manifest: error: claims[0].artifacts:")
    assert "Traceback" not in err


def test_missing_repository_reported_as_repo_not_commit(tmp_path):
    manifest = write_manifest(tmp_path, """\
edition: "e"
artifacts:
  - id: "x"
    sha256: "%s"
    locator:
      kind: git
      repo: "%s"
      commit: "%s"
      path: "p"
claims:
  - id: "c"
    statement: "s"
    artifacts: ["x"]
    intent: "i"
    judgment: support
    reason: "r"
""" % ("a" * 64, tmp_path / "no-such-repo", "f" * 40))
    result = run_cli("retrieve", str(manifest), "x")
    assert result.returncode == 2
    err = result.stderr.decode()
    assert "not a usable git repository" in err
    assert "not found in repo" not in err
