# SPDX-FileCopyrightText: 2026 HLLMR Ventures LLC
# SPDX-License-Identifier: Apache-2.0
"""Install and smoke-test Writwall from an external release candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


REQUIRED_CANDIDATE_PATHS = (
    "pyproject.toml",
    "writwall_cli/__init__.py",
    "writwall_cli/__main__.py",
    "writwall_cli/coordinator.py",
    "scripts/start_writwall.py",
    "scripts/privacy_screen.py",
    "skills/writwall-adopt/SKILL.md",
)
REQUIRED_HANDOFF_PATHS = (
    "HANDOFF.md",
    "intake.json",
    "ARCHITECT.md",
    "GENERAL.md",
    "OPERATOR.md",
    "OWNER-AGENT.md",
    "REPOSITORY-OPERATOR.md",
    "REVIEWER.md",
    "NAME-CLEARANCE.md",
    "OWNER-RATIFICATION.md",
    "writwall-adopt/SKILL.md",
    "writwall-adopt/assets/bootstrap-charter-addendum.md",
    "writwall-adopt/assets/scripts/collect_name_clearance.py",
    "writwall-adopt/assets/checks/check_name_clearance.py",
    "writwall-adopt/references/name-clearance.md",
)
MAX_RELEASE_METADATA_BYTES = 1024 * 1024

# Kept byte-for-byte identical to scripts/start_writwall.py's
# authorization_continuity_block() field labels and B.3.4 outcome sentences.
# This installed-output gate proves the actual emitted contract, not a
# semantic authorization parser or a claim of independent provider proof.
AUTHORIZATION_CONTINUITY_LABELS = (
    "Approval source/reference:",
    "Approved action:",
    "Exact scope:",
    "Exclusions:",
    "Delegation permission:",
    "Lifecycle conditions:",
    "Completion boundary:",
)
AUTHORIZATION_CONTINUITY_OUTCOMES = (
    "performs the already-authorized action once the provider itself permits it",
    "says plainly that authorization is missing and stops",
    "treats a revoked or superseded record as no longer authorizing anything",
    "performs only the authorized part and names the excess as unauthorized",
    "reports the provider's own denial as the exact blocker",
    "names the exact missing or failed environment prerequisite as the blocker",
    "never creates or transmits a task, message, or dataset outside the approved action",
)

# WO-WW-029: kept byte-for-byte equivalent (after whitespace normalization) to
# scripts/start_writwall.py's `_operational_preflight_block()` content. This
# installed-output gate proves the actual emitted operational-preflight
# contract, never a semantic scheduler/writer/account parser or a claim of
# real host discovery.
OPERATIONAL_PREFLIGHT_REQUIREMENTS = (
    "This bounded inventory is guidance only; it never performs, simulates, or "
    "confirms real host, account, or scheduler discovery.",
    "An entry the preparer cannot verify stays `unknown`, distinct from a "
    "verified-absent entry",
    "Unresolved relevant inventory blocks the affected execution, not planning.",
    "Environment/account boundary. Observation time:",
    "Alternate writers/engines/schedulers with plausible access to the same "
    "target (name each one, or state `unknown` when inaccessible to inspect).",
    "Access limitations preventing a complete inventory.",
    "Approval scope: exactly what this operational task authorizes.",
    "Revalidate this inventory's evidence at the relevant execution "
    "transition; no single universal expiry period applies to every task.",
    "Rollback: exact restoration procedure.",
    "Last safe stop: the last point at which stopping leaves no partial, "
    "unrecoverable change.",
)


class ReleaseCheckError(RuntimeError):
    """A bounded, user-facing release-candidate failure."""


RATIFIED_ADOPTION_RECORD = """# Adoption record

## D.1 Date and Owner

2026-01-01 · Owner: Example Owner

## D.2 Pre-adoption baseline commit

`0000000000000000000000000000000000000000` — baseline commit. Adoption
became effective at this commit.

## D.3 Doctrine revision bound

Revision **0.8**, ratified **2026-01-01** by `decisions/DR-EXAMPLE.md`.

## D.4 Enforcement at adoption

Observed enforcement surfaces at adoption.

## D.5 Conformance gate during the pilot

Reviewer-only controlled inference.

## D.6 Recognized controlling sources at adoption

Disposed by the Owner.

## D.7 Pilot period

10 counted work orders.

## D.8 Reasoning: why adopt, and why now

Recorded by the Owner.

## D.9 Rejected alternatives

1. Alternative rejected.

## Signature

Example Owner — Owner — 2026-01-01
"""

DRAFT_ADOPTION_RECORD = """# Adoption record

## D.1 Date and Owner

DRAFT — Owner: TBD

## D.2 Pre-adoption baseline commit

Proposed baseline; not yet selected.

## D.3 Doctrine revision bound

Revision **0.8**, PROPOSED.

## D.4 Enforcement at adoption

Draft enforcement notes.

## D.5 Conformance gate during the pilot

Draft conformance notes.

## D.6 Recognized controlling sources at adoption

Draft mapping.

## D.7 Pilot period

Draft pilot period.

## D.8 Reasoning: why adopt, and why now

Draft reasoning.

## D.9 Rejected alternatives

Draft rejected alternatives.
"""

UNRELATED_RATIFIED_DECISION = """# DR-001: Naming decision

Ratified by the Owner on 2026-01-01. This record ratifies a project naming
choice; it is not an adoption record and contains no Appendix D sections.

## Signature

Example Owner — Owner — 2026-01-01
"""


def tree_digest(root: Path) -> str:
    from scripts.build_public_projection import complete_tree_ledger
    return complete_tree_ledger(root)


def run(command: list[str], *, cwd: Path, environment: dict[str, str],
        label: str, timeout: int = 180,
        closed_stdin: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL if closed_stdin else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode:
        detail = (result.stdout + result.stderr).strip()
        raise ReleaseCheckError(
            f"{label} failed with exit {result.returncode}"
            + (f": {detail}" if detail else "")
        )
    return result


def installed_command(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "writwall.exe"
    return venv / "bin" / "writwall"


def verify_installed_version(installed: str, expected: str) -> None:
    if installed != expected:
        raise ReleaseCheckError(
            f"installed version {installed!r} does not match candidate {expected!r}"
        )


def verify_expected_tag(candidate_version: str, expected_tag: str) -> None:
    if re.fullmatch(
        r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)",
        expected_tag,
    ) is None:
        raise ReleaseCheckError(
            "intended tag is not canonical vMAJOR.MINOR.PATCH"
        )
    if expected_tag.removeprefix("v") != candidate_version:
        raise ReleaseCheckError(
            f"candidate version {candidate_version!r} does not match intended "
            f"tag {expected_tag!r}"
        )


def verify_published_release_json(metadata_path: Path, expected_tag: str) -> None:
    """Verify saved GitHub release metadata without network access."""
    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ReleaseCheckError(
                    f"published-release metadata contains duplicate field {key!r}"
                )
            result[key] = value
        return result

    try:
        path_info = metadata_path.lstat()
        isjunction = getattr(os.path, "isjunction", None)
        if (
            metadata_path.is_symlink()
            or (isjunction is not None and isjunction(metadata_path))
            or not stat.S_ISREG(path_info.st_mode)
        ):
            raise ReleaseCheckError(
                "published-release metadata must be a non-link regular file"
            )
        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        descriptor = os.open(metadata_path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            opened_info = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened_info.st_mode):
                raise ReleaseCheckError(
                    "published-release metadata must be a non-link regular file"
                )
            raw_bytes = handle.read(MAX_RELEASE_METADATA_BYTES + 1)
        if len(raw_bytes) > MAX_RELEASE_METADATA_BYTES:
            raise ReleaseCheckError(
                "published-release metadata exceeds the 1 MiB size limit"
            )
        raw = raw_bytes.decode("utf-8")
        payload = json.loads(raw, object_pairs_hook=unique_object)
    except ReleaseCheckError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseCheckError(
            f"published-release metadata is malformed JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ReleaseCheckError("published-release metadata must be a JSON object")
    tag_name = payload.get("tag_name")
    if tag_name is None:
        raise ReleaseCheckError("published-release metadata lacks tag_name")
    if tag_name != expected_tag:
        raise ReleaseCheckError(
            f"published-release tag_name {tag_name!r} does not match "
            f"expected tag {expected_tag!r}"
        )
    if payload.get("immutable") is not True:
        value = payload.get("immutable")
        if value is False:
            raise ReleaseCheckError("published release is not immutable")
        raise ReleaseCheckError(
            "published-release immutable field must be the JSON literal true"
        )


def verify_candidate_unchanged(candidate: Path, before: str) -> None:
    if tree_digest(candidate) != before:
        raise ReleaseCheckError("candidate changed during the release check")


def python_bytecode_residue(root: Path) -> list[str]:
    """Return non-canonical interpreter residue from a generated handoff."""
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if (
            any(part.casefold() == "__pycache__" for part in path.relative_to(root).parts)
            or path.suffix.casefold() == ".pyc"
        )
    )


def profile_state_snapshot(path: Path) -> str | None:
    """A comparable snapshot of isolated profile state, or None if absent.

    Used only to prove a specific `--brief` invocation did not create or
    change isolated `WRITWALL_STATE_HOME` content; it is never a claim about
    the whole check's profile usage.
    """
    return tree_digest(path) if path.exists() else None


def verify_installed_brief_contract(stdout: str, surface: str) -> None:
    """Verify the shared installed `--brief` contract against real output.

    Checks the labeled compact-brief marker, that the evidence index heading
    exists and follows the brief marker, that the prose *before* that
    heading stays within its own 500-whitespace-word budget, that the
    required bytes-vs-tokens caveat appears in the evidence index, and that
    no full ordinary copy-paste prompt was emitted. This is a real installed-
    command output check, never a source-string substitute.
    """
    if "### Compact continuation brief" not in stdout:
        raise ReleaseCheckError(
            f"installed brief ({surface}) omitted the compact-brief marker"
        )
    index_heading = "## Evidence index (outside the prose word budget)"
    if index_heading not in stdout:
        raise ReleaseCheckError(
            f"installed brief ({surface}) omitted the evidence index heading"
        )
    brief_start = stdout.index("### Compact continuation brief")
    index_start = stdout.index(index_heading)
    if not brief_start < index_start:
        raise ReleaseCheckError(
            f"installed brief ({surface}) evidence index precedes the brief marker"
        )
    prose = stdout[brief_start:index_start]
    word_count = len(prose.split())
    if word_count > 500:
        raise ReleaseCheckError(
            f"installed brief ({surface}) prose exceeded the 500-word budget: "
            f"{word_count} words"
        )
    evidence_index = " ".join(stdout[index_start:].split())
    if "bytes do not measure tokens, context, or cost" not in evidence_index:
        raise ReleaseCheckError(
            f"installed brief ({surface}) evidence index omitted the "
            "bytes-vs-tokens caveat"
        )
    if "Copy this prompt into a fresh session" in stdout:
        raise ReleaseCheckError(
            f"installed brief ({surface}) emitted the full ordinary prompt"
        )


def verify_authorization_continuity_content(text: str, surface: str) -> None:
    """Require every B.3.3 field label and B.3.4 outcome sentence verbatim.

    A missing item names the surface and the exact missing text; this is a
    content presence check against the one shared generator, never a
    semantic parser and never proof of independent provider enforcement.
    """
    missing = [
        item
        for item in (*AUTHORIZATION_CONTINUITY_LABELS, *AUTHORIZATION_CONTINUITY_OUTCOMES)
        if item not in text
    ]
    if missing:
        raise ReleaseCheckError(
            f"authorization-continuity content missing in {surface}: "
            + "; ".join(missing)
        )


def verify_operational_preflight_content(text: str, surface: str) -> None:
    """Require the complete operational-preflight contract verbatim.

    A missing requirement names the surface and the exact missing text; this
    is a content-presence check against the one shared generator, never a
    semantic scheduler/writer/account parser and never proof of independent
    provider enforcement.
    """
    normalized = " ".join(text.split())
    missing = [
        requirement for requirement in OPERATIONAL_PREFLIGHT_REQUIREMENTS
        if " ".join(requirement.split()) not in normalized
    ]
    if missing:
        raise ReleaseCheckError(
            f"operational preflight content missing in {surface}: "
            + "; ".join(missing)
        )


def verify_operational_preflight_absent(text: str, surface: str) -> None:
    """Ordinary/unclassified local work must receive no operational
    questionnaire and no invented completeness -- never a fabricated
    inventory for a task that was never classified."""
    if "Operational task classification" in text or "## Operational preflight" in text:
        raise ReleaseCheckError(
            f"ordinary/unclassified {surface} unexpectedly carried an "
            "operational preflight questionnaire"
        )


def check_candidate(candidate: Path, expected_tag: str) -> None:
    candidate = candidate.resolve()
    if not candidate.is_dir():
        raise ReleaseCheckError("candidate contract failed: directory is absent")
    missing = [relative for relative in REQUIRED_CANDIDATE_PATHS
               if not (candidate / relative).is_file()]
    if missing:
        raise ReleaseCheckError(
            "candidate contract failed; missing: " + ", ".join(missing)
        )
    with (candidate / "pyproject.toml").open("rb") as handle:
        expected_version = tomllib.load(handle)["project"]["version"]
    verify_expected_tag(expected_version, expected_tag)

    before = tree_digest(candidate)
    with tempfile.TemporaryDirectory(prefix="writwall-release-check-") as raw:
        workspace = Path(raw).resolve()
        source = workspace / "source"
        shutil.copytree(candidate, source)
        wheelhouse = workspace / "wheelhouse"
        wheelhouse.mkdir()
        venv = workspace / "venv"
        project = workspace / "external-project"
        project.mkdir()
        state = workspace / "state"

        environment = os.environ.copy()
        environment.update({
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INDEX": "1",
            "WRITWALL_STATE_HOME": str(state),
        })
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        run(
            [
                sys.executable, "-m", "pip", "wheel", "--no-deps",
                "--no-build-isolation", "--wheel-dir", str(wheelhouse),
                str(source),
            ],
            cwd=workspace,
            environment=environment,
            label="wheel build",
        )
        wheels = sorted(wheelhouse.glob("writwall-*.whl"))
        if len(wheels) != 1:
            raise ReleaseCheckError(
                f"wheel build produced {len(wheels)} writwall wheels; expected one"
            )

        run(
            [sys.executable, "-m", "venv", "--without-pip", str(venv)],
            cwd=workspace,
            environment=environment,
            label="virtual environment creation",
        )
        command = installed_command(venv)
        python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run(
            [
                sys.executable, "-m", "pip", "--python", str(python),
                "install", "--no-deps", str(wheels[0]),
            ],
            cwd=workspace,
            environment=environment,
            label="wheel installation",
        )
        version = run(
            [
                str(python), "-c",
                "import importlib.metadata; print(importlib.metadata.version('writwall'))",
            ],
            cwd=workspace,
            environment=environment,
            label="installed version",
        ).stdout.strip()
        verify_installed_version(version, expected_version)
        help_result = run(
            [str(command), "start", "--help"],
            cwd=workspace,
            environment=environment,
            label="installed help",
        )
        if "Start with an idea" not in help_result.stdout:
            raise ReleaseCheckError("installed help omitted the coordinator promise")
        root_help = run(
            [str(command), "--help"],
            cwd=workspace,
            environment=environment,
            label="installed root help",
        )
        if "inspect" not in root_help.stdout:
            raise ReleaseCheckError("installed help omitted the inspect command")

        if (candidate / "PROJECTION-PROVENANCE.md").is_file():
            for verb in ("inspect", "start"):
                distribution = run(
                    [str(command), verb, "--project-root", str(candidate)],
                    cwd=workspace, environment=environment,
                    label=f"installed distribution {verb}", closed_stdin=True,
                )
                if ("Observed lifecycle state: public_distribution" not in distribution.stdout
                        or "target project" not in distribution.stdout
                        or "Fresh General" in distribution.stdout):
                    raise ReleaseCheckError("installed distribution routing inferred adoption")
            verify_candidate_unchanged(candidate, before)

        conversation_project = workspace / "conversation-first-project"
        conversation_project.mkdir()
        run(
            [
                str(command), "start",
                "--project-root", str(conversation_project),
            ],
            cwd=workspace,
            environment=environment,
            label="installed conversation-first run",
            closed_stdin=True,
        )
        conversation_output = conversation_project / ".writwall-bootstrap"
        conversation_handoff = conversation_output / "HANDOFF.md"
        conversation_architect = conversation_output / "ARCHITECT.md"
        if not conversation_handoff.is_file() or not conversation_architect.is_file():
            raise ReleaseCheckError(
                "complete handoff failed: installed conversation-first run omitted "
                "HANDOFF.md or ARCHITECT.md"
            )
        conversation_text = conversation_handoff.read_text(encoding="utf-8")
        required_conversation_text = (
            "Fresh Architect (conversation-first)",
            'Open with exactly: "Tell me what you are thinking."',
        )
        missing_conversation_text = [
            text for text in required_conversation_text
            if text not in conversation_text
        ]
        if missing_conversation_text:
            raise ReleaseCheckError(
                "installed conversation-first handoff omitted: "
                + ", ".join(missing_conversation_text)
            )
        conversation_residue = python_bytecode_residue(conversation_output)
        if conversation_residue:
            raise ReleaseCheckError(
                "conversation-first handoff contains Python bytecode residue: "
                + ", ".join(conversation_residue)
            )

        run(
            [
                str(command), "start", "--non-interactive",
                "--project-root", str(project),
                "--problem", "A small external project needs bounded agent work.",
                "--intended-user", "A first-time Writwall adopter.",
                "--why-matters", "The first handoff must be usable without prior context.",
                "--evidence", "Release readiness remains unproven outside source tests.",
                "--smallest-outcome", "A complete create-only adoption handoff.",
                "--success-signal", "Every promised packet is present and readable.",
                "--constraint", "No network or external-system mutation.",
                "--non-goal", "No project adoption or implementation.",
                "--risk", "Packaging may omit a required bootstrap asset.",
                "--kill-condition", "Stop if any required packet is absent.",
                "--asset", "The checked Writwall release candidate.",
                "--agent", "fresh Owner-Agent",
                "--location", "outside the walled project session",
                "--environment", "disposable local external project",
                "--owner-time", "no",
                "--confirm-no-secrets",
                "--external-operator", "Synthetic release-check function",
            ],
            cwd=workspace,
            environment=environment,
            label="installed coordinator run",
        )
        output = project / ".writwall-bootstrap"
        missing_handoff = [relative for relative in REQUIRED_HANDOFF_PATHS
                           if not (output / relative).is_file()]
        if missing_handoff:
            raise ReleaseCheckError(
                "complete handoff failed; missing: " + ", ".join(missing_handoff)
            )
        residue = python_bytecode_residue(output)
        if residue:
            raise ReleaseCheckError(
                "complete handoff contains Python bytecode residue: "
                + ", ".join(residue)
            )
        for relative in ("GENERAL.md", "OPERATOR.md", "REPOSITORY-OPERATOR.md"):
            verify_authorization_continuity_content(
                (output / relative).read_text(encoding="utf-8"),
                f"installed {relative}",
            )
        operator_packets = sorted((output / "operations").glob("*.md"))
        if not operator_packets:
            raise ReleaseCheckError(
                "installed coordinator run produced no external Operator packet "
                "for the requested synthetic function"
            )
        for packet_path in operator_packets:
            verify_authorization_continuity_content(
                packet_path.read_text(encoding="utf-8"),
                f"installed external Operator packet {packet_path.name}",
            )

        intake_payload = json.loads(
            (output / "intake.json").read_text(encoding="utf-8")
        )
        recorded_root = intake_payload.get("project_root")
        expected_root = project.resolve().as_posix()
        if recorded_root in (None, ".", ""):
            raise ReleaseCheckError(
                "installed coordinator recorded no canonical root evidence: "
                f"project_root={recorded_root!r}"
            )
        if recorded_root != expected_root:
            raise ReleaseCheckError(
                f"installed coordinator recorded canonical root {recorded_root!r}, "
                f"expected {expected_root!r}"
            )

        classified_project = workspace / "operational-preflight-classified-project"
        classified_project.mkdir()
        run(
            [
                str(command), "start", "--non-interactive",
                "--project-root", str(classified_project),
                "--project-name", "Operational preflight candidate",
                "--purpose", "Exercise the real installed operational preflight.",
                "--agent", "fresh Owner-Agent",
                "--location", "outside the walled project session",
                "--environment", "disposable local external project",
                "--owner-time", "no",
                "--confirm-no-secrets",
                "--external-operator", "Synthetic cutover function",
                "--external-operator-task", "Synthetic cutover function=cutover",
            ],
            cwd=workspace,
            environment=environment,
            label="installed classified operational-task run",
        )
        classified_output = classified_project / ".writwall-bootstrap"
        classified_packets = sorted((classified_output / "operations").glob("*.md"))
        if not classified_packets:
            raise ReleaseCheckError(
                "installed classified operational-task run produced no "
                "external Operator packet"
            )
        for packet_path in classified_packets:
            packet_text = packet_path.read_text(encoding="utf-8")
            if "Operational task classification: cutover" not in packet_text:
                raise ReleaseCheckError(
                    "installed classified operational-task packet "
                    f"{packet_path.name} omitted its classification label"
                )
            verify_operational_preflight_content(
                packet_text, f"installed operational packet {packet_path.name}"
            )
        classified_intake = json.loads(
            (classified_output / "intake.json").read_text(encoding="utf-8")
        )
        if classified_intake.get("external_operator_tasks") != {
            "Synthetic cutover function": "cutover"
        }:
            raise ReleaseCheckError(
                "installed classified operational-task intake.json recorded "
                f"external_operator_tasks={classified_intake.get('external_operator_tasks')!r}, "
                "expected {'Synthetic cutover function': 'cutover'}"
            )

        unclassified_project = workspace / "operational-preflight-unclassified-project"
        unclassified_project.mkdir()
        run(
            [
                str(command), "start", "--non-interactive",
                "--project-root", str(unclassified_project),
                "--project-name", "Ordinary local coding candidate",
                "--purpose", "Exercise ordinary local coding with no operational task.",
                "--agent", "fresh Owner-Agent",
                "--location", "outside the walled project session",
                "--environment", "disposable local external project",
                "--owner-time", "no",
                "--confirm-no-secrets",
                "--external-operator", "Local coding helper",
            ],
            cwd=workspace,
            environment=environment,
            label="installed ordinary/unclassified local-work control run",
        )
        unclassified_output = unclassified_project / ".writwall-bootstrap"
        unclassified_packets = sorted((unclassified_output / "operations").glob("*.md"))
        if not unclassified_packets:
            raise ReleaseCheckError(
                "installed ordinary/unclassified control run produced no "
                "external Operator packet"
            )
        for packet_path in unclassified_packets:
            verify_operational_preflight_absent(
                packet_path.read_text(encoding="utf-8"),
                f"installed operator packet {packet_path.name}",
            )
        unclassified_intake = json.loads(
            (unclassified_output / "intake.json").read_text(encoding="utf-8")
        )
        if unclassified_intake.get("external_operator_tasks") != {}:
            raise ReleaseCheckError(
                "installed ordinary/unclassified control run recorded a "
                "non-empty external_operator_tasks: "
                f"{unclassified_intake.get('external_operator_tasks')!r}"
            )

        adopted = workspace / "adopted-project"
        governance = adopted / "governance"
        decisions = governance / "decisions"
        decisions.mkdir(parents=True)
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (governance / name).write_text(
                f"# {name}\n", encoding="utf-8", newline="\n"
            )
        (decisions / "DR-001.md").write_text(
            RATIFIED_ADOPTION_RECORD, encoding="utf-8", newline="\n"
        )
        (adopted / "CLAUDE.md").write_text(
            "# Charter\n\nA.1 Prohibitions apply.\n", encoding="utf-8", newline="\n"
        )
        adopted_before = tree_digest(adopted)
        adopted_result = run(
            [str(command), "start", "--project-root", str(adopted)],
            cwd=workspace,
            environment=environment,
            label="installed adopted-lockout route",
        )
        required_route_text = (
            "Observed lifecycle state: adopted_lockout",
            "Act as a fresh General",
            "one combined disposition and action",
            "Do not ask for the same decision again",
        )
        route_output = " ".join(adopted_result.stdout.split())
        missing_route_text = [
            text for text in required_route_text
            if text not in route_output
        ]
        if missing_route_text:
            raise ReleaseCheckError(
                "installed adopted-lockout route omitted: "
                + ", ".join(missing_route_text)
            )
        verify_authorization_continuity_content(
            adopted_result.stdout, "installed adopted-lockout start output (General)"
        )
        if (adopted / ".writwall-bootstrap").exists():
            raise ReleaseCheckError(
                "installed adopted-lockout route published a bootstrap"
            )
        if tree_digest(adopted) != adopted_before:
            raise ReleaseCheckError(
                "installed adopted-lockout route changed target bytes"
            )
        inspect_result = run(
            [
                str(command), "inspect", "--project-root", str(adopted),
                "--role", "architect",
            ],
            cwd=workspace,
            environment=environment,
            label="installed inspect route",
        )
        inspect_output = " ".join(inspect_result.stdout.split())
        required_inspect_text = (
            "Observed lifecycle state: adopted_lockout",
            "Selected role: Fresh Architect",
            "Begin read-only",
            "grants no mutation or lifecycle authority",
        )
        missing_inspect_text = [
            text for text in required_inspect_text if text not in inspect_output
        ]
        if missing_inspect_text:
            raise ReleaseCheckError(
                "installed inspect route omitted: "
                + ", ".join(missing_inspect_text)
            )
        if tree_digest(adopted) != adopted_before:
            raise ReleaseCheckError(
                "installed inspect route changed target bytes"
            )
        inspect_general_result = run(
            [
                str(command), "inspect", "--project-root", str(adopted),
                "--role", "general",
            ],
            cwd=workspace,
            environment=environment,
            label="installed inspect general route",
        )
        verify_authorization_continuity_content(
            inspect_general_result.stdout, "installed inspect --role general output"
        )
        if tree_digest(adopted) != adopted_before:
            raise ReleaseCheckError(
                "installed inspect general route changed target bytes"
            )

        brief_new_project = workspace / "brief-new-project"
        brief_new_project.mkdir()
        brief_new_before = tree_digest(brief_new_project)
        brief_new_profile_before = profile_state_snapshot(state)
        brief_new_result = run(
            [
                str(command), "inspect", "--project-root", str(brief_new_project),
                "--role", "auto", "--brief",
            ],
            cwd=workspace, environment=environment,
            label="installed brief (clean/new)", closed_stdin=True,
        )
        verify_installed_brief_contract(brief_new_result.stdout, "clean/new")
        required_new_brief_text = (
            "Observed lifecycle state: clean_new",
            "Listen to the Owner's project pitch",
            "observation snapshot",
            "unknown until",
        )
        missing_new_brief_text = [
            text for text in required_new_brief_text
            if text not in brief_new_result.stdout
        ]
        if missing_new_brief_text:
            raise ReleaseCheckError(
                "installed brief (clean/new) omitted: "
                + ", ".join(missing_new_brief_text)
            )
        if (brief_new_project / ".writwall-bootstrap").exists():
            raise ReleaseCheckError(
                "installed brief (clean/new) created a bootstrap directory"
            )
        if tree_digest(brief_new_project) != brief_new_before:
            raise ReleaseCheckError(
                "installed brief (clean/new) changed target bytes"
            )
        if profile_state_snapshot(state) != brief_new_profile_before:
            raise ReleaseCheckError(
                "installed brief (clean/new) mutated isolated profile state"
            )

        adopted_brief_profile_before = profile_state_snapshot(state)
        adopted_brief_result = run(
            [
                str(command), "inspect", "--project-root", str(adopted),
                "--role", "auto", "--brief",
            ],
            cwd=workspace, environment=environment,
            label="installed brief (adopted lockout)", closed_stdin=True,
        )
        verify_installed_brief_contract(adopted_brief_result.stdout, "adopted lockout")
        required_adopted_brief_text = (
            "Observed lifecycle state: adopted_lockout",
            "Selected role: Fresh General",
            "Prepare, but do not activate",
            "observation snapshot",
            "CLAUDE.md",
            "governance/decisions/DR-001.md",
        )
        missing_adopted_brief_text = [
            text for text in required_adopted_brief_text
            if text not in adopted_brief_result.stdout
        ]
        if missing_adopted_brief_text:
            raise ReleaseCheckError(
                "installed brief (adopted lockout) omitted: "
                + ", ".join(missing_adopted_brief_text)
            )
        if tree_digest(adopted) != adopted_before:
            raise ReleaseCheckError(
                "installed brief (adopted lockout) changed target bytes"
            )
        if profile_state_snapshot(state) != adopted_brief_profile_before:
            raise ReleaseCheckError(
                "installed brief (adopted lockout) mutated isolated profile state"
            )

        retired = workspace / "retired-project"
        retired_governance = retired / "governance"
        retired_decisions = retired_governance / "decisions"
        retired_decisions.mkdir(parents=True)
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (retired_governance / name).write_text(
                f"# {name}\n", encoding="utf-8", newline="\n"
            )
        (retired_decisions / "DR-001.md").write_text(
            RATIFIED_ADOPTION_RECORD, encoding="utf-8", newline="\n"
        )
        (retired_governance / "history").mkdir()
        (retired_governance / "history" / "WO-001.md").write_text(
            "---\nid: WO-001\nstatus: CLOSED\n---\n", encoding="utf-8", newline="\n"
        )
        retired_before = tree_digest(retired)
        retired_result = run(
            [str(command), "start", "--project-root", str(retired)],
            cwd=workspace,
            environment=environment,
            label="installed retired-lockout route",
        )
        if "Observed lifecycle state: retired_lockout" not in retired_result.stdout:
            raise ReleaseCheckError(
                "installed retired-lockout route omitted the expected lifecycle state"
            )
        if tree_digest(retired) != retired_before:
            raise ReleaseCheckError(
                "installed retired-lockout route changed target bytes"
            )

        active_project = workspace / "active-work-order-project"
        active_governance = active_project / "governance"
        active_governance.mkdir(parents=True)
        (active_project / "CLAUDE.md").write_text(
            "# Charter\n\nA.1 Prohibitions apply.\n", encoding="utf-8", newline="\n"
        )
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (active_governance / name).write_text(
                f"# {name}\n", encoding="utf-8", newline="\n"
            )
        active_docs = active_project / "docs"
        active_docs.mkdir()
        (active_docs / "example-requirement.md").write_text(
            "# Example current requirement\n\nSafely referenced.\n",
            encoding="utf-8", newline="\n",
        )
        active_work_orders = active_governance / "work-orders"
        active_work_orders.mkdir()
        (active_work_orders / "WO-001.md").write_text(
            "---\nid: WO-001\nstatus: ACTIVE\n---\n"
            "# WO-001: Example\n\n"
            "## Objective\n\n"
            "Do the bounded thing.\n\n"
            "Routing: see docs/example-requirement.md, docs/missing-current.md "
            "and docs/pinned.md@sha256:" + ("de" * 32) + ".\n",
            encoding="utf-8", newline="\n",
        )
        active_pointer = active_project / ".claude" / "active-wo.txt"
        active_pointer.parent.mkdir(parents=True)
        active_pointer.write_text(
            "governance/work-orders/WO-001.md\n", encoding="utf-8", newline="\n"
        )
        active_before = tree_digest(active_project)
        active_brief_profile_before = profile_state_snapshot(state)
        active_brief_result = run(
            [
                str(command), "inspect", "--project-root", str(active_project),
                "--role", "auto", "--brief",
            ],
            cwd=workspace, environment=environment,
            label="installed brief (active work order)", closed_stdin=True,
        )
        verify_installed_brief_contract(
            active_brief_result.stdout, "active work order"
        )
        required_active_brief_text = (
            "Observed lifecycle state: active_work_order",
            "docs/example-requirement.md",
            "docs/missing-current.md",
            "remains pending",
            "does not authorize execution",
            "observation snapshot",
        )
        missing_active_brief_text = [
            text for text in required_active_brief_text
            if text not in active_brief_result.stdout
        ]
        if missing_active_brief_text:
            raise ReleaseCheckError(
                "installed brief (active work order) omitted: "
                + ", ".join(missing_active_brief_text)
            )
        if "The only permitted next role is the bounded Operator" in active_brief_result.stdout:
            raise ReleaseCheckError(
                "installed brief (active work order) claimed confident execution "
                "readiness despite unresolved routing material"
            )
        if tree_digest(active_project) != active_before:
            raise ReleaseCheckError(
                "installed brief (active work order) changed target bytes"
            )
        if profile_state_snapshot(state) != active_brief_profile_before:
            raise ReleaseCheckError(
                "installed brief (active work order) mutated isolated profile state"
            )

        draft = workspace / "draft-unratified-project"
        draft_governance = draft / "governance"
        draft_decisions = draft_governance / "decisions"
        draft_decisions.mkdir(parents=True)
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (draft_governance / name).write_text(
                f"# {name}\n", encoding="utf-8", newline="\n"
            )
        (draft_decisions / "DR-001.md").write_text(
            DRAFT_ADOPTION_RECORD, encoding="utf-8", newline="\n"
        )
        (draft_decisions / "DR-999-unrelated.md").write_text(
            UNRELATED_RATIFIED_DECISION, encoding="utf-8", newline="\n"
        )
        (draft_governance / "history").mkdir()
        (draft_governance / "history" / "WO-001.md").write_text(
            "---\nid: WO-001\nstatus: CLOSED\n---\n", encoding="utf-8", newline="\n"
        )
        draft_before = tree_digest(draft)
        draft_result = run(
            [str(command), "start", "--project-root", str(draft)],
            cwd=workspace,
            environment=environment,
            label="installed draft-adoption-record regression route",
        )
        if "Observed lifecycle state: adopted_lockout" in draft_result.stdout:
            raise ReleaseCheckError(
                "installed draft-adoption-record regression reported adopted_lockout"
            )
        if "Observed lifecycle state: retired_lockout" in draft_result.stdout:
            raise ReleaseCheckError(
                "installed draft-adoption-record regression reported retired_lockout"
            )
        if tree_digest(draft) != draft_before:
            raise ReleaseCheckError(
                "installed draft-adoption-record regression changed target bytes"
            )

        unrelated = workspace / "unrelated-signed-decision-project"
        unrelated_governance = unrelated / "governance"
        unrelated_decisions = unrelated_governance / "decisions"
        unrelated_decisions.mkdir(parents=True)
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (unrelated_governance / name).write_text(
                f"# {name}\n", encoding="utf-8", newline="\n"
            )
        (unrelated_decisions / "DR-001.md").write_text(
            UNRELATED_RATIFIED_DECISION, encoding="utf-8", newline="\n"
        )
        unrelated_before = tree_digest(unrelated)
        unrelated_result = subprocess.run(
            [str(command), "start", "--project-root", str(unrelated)],
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if unrelated_result.returncode == 0:
            raise ReleaseCheckError(
                "installed coordinator did not fail closed for a signed but "
                "unrelated document at the exact adoption-record path"
            )
        unrelated_output = unrelated_result.stdout + unrelated_result.stderr
        if "adopted_lockout" in unrelated_output or "retired_lockout" in unrelated_output:
            raise ReleaseCheckError(
                "installed coordinator reported a lockout state for a signed "
                "but unrelated document at the exact adoption-record path"
            )
        if tree_digest(unrelated) != unrelated_before:
            raise ReleaseCheckError(
                "installed unrelated-signed-decision regression changed target bytes"
            )

        worktree_root = workspace / "worktree-project"
        worktree_root.mkdir()
        (worktree_root / ".git").mkdir()
        nested = worktree_root / "nested" / "workspace"
        nested.mkdir(parents=True)
        worktree_before = tree_digest(worktree_root)
        worktree_result = subprocess.run(
            [str(command), "start", "--project-root", str(nested)],
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if worktree_result.returncode == 0:
            raise ReleaseCheckError(
                "installed coordinator did not stop for a directory nested "
                "inside a Git worktree"
            )
        worktree_output = worktree_result.stdout + worktree_result.stderr
        if "worktree" not in worktree_output.lower():
            raise ReleaseCheckError(
                "installed coordinator's nested-worktree stop omitted a "
                "worktree diagnostic"
            )
        if (nested / ".writwall-bootstrap").exists():
            raise ReleaseCheckError(
                "installed coordinator's nested-worktree stop published a bootstrap"
            )
        if tree_digest(worktree_root) != worktree_before:
            raise ReleaseCheckError(
                "installed coordinator's nested-worktree stop changed target bytes"
            )

    verify_candidate_unchanged(candidate, before)

    print("OK: coordinator release candidate passed")
    print(f"  installed version : {expected_version}")
    print("  installed command : help and real start passed under normal bytecode behavior")
    print("  conversation-first: bare installed start produced the Architect handoff")
    print("  complete handoff  : all required packets present; no bytecode residue")
    print("  canonical root    : installed coordinator recorded the resolved project root")
    print("  adopted lockout   : fresh General route; zero target-byte change")
    print("  read-only inspect : installed Architect re-entry; zero target-byte change")
    print("  retired lockout   : ratified adoption plus closed history; zero target-byte change")
    print("  draft regression  : draft adoption record never reports adopted/retired lockout")
    print("  unrelated regression: signed unrelated document at the exact adoption-record")
    print("                      path fails closed; zero target-byte change")
    print("  nested worktree   : installed coordinator stops with a worktree diagnostic")
    print("  candidate unchanged: complete-tree digest preserved")
    print("  installed brief   : new/adopted/active --brief produced labeled sections, "
          "a <=500-word prose budget, an evidence index with byte sizes and explicit "
          "unknowns, correct lifecycle guidance, no full ordinary prompt, and zero "
          "target/profile mutation")
    print("  authorization contract: GENERAL/OPERATOR/REPOSITORY-OPERATOR, the "
          "external Operator packet, and General inspect output all carry the "
          "required authorization-continuity labels and outcome sentences")
    print("  operational preflight: an explicit --external-operator-task "
          "classification reaches the installed packet and intake.json with "
          "the complete bounded-inventory contract; an ordinary/unclassified "
          "local-work control receives no questionnaire and no invented "
          "completeness")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description=(
            "Build, install, and smoke-test Writwall from an external public "
            "release candidate without modifying candidate bytes."
        )
    )
    value.add_argument("candidate", type=Path)
    value.add_argument(
        "--expected-tag",
        required=True,
        help="canonical release tag that must match candidate package metadata",
    )
    value.add_argument(
        "--published-release-json",
        type=Path,
        help=(
            "optional saved GitHub release JSON; verifies matching tag_name and "
            "literal immutable:true without network access"
        ),
    )
    return value


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.published_release_json is not None:
            verify_published_release_json(
                arguments.published_release_json, arguments.expected_tag
            )
        check_candidate(arguments.candidate, arguments.expected_tag)
    except (OSError, ReleaseCheckError, subprocess.SubprocessError) as exc:
        print(f"FAIL: coordinator release candidate: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
