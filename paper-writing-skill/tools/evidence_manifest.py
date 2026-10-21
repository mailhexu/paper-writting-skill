#!/usr/bin/env python3
"""Evidence-manifest validator and locator retriever (Story 005, minimal).

Deterministic helper for the conventions in references/evidence-manifest.md:
schema validation of `evidence-manifest.yaml` (edition / artifacts / claims) and
byte retrieval for the three locator kinds (`git`, `snapshot`, `retained`), with
the sha256 verified before any bytes are emitted as success. A hash is never a
retrieval method; an unresolvable locator fails visibly and is never substituted
with current file bytes.

No generic library surface, no snapshot creation, no freshness checks, no
projection or export — those belong to later approved stories.

Usage:
    evidence_manifest.py validate  <manifest.yaml>
    evidence_manifest.py retrieve  <manifest.yaml> <artifact-id> [--output FILE]
    evidence_manifest.py adopt <current-file> --repo REPO --commit SHA --git-path PATH
                                   [--snapshot-dir DIR] [--artifact-id ID] [--output-manifest-fragment FILE]
    evidence_manifest.py check <manifest.yaml> [--report FILE] [--records-dir DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - dependency notice
    sys.stderr.write("evidence-manifest: error: PyYAML is required (pip install pyyaml)\n")
    raise SystemExit(2)

HEX64 = re.compile(r"[0-9a-f]{64}")
HEX40 = re.compile(r"[0-9a-f]{40}")
JUDGMENTS = ("support", "refute", "insufficient")
LOCATOR_KINDS = ("git", "snapshot", "retained")
ERROR_PREFIX = "evidence-manifest: error: "


class ManifestError(Exception):
    """Consumer-visible validation or retrieval failure (exit 2)."""


def _err(location: str, message: str) -> "ManifestError":
    return ManifestError(f"{location}: {message}")


def load_manifest(manifest_path: str) -> dict:
    path = Path(manifest_path)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ManifestError(f"manifest: unreadable: {error}") from error
    try:
        document = yaml.safe_load(raw.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as error:
        raise ManifestError(f"manifest: invalid YAML: {error}") from error
    if not isinstance(document, dict):
        raise ManifestError("manifest: top level must be a mapping")
    validate_manifest(document)
    return document


def validate_manifest(document: dict) -> None:
    if not isinstance(document.get("edition"), str) or not document["edition"].strip():
        raise _err("edition", "missing or empty; the manifest must identify its evidence edition")

    artifacts = document.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise _err("artifacts", "missing or empty; at least one adopted artifact entry is required")
    seen_ids: set[str] = set()
    for index, artifact in enumerate(artifacts):
        location = f"artifacts[{index}]"
        if not isinstance(artifact, dict):
            raise _err(location, "entry must be a mapping")
        artifact_id = artifact.get("id")
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            raise _err(f"{location}.id", "missing or empty")
        if artifact_id in seen_ids:
            raise _err(f"{location}.id", f"duplicate artifact id '{artifact_id}'")
        seen_ids.add(artifact_id)
        digest = artifact.get("sha256")
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise _err(f"{location}.sha256", "must be 64 lowercase hex characters")
        _validate_locator(location, artifact.get("locator"), artifact_id)
        _validate_lifecycle_fields(location, artifact)

    claims = document.get("claims")
    if not isinstance(claims, list) or not claims:
        raise _err("claims", "missing or empty; the manifest registers claims with their judgment")
    seen_claims: set[str] = set()
    for index, claim in enumerate(claims):
        location = f"claims[{index}]"
        if not isinstance(claim, dict):
            raise _err(location, "entry must be a mapping")
        claim_id = claim.get("id")
        if not isinstance(claim_id, str) or not claim_id.strip():
            raise _err(f"{location}.id", "missing or empty")
        if claim_id in seen_claims:
            raise _err(f"{location}.id", f"duplicate claim id '{claim_id}'")
        seen_claims.add(claim_id)
        for field in ("statement", "intent", "reason"):
            value = claim.get(field)
            if not isinstance(value, str) or not value.strip():
                raise _err(f"{location}.{field}", "missing or empty")
        references = claim.get("artifacts")
        if not isinstance(references, list) or not references:
            raise _err(f"{location}.artifacts", "missing or empty; a claim cites its artifact ids")
        for reference in references:
            if not isinstance(reference, str):
                raise _err(f"{location}.artifacts", f"artifact references must be artifact-id strings; got {type(reference).__name__}")
            if reference not in seen_ids:
                raise _err(f"{location}.artifacts", f"unknown artifact id '{reference}'")
        judgment = claim.get("judgment")
        if judgment not in JUDGMENTS:
            raise _err(f"{location}.judgment", f"must be one of {' / '.join(JUDGMENTS)}")
        _validate_lifecycle_fields(location, claim)


def _validate_locator(location: str, locator: object, artifact_id: str) -> None:
    if not isinstance(locator, dict):
        raise _err(
            f"{location}.locator",
            f"missing: sha256 is a content fingerprint, not a retrieval method; "
            f"artifact '{artifact_id}' needs a git / snapshot / retained locator",
        )
    kind = locator.get("kind")
    if kind not in LOCATOR_KINDS:
        raise _err(
            f"{location}.locator.kind",
            f"unknown locator kind '{kind}'; must be one of {' / '.join(LOCATOR_KINDS)}",
        )
    if kind == "git":
        for field in ("repo", "commit", "path"):
            value = locator.get(field)
            if not isinstance(value, str) or not value.strip():
                raise _err(f"{location}.locator.{field}", "missing for git locator")
        commit = locator["commit"]
        if not HEX40.fullmatch(commit):
            raise _err(
                f"{location}.locator.commit",
                "must be the full 40-hex commit SHA recorded at adoption; "
                "branch names and HEAD references are not immutable",
            )
    else:
        value = locator.get("path")
        if not isinstance(value, str) or not value.strip():
            raise _err(f"{location}.locator.path", f"missing for {kind} locator")


def _validate_lifecycle_fields(location: str, mapping: dict) -> None:
    """Optional Story-007 fields (claims and artifacts); backward compatible.

    - superseded_by: a non-empty string or a non-empty list of strings (ids/text).
    - deprecated: true requires a non-empty string `deprecated_reason`.
    - counter_evidence: a non-empty string or a non-empty list of strings.
    """
    superseded = mapping.get("superseded_by")
    if superseded is not None:
        values = superseded if isinstance(superseded, list) else [superseded]
        if not values or not all(isinstance(v, str) and v.strip() for v in values):
            raise _err(f"{location}.superseded_by", "must be a non-empty string or list of strings (ids or text)")
    deprecated = mapping.get("deprecated")
    if deprecated is not None:
        if not isinstance(deprecated, bool):
            raise _err(f"{location}.deprecated", "must be a boolean")
        reason = mapping.get("deprecated_reason")
        if deprecated and (not isinstance(reason, str) or not reason.strip()):
            raise _err(f"{location}.deprecated_reason", "required (non-empty string) when deprecated is true")
    counter = mapping.get("counter_evidence")
    if counter is not None:
        values = counter if isinstance(counter, list) else [counter]
        if not values or not all(isinstance(v, str) and v.strip() for v in values):
            raise _err(f"{location}.counter_evidence", "must be a non-empty string or list of strings")


def locator_description(locator: dict) -> str:
    if locator["kind"] == "git":
        return f"git {locator['repo']}@{locator['commit']}:{locator['path']}"
    return f"{locator['kind']} {locator['path']}"


# -- retrieval ---------------------------------------------------------------


def _run_git(repo: str, *arguments: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", "-C", repo, *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
        )
    except FileNotFoundError:
        raise ManifestError(f"locator.repo: git executable not found on PATH") from None
    except subprocess.TimeoutExpired:
        raise ManifestError(f"locator.repo: git command timed out in '{repo}'") from None


def _resolve_from_manifest(base: Path, value: str) -> Path:
    """Relative locator values resolve against the manifest's directory."""
    path = Path(value)
    return path if path.is_absolute() else base / path


def _git_blob(repo_display: str, repo: str, commit: str, path: str, artifact_id: str) -> bytes:
    check = _run_git(repo, "rev-parse", "--git-dir")
    if check.returncode != 0:
        raise ManifestError(
            f"{artifact_id}: git locator.repo '{repo_display}' is not a usable git repository "
            f"(resolved as '{repo}')"
        )
    check = _run_git(repo, "cat-file", "-e", f"{commit}^{{commit}}")
    if check.returncode != 0:
        raise ManifestError(
            f"{artifact_id}: git locator.commit {commit}: not found in repo '{repo_display}' "
            f"(recorded adoption commit is not resolvable; current files are not a substitute)"
        )
    result = _run_git(repo, "cat-file", "blob", f"{commit}:{path}")
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise ManifestError(
            f"{artifact_id}: git locator.path '{path}': not retrievable at commit {commit} "
            f"in repo '{repo_display}': {detail}"
        )
    return result.stdout


def retrieve_bytes(locator: dict, artifact_id: str, base: Path) -> bytes:
    kind = locator["kind"]
    if kind == "git":
        repo = _resolve_from_manifest(base, locator["repo"])
        return _git_blob(locator["repo"], str(repo), locator["commit"], locator["path"], artifact_id)
    source = _resolve_from_manifest(base, locator["path"])
    try:
        return source.read_bytes()
    except OSError as error:
        raise ManifestError(f"{artifact_id}: {kind} locator.path '{locator['path']}' (resolved '{source}'): unreadable: {error}") from None


def retrieve(manifest_path: str, artifact_id: str, output: str | None) -> None:
    document = load_manifest(manifest_path)
    base = Path(manifest_path).resolve().parent
    artifact = next((a for a in document["artifacts"] if a["id"] == artifact_id), None)
    if artifact is None:
        known = ", ".join(a["id"] for a in document["artifacts"])
        raise ManifestError(f"artifact '{artifact_id}' not in manifest (known: {known})")
    payload = retrieve_bytes(artifact["locator"], artifact_id, base)
    digest = hashlib.sha256(payload).hexdigest()
    pinned = artifact["sha256"]
    if digest != pinned:
        raise ManifestError(
            f"artifact '{artifact_id}': sha256 mismatch: pinned {pinned}, retrieved {digest}; "
            f"retrieved bytes are NOT the adopted edition and are not emitted"
        )
    destination = Path(output) if output else None
    if destination is not None:
        try:
            destination.write_bytes(payload)
        except OSError as error:
            raise ManifestError(f"output: cannot write '{destination}': {error}") from None
        print(f"{artifact_id}: {len(payload)} bytes written to {destination} (sha256 verified)")
    else:
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()


def validate_command(manifest_path: str) -> None:
    document = load_manifest(manifest_path)
    for artifact in document["artifacts"]:
        print(f"artifact {artifact['id']}: {locator_description(artifact['locator'])}")
    print(
        f"manifest {document['edition']}: valid; "
        f"{len(document['artifacts'])} artifacts, {len(document['claims'])} claims"
    )


# -- adoption (Story 006) ----------------------------------------------------


def _sanitize_filename_component(value: str, field: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value):
        raise ManifestError(
            f"{field} '{value}': must be safe ASCII ([A-Za-z0-9][A-Za-z0-9._-]*) to derive a snapshot filename"
        )
    return value


def _render_fragment(artifact: dict) -> str:
    """Serialize an artifact entry as a single-entry YAML list fragment.

    yaml.safe_dump (not string interpolation) keeps repo/path values with
    quotes or backslashes valid and truthful. The `- ` list item is emitted
    verbatim so the fragment pastes directly under a manifest's `artifacts:`.
    """
    return yaml.safe_dump(
        [artifact],
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )


def adopt(
    current_file: str,
    repo: str,
    commit: str,
    git_path: str,
    snapshot_dir: str,
    artifact_id: str | None,
    output_fragment: str | None,
) -> None:
    source = Path(current_file)
    if not source.is_file():
        raise ManifestError(f"current-file '{current_file}': does not exist; there are no bytes to adopt")
    if not HEX40.fullmatch(commit):
        raise ManifestError(
            f"--commit '{commit}': must be the full 40-hex commit SHA recorded at adoption; "
            "branch names and HEAD references are not immutable"
        )
    try:
        current_bytes = source.read_bytes()
    except OSError as error:
        raise ManifestError(f"current-file '{current_file}': unreadable: {error}") from None
    current_sha = hashlib.sha256(current_bytes).hexdigest()
    resolved_artifact_id = artifact_id or f"adopted-{current_sha[:12]}"

    # Never pass off HEAD bytes: the recorded commit must resolve before
    # anything is declared identical to it; an unresolvable commit is a visible
    # failure, never a silent substitution of current bytes.
    check = _run_git(repo, "cat-file", "-e", f"{commit}^{{commit}}")
    if check.returncode != 0:
        raise ManifestError(
            f"{resolved_artifact_id}: --commit {commit}: not found in repo '{repo}' "
            f"(recorded adoption commit is not resolvable; current files are not a substitute)"
        )
    try:
        blob = _git_blob(repo, repo, commit, git_path, resolved_artifact_id)
        blob_sha = hashlib.sha256(blob).hexdigest()
    except ManifestError as failure:
        # Commit resolves but the path is not in it: the classic uncommitted /
        # unpushed case — content differs from the recorded tree, so snapshot.
        if "locator.path" not in str(failure):
            raise
        blob = b""
        blob_sha = "(path not present at the recorded commit)"
        _ = failure

    if blob == current_bytes:
        pending_snapshot = None
        locator = {"kind": "git", "repo": repo, "commit": commit, "path": git_path}
        sha = current_sha
        verdict = (
            f"adopt {resolved_artifact_id}: current bytes identical to git blob {commit}:{git_path} "
            f"(sha256 {sha}); registered git locator"
        )
    else:
        # Distinguish a change that is ALREADY COMMITTED from true uncommitted
        # working-tree content: a committed change must fail visibly (neither
        # version may be silently registered); only genuinely uncommitted
        # bytes are snapshotted.
        head = _run_git(repo, "rev-parse", "HEAD")
        head_commit = head.stdout.decode().strip() if head.returncode == 0 else None
        if head_commit:
            head_blob = _run_git(repo, "cat-file", "blob", f"{head_commit}:{git_path}")
            if head_blob.returncode == 0 and head_blob.stdout == current_bytes:
                raise ManifestError(
                    f"{resolved_artifact_id}: current bytes already differ from the recorded commit "
                    f"as a COMMITTED change: recorded commit {commit} has blob {blob_sha} but HEAD "
                    f"{head_commit} has blob {hashlib.sha256(head_blob.stdout).hexdigest()}; "
                    "the content change is already committed and neither version may be silently "
                    "registered — re-run adoption against the intended commit explicitly"
                )
        component = _sanitize_filename_component(resolved_artifact_id, "--artifact-id")
        destination = Path(snapshot_dir) / f"{component}.bin"
        if destination.exists():
            try:
                existing = destination.read_bytes()
            except OSError as error:
                raise ManifestError(f"snapshot path '{destination}': unreadable: {error}") from None
            if existing != current_bytes:
                raise ManifestError(
                    f"snapshot path '{destination}': already exists with different bytes; "
                    "adoption is idempotent, so choose a distinct --artifact-id instead of overwriting"
                )
        pending_snapshot = destination
        locator = {"kind": "snapshot", "path": Path(snapshot_dir).joinpath(f"{component}.bin").as_posix()}
        sha = current_sha
        verdict = (
            f"adopt {resolved_artifact_id}: current bytes DIFFER from git blob {commit}:{git_path} "
            f"({blob_sha} vs current {current_sha}, HEAD {head_commit or 'none'}); "
            f"HEAD bytes were NOT substituted; snapshot written to {destination} "
            f"(sha256 {current_sha}) — COMMIT THIS SNAPSHOT TOGETHER WITH THE RECORD"
        )

    # Validate-then-write: the fragment must parse and pass the Story-005
    # schema before any snapshot file is created, so a quoting/serialization
    # failure never leaves a snapshot without a valid record.
    fragment = _render_fragment({"id": resolved_artifact_id, "sha256": sha, "locator": locator})
    parsed = yaml.safe_load(fragment)
    artifacts = parsed if isinstance(parsed, list) else [parsed]
    validate_manifest({
        "edition": "fragment-check",
        "artifacts": artifacts,
        "claims": [{
            "id": "x", "statement": "x", "intent": "x", "reason": "x",
            "artifacts": [artifacts[0]["id"]], "judgment": "support",
        }],
    })
    if pending_snapshot is not None:
        try:
            pending_snapshot.parent.mkdir(parents=True, exist_ok=True)
            pending_snapshot.write_bytes(current_bytes)
        except OSError as error:
            raise ManifestError(f"snapshot: cannot write '{pending_snapshot}': {error}") from None
    if output_fragment:
        destination = Path(output_fragment)
        try:
            destination.write_bytes(fragment.encode("utf-8"))  # verbatim safe_dump bytes (already newline-terminated)
        except OSError as error:
            raise ManifestError(f"--output-manifest-fragment: cannot write '{destination}': {error}") from None
        print(verdict)
        print(f"fragment written to {destination}")
    else:
        print(verdict)
        print("--- fragment (merge into evidence-manifest.yaml artifacts:) ---")
        print(fragment)


# -- freshness check + triage (Story 007) ------------------------------------

COUNTER_EVIDENCE_FAILURE_MARKERS = (
    "fail", "fails", "failed", "failing", "invalid", "breaks down", "unreliable",
    "inaccurate", "not valid", "violat", "erron", "wrong sign", "unphysical",
    "diverg", "breaks", "break", "unstable", "insufficient",
)
COUNTER_EVIDENCE_SCOPE_MARKERS = (
    "under", "when", "whenever", "for", "beyond", "outside", "near", "above", "below",
    "only", "regime", "limit", "condition", "case", "temperature", "pressure",
    "doping", "density", "frequency", "region", "range", "domain", "assum",
    "approxim", "small", "large", "high", "low", "strong", "weak", "long-time",
)


CANDIDATE_ADMISSIBLE = "candidate-admissible (scoped-failure wording; requires claim-wording comparison by reviewer)"
CANDIDATE_REVIEW = "candidate-review-required"


def classify_counter_evidence(text: str) -> str:
    """Deterministic CANDIDATE label for counter-evidence phrasing (FR-A3 / SPEC-004).

    Purely descriptive — this deterministic layer does NOT decide scientific
    validity and emits no validity verdict. Returns CANDIDATE_ADMISSIBLE when
    the text asserts a *scoped* failure (a failure mode such as fails /
    invalid / unreliable together with a scoping qualifier such as under /
    when / for / beyond), otherwise CANDIDATE_REVIEW. Admissibility itself is
    decided only by comparing the evidence with the specific manuscript
    claim's wording and scope (agent/author judgement, ADR-004 layer 2).
    """
    lowered = text.lower()
    has_failure = any(marker in lowered for marker in COUNTER_EVIDENCE_FAILURE_MARKERS)
    has_scope = any(marker in lowered for marker in COUNTER_EVIDENCE_SCOPE_MARKERS)
    if has_failure and has_scope:
        return CANDIDATE_ADMISSIBLE
    return CANDIDATE_REVIEW


def _git_tree_blobs(repo: str, commit: str) -> list[tuple[str, str]]:
    """All (oid, path) blob entries of a tree; NUL-delimited ls-tree so quoted
    or escaped paths report their true path."""
    listing = _run_git(repo, "ls-tree", "-z", "-r", commit)
    if listing.returncode != 0:
        return []
    entries: list[tuple[str, str]] = []
    for record in listing.stdout.split(b"\0"):
        if not record:
            continue
        meta, _, path_bytes = record.partition(b"\t")
        fields = meta.split()
        if len(fields) >= 3 and fields[1] == b"blob":
            entries.append((fields[2].decode("ascii"), path_bytes.decode("utf-8", "surrogateescape")))
    return entries


def _scan_tree_for_content(repo: str, commit: str, pinned: str) -> str | None:
    """Content-hash scan of one tree: ls-tree once, then batch-read every blob
    in a single `git cat-file --batch` call. Complexity is bounded by the tree
    size (one ls-tree pass + one batched blob read), never one process per blob."""
    entries = _git_tree_blobs(repo, commit)
    if not entries:
        return None
    oids = [oid for oid, _ in entries]
    try:
        proc = subprocess.Popen(
            ["git", "-C", repo, "cat-file", "--batch"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        raise ManifestError("locator.repo: git executable not found on PATH") from None
    out, _ = proc.communicate(("\n".join(oids) + "\n").encode())
    blobs: dict[str, bytes] = {}
    offset = 0
    for oid in oids:
        header_end = out.find(b"\n", offset)
        if header_end < 0:
            break
        header = out[offset:header_end].decode("ascii", "replace")
        parts = header.split()
        if len(parts) < 3 or parts[1] in ("missing", "ambiguous"):
            offset = header_end + 1
            continue
        size = int(parts[2])
        data = out[header_end + 1 : header_end + 1 + size]
        offset = header_end + 1 + size + 1  # trailing newline after contents
        blobs[parts[0]] = data
    for oid, path in entries:
        data = blobs.get(oid)
        if data is not None and hashlib.sha256(data).hexdigest() == pinned:
            return path
    return None


def _as_texts(value: object) -> list[str]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _detect_content(artifact_id: str, artifact: dict, base: Path) -> dict | None:
    """Deterministic freshness check for one artifact. Returns a finding dict or None.

    For git locators the recorded-commit retrieval verifies CURRENT ADOPTED
    bytes; the repository's CURRENT state (HEAD) is then examined separately so
    in-place changes and moves committed after adoption are detected."""
    locator = artifact["locator"]
    kind = locator["kind"]
    pinned = artifact["sha256"]
    adopted = f"sha256={pinned} ({locator_description(locator)})"
    if kind != "git":
        try:
            payload = retrieve_bytes(locator, artifact_id, base)
            digest = hashlib.sha256(payload).hexdigest()
            if digest == pinned:
                return None
            return {
                "category": "content-changed",
                "artifact_id": artifact_id,
                "adopted": adopted,
                "pending": f"source bytes now hash to sha256={digest} at the same locator",
            }
        except ManifestError as failure:
            return {
                "category": "source-lost",
                "artifact_id": artifact_id,
                "adopted": adopted,
                "pending": f"retrieval failed: {failure}",
            }

    repo = str(_resolve_from_manifest(base, locator["repo"]))
    try:
        payload = retrieve_bytes(locator, artifact_id, base)
    except ManifestError as failure:
        # Recorded locator unresolvable: look for the pinned content inside the
        # recorded commit's own tree (bounded batched scan) before declaring loss.
        moved = _scan_tree_for_content(repo, locator["commit"], pinned)
        if moved is not None:
            return {
                "category": "path-moved",
                "artifact_id": artifact_id,
                "adopted": adopted,
                "pending": (
                    f"recorded locator path '{locator['path']}' is not retrievable at commit "
                    f"{locator['commit']}, but the same content was found at '{moved}' in that "
                    "commit's tree"
                ),
            }
        return {
            "category": "source-lost",
            "artifact_id": artifact_id,
            "adopted": adopted,
            "pending": f"retrieval failed: {failure}",
        }
    digest = hashlib.sha256(payload).hexdigest()
    if digest != pinned:
        return {
            "category": "content-changed",
            "artifact_id": artifact_id,
            "adopted": adopted,
            "pending": f"bytes at the recorded locator hash to sha256={digest}, not the pinned content",
        }

    # Recorded locator verified; now examine repository HEAD and the working
    # tree in order. The absent working-tree path alone is informational: the
    # immutable recorded commit remains retrievable.
    worktree_path = Path(repo) / locator["path"]
    try:
        worktree_bytes = worktree_path.read_bytes()
    except OSError:
        worktree_digest = None
    else:
        worktree_digest = hashlib.sha256(worktree_bytes).hexdigest()

    head = _run_git(repo, "rev-parse", "HEAD")
    head_commit = head.stdout.decode().strip() if head.returncode == 0 else None
    if not head_commit:
        if worktree_digest is not None and worktree_digest != pinned:
            return {
                "category": "content-changed",
                "artifact_id": artifact_id,
                "adopted": adopted,
                "pending": (
                    f"working-tree path '{locator['path']}' now has sha256={worktree_digest} "
                    f"(pinned {pinned}); no resolvable HEAD state"
                ),
            }
        return None
    head_blob = _run_git(repo, "cat-file", "blob", f"{head_commit}:{locator['path']}")
    if head_blob.returncode == 0:
        head_digest = hashlib.sha256(head_blob.stdout).hexdigest()
        if head_digest == pinned:
            if worktree_digest is not None and worktree_digest != pinned:
                return {
                    "category": "content-changed",
                    "artifact_id": artifact_id,
                    "adopted": adopted,
                    "pending": (
                        f"working-tree path '{locator['path']}' now has sha256={worktree_digest} "
                        f"(pinned {pinned}); recorded commit and HEAD {head_commit} both match the pin"
                    ),
                }
            return None
        moved = _scan_tree_for_content(repo, head_commit, pinned)
        if moved is not None and moved != locator["path"]:
            return {
                "category": "path-moved",
                "artifact_id": artifact_id,
                "adopted": adopted,
                "pending": (
                    f"repository HEAD {head_commit} has sha256={head_digest} at the old path "
                    f"'{locator['path']}', while the pinned content was found at '{moved}'"
                ),
            }
        pending = (
            f"repository HEAD {head_commit} now has sha256={head_digest} at '{locator['path']}' "
            f"(pinned {pinned}); the recorded-commit verification passed"
        )
        if worktree_digest is not None and worktree_digest != pinned:
            pending += f"; working tree also diverges with sha256={worktree_digest}"
        return {
            "category": "content-changed",
            "artifact_id": artifact_id,
            "adopted": adopted,
            "pending": pending,
        }
    moved = _scan_tree_for_content(repo, head_commit, pinned)
    if moved is not None:
        return {
            "category": "path-moved",
            "artifact_id": artifact_id,
            "adopted": adopted,
            "pending": f"same content found at '{moved}' in current HEAD {head_commit}",
        }
    return {
        "category": "content-changed",
        "artifact_id": artifact_id,
        "adopted": adopted,
        "pending": (
            f"path '{locator['path']}' is absent from current HEAD {head_commit} and the pinned "
            "content was not found elsewhere in the HEAD tree"
        ),
    }


def _parse_frontmatter(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def _records_dir_findings(records_dir: str) -> list[dict]:
    """Deterministic record-inspection layer: YAML frontmatter only, no full-text semantics."""
    root = Path(records_dir)
    if not root.is_dir():
        raise ManifestError(f"--records-dir '{records_dir}': not a directory")
    findings: list[dict] = []
    for path in sorted(root.rglob("*.md")):
        data = _parse_frontmatter(path)
        if not data:
            continue
        status = data.get("status")
        if status in ("superseded", "deprecated"):
            target = data.get("artifact") or data.get("claim") or data.get("id")
            findings.append({
                "category": "superseded" if status == "superseded" else "deprecated",
                "artifact_id": str(target) if target is not None else path.name,
                "adopted": f"record {data.get('id', path.name)}",
                "pending": f"record '{path.name}' frontmatter status: {status}",
                "source": str(path),
            })
        deprecated = data.get("deprecated")
        if deprecated is True:  # strictly boolean; string values are skipped silently
            target = data.get("artifact") or data.get("claim") or data.get("id")
            reason = data.get("deprecated_reason") or data.get("reason") or ""
            entry_repr = f"{target}" + (f" ({reason})" if reason else "")
            findings.append({
                "category": "deprecated",
                "target_kind": ("artifact" if data.get("artifact") else "claim" if data.get("claim") else None),
                "artifact_id": str(target) if target is not None else path.name,
                "adopted": f"record {data.get('id', path.name)}",
                "pending": f"deprecated: {entry_repr}",
                "source": str(path),
            })
        scientific = data.get("scientific_invalidation")
        if scientific is True:  # explicit reviewer marker only; never derived by this tool
            target = data.get("artifact") or data.get("claim") or data.get("id")
            reason = data.get("reason") or ""
            findings.append({
                "category": "scientific-invalidation",
                "target_kind": ("artifact" if data.get("artifact") else "claim" if data.get("claim") else None),
                "artifact_id": str(target) if target is not None else path.name,
                "adopted": f"record {data.get('id', path.name)}",
                "pending": "scientific_invalidation flagged" + (f": {reason}" if reason else ""),
                "source": str(path),
            })
        for field, category in (("superseded_by", "superseded"), ("contrary_evidence", "counter-evidence")):
            value = data.get(field)
            if value is None:
                continue
            entries = value if isinstance(value, list) else [value]
            for entry in entries:
                if isinstance(entry, dict):
                    if entry.get("artifact"):
                        target, target_kind = entry["artifact"], "artifact"
                    elif entry.get("claim"):
                        target, target_kind = entry["claim"], "claim"
                    else:
                        target, target_kind = entry.get("id"), None
                    note = entry.get("reason") or entry.get("note") or ""
                    entry_repr = f"{target}" + (f" ({note})" if note else "")
                elif isinstance(entry, str):
                    entry_repr = entry
                    target_kind = None
                else:
                    continue  # malformed frontmatter is skipped silently
                pending = f"{field}: {entry_repr}"
                if category == "counter-evidence":
                    basis = note if isinstance(entry, dict) and note else entry_repr
                    pending = f"{field} [{classify_counter_evidence(basis)}]: {entry_repr}"
                findings.append({
                    "category": category,
                    "target_kind": target_kind,
                    "artifact_id": str(target) if isinstance(entry, dict) else entry_repr,
                    "adopted": f"named in frontmatter of '{path.name}'",
                    "pending": pending,
                    "source": str(path),
                })
    return findings


def check(manifest_path: str, report: str | None, records_dir: str | None, no_records_dir: bool = False) -> None:
    path = Path(manifest_path)
    try:
        raw_before = path.read_bytes()
    except OSError as error:
        raise ManifestError(f"manifest: unreadable: {error}") from None
    document = load_manifest(manifest_path)
    if not records_dir and not no_records_dir:
        raise ManifestError(
            "--records-dir: missing; inspecting vault records is part of the freshness workflow (FR-D6). "
            "Pass --records-dir DIR to scan record frontmatter, or --no-records-dir to acknowledge skipping."
        )
    if report:
        report_path = Path(report)
        same_destination = report_path.resolve() == path.resolve()
        if not same_destination:
            try:
                same_destination = os.path.samefile(report_path, path)
            except OSError:
                same_destination = False
        if same_destination:
            raise ManifestError(
                f"--report '{report}': resolves to the manifest file itself; check never writes manifest bytes"
            )
    base = path.resolve().parent
    findings: list[dict] = []

    for artifact in document["artifacts"]:
        finding = _detect_content(artifact["id"], artifact, base)
        if finding:
            findings.append(finding)

    # Manifest-embedded lifecycle channel (Story 007 optional fields).
    for artifact in document["artifacts"]:
        if artifact.get("superseded_by") is not None:
            findings.append({
                "category": "superseded", "artifact_id": artifact["id"],
                "adopted": f"sha256={artifact['sha256']}",
                "pending": f"superseded_by: {artifact['superseded_by']}",
            })
        if artifact.get("deprecated"):
            findings.append({
                "category": "deprecated", "artifact_id": artifact["id"],
                "adopted": f"sha256={artifact['sha256']}",
                "pending": f"deprecated: {artifact['deprecated_reason']}",
            })
        for text in ( _as_texts(artifact.get("counter_evidence"))):
            if isinstance(text, list):
                continue
            findings.append({
                "category": "counter-evidence", "artifact_id": artifact["id"],
                "adopted": f"sha256={artifact['sha256']}",
                "pending": f"counter_evidence [{classify_counter_evidence(text)}]: {text}",
            })
    for claim in document["claims"]:
        if claim.get("superseded_by") is not None:
            findings.append({
                "category": "superseded", "artifact_id": claim["id"],
                "adopted": f"claim '{claim['id']}': {claim['statement']}",
                "pending": f"superseded_by: {claim['superseded_by']}",
            })
        if claim.get("deprecated"):
            findings.append({
                "category": "deprecated", "artifact_id": claim["id"],
                "adopted": f"claim '{claim['id']}': {claim['statement']}",
                "pending": f"deprecated: {claim['deprecated_reason']}",
            })
        for text in ( _as_texts(claim.get("counter_evidence"))):
            if isinstance(text, list):
                continue
            findings.append({
                "category": "counter-evidence", "artifact_id": claim["id"],
                "adopted": f"claim '{claim['id']}': {claim['statement']}",
                "pending": f"counter_evidence [{classify_counter_evidence(text)}]: {text}",
            })

    if records_dir:
        findings.extend(_records_dir_findings(records_dir))

    lines: list[str] = []
    lines.append(f"evidence freshness check — edition {document['edition']}")
    lines.append(f"manifest: {manifest_path} (read-only; bytes never written by check)")
    lines.append(f"artifacts checked: {len(document['artifacts'])}; findings: {len(findings)}")
    if not findings:
        lines.append("RESULT: no changes — manifest matches current sources; no candidate changes produced.")
    for index, finding in enumerate(findings, 1):
        lines.append("")
        lines.append(f"[{index}] {finding['category']} — {finding['artifact_id']}")
        lines.append(f"    CURRENT ADOPTED: {finding['adopted']}")
        lines.append(f"    PENDING CHANGE:  {finding['pending']}")
        if finding.get("source"):
            lines.append(f"    source record:   {finding['source']}")
        if finding["category"] in (
            "source-lost", "content-changed", "path-moved",
            "superseded", "deprecated", "counter-evidence", "scientific-invalidation",
        ):
            kind = finding.get("target_kind")
            affected = [
                c["id"] for c in document["claims"]
                if (kind != "artifact" and finding["artifact_id"] == c["id"])
                or (kind != "claim" and finding["artifact_id"] in c["artifacts"])
            ]
            if affected:
                lines.append(
                    f"    affected claims: {', '.join(affected)} "
                    "(flagged, never deleted; review status: paused pending author review)"
                )
        if finding["category"] in ("source-lost", "content-changed", "path-moved", "counter-evidence", "scientific-invalidation"):
            lines.append(
                f"    REQUEST (draft, FR-K3 — author approval required): recover or re-adopt "
                f"'{finding['artifact_id']}': {finding['pending']}"
            )
        if finding["category"] in (
            "content-changed", "path-moved", "superseded", "deprecated",
            "counter-evidence", "scientific-invalidation",
        ):
            lines.append(
                "    COMPARABILITY TRIAGE (to be completed by sourced agent/author judgement — ADR-004 layer 2):"
            )
            lines.append(
                f"      basis (deterministic): CURRENT ADOPTED {finding['adopted']} vs PENDING {finding['pending']}"
            )
            for field in ("research question", "structure", "parameters", "approximation", "processing conditions", "scope"):
                lines.append(f"      {field}: [open]")
        if finding["category"] == "counter-evidence":
            lines.append(
                "    ADMISSIBILITY: candidate label only — admissibility is decided solely by comparing this "
                "evidence with the specific manuscript claim's wording and scope (agent/author judgement, "
                "ADR-004 layer 2); this tool emits no validity verdict."
            )
    lines.append("")
    lines.append(
        "REPLACEMENT POLICY: replacing any adopted artifact requires explicit author approval; "
        "nothing is auto-replaced; the manifest bytes are never written by check. "
        "Scientific comparability of any pending change is agent judgement (ADR-004 layer 2) "
        "expressed in this report — no rule engine decides replacement here. "
        "Record frontmatter inspection is deterministic (layer 1); newer records nobody "
        "marked are the agent's layer-2 judgement, not automation. "
        "FR-D6 requires reviewing newer UNMARKED records (agent layer-2 judgement) before declaring no changes."
    )
    text = "\n".join(lines) + "\n"

    try:
        raw_after = path.read_bytes()
    except OSError as error:
        raise ManifestError(f"manifest: unreadable after check: {error}") from None
    if raw_after != raw_before:
        raise ManifestError("manifest: bytes changed during check; this must never happen (read-only command)")

    if report:
        destination = Path(report)
        try:
            destination.write_text(text, encoding="utf-8")
        except OSError as error:
            raise ManifestError(f"--report: cannot write '{destination}': {error}") from None
        print(f"triage report written to {destination} ({len(findings)} findings); manifest bytes unchanged")
    else:
        sys.stdout.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evidence_manifest.py", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    validate_parser = commands.add_parser("validate", help="validate a manifest and echo retrieval paths")
    validate_parser.add_argument("manifest")
    retrieve_parser = commands.add_parser("retrieve", help="fetch pinned bytes with sha256 verification")
    retrieve_parser.add_argument("manifest")
    retrieve_parser.add_argument("artifact_id")
    retrieve_parser.add_argument("--output", default=None)
    adopt_parser = commands.add_parser("adopt", help="verify bytes at adoption time; snapshot uncommitted content")
    adopt_parser.add_argument("current_file")
    adopt_parser.add_argument("--repo", required=True)
    adopt_parser.add_argument("--commit", required=True)
    adopt_parser.add_argument("--git-path", required=True)
    adopt_parser.add_argument("--snapshot-dir", default="evidence-snapshots")
    adopt_parser.add_argument("--artifact-id", default=None)
    adopt_parser.add_argument("--output-manifest-fragment", default=None)
    check_parser = commands.add_parser("check", help="read-only freshness check + triage report")
    check_parser.add_argument("manifest")
    check_parser.add_argument("--report", default=None)
    check_parser.add_argument("--stdout", dest="stdout", action="store_true", default=False)
    check_parser.add_argument("--records-dir", default=None)
    check_parser.add_argument("--no-records-dir", dest="no_records_dir", action="store_true", default=False)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "validate":
            validate_command(arguments.manifest)
        elif arguments.command == "retrieve":
            retrieve(arguments.manifest, arguments.artifact_id, arguments.output)
        elif arguments.command == "adopt":
            adopt(
                arguments.current_file,
                arguments.repo,
                arguments.commit,
                arguments.git_path,
                arguments.snapshot_dir,
                arguments.artifact_id,
                arguments.output_manifest_fragment,
            )
        elif arguments.command == "check":
            check(
                arguments.manifest,
                arguments.report if not arguments.stdout else None,
                arguments.records_dir,
                arguments.no_records_dir,
            )
        else:
            adopt(
                arguments.current_file, arguments.repo, arguments.commit, arguments.git_path,
                arguments.snapshot_dir, arguments.artifact_id, arguments.output_manifest_fragment,
            )
    except ManifestError as error:
        sys.stderr.write(ERROR_PREFIX + str(error) + "\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
