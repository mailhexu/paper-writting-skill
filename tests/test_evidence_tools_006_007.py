"""Story 006 (adopt) and Story 007 (check) tests for evidence_manifest.py."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parent.parent / "paper-writing-skill" / "tools" / "evidence_manifest.py"
PYTHON = sys.executable


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([PYTHON, str(TOOLS), *args], capture_output=True, timeout=120, cwd=cwd)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def make_repo(tmp_path: Path) -> tuple[Path, str, bytes]:
    repo = tmp_path / "src-repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    data = b"experiment run 42\nperiodic table of magnons\n"
    (repo / "out.dat").write_bytes(data)
    git(repo, "add", "out.dat")
    git(repo, "commit", "-qm", "run 42")
    return repo, git(repo, "rev-parse", "HEAD"), data


def fragment_document(output: str) -> dict:
    block = output.split("--- fragment (merge into evidence-manifest.yaml artifacts:) ---\n")[1]
    parsed = yaml.safe_load(block)
    return parsed[0] if isinstance(parsed, list) else parsed


def valid_manifest(artifacts: list[dict], claims: list[dict] | None = None) -> str:
    claims = claims or [{
        "id": "claim-1", "statement": "the run supports the claim", "intent": "evidence",
        "artifacts": [artifacts[0]["id"]], "judgment": "support", "reason": "it does",
    }]
    return yaml.safe_dump({"edition": "2026-10-19-d1", "artifacts": artifacts, "claims": claims})


# ---------------------------------------------------------------- Story 006


def test_adopt_committed_matching_file_passes_with_git_locator(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    current = tmp_path / "current.dat"
    current.write_bytes(data)
    result = run("adopt", str(current), "--repo", str(repo), "--commit", commit, "--git-path", "out.dat")
    assert result.returncode == 0, result.stderr
    fragment = fragment_document(result.stdout.decode())
    assert fragment["id"] == f"adopted-{sha(data)[:12]}"
    assert fragment["locator"]["kind"] == "git"
    assert fragment["locator"]["commit"] == commit
    assert fragment["locator"]["path"] == "out.dat"
    assert fragment["sha256"] == sha(data)


def test_adopt_committed_divergent_content_fails_without_snapshot(tmp_path):
    repo, commit, _ = make_repo(tmp_path)
    later = b"experiment run 42 (corrected)\n"
    (repo / "out.dat").write_bytes(later)
    git(repo, "add", "out.dat")
    git(repo, "commit", "-qm", "correction")
    git_repo_head = git(repo, "rev-parse", "HEAD")
    current = tmp_path / "current.dat"
    current.write_bytes(later)
    snapshot_dir = tmp_path / "evidence-snapshots"
    result = run(
        "adopt", str(current), "--repo", str(repo), "--commit", commit,
        "--git-path", "out.dat", "--snapshot-dir", str(snapshot_dir),
    )
    assert result.returncode == 2
    text = result.stderr.decode()
    assert "error" in text
    assert commit in text and git_repo_head in text
    assert not snapshot_dir.exists()


def test_adopt_uncommitted_file_snapshots_current_bytes_and_retrieves_via_manifest(tmp_path):
    repo, commit, _ = make_repo(tmp_path)
    manifest_dir = tmp_path / "paper"
    manifest_dir.mkdir()
    uncommitted = repo / "notes.dat"
    uncommitted.write_bytes(b"uncommitted scratch bytes\n")
    snapshot_dir = manifest_dir / "evidence-snapshots"
    result = run(
        "adopt", str(uncommitted), "--repo", str(repo), "--commit", commit,
        "--git-path", "notes.dat", "--snapshot-dir", "evidence-snapshots",
        "--artifact-id", "uncommitted-note", "--output-manifest-fragment", "fragment.yaml",
        cwd=manifest_dir,
    )
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "COMMIT THIS SNAPSHOT TOGETHER WITH THE RECORD" in text
    snapshot = snapshot_dir / "uncommitted-note.bin"
    assert snapshot.read_bytes() == b"uncommitted scratch bytes\n"
    fragment = yaml.safe_load((manifest_dir / "fragment.yaml").read_text())
    if isinstance(fragment, list):
        fragment = fragment[0]
    assert fragment == {
        "id": "uncommitted-note",
        "sha256": sha(b"uncommitted scratch bytes\n"),
        "locator": {"kind": "snapshot", "path": "evidence-snapshots/uncommitted-note.bin"},
    }
    # snapshot + record committed TOGETHER in one commit, then retrieved through
    # the committed manifest; the manifest is built by pasting the EMITTED
    # fragment file verbatim under `artifacts:`
    joint = tmp_path / "joint-repo"
    joint.mkdir()
    git(joint, "init", "-q")
    git(joint, "config", "user.email", "t@example.com")
    git(joint, "config", "user.name", "t")
    fragment_text = (manifest_dir / "fragment.yaml").read_text()
    assert fragment_text.lstrip().startswith("- "), "fragment must be a paste-ready list item"
    manifest_text = (
        "edition: joint-1\n"
        "artifacts:\n"
        + fragment_text
        + "claims:\n"
        "  - id: claim-1\n"
        "    statement: s\n"
        "    intent: i\n"
        "    reason: r\n"
        "    artifacts: [uncommitted-note]\n"
        "    judgment: support\n"
    )
    parsed = yaml.safe_load(manifest_text)
    (joint / "evidence-manifest.yaml").write_text(manifest_text)
    (joint / "evidence-snapshots").mkdir()
    shutil.copy2(snapshot, joint / "evidence-snapshots" / "uncommitted-note.bin")
    git(joint, "add", "evidence-manifest.yaml", "evidence-snapshots/uncommitted-note.bin")
    git(joint, "commit", "-qm", "record + snapshot together")
    names = git(joint, "show", "HEAD", "--name-only", "--format=")
    assert "evidence-manifest.yaml" in names.splitlines()
    assert "evidence-snapshots/uncommitted-note.bin" in names.splitlines()
    manifest = joint / "evidence-manifest.yaml"
    validated = run("validate", str(manifest))
    assert validated.returncode == 0, validated.stderr
    retrieved = run("retrieve", str(manifest), "uncommitted-note", "--output", str(joint / "back.dat"))
    assert retrieved.returncode == 0, retrieved.stderr
    assert (joint / "back.dat").read_bytes() == b"uncommitted scratch bytes\n"


def test_adopt_unreachable_commit_fails_visibly_without_snapshot(tmp_path):
    repo, _, data = make_repo(tmp_path)
    current = tmp_path / "current.dat"
    current.write_bytes(data)
    garbage = "0" * 40
    result = run(
        "adopt", str(current), "--repo", str(repo), "--commit", garbage,
        "--git-path", "out.dat", "--snapshot-dir", str(tmp_path / "snapshots"),
    )
    assert result.returncode == 2
    assert "error" in result.stderr.decode()
    assert "commit" in result.stderr.decode()
    assert not (tmp_path / "snapshots").exists()


def test_adopt_untracked_new_file_snapshots(tmp_path):
    # path absent at the recorded commit AND at HEAD -> true uncommitted content
    repo, commit, _ = make_repo(tmp_path)
    untracked = repo / "new.dat"
    untracked.write_bytes(b"brand new untracked bytes\n")
    snapshot_dir = tmp_path / "evidence-snapshots"
    result = run(
        "adopt", str(untracked), "--repo", str(repo), "--commit", commit,
        "--git-path", "new.dat", "--snapshot-dir", str(snapshot_dir),
        "--artifact-id", "new-note",
    )
    assert result.returncode == 0, result.stderr
    fragment = fragment_document(result.stdout.decode())
    assert fragment["locator"]["kind"] == "snapshot"
    assert (snapshot_dir / "new-note.bin").read_bytes() == b"brand new untracked bytes\n"


def test_adopt_uncommitted_modification_of_committed_file_snapshots(tmp_path):
    # HEAD blob differs from BOTH the recorded commit and the current file
    repo, commit, _ = make_repo(tmp_path)
    v2 = b"committed v2\n"
    (repo / "out.dat").write_bytes(v2)
    git(repo, "add", "out.dat")
    git(repo, "commit", "-qm", "v2 committed")
    head = git(repo, "rev-parse", "HEAD")
    v3 = b"working tree v3\n"
    (repo / "out.dat").write_bytes(v3)
    snapshot_dir = tmp_path / "evidence-snapshots"
    result = run(
        "adopt", str(repo / "out.dat"), "--repo", str(repo), "--commit", commit,
        "--git-path", "out.dat", "--snapshot-dir", str(snapshot_dir),
        "--artifact-id", "v3",
    )
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert head in text
    fragment = fragment_document(text)
    assert fragment["locator"]["kind"] == "snapshot"
    assert fragment["sha256"] == sha(v3)
    assert (snapshot_dir / "v3.bin").read_bytes() == v3


@pytest.mark.parametrize("tricky", ['dir"quote/name.dat', r"dir\backslash/name.dat"])
def test_adopt_tricky_git_path_yields_valid_round_tripping_fragment(tmp_path, tricky):
    repo, commit, _ = make_repo(tmp_path)
    data = b"tricky path bytes\n"
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    # create the file at the tricky path inside the repo
    target = repo / tricky
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "tricky path")
    commit = git(repo, "rev-parse", "HEAD")
    current = tmp_path / "current.dat"
    current.write_bytes(data)
    result = run(
        "adopt", str(current), "--repo", str(repo), "--commit", commit,
        "--git-path", tricky, "--artifact-id", "tricky-path",
    )
    assert result.returncode == 0, result.stderr
    fragment = fragment_document(result.stdout.decode())
    assert fragment["locator"]["path"] == tricky
    assert fragment["sha256"] == sha(data)
    assert fragment["locator"]["commit"] == commit


def test_adopt_matching_content_creates_no_snapshot_dir(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    current = tmp_path / "current.dat"
    current.write_bytes(data)
    snapshot_dir = tmp_path / "never-created"
    result = run(
        "adopt", str(current), "--repo", str(repo), "--commit", commit,
        "--git-path", "out.dat", "--snapshot-dir", str(snapshot_dir),
    )
    assert result.returncode == 0, result.stderr
    assert not snapshot_dir.exists()


def test_adopt_missing_current_file_refuses(tmp_path):
    repo, commit, _ = make_repo(tmp_path)
    result = run("adopt", str(tmp_path / "nope.dat"), "--repo", str(repo), "--commit", commit, "--git-path", "out.dat")
    assert result.returncode == 2
    assert "current-file" in result.stderr.decode()


# ---------------------------------------------------------------- Story 007


def write_manifest(tmp_path: Path, artifacts: list[dict], claims: list[dict] | None = None) -> Path:
    path = tmp_path / "evidence-manifest.yaml"
    path.write_text(valid_manifest(artifacts, claims))
    return path


def artifact_git(commit: str, path: str, digest: str, repo: str, **extra) -> dict:
    base = {
        "id": "a1", "sha256": digest,
        "locator": {"kind": "git", "repo": repo, "commit": commit, "path": path},
    }
    base.update(extra)
    return base


def test_check_unchanged_reports_no_changes(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    result = run("check", str(manifest), "--no-records-dir")
    assert result.returncode == 0, result.stderr
    assert "no changes" in result.stdout.decode()


def test_check_modified_in_place_snapshot(tmp_path):
    manifest_dir = tmp_path / "paper"
    manifest_dir.mkdir()
    data = b"snapshot bytes v1\n"
    snapshot = manifest_dir / "evidence-snapshots" / "a.bin"
    snapshot.parent.mkdir()
    snapshot.write_bytes(data)
    manifest = manifest_dir / "evidence-manifest.yaml"
    manifest.write_text(valid_manifest([{
        "id": "a1", "sha256": sha(data), "locator": {"kind": "snapshot", "path": "evidence-snapshots/a.bin"},
    }]))
    snapshot.write_bytes(b"snapshot bytes v2\n")  # modified in place
    result = run("check", str(manifest), "--no-records-dir")
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "content-changed" in text
    assert "CURRENT ADOPTED" in text and "PENDING CHANGE" in text
    assert sha(b"snapshot bytes v2\n") in text


def test_check_path_moved_detected_via_ls_tree(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    (repo / "runs" / "42").mkdir(parents=True)
    git(repo, "mv", "out.dat", "runs/42/out.dat")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "move run output")
    moved_commit = git(repo, "rev-parse", "HEAD")
    # stale locator: pinned to the post-move commit but with the pre-move path
    manifest = write_manifest(tmp_path, [artifact_git(moved_commit, "out.dat", sha(data), str(repo))])
    result = run("check", str(manifest), "--no-records-dir")
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "path-moved" in text
    assert "runs/42/out.dat" in text and "out.dat" in text


def test_check_source_lost_for_garbage_commit(tmp_path):
    repo, _, data = make_repo(tmp_path)
    manifest = write_manifest(tmp_path, [artifact_git("f" * 40, "out.dat", sha(data), str(repo))])
    result = run("check", str(manifest), "--no-records-dir")
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "source-lost" in text
    assert "REQUEST" in text


def test_check_lifecycle_fields_and_counter_evidence_admissibility(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    claims = [{
        "id": "claim-1", "statement": "s", "intent": "i", "artifacts": ["a1"],
        "judgment": "insufficient", "reason": "r",
        "superseded_by": "claim-2",
        "deprecated": True,
        "deprecated_reason": "better data arrived",
        "counter_evidence": "the LSA approximation fails under high magnetic field conditions",
    }]
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo), superseded_by="a2")], claims)
    result = run("check", str(manifest), "--no-records-dir")
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "superseded" in text and "deprecated" in text
    assert "counter-evidence" in text
    assert "candidate-admissible" in text


def test_check_backward_compatible_without_lifecycle_fields(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    result = run("validate", str(manifest))
    assert result.returncode == 0, result.stderr


def test_check_deprecated_requires_reason(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    artifact = artifact_git(commit, "out.dat", sha(data), str(repo), deprecated=True)
    manifest = tmp_path / "m.yaml"
    manifest.write_text(yaml.safe_dump({"edition": "e", "artifacts": [artifact]}))
    result = run("validate", str(manifest))
    assert result.returncode == 2
    assert "deprecated_reason" in result.stderr.decode()


def test_check_never_writes_manifest_bytes(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    before = manifest.read_bytes()
    result = run("check", str(manifest), "--no-records-dir", "--report", str(tmp_path / "report.txt"))
    assert result.returncode == 0, result.stderr
    assert manifest.read_bytes() == before
    assert (tmp_path / "report.txt").read_text()


def test_check_records_dir_frontmatter_scan(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    records = tmp_path / "records"
    records.mkdir()
    (records / "supersession.md").write_text(
        textwrap.dedent("""\
        ---
        id: rec-1
        status: superseded
        ---
        # Supersession note
        """)
    )
    (records / "counter.md").write_text(
        textwrap.dedent("""\
        ---
        contrary_evidence:
          artifact: a1
          reason: "approximation X fails under low-temperature conditions"
        ---
        # Counter evidence note
        """)
    )
    (records / "unrelated.md").write_text("# no frontmatter here\n")
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    result = run("check", str(manifest), "--records-dir", str(records))
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "superseded" in text
    assert "counter-evidence" in text
    assert "rec-1" in text and "a1" in text


def test_check_records_dir_bare_deprecated_flag(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    records = tmp_path / "records"
    records.mkdir()
    (records / "note-b.md").write_text(
        textwrap.dedent("""\
        ---
        id: note-b
        deprecated: true
        artifact: changed
        deprecated_reason: superseded by rerun with corrected calibration
        ---
        # Deprecation note
        """)
    )
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    result = run("check", str(manifest), "--records-dir", str(records))
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "deprecated" in text
    assert "changed" in text
    assert "corrected calibration" in text


def test_check_records_dir_counter_evidence_carries_admissibility_label(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    records = tmp_path / "records"
    records.mkdir()
    (records / "counter.md").write_text(
        textwrap.dedent("""\
        ---
        contrary_evidence:
          artifact: a1
          reason: "the static approximation fails below the magnon gap"
        ---
        # Counter evidence note
        """)
    )
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    result = run("check", str(manifest), "--records-dir", str(records))
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "counter-evidence" in text
    assert "contrary_evidence [candidate-admissible" in text


def test_classify_counter_evidence_direct():
    script = textwrap.dedent(f"""\
        import importlib.util
        spec = importlib.util.spec_from_file_location("em", {str(TOOLS)!r})
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cases = [
            ("The static approximation fails below the magnon gap.", "candidate-admissible"),
            ("Approximation X is invalid for small systems at high doping.", "candidate-admissible"),
            ("This result is wrong.", "candidate-review-required"),
            ("Everything checks out.", "candidate-review-required"),
        ]
        for text, expected in cases:
            got = mod.classify_counter_evidence(text)
            assert got.startswith(expected), (text, got, expected)
            assert "requires claim-wording comparison by reviewer" in got or got == mod.CANDIDATE_REVIEW
    """)
    result = subprocess.run([PYTHON, "-c", script], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr

# ------------------------------------------------- Story 007 review round 1


def git_commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


def test_check_detects_in_place_change_committed_after_adoption(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    (repo / "out.dat").write_bytes(b"run 42 revised in place\n")
    head = git_commit_all(repo, "revise in place")
    result = run("check", str(manifest), "--no-records-dir")
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "content-changed" in text
    assert head in text
    assert commit in text


def test_check_detects_move_committed_after_adoption(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    (repo / "runs").mkdir()
    git(repo, "mv", "out.dat", "runs/out-renamed.dat")
    head = git_commit_all(repo, "move output")
    result = run("check", str(manifest), "--no-records-dir")
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "path-moved" in text
    assert "runs/out-renamed.dat" in text
    assert head in text


def test_check_move_with_quoted_path_reports_true_path(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    tricky_dir = repo / 'we"dir'
    tricky_dir.mkdir()
    git(repo, "mv", "out.dat", 'we"dir/out".dat')
    git_commit_all(repo, "move to quoted path")
    result = run("check", str(manifest), "--no-records-dir")
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "path-moved" in text
    assert 'we"dir/out".dat' in text


def test_check_scan_stays_correct_on_multi_file_tree(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    for index in range(40):
        (repo / f"noise-{index:02d}.dat").write_bytes(f"noise payload {index}\n".encode())
    git_commit_all(repo, "add noise files")
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    (repo / "archive").mkdir()
    git(repo, "mv", "out.dat", "archive/out.dat")
    git_commit_all(repo, "move run output among noise")
    result = run("check", str(manifest), "--no-records-dir")
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "path-moved" in text and "archive/out.dat" in text


def test_check_counter_evidence_requires_claim_specific_comparison(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    evidence = "the static approximation fails below the magnon gap"
    claims = [
        {
            "id": f"claim-{n}", "statement": f"wording {n}", "intent": "i", "reason": "r",
            "artifacts": ["a1"], "judgment": "insufficient", "counter_evidence": evidence,
        }
        for n in (1, 2)
    ]
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))], claims)
    result = run("check", str(manifest), "--no-records-dir")
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert text.count("candidate-") >= 2
    assert "claim's wording and scope" in text
    assert "no validity verdict" in text


def test_check_comparability_triage_block_present(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    (repo / "out.dat").write_bytes(b"revised\n")
    git_commit_all(repo, "revise")
    result = run("check", str(manifest), "--no-records-dir")
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "COMPARABILITY TRIAGE (to be completed by sourced agent/author judgement — ADR-004 layer 2):" in text
    for field in ("research question", "structure", "parameters", "approximation", "processing conditions", "scope"):
        assert f"{field}: [open]" in text
    assert "basis (deterministic):" in text


def test_check_scientific_invalidation_only_from_explicit_record(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    records = tmp_path / "records"
    records.mkdir()
    (records / "invalidation.md").write_text(
        textwrap.dedent("""\
        ---
        id: inv-1
        scientific_invalidation: true
        artifact: a1
        reason: "normalization sign error found in rerun"
        ---
        # Invalidation record
        """)
    )
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    result = run("check", str(manifest), "--records-dir", str(records))
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "scientific-invalidation" in text
    assert "a1" in text
    assert "review status: paused pending author review" in text


def test_check_deprecated_record_resolves_target_and_pauses_claims(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    records = tmp_path / "records"
    records.mkdir()
    (records / "dep.md").write_text(
        textwrap.dedent("""\
        ---
        id: dep-1
        deprecated: true
        artifact: a1
        deprecated_reason: recalibrated data available
        ---
        # Deprecation record
        """)
    )
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    result = run("check", str(manifest), "--records-dir", str(records))
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "deprecated" in text
    assert "claim-1" in text
    assert "paused pending author review" in text


def test_check_requires_records_dir_or_explicit_skip(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    result = run("check", str(manifest))
    assert result.returncode == 2
    text = result.stderr.decode()
    assert "error" in text and "--records-dir" in text
    acknowledged = run("check", str(manifest), "--no-records-dir")
    assert acknowledged.returncode == 0, acknowledged.stderr
    assert "UNMARKED records" in acknowledged.stdout.decode()


def test_check_rejects_report_destination_equal_to_manifest(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    before = manifest.read_bytes()
    result = run("check", str(manifest), "--no-records-dir", "--report", str(manifest))
    assert result.returncode == 2
    assert "manifest" in result.stderr.decode()
    assert manifest.read_bytes() == before


def test_check_records_deprecated_string_value_is_skipped(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    records = tmp_path / "records"
    records.mkdir()
    (records / "bad.md").write_text(
        textwrap.dedent("""\
        ---
        id: bad
        deprecated: "false"
        ---
        # Not a real deprecation flag
        """)
    )
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    result = run("check", str(manifest), "--records-dir", str(records))
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "findings: 0" in text


def test_check_detects_uncommitted_worktree_change(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    (repo / "out.dat").write_bytes(b"uncommitted working tree bytes\n")
    result = run("check", str(manifest), "--no-records-dir")
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "content-changed" in text
    assert "working-tree" in text
    assert sha(b"uncommitted working tree bytes\n") in text


def test_check_deprecated_record_status_explicit_artifact_target_pauses_claim(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    records = tmp_path / "records"
    records.mkdir()
    (records / "deprecated.md").write_text(
        textwrap.dedent("""\
        ---
        id: record-id
        status: deprecated
        artifact: a1
        ---
        # Deprecated artifact
        """)
    )
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    result = run("check", str(manifest), "--records-dir", str(records))
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "deprecated — a1" in text
    assert "affected claims: claim-1" in text
    assert "paused pending author review" in text


def test_check_record_targeting_claim_pauses_that_claim(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    records = tmp_path / "records"
    records.mkdir()
    (records / "claim-review.md").write_text(
        textwrap.dedent("""\
        ---
        id: record-id
        deprecated: true
        claim: claim-1
        reason: wording requires review
        ---
        # Claim review
        """)
    )
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    result = run("check", str(manifest), "--records-dir", str(records))
    assert result.returncode == 0, result.stderr
    text = result.stdout.decode()
    assert "deprecated — claim-1" in text
    assert "affected claims: claim-1" in text
    assert "paused pending author review" in text


def test_check_rejects_hard_link_report_destination(tmp_path):
    repo, commit, data = make_repo(tmp_path)
    manifest = write_manifest(tmp_path, [artifact_git(commit, "out.dat", sha(data), str(repo))])
    before = manifest.read_bytes()
    hardlink = tmp_path / "manifest-hardlink.yaml"
    os.link(manifest, hardlink)
    result = run("check", str(manifest), "--no-records-dir", "--report", str(hardlink))
    assert result.returncode == 2
    assert "manifest file itself" in result.stderr.decode()
    assert manifest.read_bytes() == before
    assert hardlink.read_bytes() == before


def test_check_record_target_kind_no_cross_id_collision(tmp_path):
    """A record explicitly targeting claim X must not pause unrelated claims that
    merely cite a same-named ARTIFACT (and vice versa) when ids collide."""
    import hashlib
    data = b"payload\n"
    (tmp_path / "a.bin").write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    manifest = tmp_path / "evidence-manifest.yaml"
    manifest.write_text(
        "edition: e1\n"
        "artifacts:\n"
        f"  - {{id: shared, sha256: '{sha}', locator: {{kind: snapshot, path: 'a.bin'}}}}\n"
        "claims:\n"
        "  - {id: shared, statement: s, intent: i, reason: r, artifacts: [shared], judgment: support}\n"
        "  - {id: other, statement: s, intent: i, reason: r, artifacts: [shared], judgment: support}\n"
    )
    records = tmp_path / "records"
    records.mkdir()
    (records / "n.md").write_text(
        "---\ncontrary_evidence: \"the approximation fails under high field\"\nclaim: shared\n---\n# n\n"
    )
    result = subprocess.run(
        [sys.executable, str(TOOLS), "check", str(manifest), "--records-dir", str(records)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    # the explicitly claim-targeted finding must pause ONLY claim 'shared' ... but
    # 'shared' is also the artifact cited by 'other'; target kind claim => only the
    # claim-id match counts, so 'other' must NOT be paused by this finding.
    for line in result.stdout.splitlines():
        if line.startswith("affected claims:"):
            assert line == "affected claims: shared (flagged, never deleted; review status: paused pending author review)", line
