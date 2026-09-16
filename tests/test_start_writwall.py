# SPDX-FileCopyrightText: 2026 HLLMR Ventures LLC
# SPDX-License-Identifier: Apache-2.0
"""Public-interface tests for the day-zero Writwall coordinator."""

from __future__ import annotations

import json
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts import start_writwall as starter_module


REPO_ROOT = Path(__file__).resolve().parents[1]
STARTER = REPO_ROOT / "scripts" / "start_writwall.py"


def ratified_adoption_record(
    *, owner: str = "Test Owner", date: str = "2026-01-01",
    revision: str = "0.8", revision_date: str = "2026-08-21",
    revision_record: str = "decisions/DR-005.md",
    baseline: str = "0" * 40,
    title: str = "# Adoption record",
) -> str:
    """A complete, well-formed, signed Appendix D record.

    This is the deterministic ratified shape: an adoption title, all of
    D.1-D.9, a concrete D.2 baseline commit with adoption-effective
    language, a D.3 revision, and a dated Owner Signature. It matches the
    established shape of this repository's own `governance/decisions/DR-001.md`.
    """
    return f"""{title}

## D.1 Date and Owner

{date} · Owner: {owner}

## D.2 Pre-adoption baseline commit

`{baseline}` — baseline commit. Adoption became effective at this commit.

## D.3 Doctrine revision bound

Revision **{revision}**, ratified **{revision_date}** by `{revision_record}`.

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

{owner} — Owner — {date}
"""


def draft_adoption_record() -> str:
    """Complete Appendix D section shape, but explicitly unsigned/proposed."""
    return """# Adoption record

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


def unrelated_ratified_decision() -> str:
    """A signed, ratified decision that is not an Appendix D adoption record.

    Used both at an unrelated path (to prove it cannot lend adoption
    authority to a draft record elsewhere) and at the exact adoption-record
    path itself (to prove a filename alone, even carrying a real Signature,
    is never adoption authority).
    """
    return """# DR-001: Naming decision

Ratified by the Owner on 2026-01-01. This record ratifies a project naming
choice; it is not an adoption record and contains no Appendix D sections.

## Signature

Test Owner — Owner — 2026-01-01
"""


class StartWritwallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.temp, True)
        self.project = self.temp / "project"
        self.project.mkdir()
        self.state = self.temp / "state"

    def environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment["WRITWALL_STATE_HOME"] = str(self.state)
        return environment

    def run_start(self, *extra: str, project: Path | None = None):
        return subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "writwall_cli",
                "start",
                "--non-interactive",
                "--project-root",
                str(project or self.project),
                "--project-name",
                "Example project",
                "--purpose",
                "Build a small, governed project.",
                "--agent",
                "Claude Code in VS Code",
                "--location",
                "local workstation",
                "--environment",
                "local repository with separately administered hosting",
                "--owner-time",
                "no",
                "--confirm-no-secrets",
                *extra,
            ],
            cwd=REPO_ROOT,
            env=self.environment(),
            capture_output=True,
            text=True,
            timeout=60,
        )

    def run_idea_start(self, *extra: str, project: Path | None = None):
        return subprocess.run(
            [
                sys.executable, "-B", "-m", "writwall_cli", "start",
                "--non-interactive",
                "--project-root", str(project or self.project),
                "--problem", "Small teams lose decisions between idea and implementation.",
                "--intended-user", "A technical founder working with agents.",
                "--why-matters", "Early ambiguity causes expensive rework.",
                "--evidence", "Two abandoned prototypes; demand remains an assumption.",
                "--smallest-outcome", "A ratifiable discovery packet.",
                "--success-signal", "The Owner can approve or stop without reconstruction.",
                "--constraint", "Local-only and standard library.",
                "--non-goal", "No production deployment.",
                "--risk", "The workflow may be too heavy for small ideas.",
                "--kill-condition", "Stop if qualification cannot name a useful outcome.",
                "--asset", "An existing written brief.",
                "--agent", "Codex",
                "--location", "local workstation",
                "--environment", "local repository only",
                "--owner-time", "no",
                "--confirm-no-secrets",
                *extra,
            ],
            cwd=REPO_ROOT,
            env=self.environment(),
            capture_output=True,
            text=True,
            timeout=60,
        )

    def run_lifecycle_start(self, project: Path | None = None, *extra: str):
        return subprocess.run(
            [
                sys.executable, "-B", "-m", "writwall_cli", "start",
                "--project-root", str(project or self.project),
                *extra,
            ],
            cwd=REPO_ROOT,
            env=self.environment(),
            capture_output=True,
            text=True,
            timeout=60,
        )

    def run_inspect(self, role: str = "auto", project: Path | None = None,
                     brief: bool = False):
        return subprocess.run(
            [
                sys.executable, "-B", "-m", "writwall_cli", "inspect",
                "--project-root", str(project or self.project),
                "--role", role,
                *(("--brief",) if brief else ()),
            ],
            cwd=REPO_ROOT,
            env=self.environment(),
            capture_output=True,
            text=True,
            timeout=60,
        )

    @staticmethod
    def tree_snapshot(root: Path) -> dict[str, bytes | None]:
        return {
            path.relative_to(root).as_posix(): (
                path.read_bytes() if path.is_file() else None
            )
            for path in sorted(root.rglob("*"))
        }

    @property
    def output(self) -> Path:
        return self.project / ".writwall-bootstrap"

    def intake(self) -> dict:
        return json.loads((self.output / "intake.json").read_text(encoding="utf-8"))

    def handoff(self) -> str:
        return (self.output / "HANDOFF.md").read_text(encoding="utf-8")

    def assert_contains_canonical_root(self, text: str, root: Path, label: str) -> None:
        """Accept either native or portable rendering of one resolved root."""
        native = str(root)
        posix = root.as_posix()
        self.assertTrue(
            native in text or posix in text,
            f"{label} does not carry the canonical project root {root!s}",
        )

    def git(self, *args: str, cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30,
        )

    def make_git_worktree(self, repo_name: str, worktree_name: str,
                          branch: str) -> Path:
        """Build a minimal seeded repository plus one linked worktree.

        Skips the calling test outright when a local git executable is
        unavailable; otherwise returns the worktree top-level path.
        """
        repo = self.temp / repo_name
        repo.mkdir()
        init = self.git("init", "--quiet", cwd=repo)
        if init.returncode != 0:
            self.skipTest(f"git unavailable: {init.stderr}")
        self.git("config", "user.email", "test@example.invalid", cwd=repo)
        self.git("config", "user.name", "Test", cwd=repo)
        (repo / "README.md").write_text("seed\n", encoding="utf-8")
        self.git("add", "README.md", cwd=repo)
        commit = self.git("commit", "--quiet", "-m", "seed", cwd=repo)
        self.assertEqual(commit.returncode, 0, commit.stdout + commit.stderr)
        worktree = self.temp / worktree_name
        add = self.git(
            "worktree", "add", "--quiet", str(worktree), "-b", branch, cwd=repo,
        )
        self.assertEqual(add.returncode, 0, add.stdout + add.stderr)
        return worktree

    def install_writwall(self) -> Path:
        build_source = self.temp / "build-source"
        shutil.copytree(
            REPO_ROOT,
            build_source,
            ignore=shutil.ignore_patterns(
                ".git", "dist", "archive", "governance", "tests",
                "__pycache__", "*.egg-info",
            ),
        )
        wheelhouse = self.temp / "wheelhouse"
        wheelhouse.mkdir()
        build = subprocess.run(
            [
                sys.executable, "-m", "pip", "wheel", "--no-deps",
                "--no-build-isolation", "--wheel-dir", str(wheelhouse),
                str(build_source),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        wheels = list(wheelhouse.glob("writwall-*.whl"))
        self.assertEqual(len(wheels), 1, build.stdout + build.stderr)

        venv = self.temp / "venv"
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(venv)],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        python = venv / ("Scripts/python.exe" if sys.platform == "win32"
                         else "bin/python")
        install = subprocess.run(
            [
                sys.executable, "-m", "pip", "--python", str(python),
                "install", "--no-deps", str(wheels[0]),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(install.returncode, 0, install.stdout + install.stderr)
        return venv / ("Scripts/writwall.exe" if sys.platform == "win32"
                       else "bin/writwall")

    def test_isolated_install_exposes_writwall_start(self):
        command = self.install_writwall()
        result = subprocess.run(
            [str(command), "start", "--help"],
            env=self.environment(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Start with an idea", result.stdout)

    def test_isolated_install_runs_the_real_coordinator(self):
        command = self.install_writwall()
        result = subprocess.run(
            [
                str(command), "start", "--non-interactive",
                "--project-root", str(self.project),
                "--project-name", "Example project",
                "--purpose", "Build a small, governed project.",
                "--agent", "Codex",
                "--location", "local workstation",
                "--environment", "local repository only",
                "--owner-time", "no",
                "--confirm-no-secrets",
            ],
            env=self.environment(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.output / "HANDOFF.md").is_file())
        self.assertTrue((self.output / "writwall-adopt" / "SKILL.md").is_file())
        for relative in (
            "assets/scripts/collect_name_clearance.py",
            "assets/checks/check_name_clearance.py",
            "references/name-clearance.md",
        ):
            self.assertTrue((self.output / "writwall-adopt" / relative).is_file(), relative)

    def test_isolated_install_emits_no_bytecode_residue_under_normal_environment(self):
        command = self.install_writwall()
        environment = self.environment()
        environment.pop("PYTHONDONTWRITEBYTECODE", None)
        result = subprocess.run(
            [
                str(command), "start", "--non-interactive",
                "--project-root", str(self.project),
                "--project-name", "Example project",
                "--purpose", "Build a small, governed project.",
                "--agent", "Codex",
                "--location", "local workstation",
                "--environment", "local repository only",
                "--owner-time", "no",
                "--confirm-no-secrets",
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        cache_dirs = sorted(
            path.relative_to(self.output).as_posix()
            for path in self.output.rglob("__pycache__") if path.is_dir()
        )
        bytecode_files = sorted(
            path.relative_to(self.output).as_posix()
            for path in self.output.rglob("*.pyc") if path.is_file()
        )
        self.assertEqual(cache_dirs, [])
        self.assertEqual(bytecode_files, [])

    def test_unnamed_idea_emits_complete_unratified_architect_packet_set(self):
        result = self.run_idea_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        discovery = json.loads(
            (self.output / "discovery.json").read_text(encoding="utf-8")
        )
        self.assertEqual(discovery["identity"]["state"], "unnamed")
        self.assertEqual(discovery["authority"], "unratified_discovery_only")
        for field in (
            "problem_or_opportunity", "intended_user", "why_outcome_matters",
            "evidence_and_assumptions", "smallest_useful_outcome", "success_signal",
            "constraints", "non_goals", "material_risks", "stop_kill_conditions",
            "existing_assets", "repository_runtime_deployment_environment",
            "preferred_agent_interface", "external_systems_and_operators",
            "owner_time_capture",
        ):
            self.assertIn(field, discovery["qualification"])
        for relative in (
            "OWNER-AGENT.md", "REPOSITORY-OPERATOR.md", "REVIEWER.md",
            "NAME-CLEARANCE.md", "OWNER-RATIFICATION.md",
        ):
            text = (self.output / relative).read_text(encoding="utf-8")
            self.assertIn("unratified", text.lower(), relative)

    def test_observed_boundaries_select_different_smallest_credible_topologies(self):
        local = self.run_idea_start()
        self.assertEqual(local.returncode, 0, local.stdout + local.stderr)
        local_discovery = json.loads(
            (self.output / "discovery.json").read_text(encoding="utf-8")
        )
        self.assertEqual(local_discovery["topology"]["tier"], "local_only")
        self.assertIn("Architect", local_discovery["topology"]["roles"])
        self.assertIn("General", local_discovery["topology"]["roles"])
        self.assertIn("repository Operator", local_discovery["topology"]["roles"])
        self.assertNotIn(
            "Owner-Agent architect/coordinator",
            local_discovery["topology"]["roles"],
        )

        high_impact_project = self.temp / "high-impact-project"
        high_impact_project.mkdir()
        high_impact = self.run_idea_start(
            "--scenario", "dns-mail-migration", project=high_impact_project
        )
        self.assertEqual(
            high_impact.returncode, 0, high_impact.stdout + high_impact.stderr
        )
        high_output = high_impact_project / ".writwall-bootstrap"
        high_discovery = json.loads(
            (high_output / "discovery.json").read_text(encoding="utf-8")
        )
        self.assertEqual(high_discovery["topology"]["tier"], "high_impact")
        self.assertNotEqual(local_discovery["topology"], high_discovery["topology"])
        packets = {path.name for path in (high_output / "operations").glob("*.md")}
        self.assertTrue({
            "dns-inventory-and-cutover.md",
            "mail-routing-cutover.md",
            "mailbox-data-migration.md",
        }.issubset(packets))

    def test_operation_packet_names_operational_task_elicits_bounded_inventory(self):
        """RED: explicit operational-task classification bounds a preflight.

        Ordinary local coding (no `operational_task`) gets no operational
        questionnaire and stays byte-identical to today's packet. An explicit
        classification (deployment/migration/source_freeze/cutover) adds a
        bounded inventory naming alternate writers/engines/schedulers,
        observation time, access unknowns, transition revalidation, rollback,
        and the last safe stop -- guidance only, never real host discovery.
        """
        ordinary = starter_module.operation_packet("Local coding task", "/example/root")
        self.assertNotIn("Operational task classification", ordinary)
        self.assertNotIn("Alternate writers", ordinary)

        for task in ("deployment", "migration", "source_freeze", "cutover"):
            with self.subTest(operational_task=task):
                packet = starter_module.operation_packet(
                    "Example operational step", "/example/root",
                    operational_task=task,
                )
                self.assertIn(f"Operational task classification: {task}", packet)
                self.assertIn("Alternate writers/engines/schedulers", packet)
                self.assertIn("unknown", packet.lower())
                self.assertIn("Observation time", packet)
                self.assertIn("Revalidate", packet)
                self.assertIn("Last safe stop", packet)

    def test_external_operator_task_classification_reaches_packet_and_intake(self):
        """RED (next slice, not yet implemented): explicit, opt-in, per-Operator
        operational classification -- never inferred from the function's own
        free-text name -- must reach the generated Operator packet file and
        intake.json unchanged for ordinary/unclassified functions.
        """
        result = self.run_idea_start(
            "--external-operator", "DNS cutover",
            "--external-operator-task", "DNS cutover=cutover",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        packet = (self.output / "operations" / "dns-cutover.md").read_text(encoding="utf-8")
        self.assertIn("Operational task classification: cutover", packet)
        intake = self.intake()
        self.assertEqual(intake["external_operator_tasks"], {"DNS cutover": "cutover"})

    # WO-WW-029 post-implementation coverage (already-implemented behavior;
    # not new RED claims): adversarial and backward-compatibility coverage
    # of the --external-operator-task CLI contract across every intake path.

    def test_external_operator_task_rejects_malformed_unmatched_invalid_duplicate_before_output(self):
        cases = {
            "malformed": (
                ("--external-operator", "DNS cutover",
                 "--external-operator-task", "not-a-pair"),
                "malformed --external-operator-task",
            ),
            "unmatched name": (
                ("--external-operator", "DNS cutover",
                 "--external-operator-task", "Wrong function=cutover"),
                "unmatched external Operator function",
            ),
            "invalid classification": (
                ("--external-operator", "DNS cutover",
                 "--external-operator-task", "DNS cutover=not-a-real-classification"),
                "unsupported operational task classification",
            ),
            "duplicate name": (
                ("--external-operator", "DNS cutover",
                 "--external-operator-task", "DNS cutover=cutover",
                 "--external-operator-task", "DNS cutover=migration"),
                "duplicate --external-operator-task classification",
            ),
        }
        for label, (extra, expected_diagnostic) in cases.items():
            with self.subTest(case=label):
                project = self.temp / f"reject-{label.replace(' ', '-')}"
                project.mkdir()
                result = self.run_idea_start(*extra, project=project)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(expected_diagnostic, result.stderr)
                self.assertFalse((project / starter_module.OUTPUT_NAME).exists())

    def test_ordinary_local_coding_receives_no_operational_questionnaire(self):
        result = self.run_idea_start("--external-operator", "Local coding helper")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        packets = list((self.output / "operations").glob("*.md"))
        self.assertTrue(packets)
        for packet_path in packets:
            text = packet_path.read_text(encoding="utf-8")
            self.assertNotIn("Operational task classification", text)
            self.assertNotIn("## Operational preflight", text)
        self.assertEqual(self.intake()["external_operator_tasks"], {})

    def test_legacy_free_text_operator_names_are_never_inferred_as_classified(self):
        result = self.run_idea_start(
            "--external-operator",
            "Cutover step for production deployment and migration",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        packets = list((self.output / "operations").glob("*.md"))
        self.assertTrue(packets)
        for packet_path in packets:
            text = packet_path.read_text(encoding="utf-8")
            self.assertNotIn("Operational task classification", text)
            self.assertNotIn("## Operational preflight", text)
        self.assertEqual(self.intake()["external_operator_tasks"], {})

    def test_all_four_operational_task_classifications_reach_packet_and_intake(self):
        for task in ("deployment", "migration", "source_freeze", "cutover"):
            with self.subTest(operational_task=task):
                project = self.temp / f"classified-{task}"
                project.mkdir()
                result = self.run_idea_start(
                    "--external-operator", "Example operator",
                    "--external-operator-task", f"Example operator={task}",
                    project=project,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                output = project / starter_module.OUTPUT_NAME
                packets = list((output / "operations").glob("*.md"))
                self.assertTrue(packets)
                for packet_path in packets:
                    text = packet_path.read_text(encoding="utf-8")
                    self.assertIn(f"Operational task classification: {task}", text)
                intake = json.loads(
                    (output / "intake.json").read_text(encoding="utf-8")
                )
                self.assertEqual(
                    intake["external_operator_tasks"], {"Example operator": task}
                )

    def test_operational_task_classification_reaches_structured_and_conversation_first_paths(self):
        structured_project = self.temp / "structured-classified"
        structured_project.mkdir()
        structured_result = self.run_start(
            "--structured-intake",
            "--external-operator", "Example operator",
            "--external-operator-task", "Example operator=migration",
            project=structured_project,
        )
        self.assertEqual(
            structured_result.returncode, 0,
            structured_result.stdout + structured_result.stderr,
        )
        structured_output = structured_project / starter_module.OUTPUT_NAME
        structured_packets = list((structured_output / "operations").glob("*.md"))
        self.assertTrue(structured_packets)
        for packet_path in structured_packets:
            self.assertIn(
                "Operational task classification: migration",
                packet_path.read_text(encoding="utf-8"),
            )

        conversation_project = self.temp / "conversation-first-classified"
        conversation_project.mkdir()
        conversation_result = self.run_lifecycle_start(
            conversation_project,
            "--external-operator", "Example operator",
            "--external-operator-task", "Example operator=migration",
        )
        self.assertEqual(
            conversation_result.returncode, 0,
            conversation_result.stdout + conversation_result.stderr,
        )
        conversation_output = conversation_project / starter_module.OUTPUT_NAME
        conversation_packets = list((conversation_output / "operations").glob("*.md"))
        self.assertTrue(conversation_packets)
        for packet_path in conversation_packets:
            self.assertIn(
                "Operational task classification: migration",
                packet_path.read_text(encoding="utf-8"),
            )

    def test_high_impact_environment_selects_high_impact_without_named_operator(self):
        result = self.run_idea_start(
            "--environment", "Production DNS and mail migration."
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        discovery = json.loads(
            (self.output / "discovery.json").read_text(encoding="utf-8")
        )
        self.assertEqual(discovery["topology"]["tier"], "high_impact")
        self.assertIn("DNS", discovery["topology"]["reason"])

    def test_supplied_name_remains_working_candidate_until_evidenced_owner_disposition(self):
        result = self.run_idea_start("--project-name", "Northstar")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        discovery = json.loads(
            (self.output / "discovery.json").read_text(encoding="utf-8")
        )
        self.assertEqual(discovery["identity"], {
            "state": "working_candidate",
            "working_candidate": "Northstar",
            "canonical_name": None,
        })
        packet = (self.output / "NAME-CLEARANCE.md").read_text(encoding="utf-8")
        for source in (
            "github", "pypi", "npm", "crates_io", "com_rdap",
            "web_common_law", "uspto",
        ):
            self.assertIn(f"`{source}`", packet)
        self.assertIn("collect_name_clearance.py", packet)
        self.assertIn("check_name_clearance.py", packet)
        self.assertIn("named-human", packet)
        self.assertIn("explicit later Owner disposition", packet)
        self.assertIn("before the first public repository slug", packet)

    def test_clean_project_creates_bundle_and_exact_handoff(self):
        result = self.run_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.intake()["observed_state"], "clean_new")
        self.assertTrue((self.output / "writwall-adopt" / "SKILL.md").is_file())
        handoff = self.handoff()
        flat = " ".join(handoff.split())
        self.assertIn("Act as a fresh Writwall Architect", handoff)
        self.assertIn("explicitly promotes", handoff)
        self.assertIn("does not install or adopt Writwall", flat)
        self.assertIn("Do not enter passwords, API tokens", handoff)

    def test_clean_structured_intake_still_routes_through_fresh_architect(self):
        result = self.run_start("--structured-intake")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        handoff = self.handoff()
        self.assertIn("Fresh Architect", handoff)
        self.assertIn("unratified discovery evidence", handoff)
        self.assertIn("explicitly promote", handoff)
        self.assertNotIn("Next role: Adoption coordinator", handoff)

    def test_existing_bootstrap_routes_to_recovery_without_overwrite(self):
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_text("unchanged", encoding="utf-8")
        before = self.tree_snapshot(self.project)
        result = self.run_lifecycle_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "unchanged")
        self.assertEqual(sorted(p.name for p in self.output.iterdir()), ["keep.txt"])
        self.assertIn("Observed lifecycle state: partial_bootstrap", result.stdout)
        self.assertIn("Act as a fresh recovery coordinator", result.stdout)

    def test_lifecycle_change_during_interactive_intake_stops_before_any_write(self):
        process = subprocess.Popen(
            [
                sys.executable, "-B", "-m", "writwall_cli", "start",
                "--structured-intake",
                "--project-root", str(self.project),
                "--project-name", "Example project",
                "--purpose", "Build a small, governed project.",
                "--agent", "Codex",
                "--location", "local workstation",
                "--environment", "local repository only",
            ],
            cwd=REPO_ROOT,
            env=self.environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert process.stdout is not None
        prompt = ""
        while "Track Owner active minutes?" not in prompt:
            char = process.stdout.read(1)
            if not char:
                break
            prompt += char
        self.assertIn("Track Owner active minutes?", prompt)

        governance = self.project / "governance"
        decisions = governance / "decisions"
        decisions.mkdir(parents=True)
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (governance / name).write_text(f"# {name}\n", encoding="utf-8")
        (decisions / "DR-001.md").write_text(
            draft_adoption_record(), encoding="utf-8"
        )
        changed_state = self.tree_snapshot(self.project)

        stdout_tail, stderr = process.communicate("no\nyes\n\n\n", timeout=60)
        self.assertNotEqual(process.returncode, 0, prompt + stdout_tail + stderr)
        self.assertEqual(self.tree_snapshot(self.project), changed_state)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.state.exists())
        self.assertIn("lifecycle changed during intake", stderr)

    def test_missing_secret_confirmation_fails_before_output(self):
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(STARTER),
                "--non-interactive",
                "--project-root",
                str(self.project),
                "--project-name",
                "Example",
                "--purpose",
                "Example",
                "--agent",
                "Codex",
                "--location",
                "desktop",
                "--environment",
                "local repository",
                "--owner-time",
                "no",
            ],
            cwd=REPO_ROOT,
            env=self.environment(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        self.assertIn("secrets", (result.stdout + result.stderr).lower())

    def test_malformed_incomplete_idea_fails_without_output_or_stage(self):
        result = subprocess.run(
            [
                sys.executable, "-B", "-m", "writwall_cli", "start",
                "--non-interactive", "--project-root", str(self.project),
                "--problem", "An incomplete idea.",
                "--agent", "Codex", "--location", "local workstation",
                "--environment", "local repository only",
                "--owner-time", "no", "--confirm-no-secrets",
            ],
            cwd=REPO_ROOT,
            env=self.environment(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing idea qualification", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertEqual(
            list(self.project.parent.glob(
                f".{self.project.name}-writwall-bootstrap-stage-*"
            )),
            [],
        )

    def test_whitespace_only_idea_answers_fail_without_output(self):
        result = self.run_idea_start(
            "--intended-user", "   ",
            "--constraint", "",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing idea qualification", result.stderr)
        self.assertFalse(self.output.exists())

    def test_contradictory_idea_qualification_fails_without_output(self):
        result = self.run_idea_start(
            "--constraint", "Production deployment.",
            "--non-goal", "Production deployment.",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("contradictory idea qualification", result.stderr)
        self.assertFalse(self.output.exists())

    def test_active_pointer_routes_to_implementer_only_when_target_is_active(self):
        work_order = self.project / "governance" / "work-orders" / "WO-001.md"
        work_order.parent.mkdir(parents=True)
        work_order.write_text("---\nid: WO-001\nstatus: ACTIVE\n---\n# Work\n",
                              encoding="utf-8")
        pointer = self.project / ".claude" / "active-wo.txt"
        pointer.parent.mkdir(parents=True)
        pointer.write_text("governance/work-orders/WO-001.md\n", encoding="utf-8")
        before = self.tree_snapshot(self.project)
        result = self.run_lifecycle_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.state.exists())
        self.assertIn("Observed lifecycle state: active_work_order", result.stdout)
        self.assertIn("Act as a fresh Implementer for the active work order only", result.stdout)

    def test_pointer_plus_second_active_order_stops_as_inconsistent(self):
        orders = self.project / "governance" / "work-orders"
        orders.mkdir(parents=True)
        for name in ("WO-001.md", "WO-002.md"):
            (orders / name).write_text(
                f"---\nid: {name[:-3]}\nstatus: ACTIVE\n---\n",
                encoding="utf-8",
            )
        pointer = self.project / ".claude" / "active-wo.txt"
        pointer.parent.mkdir(parents=True)
        pointer.write_text("governance/work-orders/WO-001.md\n", encoding="utf-8")
        before = self.tree_snapshot(self.project)
        result = self.run_lifecycle_start()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertIn(
            "activation pointer does not identify the only ACTIVE work order",
            result.stderr,
        )

    def test_missing_pointer_with_closed_history_never_emits_resume_prompt(self):
        closed = self.project / "governance" / "history" / "WO-001.md"
        closed.parent.mkdir(parents=True)
        closed.write_text("---\nid: WO-001\nstatus: CLOSED\n---\n", encoding="utf-8")
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (self.project / "governance" / name).write_text(f"# {name}\n", encoding="utf-8")
        decision = self.project / "governance" / "decisions" / "DR-001.md"
        decision.parent.mkdir(parents=True)
        decision.write_text(ratified_adoption_record(), encoding="utf-8")
        before = self.tree_snapshot(self.project)
        result = self.run_lifecycle_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.state.exists())
        self.assertIn("Observed lifecycle state: retired_lockout", result.stdout)
        self.assertIn("Act as a fresh General", result.stdout)
        self.assertIn("General", result.stdout)
        self.assertNotIn("Owner-Agent / Project-Architect", result.stdout)
        self.assertNotIn("resume", result.stdout.lower())
        self.assertNotIn("Act as a fresh Implementer", result.stdout)

    def test_pointer_to_closed_order_is_inconsistent_and_creates_nothing(self):
        work_order = self.project / "governance" / "work-orders" / "WO-001.md"
        work_order.parent.mkdir(parents=True)
        work_order.write_text("---\nid: WO-001\nstatus: CLOSED\n---\n", encoding="utf-8")
        pointer = self.project / ".claude" / "active-wo.txt"
        pointer.parent.mkdir(parents=True)
        pointer.write_text("governance/work-orders/WO-001.md\n", encoding="utf-8")
        before = self.tree_snapshot(self.project)
        result = self.run_lifecycle_start()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertIn(
            "activation pointer resolves, but the work order status is 'CLOSED', not 'ACTIVE'",
            result.stderr,
        )

    def test_partial_bootstrap_routes_to_recovery_coordinator(self):
        settings = self.project / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text("{}\n", encoding="utf-8")
        before = self.tree_snapshot(self.project)
        result = self.run_lifecycle_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.state.exists())
        self.assertIn("Observed lifecycle state: partial_bootstrap", result.stdout)
        self.assertIn("Act as a fresh recovery coordinator", result.stdout)

    def test_partial_bootstrap_directory_routes_without_republication(self):
        self.output.mkdir()
        sentinel = self.output / "HANDOFF.md"
        sentinel.write_text("incomplete bootstrap\n", encoding="utf-8")
        before = self.tree_snapshot(self.project)
        result = self.run_lifecycle_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "incomplete bootstrap\n")
        self.assertFalse(self.state.exists())
        self.assertIn("Observed lifecycle state: partial_bootstrap", result.stdout)
        self.assertIn("Act as a fresh recovery coordinator", result.stdout)

    def test_bootstrap_mixed_with_established_lifecycle_fails_closed(self):
        for lifecycle in ("active", "adopted", "retired"):
            with self.subTest(lifecycle=lifecycle):
                project = self.temp / f"project-{lifecycle}"
                project.mkdir()
                bootstrap = project / ".writwall-bootstrap"
                bootstrap.mkdir()
                (bootstrap / "HANDOFF.md").write_text(
                    "incomplete bootstrap\n", encoding="utf-8"
                )
                governance = project / "governance"
                if lifecycle == "active":
                    order = governance / "work-orders" / "WO-001.md"
                    order.parent.mkdir(parents=True)
                    order.write_text(
                        "---\nid: WO-001\nstatus: ACTIVE\n---\n", encoding="utf-8"
                    )
                    pointer = project / ".claude" / "active-wo.txt"
                    pointer.parent.mkdir(parents=True)
                    pointer.write_text(
                        "governance/work-orders/WO-001.md\n", encoding="utf-8"
                    )
                else:
                    governance.mkdir()
                    for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
                        (governance / name).write_text(
                            f"# {name}\n", encoding="utf-8"
                        )
                    if lifecycle == "adopted":
                        decision = governance / "decisions" / "DR-001.md"
                        decision.parent.mkdir()
                        decision.write_text(ratified_adoption_record(), encoding="utf-8")
                    else:
                        decision = governance / "decisions" / "DR-001.md"
                        decision.parent.mkdir()
                        decision.write_text(ratified_adoption_record(), encoding="utf-8")
                        closed = governance / "history" / "WO-001.md"
                        closed.parent.mkdir()
                        closed.write_text(
                            "---\nid: WO-001\nstatus: CLOSED\n---\n",
                            encoding="utf-8",
                        )

                before = self.tree_snapshot(project)
                result = self.run_lifecycle_start(project)
                self.assertNotEqual(
                    result.returncode, 0, result.stdout + result.stderr
                )
                self.assertEqual(self.tree_snapshot(project), before)
                self.assertFalse(self.state.exists())
                self.assertIn("inconsistent state", result.stderr)
                self.assertIn(".writwall-bootstrap", result.stderr)

    def seed_public_distribution(self):
        from scripts.build_public_projection import PUBLIC_CLAUDE_BYTES
        import hashlib
        governance = self.project / "governance"
        (governance / "decisions").mkdir(parents=True)
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (governance / name).write_text(f"# {name}\n", encoding="utf-8")
        (governance / "decisions" / "DR-001.md").write_text(
            ratified_adoption_record(), encoding="utf-8")
        (self.project / "CLAUDE.md").write_bytes(PUBLIC_CLAUDE_BYTES)
        (self.project / "PROJECTION-PROVENANCE.md").write_text(
            "# Projection provenance\n\nThis candidate is derived from a private governed source repository.\n",
            encoding="utf-8")
        paths = ("CLAUDE.md", "PROJECTION-PROVENANCE.md")
        (self.project / "PROJECTION-MANIFEST.sha256").write_text(
            "".join(f"{hashlib.sha256((self.project / p).read_bytes()).hexdigest()}  {p}\n"
                    for p in paths), encoding="utf-8")

    def test_public_distribution_inspect_and_start_do_not_inherit_adoption(self):
        self.seed_public_distribution()
        before = self.tree_snapshot(self.project)
        for result in (self.run_inspect(), self.run_lifecycle_start()):
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("public_distribution", result.stdout)
            self.assertIn("target project", result.stdout)
            self.assertNotIn("Fresh General", result.stdout)
        self.assertEqual(self.tree_snapshot(self.project), before)

    def test_public_distribution_rejects_explicit_execution_roles(self):
        self.seed_public_distribution()
        for role in ("general", "recovery"):
            result = self.run_inspect(role)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        result = self.run_inspect("architect")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("public distribution", result.stdout)
        self.assertIn("read-only", result.stdout)

    def test_public_notice_with_missing_manifest_stops(self):
        self.seed_public_distribution()
        (self.project / "PROJECTION-MANIFEST.sha256").unlink()
        result = self.run_inspect()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("distribution", result.stderr)

    def test_public_distribution_does_not_hide_active_or_bootstrap_state(self):
        self.seed_public_distribution()
        (self.project / ".writwall-bootstrap").mkdir()
        result = self.run_inspect()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        (self.project / ".writwall-bootstrap").rmdir()
        orders = self.project / "governance" / "work-orders"
        orders.mkdir()
        (orders / "WO-001.md").write_text("---\nstatus: ACTIVE\n---\n", encoding="utf-8")
        result = self.run_inspect()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        pointer = self.project / ".claude" / "active-wo.txt"
        pointer.parent.mkdir()
        pointer.write_text("governance/work-orders/WO-001.md\n", encoding="utf-8")
        result = self.run_inspect()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("active_work_order", result.stdout)

    def test_public_marker_cannot_override_a_changed_local_charter(self):
        self.seed_public_distribution()
        (self.project / "CLAUDE.md").write_text("# Local charter\n", encoding="utf-8")
        result = self.run_inspect()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("conflicting", result.stderr)

    def test_public_notice_without_both_markers_never_infers_adoption(self):
        self.seed_public_distribution()
        for name in ("PROJECTION-MANIFEST.sha256", "PROJECTION-PROVENANCE.md"):
            (self.project / name).unlink()
        result = self.run_inspect()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("distribution", result.stderr)

    def test_public_distribution_preserves_governance_path_checks(self):
        self.seed_public_distribution()
        plan = self.project / "governance" / "PLAN.md"
        plan.unlink()
        plan.mkdir()
        result = self.run_inspect()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("governance control", result.stderr)

    def test_adopted_lockout_routes_to_fresh_general(self):
        governance = self.project / "governance"
        governance.mkdir()
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (governance / name).write_text(f"# {name}\n", encoding="utf-8")
        decision = governance / "decisions" / "DR-001.md"
        decision.parent.mkdir()
        decision.write_text(ratified_adoption_record(), encoding="utf-8")
        before = self.tree_snapshot(self.project)
        result = self.run_lifecycle_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.state.exists())
        self.assertIn("Observed lifecycle state: adopted_lockout", result.stdout)
        self.assertIn("Act as a fresh General", result.stdout)
        self.assertNotIn("Owner-Agent / Project-Architect", result.stdout)
        flat = " ".join(result.stdout.split())
        self.assertIn("Recommendation and material tradeoff", flat)
        self.assertIn("supporting evidence", flat)
        self.assertIn("one combined disposition and action", flat)
        self.assertIn("explicitly include creation and dispatch", flat)
        self.assertIn("Do not ask for the same decision again", flat)
        self.assertIn("perform every mechanically available authorized step", flat)

    def test_inspect_architect_reenters_adopted_lockout_without_writes(self):
        governance = self.project / "governance"
        governance.mkdir()
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (governance / name).write_text(f"# {name}\n", encoding="utf-8")
        decision = governance / "decisions" / "DR-001.md"
        decision.parent.mkdir()
        decision.write_text(ratified_adoption_record(), encoding="utf-8")
        (self.project / "README.md").write_text("# Existing project\n", encoding="utf-8")
        before = self.tree_snapshot(self.project)

        result = self.run_inspect("architect")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.state.exists())
        self.assertIn("Observed lifecycle state: adopted_lockout", result.stdout)
        self.assertIn("Selected role: Fresh Architect", result.stdout)
        self.assertIn("Begin read-only", result.stdout)
        self.assertIn(
            "grants no mutation or lifecycle authority",
            " ".join(result.stdout.split()),
        )

    def test_inspect_partial_bootstrap_routes_recovery_without_writes(self):
        settings = self.project / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text("{}\n", encoding="utf-8")
        before = self.tree_snapshot(self.project)

        result = self.run_inspect("recovery")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.state.exists())
        self.assertIn("Observed lifecycle state: partial_bootstrap", result.stdout)
        self.assertIn("Selected role: Fresh external recovery coordinator", result.stdout)

        architect = self.run_inspect("architect")
        self.assertEqual(architect.returncode, 0, architect.stdout + architect.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertIn("Selected role: Fresh Architect", architect.stdout)
        self.assertIn("observed lifecycle is partial_bootstrap", architect.stdout)

    def test_inspect_general_routes_adopted_and_retired_lockout(self):
        for lifecycle in ("adopted_lockout", "retired_lockout"):
            with self.subTest(lifecycle=lifecycle):
                project = self.temp / lifecycle
                governance = project / "governance"
                governance.mkdir(parents=True)
                for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
                    (governance / name).write_text(f"# {name}\n", encoding="utf-8")
                decision = governance / "decisions" / "DR-001.md"
                decision.parent.mkdir()
                decision.write_text(ratified_adoption_record(), encoding="utf-8")
                if lifecycle == "retired_lockout":
                    closed = governance / "history" / "WO-001.md"
                    closed.parent.mkdir()
                    closed.write_text(
                        "---\nid: WO-001\nstatus: CLOSED\n---\n", encoding="utf-8"
                    )
                before = self.tree_snapshot(project)

                result = self.run_inspect("general", project)

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.tree_snapshot(project), before)
                self.assertIn(f"Observed lifecycle state: {lifecycle}", result.stdout)
                self.assertIn("Selected role: Fresh General", result.stdout)

    def test_retired_lockout_history_read_stops_before_invalid_utf8_body(self):
        """File-I/O boundary regression for ratified Amendment 1.

        Entirely synthetic fixture: a valid CLOSED historical work-order
        header immediately followed by invalid-UTF-8 body bytes. Correct
        classification depends only on the header; it must never *read* the
        body, not merely avoid decoding it. This instruments the actual raw
        file-I/O boundary (not the classifier): it requires the record be
        opened unbuffered (`buffering=0`, so no internal buffered reader can
        silently pull body bytes into memory ahead of the caller's requests),
        and it sums every byte ever returned across every read call -- the
        cumulative total, not merely the largest single call -- asserting it
        equals exactly the header's byte length, including its closing
        delimiter, with zero slack. It also asserts no returned chunk ever
        contains either invalid marker byte from the synthetic body.
        """
        governance = self.project / "governance"
        governance.mkdir()
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (governance / name).write_text(f"# {name}\n", encoding="utf-8")
        decisions = governance / "decisions"
        decisions.mkdir(parents=True)
        (decisions / "DR-001.md").write_text(
            ratified_adoption_record(), encoding="utf-8"
        )
        history = governance / "history"
        history.mkdir()
        header = b"---\nid: WO-SYN-001\nstatus: CLOSED\n---\n"
        invalid_body = b"\xff\xfe not valid utf-8 body content\n"
        record = history / "WO-SYN-001.md"
        record.write_bytes(header + invalid_body)

        raw_bytes_consumed = 0
        buffering_used: list[object] = []
        original_open = Path.open
        test_case = self

        class _RawIOBoundaryProxy:
            """Forwards to the real handle while measuring every byte it
            ever returns, at the exact boundary the production code calls,
            and asserting no returned chunk ever carries a body byte."""

            def __init__(self, handle):
                self._handle = handle

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return self._handle.__exit__(*exc_info)

            @staticmethod
            def _record_chunk(chunk: bytes) -> None:
                nonlocal raw_bytes_consumed
                raw_bytes_consumed += len(chunk)
                test_case.assertNotIn(
                    b"\xff", chunk, "raw read consumed an invalid body byte"
                )
                test_case.assertNotIn(
                    b"\xfe", chunk, "raw read consumed an invalid body byte"
                )

            def read(self, size=-1, *args, **kwargs):
                result = self._handle.read(size, *args, **kwargs)
                self._record_chunk(
                    result if isinstance(result, (bytes, bytearray)) else b""
                )
                return result

            def readinto(self, buffer):
                result = self._handle.readinto(buffer)
                if result:
                    self._record_chunk(bytes(buffer[:result]))
                return result

            def __getattr__(self, name):
                return getattr(self._handle, name)

        def instrumented_open(self_path, *args, **kwargs):
            handle = original_open(self_path, *args, **kwargs)
            if self_path != record:
                return handle
            buffering_used.append(
                kwargs.get("buffering", args[1] if len(args) > 1 else -1)
            )
            return _RawIOBoundaryProxy(handle)

        with mock.patch.object(Path, "open", instrumented_open):
            state = starter_module.classify_project(self.project)

        self.assertEqual(state.name, "retired_lockout")
        self.assertTrue(buffering_used, "expected the historical record to be opened")
        self.assertIn(
            0, buffering_used,
            "the historical record must be opened with buffering=0 (raw, "
            "unbuffered binary I/O), so no internal buffer can pull body "
            "bytes into memory ahead of the caller's own requests",
        )
        self.assertEqual(
            raw_bytes_consumed, len(header),
            "total raw bytes ever read from the historical record must equal "
            "exactly the header including its closing delimiter, with zero "
            "slack into the body",
        )

    def test_inspect_rejects_unsafe_explicit_role_lifecycle_combinations(self):
        cases = (("general", "clean_new"), ("recovery", "clean_new"))
        for role, lifecycle in cases:
            with self.subTest(role=role, lifecycle=lifecycle):
                before = self.tree_snapshot(self.project)
                result = self.run_inspect(role)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(self.tree_snapshot(self.project), before)
                self.assertIn(f"role {role!r}", result.stderr)
                self.assertIn(lifecycle, result.stderr)
                self.assertIn("allowed", result.stderr)

    def test_inspect_auto_preserves_active_operator_routing_without_writes(self):
        order = self.project / "governance" / "work-orders" / "WO-001.md"
        order.parent.mkdir(parents=True)
        order.write_text(
            "---\nid: WO-001\nstatus: ACTIVE\n---\n# Work\n", encoding="utf-8"
        )
        pointer = self.project / ".claude" / "active-wo.txt"
        pointer.parent.mkdir(parents=True)
        pointer.write_text("governance/work-orders/WO-001.md\n", encoding="utf-8")
        before = self.tree_snapshot(self.project)

        result = self.run_inspect("auto")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertIn("Observed lifecycle state: active_work_order", result.stdout)
        self.assertIn("Selected role: Fresh walled repository Operator/Implementer", result.stdout)
        self.assertIn("active work order only", result.stdout)

        rejected = self.run_inspect("architect")
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("bounded Operator", rejected.stderr)

    def test_inspect_default_auto_is_read_only_and_creates_no_state_or_cache(self):
        (self.project / "README.md").write_text(
            "# Existing unadopted project\n", encoding="utf-8"
        )
        before = self.tree_snapshot(self.project)
        result = subprocess.run(
            [
                sys.executable, "-B", "-m", "writwall_cli", "inspect",
                "--project-root", str(self.project),
            ],
            cwd=REPO_ROOT,
            env=self.environment(),
            capture_output=True,
            text=True,
            timeout=60,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.state.exists())
        self.assertEqual(list(self.temp.rglob("__pycache__")), [])
        self.assertEqual(list(self.temp.rglob("*.pyc")), [])
        self.assertIn("Observed lifecycle state: clean_new", result.stdout)
        self.assertIn("Selected role: Fresh Architect (conversation-first)", result.stdout)
        self.assertIn("Top-level project entries: README.md", result.stdout)
        self.assertNotIn("discovery.json", result.stdout)
        self.assertNotIn("ARCHITECT.md", result.stdout)

    def test_inspect_brief_on_new_project_is_zero_write_with_labeled_sections_and_bounded_prose(self):
        (self.project / "README.md").write_text(
            "# Existing unadopted project\n", encoding="utf-8"
        )
        before = self.tree_snapshot(self.project)

        result = self.run_inspect("architect", brief=True)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.state.exists())

        stdout = result.stdout
        self.assertIn("### Compact continuation brief", stdout)
        self.assertNotIn("Copy this prompt into a fresh session", stdout)
        for heading in (
            "## Observed lifecycle and objective evidence",
            "## Decision and authority references",
            "## Proposals (not approval)",
            "## Next permitted step or unresolved condition",
            "## Mandatory evidence",
            "## Optional references",
            "## Evidence index (outside the prose word budget)",
        ):
            self.assertIn(heading, stdout, heading)

        brief_start = stdout.index("### Compact continuation brief")
        index_heading = "## Evidence index (outside the prose word budget)"
        index_start = stdout.index(index_heading)
        self.assertLess(brief_start, index_start)
        prose = stdout[brief_start:index_start]
        self.assertLessEqual(len(prose.split()), 500)
        self.assertIn("evidence index excluded", prose)

        evidence_index = stdout[index_start:]
        self.assertIn(
            "bytes do not measure tokens, context, or cost",
            " ".join(evidence_index.split()),
        )

    def test_inspect_brief_on_active_work_order_cites_evidence_paths_and_pending_route(self):
        charter_bytes = b"# Charter\n\nA.1 Prohibitions apply.\n"
        plan_bytes = b"# PLAN\n\nRatified intent.\n"
        routing_bytes = b"# ROUTING\n\nR.4 governs skills/**.\n"
        state_bytes = b"# STATE\n\nOBSERVED and INTERPRETED sections.\n"
        requirement_bytes = b"# Example current requirement\n\nSafely referenced.\n"
        work_order_bytes = (
            b"---\nid: WO-001\nstatus: ACTIVE\n---\n"
            b"# WO-001: Example\n\n"
            b"## Objective\n\n"
            b"Do the bounded thing.\n\n"
            b"Routing: see docs/example-requirement.md and docs/unmapped-note.md.\n"
        )

        (self.project / "CLAUDE.md").write_bytes(charter_bytes)
        governance = self.project / "governance"
        governance.mkdir()
        (governance / "PLAN.md").write_bytes(plan_bytes)
        (governance / "ROUTING.md").write_bytes(routing_bytes)
        (governance / "STATE.md").write_bytes(state_bytes)
        work_orders = governance / "work-orders"
        work_orders.mkdir()
        work_order_path = work_orders / "WO-001.md"
        work_order_path.write_bytes(work_order_bytes)
        docs = self.project / "docs"
        docs.mkdir()
        (docs / "example-requirement.md").write_bytes(requirement_bytes)
        pointer = self.project / ".claude" / "active-wo.txt"
        pointer.parent.mkdir(parents=True)
        pointer.write_text("governance/work-orders/WO-001.md\n", encoding="utf-8")

        before = self.tree_snapshot(self.project)

        result = self.run_inspect("auto", brief=True)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.state.exists())

        stdout = result.stdout
        self.assertIn("### Compact continuation brief", stdout)
        self.assertNotIn("Copy this prompt into a fresh session", stdout)
        self.assertNotIn(
            "Act as a fresh Implementer for the active work order only", stdout
        )
        self.assertNotIn("governance/history", stdout)
        self.assertNotIn("history", stdout.lower())

        for relative, size in (
            ("CLAUDE.md", len(charter_bytes)),
            ("governance/PLAN.md", len(plan_bytes)),
            ("governance/ROUTING.md", len(routing_bytes)),
            ("governance/STATE.md", len(state_bytes)),
            ("governance/work-orders/WO-001.md", len(work_order_bytes)),
            ("docs/example-requirement.md", len(requirement_bytes)),
        ):
            self.assertIn(f"{relative} ({size} bytes)", stdout, relative)

        self.assertIn("docs/unmapped-note.md", stdout)
        self.assertIn("remains pending", stdout)
        self.assertIn("unresolved", stdout)

        self.assertIn("not inferred Owner approval", stdout)
        # This fixture's Routing: line names one genuinely unresolved
        # reference (docs/unmapped-note.md), so the brief must not claim the
        # unqualified confident-execution phrasing; it must state the
        # stricter, now-correct safety contract instead.
        self.assertNotIn(
            "Mandatory evidence in the index below is present. The only "
            "permitted next role is the bounded Operator",
            stdout,
        )
        self.assertIn("remains the bounded Operator", stdout)
        self.assertIn("does not authorize execution", stdout)
        self.assertIn("observation snapshot", stdout)

    def test_inspect_brief_active_work_order_bounds_prose_and_moves_evidence_index_after_boundary(self):
        """Excess current routing references must never blow the 500-word
        prose budget; every mandatory input and every routed reference must
        still appear, with safe byte sizes, in the trailing evidence index
        -- never truncated, never counted against the prose budget. Entirely
        synthetic fixture; no real project material is read or referenced.
        """
        charter_bytes = b"# Charter\n\nA.1 Prohibitions apply.\n"
        plan_bytes = b"# PLAN\n\nRatified intent.\n"
        routing_bytes = b"# ROUTING\n\nR.4 governs skills/**.\n"
        state_bytes = b"# STATE\n\nOBSERVED and INTERPRETED sections.\n"

        (self.project / "CLAUDE.md").write_bytes(charter_bytes)
        governance = self.project / "governance"
        governance.mkdir()
        (governance / "PLAN.md").write_bytes(plan_bytes)
        (governance / "ROUTING.md").write_bytes(routing_bytes)
        (governance / "STATE.md").write_bytes(state_bytes)

        docs = self.project / "docs"
        docs.mkdir()
        routed_relatives: list[tuple[str, int]] = []
        for index in range(1, 121):
            name = f"req-{index:03d}.md"
            content = f"# Requirement {index}\n".encode("utf-8")
            (docs / name).write_bytes(content)
            routed_relatives.append((f"docs/{name}", len(content)))

        routing_line = (
            "Routing: see " + ", ".join(relative for relative, _ in routed_relatives) + "."
        )
        work_order_bytes = (
            b"---\nid: WO-001\nstatus: ACTIVE\n---\n"
            b"# WO-001: Example\n\n"
            b"## Objective\n\n"
            b"Do the bounded thing.\n\n"
            + routing_line.encode("utf-8") + b"\n"
        )
        work_orders = governance / "work-orders"
        work_orders.mkdir()
        work_order_path = work_orders / "WO-001.md"
        work_order_path.write_bytes(work_order_bytes)
        pointer = self.project / ".claude" / "active-wo.txt"
        pointer.parent.mkdir(parents=True)
        pointer.write_text("governance/work-orders/WO-001.md\n", encoding="utf-8")

        before = self.tree_snapshot(self.project)

        result = self.run_inspect("auto", brief=True)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.state.exists())

        stdout = result.stdout
        self.assertNotIn("Copy this prompt into a fresh session", stdout)
        self.assertNotIn(
            "Act as a fresh Implementer for the active work order only", stdout
        )

        index_heading = "## Evidence index (outside the prose word budget)"
        self.assertIn(index_heading, stdout)
        brief_start = stdout.index("### Compact continuation brief")
        index_start = stdout.index(index_heading)
        self.assertLess(brief_start, index_start)

        prose = stdout[brief_start:index_start]
        self.assertLessEqual(
            len(prose.split()), 500,
            "prose before the evidence index must stay within its own "
            "500-word budget even when many current routing references "
            "are supplied",
        )

        evidence_index = stdout[index_start:]
        for relative, size in (
            ("CLAUDE.md", len(charter_bytes)),
            ("governance/PLAN.md", len(plan_bytes)),
            ("governance/ROUTING.md", len(routing_bytes)),
            ("governance/STATE.md", len(state_bytes)),
            ("governance/work-orders/WO-001.md", len(work_order_bytes)),
        ):
            self.assertIn(
                f"{relative} ({size} bytes)", evidence_index,
                f"mandatory input {relative} missing from the evidence index",
            )
        for relative, size in routed_relatives:
            self.assertIn(
                f"{relative} ({size} bytes)", evidence_index,
                f"routed reference {relative} missing from the evidence index",
            )

    def test_inspect_brief_on_lockout_cites_current_governance_evidence_and_general_guidance(self):
        """One parameterized regression for adopted and retired lockout.

        Entirely synthetic fixtures built with the existing
        ``ratified_adoption_record()`` helper. Mandatory evidence must cite
        the current charter, Plan, State, Routing, and the current ratified
        adoption record with byte sizes. A retired lockout's closed-history
        evidence must stay aggregate (a count only) -- no historical
        pathname or body ever appears in the brief. The next-permitted-step
        must give concrete General planning/dispatch-next-work guidance,
        never mutation permission, and state plainly that this is an
        observation snapshot requiring a re-read of mandatory evidence
        before acting.
        """
        for lifecycle in ("adopted_lockout", "retired_lockout"):
            with self.subTest(lifecycle=lifecycle):
                project = self.temp / lifecycle
                charter_bytes = b"# Charter\n\nA.1 Prohibitions apply.\n"
                plan_bytes = b"# PLAN\n\nRatified intent.\n"
                state_bytes = b"# STATE\n\nOBSERVED and INTERPRETED sections.\n"
                routing_bytes = b"# ROUTING\n\nR.4 governs skills/**.\n"
                adoption_bytes = ratified_adoption_record().encode("utf-8")

                governance = project / "governance"
                governance.mkdir(parents=True)
                (project / "CLAUDE.md").write_bytes(charter_bytes)
                (governance / "PLAN.md").write_bytes(plan_bytes)
                (governance / "STATE.md").write_bytes(state_bytes)
                (governance / "ROUTING.md").write_bytes(routing_bytes)
                decisions = governance / "decisions"
                decisions.mkdir()
                (decisions / "DR-001.md").write_bytes(adoption_bytes)

                if lifecycle == "retired_lockout":
                    closed = governance / "history" / "WO-001.md"
                    closed.parent.mkdir(parents=True)
                    closed.write_text(
                        "---\nid: WO-001\nstatus: CLOSED\n---\n", encoding="utf-8"
                    )

                before = self.tree_snapshot(project)

                result = self.run_inspect("auto", project=project, brief=True)

                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.tree_snapshot(project), before)
                self.assertFalse((project / ".writwall-bootstrap").exists())
                self.assertFalse(self.state.exists())

                stdout = result.stdout
                self.assertIn(f"Observed lifecycle state: {lifecycle}", stdout)
                self.assertNotIn("Copy this prompt into a fresh session", stdout)
                self.assertNotIn("Act as a fresh General", stdout)

                for relative, size in (
                    ("CLAUDE.md", len(charter_bytes)),
                    ("governance/PLAN.md", len(plan_bytes)),
                    ("governance/STATE.md", len(state_bytes)),
                    ("governance/ROUTING.md", len(routing_bytes)),
                    ("governance/decisions/DR-001.md", len(adoption_bytes)),
                ):
                    self.assertIn(f"{relative} ({size} bytes)", stdout, relative)

                self.assertNotIn("governance/history", stdout)
                self.assertNotIn("WO-001.md", stdout)
                if lifecycle == "retired_lockout":
                    self.assertIn("closed work-order record", stdout)

                self.assertIn("observation snapshot", stdout)
                self.assertIn("re-read", stdout)
                self.assertIn("Prepare, but do not activate", stdout)
                self.assertIn("bounded Operator packet", stdout)
                self.assertIn("no mutation authority", stdout)

    def test_inspect_brief_active_work_order_flags_unresolved_unsafe_and_unsupported_routing_without_confidence(self):
        """One parameterized public-CLI regression.

        An active brief must never imply execution readiness while any
        routed evidence is unresolved, unsafe, or unsupported -- even though
        every recognized mandatory input (charter, Plan, Routing, State, the
        work order itself) is genuinely present. Entirely synthetic
        fixtures; no real history/archive/dist/other-project content is
        read, and no network or out-of-fixture filesystem access occurs.
        """
        charter_bytes = b"# Charter\n\nA.1 Prohibitions apply.\n"
        plan_bytes = b"# PLAN\n\nRatified intent.\n"
        routing_bytes = b"# ROUTING\n\nR.4 governs skills/**.\n"
        state_bytes = b"# STATE\n\nOBSERVED and INTERPRETED sections.\n"

        (self.project / "CLAUDE.md").write_bytes(charter_bytes)
        governance = self.project / "governance"
        governance.mkdir()
        (governance / "PLAN.md").write_bytes(plan_bytes)
        (governance / "ROUTING.md").write_bytes(routing_bytes)
        (governance / "STATE.md").write_bytes(state_bytes)

        # Case: relative escape -- a real file that exists just outside the
        # project root, so a leaked byte size would be detectable.
        outside_content = b"Secret sibling content.\n"
        (self.temp / "outside-secret.md").write_bytes(outside_content)

        # Case: an excluded protected-prefix reference. Entirely synthetic
        # content at a synthetic project-local path; not a real historical,
        # archived, RFI, or dist record of any actual project.
        history_dir = governance / "history"
        history_dir.mkdir()
        history_content = b"Synthetic excluded-prefix content.\n"
        (history_dir / "WO-999.md").write_bytes(history_content)

        # Case: digest-bearing reference. The plain, undecorated file is
        # real; the digest annotation must not be silently stripped and the
        # plain file confidently substituted in its place.
        docs = self.project / "docs"
        docs.mkdir()
        (docs / "pinned.md").write_bytes(b"# Pinned content\n")
        digest = "de" * 32

        routing_line = (
            "Routing: see docs/missing-current.md, ../outside-secret.md, "
            "https://example.com/spec.md, governance/history/WO-999.md and "
            f"docs/pinned.md@sha256:{digest}."
        )
        work_order_bytes = (
            b"---\nid: WO-001\nstatus: ACTIVE\n---\n"
            b"# WO-001: Example\n\n"
            b"## Objective\n\n"
            b"Do the bounded thing.\n\n"
            + routing_line.encode("utf-8") + b"\n"
        )
        work_orders = governance / "work-orders"
        work_orders.mkdir()
        work_order_path = work_orders / "WO-001.md"
        work_order_path.write_bytes(work_order_bytes)
        pointer = self.project / ".claude" / "active-wo.txt"
        pointer.parent.mkdir(parents=True)
        pointer.write_text("governance/work-orders/WO-001.md\n", encoding="utf-8")

        before = self.tree_snapshot(self.project)

        result = self.run_inspect("auto", brief=True)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.state.exists())

        stdout = result.stdout
        self.assertNotIn("Copy this prompt into a fresh session", stdout)
        self.assertNotIn(
            "Act as a fresh Implementer for the active work order only", stdout
        )

        with self.subTest(case="missing_current_path"):
            self.assertIn("docs/missing-current.md", stdout)
            self.assertIn("remains pending", stdout)

        with self.subTest(case="relative_escape_never_leaks_size"):
            self.assertIn("../outside-secret.md", stdout)
            self.assertNotIn(f"({len(outside_content)} bytes)", stdout)

        with self.subTest(case="url_named_in_full_never_mangled_fragment"):
            self.assertIn("https://example.com/spec.md", stdout)
            self.assertNotIn("- //example.com/spec.md", stdout)

        with self.subTest(case="excluded_prefix_never_measured"):
            self.assertIn("governance/history/WO-999.md", stdout)
            self.assertIn("excluded", stdout)
            self.assertNotIn(
                f"governance/history/WO-999.md ({len(history_content)} bytes)",
                stdout,
            )

        with self.subTest(case="digest_bearing_reference_never_substituted"):
            self.assertIn(f"docs/pinned.md@sha256:{digest}", stdout)
            self.assertNotIn("- docs/pinned.md (", stdout)

        with self.subTest(case="no_confident_execution_readiness"):
            self.assertNotIn(
                "Mandatory evidence in the index below is present. The only "
                "permitted next role is the bounded Operator",
                stdout,
            )
            self.assertIn("does not authorize execution", stdout)
            self.assertIn("remains the bounded Operator", stdout)
            self.assertIn("observation snapshot", stdout)
            self.assertIn("re-read", stdout)

        with self.subTest(case="contradictory_lifecycle_stays_fail_closed"):
            contradictory = self.temp / "contradictory"
            contradictory.mkdir()
            orders = contradictory / "governance" / "work-orders"
            orders.mkdir(parents=True)
            for name in ("WO-001.md", "WO-002.md"):
                (orders / name).write_text(
                    f"---\nid: {name[:-3]}\nstatus: ACTIVE\n---\n",
                    encoding="utf-8",
                )
            contradictory_pointer = contradictory / ".claude" / "active-wo.txt"
            contradictory_pointer.parent.mkdir(parents=True)
            contradictory_pointer.write_text(
                "governance/work-orders/WO-001.md\n", encoding="utf-8"
            )
            before_contradictory = self.tree_snapshot(contradictory)
            contradictory_result = self.run_inspect(
                "auto", project=contradictory, brief=True
            )
            self.assertNotEqual(contradictory_result.returncode, 0)
            self.assertEqual(
                self.tree_snapshot(contradictory), before_contradictory
            )
            self.assertIn(
                "activation pointer does not identify the only ACTIVE "
                "work order",
                contradictory_result.stderr,
            )

    def test_inspect_brief_active_work_order_routing_boundary_cases(self):
        """One focused extension of the routing regression, covering two
        additional boundary cases found by source review, plus one
        preventive I/O-boundary guard.

        Run in-process (not via subprocess) so the file-I/O boundary can be
        instrumented directly. Entirely synthetic fixtures; no real
        history/archive/RFI/dist/other-project content is read.
        """
        charter_bytes = b"# Charter\n\nA.1 Prohibitions apply.\n"
        plan_bytes = b"# PLAN\n\nRatified intent.\n"
        routing_bytes = b"# ROUTING\n\nR.4 governs skills/**.\n"
        state_bytes = b"# STATE\n\nOBSERVED and INTERPRETED sections.\n"
        confident_phrase = (
            "Mandatory evidence in the index below is present. The only "
            "permitted next role is the bounded Operator"
        )

        def make_project(name: str) -> Path:
            project = self.temp / name
            governance = project / "governance"
            governance.mkdir(parents=True)
            (project / "CLAUDE.md").write_bytes(charter_bytes)
            (governance / "PLAN.md").write_bytes(plan_bytes)
            (governance / "ROUTING.md").write_bytes(routing_bytes)
            (governance / "STATE.md").write_bytes(state_bytes)
            return project

        def write_work_order(project: Path, routing_line: str | None) -> None:
            work_orders = project / "governance" / "work-orders"
            work_orders.mkdir(parents=True)
            body = (
                b"---\nid: WO-001\nstatus: ACTIVE\n---\n"
                b"# WO-001: Example\n\n"
                b"## Objective\n\n"
                b"Do the bounded thing.\n"
            )
            if routing_line is not None:
                body += b"\n" + routing_line.encode("utf-8") + b"\n"
            (work_orders / "WO-001.md").write_bytes(body)
            pointer = project / ".claude" / "active-wo.txt"
            pointer.parent.mkdir(parents=True)
            pointer.write_text(
                "governance/work-orders/WO-001.md\n", encoding="utf-8"
            )

        def render(project: Path) -> str:
            output = io.StringIO()
            with redirect_stdout(output):
                result = starter_module.inspect_main(
                    ["--project-root", str(project), "--role", "auto", "--brief"]
                )
            self.assertEqual(result, 0)
            return output.getvalue()

        def make_recording_stat(sink: list[str]):
            original_stat = Path.stat

            def recording_stat(self_path, *args, **kwargs):
                sink.append(str(self_path))
                return original_stat(self_path, *args, **kwargs)

            return recording_stat

        with self.subTest(case="no_routing_line"):
            project = make_project("no-routing-line")
            write_work_order(project, None)
            stdout = render(project)
            self.assertNotIn(confident_phrase, stdout)

        with self.subTest(case="empty_routing_line"):
            project = make_project("empty-routing-line")
            write_work_order(project, "Routing:")
            stdout = render(project)
            self.assertNotIn(confident_phrase, stdout)

        with self.subTest(case="mixed_case_excluded_prefix"):
            project = make_project("mixed-case-excluded")
            history_dir = project / "governance" / "history"
            history_dir.mkdir()
            history_content = b"Synthetic excluded-prefix content, mixed case.\n"
            (history_dir / "WO-999.md").write_bytes(history_content)
            write_work_order(project, "Routing: see Governance/History/WO-999.md.")
            stat_calls: list[str] = []
            with mock.patch.object(Path, "stat", make_recording_stat(stat_calls)):
                stdout = render(project)
            self.assertIn("Governance/History/WO-999.md", stdout)
            self.assertIn("excluded", stdout)
            self.assertNotIn(
                f"Governance/History/WO-999.md ({len(history_content)} bytes)",
                stdout,
            )
            real_history_file = str((history_dir / "WO-999.md").resolve())
            self.assertFalse(
                any(call.lower() == real_history_file.lower() for call in stat_calls),
                "the excluded record must never be stat'd, even via a "
                "differently-cased alias",
            )

        with self.subTest(case="trailing_dot_directory_alias_excluded_prefix"):
            project = make_project("trailing-dot-alias")
            history_dir = project / "governance" / "history"
            history_dir.mkdir()
            history_content = b"Synthetic excluded-prefix content, dot alias.\n"
            (history_dir / "WO-999.md").write_bytes(history_content)
            write_work_order(project, "Routing: see governance/history./WO-999.md.")
            stat_calls = []
            with mock.patch.object(Path, "stat", make_recording_stat(stat_calls)):
                stdout = render(project)
            self.assertIn("governance/history./WO-999.md", stdout)
            self.assertIn("excluded", stdout)
            self.assertNotIn(
                f"governance/history./WO-999.md ({len(history_content)} bytes)",
                stdout,
            )
            real_history_file = str((history_dir / "WO-999.md").resolve())
            self.assertFalse(
                any(call.lower() == real_history_file.lower() for call in stat_calls),
                "the excluded record must never be stat'd via a trailing-dot "
                "directory alias",
            )

        with self.subTest(case="symlink_outside_root_never_stated_before_rejection"):
            project = make_project("symlink-outside-root")
            outside_target = self.temp / "symlink-outside-target.md"
            outside_content = b"Outside-root symlink target content.\n"
            outside_target.write_bytes(outside_content)
            docs = project / "docs"
            docs.mkdir()
            symlink_path = docs / "linked.md"
            try:
                symlink_path.symlink_to(outside_target)
            except OSError as exc:
                self.skipTest(f"symlink privilege unavailable: {exc}")
            write_work_order(project, "Routing: see docs/linked.md.")
            stat_calls = []
            with mock.patch.object(Path, "stat", make_recording_stat(stat_calls)):
                stdout = render(project)
            self.assertIn("docs/linked.md", stdout)
            self.assertNotIn(f"({len(outside_content)} bytes)", stdout)
            real_outside = str(outside_target.resolve())
            self.assertFalse(
                any(call == real_outside for call in stat_calls),
                "a symlink resolving outside the project root must never be "
                "stat'd for its metadata before the safety check rejects it",
            )

    def test_inspect_brief_entry_states_give_concrete_state_specific_guidance(self):
        """One parameterized public-CLI regression for clean/new, incomplete
        adoption (partial bootstrap), and public-distribution entry states.

        Each must give concrete, read-only, state-specific next-step
        guidance -- never a generic "fresh Fresh" role-name duplication,
        never a redundant instruction to re-run `inspect` from within its
        own brief output, and always an explicit observation-snapshot/
        re-read statement with authority/objective named unknown until
        actually cited or read. Reuses existing synthetic fixture helpers
        (``seed_public_distribution``); no real or disallowed sources are
        read, and no target/profile mutation occurs.
        """
        with self.subTest(case="clean_new"):
            project = self.temp / "brief-clean-new"
            project.mkdir()
            (project / "README.md").write_text(
                "# Existing unadopted project\n", encoding="utf-8"
            )
            before = self.tree_snapshot(project)

            result = self.run_inspect("auto", project=project, brief=True)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.tree_snapshot(project), before)
            self.assertFalse((project / ".writwall-bootstrap").exists())
            self.assertFalse(self.state.exists())

            stdout = result.stdout
            self.assertNotIn("Copy this prompt into a fresh session", stdout)
            self.assertNotIn("fresh Fresh", stdout)
            self.assertNotIn("Re-enter a fresh", stdout)
            self.assertIn("observation snapshot", stdout)
            self.assertIn("re-read", stdout)
            self.assertIn("unknown until", stdout)
            self.assertIn(
                "Selected role: Fresh Architect (conversation-first)", stdout
            )
            self.assertIn("Listen to the Owner's project pitch", stdout)
            self.assertIn("CLAUDE.md", stdout)
            self.assertIn("not yet materialized", stdout)

        with self.subTest(case="incomplete_adoption"):
            project = self.temp / "brief-incomplete-adoption"
            settings = project / ".claude" / "settings.json"
            settings.parent.mkdir(parents=True)
            settings.write_text("{}\n", encoding="utf-8")
            before = self.tree_snapshot(project)

            result = self.run_inspect("auto", project=project, brief=True)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.tree_snapshot(project), before)
            self.assertFalse((project / ".writwall-bootstrap").exists())
            self.assertFalse(self.state.exists())

            stdout = result.stdout
            self.assertNotIn("Copy this prompt into a fresh session", stdout)
            self.assertNotIn("fresh Fresh", stdout)
            self.assertNotIn("Re-enter a fresh", stdout)
            self.assertIn("observation snapshot", stdout)
            self.assertIn("re-read", stdout)
            self.assertIn("unknown until", stdout)
            self.assertIn(
                "Selected role: Fresh external recovery coordinator", stdout
            )
            self.assertIn("Preserve and reconcile", stdout)
            self.assertIn("do not reset or re-adopt", stdout)
            self.assertIn("missing Owner decision", stdout)

        with self.subTest(case="public_distribution"):
            self.seed_public_distribution()
            before = self.tree_snapshot(self.project)

            result = self.run_inspect("auto", brief=True)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.tree_snapshot(self.project), before)
            self.assertFalse(self.output.exists())
            self.assertFalse(self.state.exists())

            stdout = result.stdout
            self.assertNotIn("Copy this prompt into a fresh session", stdout)
            self.assertNotIn("fresh Fresh", stdout)
            self.assertNotIn("Re-enter a fresh", stdout)
            self.assertIn("observation snapshot", stdout)
            self.assertIn("re-read", stdout)
            self.assertIn("unknown until", stdout)
            self.assertIn("public distribution", stdout)
            self.assertIn("not an adopter project", stdout)
            self.assertIn("CONTRIBUTING.md", stdout)
            self.assertIn("separate target project", stdout)

    # -- Supplementary regressions for already-implemented behavior. Each
    # test below covers a case identified by source review *after* the
    # code it exercises was already implemented and confirmed GREEN in an
    # earlier slice. These are coverage additions, not a newly claimed
    # RED/GREEN chronology: no production behavior changes accompany them.

    def test_bounded_frontmatter_status_supplementary_bom_and_crlf_coverage(self):
        """Supplementary coverage for the already-implemented Amendment 1
        bounded reader (`_bounded_frontmatter_status`): a leading UTF-8 BOM
        and CRLF line endings on an otherwise well-formed header must still
        classify correctly. Entirely synthetic content.
        """
        record = self.temp / "WO-BOM-CRLF.md"
        record.write_bytes(
            b"\xef\xbb\xbf---\r\nid: WO-BOM\r\nstatus: CLOSED\r\n---\r\n"
            b"Synthetic body content, irrelevant to header parsing.\r\n"
        )
        status = starter_module._bounded_frontmatter_status(record)
        self.assertEqual(status, "CLOSED")

    def test_bounded_frontmatter_status_supplementary_finite_bound_failure(self):
        """Supplementary coverage: a frontmatter exceeding the documented
        byte bound fails closed with an explicit diagnostic naming the
        bound, never silently truncated or accepted. Entirely synthetic
        content.
        """
        oversized_header = (
            b"---\nid: WO-OVERSIZED\n"
            + b"x" * (starter_module._MAX_FRONTMATTER_BYTES + 100)
            + b"\n---\n"
        )
        record = self.temp / "WO-OVERSIZED.md"
        record.write_bytes(oversized_header)
        with self.assertRaisesRegex(
            starter_module.CoordinatorError, "exceeds the .*byte bound"
        ):
            starter_module._bounded_frontmatter_status(record)

    def test_safe_relative_stat_supplementary_no_leaf_measurement_through_symlinked_intermediate_directory(self):
        """Supplementary coverage for the already-corrected
        `_safe_relative_stat` I/O ordering: exercises the specific shape
        that correction targets -- a symlinked *intermediate* directory
        component, not a symlinked leaf (the existing routing-boundary test
        only covers the leaf case). Uses raw `Path.stat` instrumentation to
        prove the outside-root file reached only through the symlinked
        parent is never measured. Honestly skips if the executing account
        lacks symlink privilege.
        """
        project = self.temp / "intermediate-symlink-project"
        project.mkdir()
        outside_dir = self.temp / "outside-directory"
        outside_dir.mkdir()
        outside_file = outside_dir / "leaf.md"
        outside_content = b"Outside-root content reached through a symlinked parent.\n"
        outside_file.write_bytes(outside_content)
        linked_dir = project / "docs"
        try:
            linked_dir.symlink_to(outside_dir, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink privilege unavailable: {exc}")

        stat_calls: list[str] = []
        original_stat = Path.stat

        def recording_stat(self_path, *args, **kwargs):
            stat_calls.append(str(self_path))
            return original_stat(self_path, *args, **kwargs)

        with mock.patch.object(Path, "stat", recording_stat):
            size = starter_module._safe_relative_stat(project, "docs/leaf.md")

        self.assertIsNone(size)
        real_outside_file = str(outside_file.resolve())
        self.assertFalse(
            any(call == real_outside_file for call in stat_calls),
            "a leaf reached only through a symlinked intermediate directory "
            "must never be stat'd for its metadata",
        )

    def test_inspect_brief_explicit_architect_role_retained_on_adopted_lockout(self):
        """Supplementary coverage for the already-implemented Architect-
        scoped lockout guidance in `_render_lockout_brief`: an explicitly
        selected `--role architect` on an adopted-lockout project must
        receive Architect-scoped guidance, never the General planning/
        dispatch instruction. Synthetic ratified fixture.
        """
        governance = self.project / "governance"
        governance.mkdir()
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (governance / name).write_text(f"# {name}\n", encoding="utf-8")
        decision = governance / "decisions" / "DR-001.md"
        decision.parent.mkdir()
        decision.write_text(ratified_adoption_record(), encoding="utf-8")
        before = self.tree_snapshot(self.project)

        result = self.run_inspect("architect", brief=True)

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.state.exists())

        stdout = result.stdout
        self.assertIn("Selected role: Fresh Architect", stdout)
        self.assertIn("does not instruct a role change to General", stdout)
        self.assertNotIn("Prepare, but do not activate", stdout)

    def test_local_inventory_git_status_disables_optional_index_writes(self):
        with mock.patch.object(starter_module.shutil, "which", return_value="git"), \
                mock.patch.object(
                    starter_module.subprocess,
                    "run",
                    return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
                ) as run:
            self.assertEqual(starter_module._observe_git_cleanliness(self.project), "clean")

        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment["GIT_OPTIONAL_LOCKS"], "0")

    def test_inspect_never_invokes_repository_configured_git_processes(self):
        git_dir = self.project / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text(
            "ref: refs/heads/main\n", encoding="utf-8"
        )
        output = io.StringIO()
        with mock.patch.object(
            starter_module.subprocess,
            "run",
            side_effect=AssertionError("inspect must not execute git"),
        ), redirect_stdout(output):
            result = starter_module.inspect_main(
                ["--project-root", str(self.project), "--role", "architect"]
            )

        self.assertEqual(result, 0)
        self.assertIn("Git repository observed", output.getvalue())
        self.assertNotIn("Git working tree:", output.getvalue())

    def test_draft_adoption_record_with_closed_history_never_reports_adopted_or_retired(self):
        governance = self.project / "governance"
        governance.mkdir()
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (governance / name).write_text(f"# {name}\n", encoding="utf-8")
        decisions = governance / "decisions"
        decisions.mkdir(parents=True)
        (decisions / "DR-001.md").write_text(draft_adoption_record(), encoding="utf-8")
        (decisions / "DR-999-unrelated.md").write_text(
            unrelated_ratified_decision(), encoding="utf-8"
        )
        closed = governance / "history" / "WO-001.md"
        closed.parent.mkdir(parents=True)
        closed.write_text("---\nid: WO-001\nstatus: CLOSED\n---\n", encoding="utf-8")
        before = self.tree_snapshot(self.project)
        result = self.run_lifecycle_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.state.exists())
        self.assertNotIn("Observed lifecycle state: adopted_lockout", result.stdout)
        self.assertNotIn("Observed lifecycle state: retired_lockout", result.stdout)
        self.assertIn("Observed lifecycle state: partial_bootstrap", result.stdout)

    def test_signed_unrelated_decision_at_exact_adoption_path_fails_closed(self):
        governance = self.project / "governance"
        governance.mkdir()
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (governance / name).write_text(f"# {name}\n", encoding="utf-8")
        decisions = governance / "decisions"
        decisions.mkdir(parents=True)
        (decisions / "DR-001.md").write_text(
            unrelated_ratified_decision(), encoding="utf-8"
        )
        closed = governance / "history" / "WO-001.md"
        closed.parent.mkdir(parents=True)
        closed.write_text("---\nid: WO-001\nstatus: CLOSED\n---\n", encoding="utf-8")
        before = self.tree_snapshot(self.project)
        result = self.run_lifecycle_start()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.state.exists())
        self.assertNotIn("Observed lifecycle state: adopted_lockout", result.stdout)
        self.assertNotIn("Observed lifecycle state: retired_lockout", result.stdout)
        self.assertIn("inconsistent state", result.stderr)
        self.assertIn("does not carry", result.stderr)
        self.assertIn("adoption-record title", result.stderr)
        # Nondisclosing: the diagnostic names the path, never the document body.
        self.assertNotIn("Test Owner", result.stderr)
        self.assertNotIn("Naming decision", result.stderr)

    def test_adopted_lockout_requires_ratified_evidence_not_mere_filename(self):
        governance = self.project / "governance"
        governance.mkdir()
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (governance / name).write_text(f"# {name}\n", encoding="utf-8")
        decision = governance / "decisions" / "DR-001.md"
        decision.parent.mkdir(parents=True)
        decision.write_text("# Adoption record\n", encoding="utf-8")
        before = self.tree_snapshot(self.project)
        result = self.run_lifecycle_start()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertNotIn("Observed lifecycle state: adopted_lockout", result.stdout)
        self.assertIn("inconsistent state", result.stderr)
        self.assertIn("missing required Appendix D section", result.stderr)

    def test_retired_lockout_requires_ratified_adoption_evidence(self):
        governance = self.project / "governance"
        governance.mkdir()
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (governance / name).write_text(f"# {name}\n", encoding="utf-8")
        closed = governance / "history" / "WO-001.md"
        closed.parent.mkdir(parents=True)
        closed.write_text("---\nid: WO-001\nstatus: CLOSED\n---\n", encoding="utf-8")
        before = self.tree_snapshot(self.project)
        result = self.run_lifecycle_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertNotIn("Observed lifecycle state: retired_lockout", result.stdout)
        self.assertIn("Observed lifecycle state: partial_bootstrap", result.stdout)

    def test_alternate_adoption_record_path_routes_to_adopted_lockout(self):
        governance = self.project / "governance"
        governance.mkdir()
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (governance / name).write_text(f"# {name}\n", encoding="utf-8")
        (governance / "ADOPTION-RECORD.md").write_text(
            ratified_adoption_record(title="# Adoption record (alternate path)"),
            encoding="utf-8",
        )
        before = self.tree_snapshot(self.project)
        result = self.run_lifecycle_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertIn("Observed lifecycle state: adopted_lockout", result.stdout)

    def test_contradictory_coexisting_adoption_records_fail_closed(self):
        governance = self.project / "governance"
        governance.mkdir()
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (governance / name).write_text(f"# {name}\n", encoding="utf-8")
        decisions = governance / "decisions"
        decisions.mkdir(parents=True)
        (decisions / "DR-001.md").write_text(ratified_adoption_record(), encoding="utf-8")
        (governance / "ADOPTION-RECORD.md").write_text(
            ratified_adoption_record(
                title="# Adoption record (alternate path)", revision="0.6",
            ),
            encoding="utf-8",
        )
        before = self.tree_snapshot(self.project)
        result = self.run_lifecycle_start()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertIn("inconsistent state", result.stderr)
        self.assertIn("contradictory", result.stderr)

    def test_contradictory_baseline_between_coexisting_adoption_records_fails_closed(self):
        governance = self.project / "governance"
        governance.mkdir()
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (governance / name).write_text(f"# {name}\n", encoding="utf-8")
        decisions = governance / "decisions"
        decisions.mkdir(parents=True)
        (decisions / "DR-001.md").write_text(ratified_adoption_record(), encoding="utf-8")
        (governance / "ADOPTION-RECORD.md").write_text(
            ratified_adoption_record(
                title="# Adoption record (alternate path)", baseline="1" * 40,
            ),
            encoding="utf-8",
        )
        before = self.tree_snapshot(self.project)
        result = self.run_lifecycle_start()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.tree_snapshot(self.project), before)
        self.assertFalse(self.output.exists())
        self.assertIn("inconsistent state", result.stderr)
        self.assertIn("contradictory", result.stderr)
        self.assertIn("baseline", result.stderr)

    def test_owner_time_yes_defines_capture_and_no_records_not_reported(self):
        yes = self.run_start("--owner-time", "yes")
        self.assertEqual(yes.returncode, 0, yes.stdout + yes.stderr)
        handoff = self.handoff()
        flat = " ".join(handoff.split())
        self.assertIn("Owner active-minute capture: ENABLED", handoff)
        self.assertIn("Human reading, deciding, responding, authentication", flat)

        shutil.rmtree(self.output)
        no = self.run_start()
        self.assertEqual(no.returncode, 0, no.stdout + no.stderr)
        self.assertIn("Owner active minutes: NOT REPORTED", self.handoff())

    def test_external_operators_receive_separate_inert_packets(self):
        result = self.run_start(
            "--external-operator", "DNS authority migration",
            "--external-operator", "mail routing cutover",
            "--external-operator", "mailbox data migration",
            "--external-operator", "repository and website work",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        packets = sorted(p.name for p in (self.output / "operations").glob("*.md"))
        self.assertEqual(packets, [
            "dns-authority-migration.md",
            "mail-routing-cutover.md",
            "mailbox-data-migration.md",
            "repository-and-website-work.md",
        ])
        for path in (self.output / "operations").glob("*.md"):
            text = path.read_text(encoding="utf-8")
            for heading in (
                "## Preconditions", "## Permitted actions", "## Prohibited actions",
                "## Verification", "## Rollback", "## Evidence to return",
                "## Credential boundary",
            ):
                self.assertIn(heading, text)
            self.assertIn("confers no authority", text)

    def test_external_operator_packet_states_authorization_continuity_fields(self):
        packet = starter_module.operation_packet("Example function", "/example/project")
        self.assertIn("## Authorization", packet)
        for label in (
            "Approval source/reference:",
            "Approved action:",
            "Exact scope:",
            "Exclusions:",
            "Delegation permission:",
            "Lifecycle conditions:",
            "Completion boundary:",
        ):
            self.assertIn(label, packet)
        self.assertIn("evidence of a decision", packet)
        self.assertIn("not itself a decision", packet)

    def test_repository_role_handoffs_state_authorization_continuity_fields(self):
        """Table-driven: the same source/scope/delegation/conditions/completion
        contract used by the external Operator packet must also reach
        generated repository General and repository-Operator handoffs,
        including the zero-write adopted inspect route. Stable field labels
        are the emitted interface; prose around them is not asserted."""
        labels = (
            "Approval source/reference:",
            "Approved action:",
            "Exact scope:",
            "Exclusions:",
            "Delegation permission:",
            "Lifecycle conditions:",
            "Completion boundary:",
        )

        with self.subTest(surface="GENERAL_PROMPT constant"):
            for label in labels:
                self.assertIn(label, starter_module.GENERAL_PROMPT)

        packets = starter_module.architect_packets(
            SimpleNamespace(), (), "/example/project"
        )
        for packet_name in ("GENERAL.md", "OPERATOR.md", "REPOSITORY-OPERATOR.md"):
            with self.subTest(surface=f"architect_packets {packet_name}"):
                for label in labels:
                    self.assertIn(label, packets[packet_name])

        with self.subTest(surface="adopted zero-write inspect route (general role)"):
            governance = self.project / "governance"
            governance.mkdir()
            for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
                (governance / name).write_text(f"# {name}\n", encoding="utf-8")
            decision = governance / "decisions" / "DR-001.md"
            decision.parent.mkdir()
            decision.write_text(ratified_adoption_record(), encoding="utf-8")
            before = self.tree_snapshot(self.project)
            result = self.run_inspect("general")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(self.tree_snapshot(self.project), before)
            for label in labels:
                self.assertIn(label, result.stdout)

    def test_authorization_continuity_block_preserves_supplied_values_without_inventing_others(self):
        block = starter_module.authorization_continuity_block(
            approval_source="governance/decisions/DR-005.md",
            approved_action="Publish the v0.11.0 release archive.",
        )
        self.assertIn(
            "Approval source/reference: governance/decisions/DR-005.md", block
        )
        self.assertIn(
            "Approved action: Publish the v0.11.0 release archive.", block
        )
        for label in (
            "Exact scope", "Exclusions", "Delegation permission",
            "Lifecycle conditions", "Completion boundary",
        ):
            self.assertIn(
                f"{label}: {starter_module._AUTHORIZATION_UNKNOWN}", block
            )

    def test_generated_guidance_covers_b34_authorization_outcomes(self):
        """Table-driven: repository General guidance and the external Operator
        packet must each give distinguishing instruction for every B.3.4
        authorization outcome, not a generic keyword shared across cases.
        This is prose guidance for a reasoning agent, not a claim that the
        generator itself parses or validates arbitrary prose decisions."""
        cases = (
            (
                "matching current approval",
                "performs the already-authorized action once the provider itself permits it",
            ),
            (
                "missing approval",
                "says plainly that authorization is missing and stops",
            ),
            (
                "explicit revocation or supersession",
                "treats a revoked or superseded record as no longer authorizing anything",
            ),
            (
                "requested action beyond scope",
                "performs only the authorized part and names the excess as unauthorized",
            ),
            (
                "independent provider denial",
                "reports the provider's own denial as the exact blocker",
            ),
            (
                "environment prerequisite failure",
                "names the exact missing or failed environment prerequisite as the blocker",
            ),
            (
                "unapproved task creation or data transmission",
                "never creates or transmits a task, message, or dataset outside the approved action",
            ),
        )
        surfaces = {
            "GENERAL_PROMPT": starter_module.GENERAL_PROMPT,
            "external operation_packet": starter_module.operation_packet(
                "Example function", "/example/project"
            ),
        }
        for surface_name, text in surfaces.items():
            for outcome, expected_guidance in cases:
                with self.subTest(surface=surface_name, outcome=outcome):
                    self.assertIn(expected_guidance, text)

    def test_static_general_prompt_docs_stay_normalized_equal_to_generated_prompt(self):
        """Retrospective regression (WO-WW-027): the three static GENERAL_PROMPT
        copies (START-HERE.md, ADOPTING.md, skills/writwall-adopt/SKILL.md) must
        each carry the exact generated prompt text, whitespace-normalized, so a
        future change to the shared renderer cannot silently desync the docs.
        This does not weaken or alter GENERAL_PROMPT itself; it only pins the
        static copies to whatever it currently says."""
        normalized_prompt = " ".join(starter_module.GENERAL_PROMPT.split())
        for relative in (
            "START-HERE.md", "ADOPTING.md", "skills/writwall-adopt/SKILL.md",
        ):
            with self.subTest(document=relative):
                text = (REPO_ROOT / relative).read_text(encoding="utf-8")
                normalized_text = " ".join(text.split())
                self.assertIn(normalized_prompt, normalized_text)

    def test_dns_mail_scenario_is_split_without_real_values(self):
        result = self.run_start("--scenario", "dns-mail-migration")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        intake = self.intake()
        self.assertEqual(intake["external_operator_functions"], [
            "DNS provider selection",
            "DNS inventory and cutover",
            "mail routing cutover",
            "mailbox data migration",
            "repository and website work",
        ])
        combined = self.handoff() + "\n" + "\n".join(
            path.read_text(encoding="utf-8")
            for path in (self.output / "operations").glob("*.md")
        )
        scenario_text = combined.replace(
            self.project.resolve().as_posix(), "<canonical-project-root>"
        ).lower()
        self.assertNotIn("fastmail", scenario_text)
        self.assertNotIn("proton", scenario_text)
        self.assertNotIn("hllmr", scenario_text)
        self.assertIn("eight domains", combined.lower())
        self.assertIn("dns authority cutover", combined.lower())
        self.assertIn("historical mailbox data", combined.lower())
        self.assertLess(
            combined.lower().index("dns authority cutover"),
            combined.lower().index("change mail routing"),
        )

    def test_complete_bundle_is_byte_identical_to_source(self):
        result = self.run_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        source = REPO_ROOT / "skills" / "writwall-adopt"
        copied = self.output / "writwall-adopt"
        source_files = sorted(
            path.relative_to(source).as_posix()
            for path in source.rglob("*") if path.is_file()
        )
        copied_files = sorted(
            path.relative_to(copied).as_posix()
            for path in copied.rglob("*") if path.is_file()
        )
        self.assertEqual(copied_files, source_files)
        for relative in source_files:
            self.assertEqual((copied / relative).read_bytes(),
                             (source / relative).read_bytes(), relative)

    def test_clean_new_handoff_routes_bootstrap_charter_addendum(self):
        result = self.run_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        handoff = self.handoff()
        self.assertIn(
            ".writwall-bootstrap/writwall-adopt/assets/"
            "bootstrap-charter-addendum.md",
            handoff,
        )
        self.assertIn("Ordinary no-pointer work", handoff)
        self.assertIn("confers no mutation authority", handoff)

    def test_clean_new_handoff_carries_terminal_fresh_architect_prompt(self):
        result = self.run_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        handoff = self.handoff()
        self.assertIn("After adoption closeout", handoff)
        self.assertIn(starter_module.PROJECT_ARCHITECT_PROMPT, handoff)
        self.assertIn("onboarding coordinator stops", handoff)

    def test_name_clearance_proof_tools_are_canonical_in_emitted_bundle(self):
        result = self.run_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        copies = {
            "assets/scripts/collect_name_clearance.py":
                REPO_ROOT / "scripts" / "collect_name_clearance.py",
            "assets/checks/check_name_clearance.py":
                REPO_ROOT / "checks" / "check_name_clearance.py",
            "references/name-clearance.md":
                REPO_ROOT / "docs" / "name-clearance.md",
        }
        for relative, canonical in copies.items():
            bundled = self.output / "writwall-adopt" / relative
            self.assertTrue(bundled.is_file(), relative)
            self.assertEqual(bundled.read_bytes(), canonical.read_bytes(), relative)

    def test_role_split_recommends_minimum_and_bounded_external_functions(self):
        result = self.run_start(
            "--external-operator", "DNS administration",
            "--external-operator", "mail administration",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        handoff = self.handoff()
        self.assertIn("Recommended smallest credible role split", handoff)
        self.assertIn(
            "one human Owner, one Architect, one General, one repository Operator",
            handoff,
        )
        self.assertIn("The Architect may interview", handoff)
        self.assertIn("The General may draft, route", handoff)
        self.assertIn("2 separately bounded external function packet(s)", handoff)

    def test_windows_reserved_operator_name_is_made_portable(self):
        result = self.run_start("--external-operator", "CON")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.output / "operations" / "operator-con.md").is_file())

    def test_dangling_output_symlink_is_a_collision(self):
        missing = self.project / "missing-output-target"
        try:
            self.output.symlink_to(missing, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        result = self.run_start()
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.output.is_symlink())
        self.assertFalse(missing.exists())

    def test_atomic_publication_failure_leaves_no_target_output_or_stage(self):
        args = SimpleNamespace(
            project_name="Example",
            purpose="Example purpose",
            agent="Codex",
            location="desktop",
            environment="local repository",
            owner_time="no",
            scenario=None,
        )
        state = starter_module.ObservedState(
            "clean_new", ("activation pointer is absent",)
        )
        stage_pattern = f".{self.project.name}-writwall-bootstrap-stage-*"
        with mock.patch.object(
            starter_module, "_atomic_publish",
            side_effect=OSError("injected rename failure"),
        ):
            with self.assertRaises(starter_module.CoordinatorError) as raised:
                starter_module.write_bootstrap(self.project, args, state, (), 1)
        self.assertIn("before atomic publication", str(raised.exception))
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.project.parent.glob(stage_pattern)), [])

    def test_destination_appearing_during_publication_is_never_replaced(self):
        args = SimpleNamespace(
            project_name="Example", purpose="Example purpose", agent="Codex",
            location="desktop", environment="local repository", owner_time="no",
            scenario=None,
        )
        state = starter_module.ObservedState(
            "clean_new", ("activation pointer is absent",)
        )
        actual_publish = starter_module._atomic_publish

        def competing_publication(stage: Path, output: Path) -> None:
            output.mkdir()
            actual_publish(stage, output)

        with mock.patch.object(
            starter_module, "_atomic_publish", side_effect=competing_publication
        ):
            with self.assertRaises(starter_module.CoordinatorError) as raised:
                starter_module.write_bootstrap(self.project, args, state, (), 1)
        self.assertIn(
            "Writwall published no target; an independently existing destination may remain",
            str(raised.exception),
        )
        self.assertTrue(self.output.is_dir())
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertEqual(list(self.project.parent.glob(
            f".{self.project.name}-writwall-bootstrap-stage-*"
        )), [])

    def test_nested_history_symlink_stops_before_external_read(self):
        external = self.temp / "external-history"
        external.mkdir()
        (external / "WO-001.md").write_text(
            "---\nid: WO-001\nstatus: CLOSED\n---\nSECRET-SENTINEL\n",
            encoding="utf-8",
        )
        governance = self.project / "governance"
        governance.mkdir()
        for name in ("PLAN.md", "STATE.md", "ROUTING.md"):
            (governance / name).write_text(f"# {name}\n", encoding="utf-8")
        try:
            (governance / "history").symlink_to(external, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        result = self.run_start()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        self.assertIn("symlink", (result.stdout + result.stderr).lower())
        self.assertNotIn("SECRET-SENTINEL", result.stdout + result.stderr)

    def test_junction_detection_fallback_is_exercised(self):
        ordinary = self.project / "ordinary"
        ordinary.mkdir()
        with mock.patch.object(
            starter_module.os.path, "isjunction", create=True, return_value=True
        ):
            self.assertTrue(starter_module._is_linklike(ordinary))

    def test_interactive_flow_offers_brief_and_time_capture_before_intake(self):
        brief = self.temp / "existing-brief.md"
        brief.write_text("Existing project thesis.\n", encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable, "-B", str(STARTER),
                "--structured-intake",
                "--project-root", str(self.project),
                "--project-name", "Interactive project",
            ],
            cwd=REPO_ROOT,
            env=self.environment(),
            input=(
                "yes\n"  # Owner-time choice
                "yes\n"  # no-secret confirmation
                f"{brief}\n"
                "\n"  # default agent
                "\n"  # default location
                "\n"  # default environment
                "\n"  # no external functions
            ),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertLess(
            result.stdout.index("Track Owner active minutes"),
            result.stdout.index("Continue without entering secrets"),
        )
        self.assertIn("Existing project brief file path", result.stdout)
        self.assertEqual(self.intake()["purpose"], "Existing project thesis.")

    def test_interactive_unnamed_idea_is_qualified_one_question_at_a_time(self):
        answers = (
            "no\n" "yes\n" "\n" "\n"
            "Important decisions disappear before implementation.\n"
            "Technical founders.\n"
            "Rework is costly.\n"
            "Two failed prototypes; demand is assumed.\n"
            "A ratifiable discovery packet.\n"
            "Owner can approve or stop.\n"
            "Local-only.\n"
            "No deployment.\n"
            "May be too heavy.\n"
            "Stop if no useful outcome emerges.\n"
            "A written brief.\n"
            "\n" "\n" "\n" "\n"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-m", "writwall_cli", "start",
             "--structured-intake",
             "--project-root", str(self.project)],
            cwd=REPO_ROOT,
            env=self.environment(),
            input=answers,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        prompts = (
            "Problem or opportunity", "Intended user", "Why the outcome matters",
            "Current evidence and assumptions", "Smallest useful outcome",
            "Success signal", "Constraints", "Non-goals", "Material risks",
            "Stop or kill conditions", "Existing assets",
        )
        positions = [result.stdout.index(prompt) for prompt in prompts]
        self.assertEqual(positions, sorted(positions))
        discovery = json.loads(
            (self.output / "discovery.json").read_text(encoding="utf-8")
        )
        self.assertEqual(discovery["identity"]["state"], "unnamed")

    def test_brief_file_is_read_but_never_modified(self):
        brief = self.temp / "brief.md"
        brief.write_text("A supplied project thesis.\n", encoding="utf-8")
        result = self.run_start("--brief-file", str(brief))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(brief.read_text(encoding="utf-8"),
                         "A supplied project thesis.\n")
        self.assertEqual(self.intake()["purpose"], "A supplied project thesis.")

    def test_existing_brief_emits_architect_packets_with_explicit_unknowns(self):
        brief = self.temp / "architect-brief.md"
        brief.write_text("A supplied project thesis.\n", encoding="utf-8")
        result = self.run_start("--brief-file", str(brief))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        discovery = json.loads(
            (self.output / "discovery.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            discovery["qualification"]["problem_or_opportunity"],
            "A supplied project thesis.",
        )
        self.assertIsNone(discovery["qualification"]["intended_user"])
        for relative in (
            "OWNER-AGENT.md", "REPOSITORY-OPERATOR.md", "REVIEWER.md",
            "NAME-CLEARANCE.md", "OWNER-RATIFICATION.md",
        ):
            self.assertTrue((self.output / relative).is_file(), relative)

    def test_paths_are_recorded_portably(self):
        result = self.run_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = (self.output / "intake.json").read_text(encoding="utf-8")
        self.assertNotIn("\\", text)
        self.assertIn(".writwall-bootstrap", self.handoff())

    def test_intake_records_one_resolved_canonical_project_root(self):
        result = self.run_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        canonical = self.project.resolve()
        self.assertEqual(self.intake()["project_root"], canonical.as_posix())
        self.assertNotEqual(self.intake()["project_root"], ".")

    def test_discovery_record_carries_the_same_canonical_project_root(self):
        result = self.run_idea_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        canonical = self.project.resolve()
        discovery = json.loads(
            (self.output / "discovery.json").read_text(encoding="utf-8")
        )
        self.assertEqual(discovery.get("project_root"), canonical.as_posix())

    def test_every_generated_role_packet_carries_the_canonical_project_root(self):
        result = self.run_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        canonical = self.project.resolve()
        for relative in (
            "HANDOFF.md", "OWNER-AGENT.md", "REPOSITORY-OPERATOR.md",
            "REVIEWER.md", "NAME-CLEARANCE.md", "OWNER-RATIFICATION.md",
        ):
            text = (self.output / relative).read_text(encoding="utf-8")
            self.assert_contains_canonical_root(text, canonical, relative)

    def test_handoff_states_the_no_shadow_repository_no_durable_temp_rule(self):
        result = self.run_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        handoff = self.handoff()
        flat = " ".join(handoff.split()).lower()
        self.assertIn("durable project artifacts", flat)
        self.assertIn("never become the authoritative project tree", flat)
        self.assertIn("removed after use", flat)

    def test_operation_packets_carry_root_and_no_shadow_repository_rule(self):
        result = self.run_start("--external-operator", "DNS administration")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        canonical = self.project.resolve()
        packet = (self.output / "operations" / "dns-administration.md").read_text(
            encoding="utf-8"
        )
        self.assert_contains_canonical_root(packet, canonical, "operation packet")
        self.assertIn("shadow", packet.lower())
        self.assertIn("canonical", packet.lower())

    def test_supplied_path_spelling_is_resolved_to_one_canonical_form(self):
        spelled = str(self.project) + os.sep + "." + os.sep
        result = subprocess.run(
            [
                sys.executable, "-B", "-m", "writwall_cli", "start",
                "--non-interactive",
                "--project-root", spelled,
                "--project-name", "Example project",
                "--purpose", "Build a small, governed project.",
                "--agent", "Codex",
                "--location", "local workstation",
                "--environment", "local repository only",
                "--owner-time", "no",
                "--confirm-no-secrets",
            ],
            cwd=REPO_ROOT,
            env=self.environment(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        canonical = self.project.resolve()
        self.assertEqual(self.intake()["project_root"], canonical.as_posix())

    def test_non_git_project_directory_is_recorded_canonically(self):
        result = self.run_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.project / ".git").exists())
        canonical = self.project.resolve()
        self.assertEqual(self.intake()["project_root"], canonical.as_posix())

    def test_git_worktree_top_level_is_recorded_as_its_own_canonical_root(self):
        worktree = self.make_git_worktree(
            "wt-top-repo", "wt-top-worktree", "wt-top-branch"
        )
        result = self.run_start(project=worktree)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        intake = json.loads(
            ((worktree / ".writwall-bootstrap") / "intake.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(intake["project_root"], worktree.resolve().as_posix())

    def test_nested_directory_inside_git_worktree_stops_with_rerun_diagnostic(self):
        worktree = self.make_git_worktree(
            "wt-nested-repo", "wt-nested-worktree", "wt-nested-branch"
        )
        nested = worktree / "nested" / "project"
        nested.mkdir(parents=True)
        before = self.tree_snapshot(worktree)
        result = subprocess.run(
            [
                sys.executable, "-B", "-m", "writwall_cli", "start",
                "--non-interactive",
                "--project-root", str(nested),
                "--project-name", "Example project",
                "--purpose", "Build a small, governed project.",
                "--agent", "Codex",
                "--location", "local workstation",
                "--environment", "local repository only",
                "--owner-time", "no",
                "--confirm-no-secrets",
            ],
            cwd=REPO_ROOT,
            env=self.environment(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.tree_snapshot(worktree), before)
        self.assertFalse((nested / ".writwall-bootstrap").exists())
        combined = (result.stdout + result.stderr).lower()
        self.assertIn("worktree", combined)
        self.assertIn("rerun", combined)
        self.assert_contains_canonical_root(
            result.stdout + result.stderr, worktree.resolve(),
            "worktree rerun diagnostic",
        )

    def test_environment_is_captured_without_becoming_authority(self):
        result = self.run_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            self.intake()["repository_external_environment"],
            "local repository with separately administered hosting",
        )
        self.assertIn(
            "Repository and external environment: local repository with separately administered hosting",
            self.handoff(),
        )
        self.assertEqual(self.intake()["authority"], "unratified_intake_only")

    def test_start_initializes_privacy_without_disclosing_its_location(self):
        result = self.run_idea_start()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        intake = self.intake()
        self.assertTrue(intake["privacy_screen"]["ready"])
        self.assertGreater(intake["privacy_screen"]["entry_count"], 0)
        combined = result.stdout + result.stderr + self.handoff()
        self.assertNotIn(str(self.state), combined)
        self.assert_contains_canonical_root(
            self.handoff(), self.project.resolve(), "HANDOFF.md"
        )
        self.assertEqual(len(list(self.state.rglob("private-patterns.txt"))), 1)

    def test_start_preserves_local_private_identifiers_without_copying_them_to_bootstrap(self):
        private_identifier = "CLIENT-CODENAME-EMBER"
        added = subprocess.run(
            [sys.executable, "-B", "-m", "writwall_cli", "privacy", "add",
             "--project-root", str(self.project), "--identifier-stdin",
             "--confirm-no-secrets"],
            cwd=REPO_ROOT, env=self.environment(), input=private_identifier + "\n",
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(added.returncode, 0, added.stdout + added.stderr)
        result = self.run_idea_start()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        bootstrap_text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in self.output.rglob("*") if path.is_file()
        )
        self.assertNotIn(private_identifier, result.stdout + result.stderr)
        self.assertNotIn(private_identifier, bootstrap_text)
        profile = next(self.state.rglob("private-patterns.txt"))
        self.assertIn(private_identifier, profile.read_text(encoding="utf-8"))

    # -- WO-WW-021: conversation-first inception and existing-project
    # continuity. Prove the ordinary bare invocation no longer demands the
    # long structured questionnaire, existing repositories get a bounded
    # local inventory and conversation-first Architect opening, empty
    # projects get one open invitation, structured/non-interactive intake
    # still works and now also emits the Owner/Architect/General/Operator
    # topology, and active work still routes to a bounded Operator/
    # Implementer. Added RED in this work order; now exercised against the
    # GREEN implementation.

    def run_conversation_start(self, *extra: str, project: Path | None = None):
        """The ordinary, low-friction invocation: only --project-root, no
        other intake flags, and no answers available on stdin. Today this
        falls straight into the full interactive questionnaire and crashes
        with EOFError on the first blocking `input()` call; the conversation
        -first coordinator must instead succeed without it.
        """
        return subprocess.run(
            [
                sys.executable, "-B", "-m", "writwall_cli", "start",
                "--project-root", str(project or self.project),
                *extra,
            ],
            cwd=REPO_ROOT,
            env=self.environment(),
            input="",
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_ordinary_project_root_only_invocation_skips_long_questionnaire(self):
        result = self.run_conversation_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        combined = result.stdout + result.stderr
        for legacy_prompt in (
            "Track Owner active minutes?",
            "Continue without entering secrets?",
            "Problem or opportunity",
            "Working candidate name",
        ):
            self.assertNotIn(legacy_prompt, combined)

    def test_existing_git_repository_yields_bounded_local_observations_and_architect_opening(self):
        init = self.git("init", "--quiet", cwd=self.project)
        if init.returncode != 0:
            self.skipTest(f"git unavailable: {init.stderr}")
        self.git("config", "user.email", "test@example.invalid", cwd=self.project)
        self.git("config", "user.name", "Test", cwd=self.project)
        (self.project / "README.md").write_text("An existing project.\n", encoding="utf-8")
        self.git("add", "README.md", cwd=self.project)
        commit = self.git(
            "commit", "--quiet", "-m", "Seed existing project inventory marker",
            cwd=self.project,
        )
        self.assertEqual(commit.returncode, 0, commit.stdout + commit.stderr)
        branch = self.git("branch", "--show-current", cwd=self.project).stdout.strip()
        self.assertTrue(branch)

        # A direct ordinary Git repository root (not a linked or nested
        # worktree) used as the project root itself.
        result = self.run_conversation_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        combined = result.stdout + result.stderr + self.handoff()
        self.assertIn(branch, combined)
        self.assertIn("Seed existing project inventory marker", combined)
        self.assertIn("clean", combined.lower())
        self.assertIn("read-only", combined.lower())
        self.assertTrue(
            "explore" in combined.lower() or "start elsewhere" in combined.lower(),
            combined,
        )

    def test_empty_new_project_receives_open_conversational_invitation(self):
        result = self.run_conversation_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        combined = result.stdout + result.stderr + self.handoff()
        self.assertIn("Tell me what you are thinking", combined)
        self.assertNotIn("Problem or opportunity", combined)
        self.assertNotIn("Working candidate name", combined)

    def test_conversation_first_partial_idea_flags_keep_validation(self):
        result = self.run_conversation_start(
            "--problem", "A stated problem without the remaining qualification.",
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("missing idea qualification", result.stderr)
        self.assertFalse(self.output.exists())

    def test_conversation_first_contradictory_idea_flags_keep_validation(self):
        flags = [
            "--problem", "A fully stated idea.",
            "--intended-user", "The Owner.",
            "--why-matters", "It avoids drift.",
            "--evidence", "A concrete observed failure.",
            "--smallest-outcome", "One bounded fix.",
            "--success-signal", "The regression stays green.",
            "--constraint", "Do not publish.",
            "--non-goal", "Do not publish.",
            "--risk", "The intake could overreach.",
            "--kill-condition", "Stop on ambiguity.",
            "--asset", "The existing repository.",
        ]
        result = self.run_conversation_start(*flags)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("contradictory idea qualification", result.stderr)
        self.assertFalse(self.output.exists())

    def test_structured_non_interactive_intake_still_emits_new_role_topology(self):
        result = self.run_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.output / "ARCHITECT.md").is_file())
        self.assertTrue((self.output / "GENERAL.md").is_file())
        self.assertTrue((self.output / "OPERATOR.md").is_file())
        self.assertTrue((self.output / "REPOSITORY-OPERATOR.md").is_file())
        self.assertTrue((self.output / "REVIEWER.md").is_file())

    def test_legacy_role_packet_names_remain_as_documented_compatibility_aliases(self):
        result = self.run_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        owner_agent = (self.output / "OWNER-AGENT.md").read_text(encoding="utf-8")
        repository_operator = (self.output / "REPOSITORY-OPERATOR.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("compatibility alias", owner_agent.lower())
        self.assertIn("Architect", owner_agent)
        self.assertIn("compatibility alias", repository_operator.lower())
        self.assertIn("Operator", repository_operator)

    def test_active_work_order_routes_to_bounded_operator_implementer(self):
        work_order = self.project / "governance" / "work-orders" / "WO-001.md"
        work_order.parent.mkdir(parents=True)
        work_order.write_text(
            "---\nid: WO-001\nstatus: ACTIVE\n---\n# Work\n", encoding="utf-8"
        )
        pointer = self.project / ".claude" / "active-wo.txt"
        pointer.parent.mkdir(parents=True)
        pointer.write_text("governance/work-orders/WO-001.md\n", encoding="utf-8")
        result = self.run_lifecycle_start()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Observed lifecycle state: active_work_order", result.stdout)
        self.assertIn("Operator", result.stdout)


if __name__ == "__main__":
    unittest.main()
