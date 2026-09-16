# SPDX-FileCopyrightText: 2026 HLLMR Ventures LLC
# SPDX-License-Identifier: Apache-2.0
"""Create a local-first Writwall bootstrap handoff without adopting a project."""

from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))
SOURCE_BUNDLE = SOURCE_ROOT / "skills" / "writwall-adopt"
INSTALLED_BUNDLE = Path(sys.prefix) / "share" / "writwall" / "writwall-adopt"
BUNDLE_SOURCE = INSTALLED_BUNDLE if INSTALLED_BUNDLE.is_dir() else SOURCE_BUNDLE
OUTPUT_NAME = ".writwall-bootstrap"
SECRET_WARNING = (
    "Do not enter passwords, API tokens, private keys, mail contents, DNS "
    "record values, or other secrets. This tool writes your answers as plain "
    "text inside the target project."
)
_AUTHORIZATION_UNKNOWN = "unknown: not yet transcribed from an already-authorized record"


def authorization_continuity_block(
    *,
    approval_source: str | None = None,
    approved_action: str | None = None,
    exact_scope: str | None = None,
    exclusions: str | None = None,
    delegation_permission: str | None = None,
    lifecycle_conditions: str | None = None,
    completion_boundary: str | None = None,
) -> str:
    """Render the one shared Authorization section for every generated handoff.

    A field carries an already-authorized record's own reference and wording
    when the preparer supplies one, including an equivalent legacy record's
    existing scope and stated authority transcribed verbatim; the human Owner
    never retypes or re-approves it. A field left unset renders as explicitly
    unknown rather than a fabricated value: that means the preparer has not
    yet located it in an already-authorized current record, not that no such
    record exists, and the preparer inspects those records before asking
    anyone. Only a field genuinely missing from every authorized record is a
    question for the Owner; a blank field alone never invalidates existing
    adoption or authority. This function performs no natural-language
    parsing; a caller supplies each value only from a record it has already
    read.
    """
    fields = (
        ("Approval source/reference", approval_source),
        ("Approved action", approved_action),
        ("Exact scope", exact_scope),
        ("Exclusions", exclusions),
        ("Delegation permission", delegation_permission),
        ("Lifecycle conditions", lifecycle_conditions),
        ("Completion boundary", completion_boundary),
    )
    lines = "\n".join(
        f"- {label}: {value if value else _AUTHORIZATION_UNKNOWN}"
        for label, value in fields
    )
    return f"""## Authorization

{lines}

This section carries forward evidence of a decision already made elsewhere;
it is not itself a decision, and it never substitutes for an independent
provider authorization. A field populated above transcribes that
already-authorized record's own reference and wording; the human Owner never
retypes or re-approves it. A field left unknown above means the preparer has
not yet located it in an already-authorized current record; the preparer
inspects those records before asking anyone. Only a genuinely missing, materially necessary decision is a question for the Owner; the absence of optional or formal metadata is not itself an approval loop, and an existing valid legacy approval remains usable without new paperwork.

Matching current approval: performs the already-authorized action once the provider itself permits it.
Missing approval: says plainly that authorization is missing and stops.
Explicit revocation or supersession: treats a revoked or superseded record as no longer authorizing anything.
Requested action beyond scope: performs only the authorized part and names the excess as unauthorized.
Independent provider denial: reports the provider's own denial as the exact blocker.
Environment prerequisite failure: names the exact missing or failed environment prerequisite as the blocker.
Unapproved task creation or data transmission: never creates or transmits a task, message, or dataset outside the approved action."""


GENERAL_PROMPT = f"""Act as a fresh General for this already-adopted project's continuity. Begin
read-only and verify the lifecycle from repository bytes rather than prior chat. Read the
charter, Plan, State, Routing, ratified adoption record, and open transactional records. State
the project's next decision plainly. Prepare, but do not activate, the smallest genuine work
order or bounded Operator packet; route it to a fresh Architect instead only when the next
decision requires new design or design-conformance judgment rather than routine continuity. Lead
with a concise Recommendation and material tradeoff; keep the detailed packet behind it as
supporting evidence rather than the conversational front door. When the next safe mechanical
action is available, ask once for one combined disposition and action. If that action uses a new
user-owned task, explicitly include creation and dispatch of the named task in that approval
request; never infer task-creation permission afterward. Carry that approval's continuity in the
shared Authorization section below, transcribed from an already-authorized current record rather
than retyped or re-approved by the Owner.

{authorization_continuity_block()}

Once approved, perform every
mechanically available authorized step. Do not ask for the same decision again. The human Owner
alone ratifies intent and activates work; preserve a distinct fresh Reviewer after
implementation. The onboarding coordinator stops here and does not continue into project work."""

# Compatibility export for existing imports and synchronized static handoff
# tests. The post-adoption role formerly called Project-Architect is now the
# General; retaining this symbol does not retain the obsolete role semantics.
PROJECT_ARCHITECT_PROMPT = GENERAL_PROMPT

ARCHITECT_EXISTING_PROJECT_PROMPT = """Act as the Architect. Begin read-only; do not implement, install, or adopt
anything yet. Before asking the Owner to restate anything already visible in repository bytes,
use the observed lifecycle state and local evidence recorded above, and inspect other
high-signal local material (README-like files, top-level structure, and recent history) the same
way. Summarize the apparent project in plain language from that evidence alone. Then ask the
Owner plainly whether they want to explore and develop this existing work, or start elsewhere
with a different idea. Treat every local observation as evidence only, never as ratified intent;
the human Owner alone decides and ratifies. Read discovery.json and ARCHITECT.md in this
directory for the complete procedure, including the required project sketch, recommended
Owner/Architect/General/Operator topology, provisional first backlog, key uncertainties and
risks, and the one explicit Owner promotion decision before any adoption mechanics begin."""

ARCHITECT_EMPTY_PROJECT_PROMPT = """Act as the Architect for a new, empty project; no existing
project material was found at this root. Begin read-only and do not implement, install, or adopt
anything yet. Do not impose a fixed list of qualification questions.

Open with exactly: "Tell me what you are thinking."

Let the Owner's own words guide every question that follows, one at a time. Nothing said is
ratified intent until the human Owner explicitly ratifies it. Read discovery.json and
ARCHITECT.md in this directory for the complete procedure, including the required project
sketch, recommended Owner/Architect/General/Operator topology, provisional first backlog, key
uncertainties and risks, and the one explicit Owner promotion decision before any adoption
mechanics begin."""

ARCHITECT_PREPARED_INTAKE_PROMPT = f"""Act as a fresh Writwall Architect. Begin read-only; do
not implement, install, register a wall, adopt the project, or activate work. Read
`.writwall-bootstrap/intake.json`, `discovery.json`, and `ARCHITECT.md`. Treat every collected
answer as unratified discovery evidence, not authority. Summarize the Owner's apparent pitch in
plain language, challenge material assumptions and alternatives, and continue the conversation
one question at a time for as long as it is useful. Produce a project sketch, recommended
Owner/Architect/General/Operator topology, provisional backlog, uncertainties, risks, and stop
conditions. Nothing advances until the human Owner explicitly promotes that sketch.

Only after explicit promotion, use the local `writwall-adopt` bundle to prepare the proposed
adoption and recorder actions. The Owner separately ratifies material intent and authorizes
mechanics. Before wall registration or any Level 1 call, copy
`.writwall-bootstrap/writwall-adopt/assets/bootstrap-charter-addendum.md` verbatim into the
engine-visible pre-adoption charter. Ordinary no-pointer work remains forbidden; the addendum
permits only exact expected-denial probes named by a durably Owner-ratified lifecycle. It confers no mutation authority. Denial is the only valid outcome, and any success stops adoption. Remove
the addendum before the adoption commit. Do not begin product work or WO-001 before adoption.
After adoption closeout, present
the following exact fresh-role handoff and stop; the Architect does not continue as General:

{GENERAL_PROMPT}"""

DNS_MAIL_SCENARIO = (
    "DNS provider selection",
    "DNS inventory and cutover",
    "mail routing cutover",
    "mailbox data migration",
    "repository and website work",
)
DNS_MAIL_SCENARIO_CONTEXT = (
    "Move authoritative DNS for eight domains first; only after verified DNS "
    "authority cutover, change mail routing; separately inventory, clean, and "
    "migrate historical mailbox data."
)
WINDOWS_RESERVED_STEMS = frozenset({
    "con", "prn", "aux", "nul", "clock$",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
})


class CoordinatorError(RuntimeError):
    """A safe, user-facing stop before the published output exists."""


@dataclass(frozen=True)
class ObservedState:
    name: str
    evidence: tuple[str, ...]
    active_work_order: str | None = None


def _is_linklike(path: Path) -> bool:
    """Return true for symlinks and Windows junction/reparse entries."""
    try:
        if path.is_symlink():
            return True
        isjunction = getattr(os.path, "isjunction", None)
        if isjunction and isjunction(path):
            return True
        try:
            attributes = path.lstat().st_file_attributes
        except FileNotFoundError:
            return False
        except AttributeError:
            return False
        return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        return True


def _entry_exists(path: Path) -> bool:
    """Unlike Path.exists(), include dangling symlinks and reparse entries."""
    try:
        return os.path.lexists(path)
    except OSError:
        return True


def _is_python_bytecode_residue(path: Path, root: Path) -> bool:
    """Identify interpreter-created files that are not canonical bundle assets."""
    relative = path.relative_to(root)
    return (
        any(part.casefold() == "__pycache__" for part in relative.parts)
        or path.suffix.casefold() == ".pyc"
    )


def _safe_project_path(project: Path, path: Path, label: str) -> Path:
    """Reject linklike components and containment escapes before any read."""
    try:
        relative = path.relative_to(project)
    except ValueError as exc:
        raise CoordinatorError(f"inconsistent state: {label} is outside the project") from exc
    current = project
    for part in relative.parts:
        current = current / part
        if _is_linklike(current):
            raise CoordinatorError(
                f"inconsistent state: {label} contains a symlink, junction, or reparse entry"
            )
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise CoordinatorError(f"inconsistent state: {label} is unreadable: {exc}") from exc
    if resolved != project and project not in resolved.parents:
        raise CoordinatorError(f"inconsistent state: {label} resolves outside the project")
    return resolved


def frontmatter_status(path: Path) -> str | None:
    """Read only an exact top-level status scalar from opening frontmatter."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        raise CoordinatorError(f"cannot read pointed work order: {exc}") from exc
    if not lines or lines[0] != "---":
        return None
    for line in lines[1:]:
        if line == "---":
            break
        if line.startswith((" ", "\t")):
            continue
        match = re.fullmatch(r"status:\s*(['\"]?)([^'\"#]+)\1\s*(?:#.*)?", line)
        if match:
            return match.group(2).strip()
    return None


def _safe_pointer_target(project: Path, value: str) -> Path:
    raw = value.strip().replace("\\", "/")
    if not raw or "\n" in raw or "\r" in raw:
        raise CoordinatorError("inconsistent state: activation pointer is empty or multiline")
    parts = tuple(part for part in raw.split("/") if part)
    if parts[:2] != ("governance", "work-orders") or any(
        part in (".", "..") for part in parts
    ):
        raise CoordinatorError(
            "inconsistent state: activation pointer is not a repository-relative "
            "governance/work-orders path"
        )
    target = project.joinpath(*parts)
    resolved_target = _safe_project_path(
        project, target, "activation pointer target"
    )
    work_orders = _safe_project_path(
        project, project / "governance" / "work-orders", "work-order directory"
    )
    if work_orders not in resolved_target.parents or not resolved_target.is_file():
        raise CoordinatorError(
            "inconsistent state: activation pointer target is outside the work-order "
            "directory or not a regular file"
        )
    return resolved_target


_ADOPTION_TITLE = re.compile(r"(?im)^#[ \t]+.*\bAdoption record\b")
_ADOPTION_DRAFT_MARKER = re.compile(
    r"\b(?:DRAFT|PROPOSED|UNRATIFIED|PENDING|PLACEHOLDER|TBD|TODO|UNSIGNED)\b",
    re.IGNORECASE,
)
_UNRESOLVED_CHECKLIST_ITEM = re.compile(r"(?m)^[ \t]*-[ \t]*\[[ \t]\]")
_ADOPTION_PLACEHOLDER_TOKEN = re.compile(
    r"(?i)\[[ \t]*(?:date|owner|hash|name|insert|fill[- ]?in|tbd|todo|xxx)\b[^\]]*\]"
)
_SIGNATURE_HEADING = re.compile(r"(?im)^#{1,6}[ \t]+(?:[A-Z]+\.\d+[ \t]+)?Signature\b.*$")
_HEADING_LINE = re.compile(r"(?m)^#{1,6}[ \t]")
_SIGNATURE_DATE = re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b")
_ADOPTION_REVISION = re.compile(r"(?im)Revision[ \t]+\*{0,2}([0-9]+\.[0-9]+)\*{0,2}")
_ADOPTION_OWNER_FIELD = re.compile(r"(?im)^.*\bOwner:[ \t]*([^\n\r·]+)$")
_ADOPTION_BASELINE_HASH = re.compile(r"`([0-9a-fA-F]{7,40})`")
_ADOPTION_REQUIRED_SECTION_NUMBERS = tuple(range(1, 10))


def _adoption_section_block(text: str, number: str) -> str:
    """Return one Appendix D `D.<number>` section's own text.

    Stops at the next heading whose `D.<n>` prefix differs, so a nested
    `D.<number>.x` subsection (as used by this repository's own D.4) stays
    inside the block instead of truncating it.
    """
    pattern = re.compile(
        rf"(?ms)^#{{1,6}}[ \t]*D\.{re.escape(number)}\b.*?"
        rf"(?=^#{{1,6}}[ \t]*D\.(?!{re.escape(number)}\b)\d|\Z)"
    )
    match = pattern.search(text)
    return match.group(0) if match else ""


@dataclass(frozen=True)
class AdoptionEvidence:
    """One candidate adoption-record path and its deterministic ratification status."""
    relative: str
    status: str
    reason: str
    revision: str | None = None
    owner: str | None = None
    baseline: str | None = None

    @property
    def ratified(self) -> bool:
        return self.status == "ratified"


def _classify_adoption_record(project: Path, resolved_path: Path) -> AdoptionEvidence:
    """Require complete, affirmative Appendix D ratification evidence.

    A filename, a signed-but-unrelated document, or a partial Appendix D
    section set is never adoption authority. An explicit draft/proposed/
    pending/unsigned/placeholder signal routes to recovery (status
    "draft"); anything else at this exact adoption-record path that fails
    to carry recognizable, complete Appendix D content is "malformed" and
    the caller fails closed, naming only the path, never the contents.
    """
    relative = resolved_path.relative_to(project).as_posix()
    try:
        text = resolved_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise CoordinatorError(f"cannot read adoption record {relative}: {exc}") from exc
    if not text.strip():
        return AdoptionEvidence(relative, "malformed", f"{relative} is empty")

    date_owner_block = _adoption_section_block(text, "1")
    revision_block = _adoption_section_block(text, "3")
    baseline_block = _adoption_section_block(text, "2")
    signature = _SIGNATURE_HEADING.search(text)
    if signature:
        tail = text[signature.end():]
        next_heading = _HEADING_LINE.search(tail)
        signature_block = tail[: next_heading.start()] if next_heading else tail
    else:
        signature_block = ""
    heading_lines = "\n".join(re.findall(r"(?m)^#{1,6}[ \t].*$", text))
    # Scope the draft/placeholder scan to structurally meaningful fields
    # (headings, D.1, D.3, Signature) rather than the whole document, so a
    # ratified record's own prose about *other*, unrelated draft/proposed
    # material (e.g. an archived, never-ratified prior revision) is never
    # mistaken for this record's own status.
    draft_scope = "\n".join(
        part for part in
        (heading_lines, date_owner_block, revision_block, signature_block)
        if part
    )
    if _ADOPTION_DRAFT_MARKER.search(draft_scope):
        return AdoptionEvidence(
            relative, "draft",
            f"{relative} carries an explicit draft/proposed/pending/unsigned status signal",
        )
    if _UNRESOLVED_CHECKLIST_ITEM.search(text):
        return AdoptionEvidence(
            relative, "draft",
            f"{relative} has an unresolved outstanding checklist item",
        )
    if _ADOPTION_PLACEHOLDER_TOKEN.search(text):
        return AdoptionEvidence(
            relative, "draft",
            f"{relative} contains an unfilled template placeholder",
        )

    if not _ADOPTION_TITLE.search(text):
        return AdoptionEvidence(
            relative, "malformed",
            f"{relative} does not carry an Appendix D adoption-record title",
        )
    missing_sections = [
        str(number) for number in _ADOPTION_REQUIRED_SECTION_NUMBERS
        if not re.search(rf"(?m)^#{{1,6}}[ \t]*D\.{number}\b", text)
    ]
    if missing_sections:
        return AdoptionEvidence(
            relative, "malformed",
            f"{relative} is missing required Appendix D section(s) D."
            + ", D.".join(missing_sections),
        )
    baseline_match = _ADOPTION_BASELINE_HASH.search(baseline_block)
    if not baseline_match or "effective" not in baseline_block.lower():
        return AdoptionEvidence(
            relative, "malformed",
            f"{relative} D.2 lacks a concrete baseline commit and an "
            "adoption-effective statement",
        )
    revision_match = _ADOPTION_REVISION.search(revision_block)
    if not revision_match:
        return AdoptionEvidence(
            relative, "malformed",
            f"{relative} D.3 lacks a stated Doctrine revision",
        )
    if not signature:
        return AdoptionEvidence(relative, "malformed", f"{relative} has no Signature section")
    if "owner" not in signature_block.lower() or not _SIGNATURE_DATE.search(signature_block):
        return AdoptionEvidence(
            relative, "malformed",
            f"{relative} Signature section lacks an Owner attribution and date",
        )
    owner_match = _ADOPTION_OWNER_FIELD.search(text)
    return AdoptionEvidence(
        relative, "ratified",
        f"{relative} carries complete, ratified Appendix D adoption evidence",
        revision_match.group(1),
        owner_match.group(1).strip() if owner_match else None,
        baseline_match.group(1).lower(),
    )


_MAX_FRONTMATTER_BYTES = 8192
_MAX_FRONTMATTER_LINES = 200
_UTF8_BOM = b"\xef\xbb\xbf"


def _bounded_frontmatter_status(path: Path) -> str | None:
    """Read only a bounded opening frontmatter block via raw binary I/O.

    Amendment 1 (WO-WW-028): historical work-order lifecycle classification
    must never *read* a record's body, not merely avoid decoding it. This
    opens the record unbuffered (``buffering=0``, so no internal buffered
    reader can pull body bytes into memory ahead of this function's own
    requests) and reads exactly one raw byte at a time, assembling only
    complete header lines. It stops issuing further reads the instant the
    closing delimiter line's own trailing newline has been consumed -- no
    chunked read-ahead, and never a byte beyond that boundary is requested. A
    header exceeding the byte or line bound, one missing a closing delimiter
    within that bound, or one whose collected bytes are not valid frontmatter
    text is explicit malformed metadata -- never a silent guess and never a
    reason to read further into the body. A leading UTF-8 BOM and CRLF line
    endings are tolerated on the header exactly as the existing
    ``frontmatter_status`` tolerates them, so a well-formed record's status
    interpretation is unchanged.
    """
    lines: list[bytes] = []
    current_line = bytearray()
    total_bytes = 0
    closing_found = False
    try:
        with path.open("rb", buffering=0) as handle:
            while True:
                byte = handle.read(1)
                if not byte:
                    break
                total_bytes += 1
                if total_bytes > _MAX_FRONTMATTER_BYTES:
                    raise CoordinatorError(
                        "cannot read historical work-order record: frontmatter "
                        f"exceeds the {_MAX_FRONTMATTER_BYTES}-byte bound"
                    )
                if byte != b"\n":
                    current_line += byte
                    continue
                line = bytes(current_line)
                current_line = bytearray()
                if not lines:
                    if line.startswith(_UTF8_BOM):
                        line = line[len(_UTF8_BOM):]
                    if line.rstrip(b"\r") != b"---":
                        return None
                    lines.append(b"---")
                    continue
                if len(lines) > _MAX_FRONTMATTER_LINES:
                    raise CoordinatorError(
                        "cannot read historical work-order record: frontmatter "
                        f"exceeds the {_MAX_FRONTMATTER_LINES}-line bound"
                    )
                if line.rstrip(b"\r") == b"---":
                    closing_found = True
                    break
                lines.append(line.rstrip(b"\r"))
    except OSError as exc:
        raise CoordinatorError(f"cannot read historical work-order record: {exc}") from exc

    if not closing_found:
        raise CoordinatorError(
            "cannot read historical work-order record: no closing frontmatter "
            f"delimiter within the {_MAX_FRONTMATTER_BYTES}-byte bound"
        )
    for raw_line in lines[1:]:
        try:
            line = raw_line.decode("utf-8")
        except UnicodeError as exc:
            raise CoordinatorError(
                "cannot read historical work-order record: malformed "
                f"frontmatter encoding: {exc}"
            ) from exc
        if line.startswith((" ", "\t")):
            continue
        match = re.fullmatch(r"status:\s*(['\"]?)([^'\"#]+)\1\s*(?:#.*)?", line)
        if match:
            return match.group(2).strip()
    return None


def classify_project(project: Path) -> ObservedState:
    """Classify lifecycle state from repository bytes, never chat context."""
    bootstrap = project / OUTPUT_NAME
    bootstrap_exists = _entry_exists(bootstrap)
    if bootstrap_exists:
        _safe_project_path(project, bootstrap, "bootstrap recovery marker")

    def reject_bootstrap_conflict(lifecycle: str) -> None:
        if bootstrap_exists:
            raise CoordinatorError(
                "inconsistent state: .writwall-bootstrap recovery marker "
                f"coexists with {lifecycle} lifecycle state"
            )

    claude_dir = project / ".claude"
    if _entry_exists(claude_dir):
        resolved_claude = _safe_project_path(project, claude_dir, ".claude directory")
        if not resolved_claude.is_dir():
            raise CoordinatorError("inconsistent state: .claude is not a directory")
    pointer = claude_dir / "active-wo.txt"
    pointer_siblings = tuple(
        path for path in claude_dir.glob("active-wo.*")
        if path.name != "active-wo.txt"
    ) if claude_dir.is_dir() else ()
    if pointer_siblings:
        for sibling in pointer_siblings:
            _safe_project_path(project, sibling, "possible activation pointer")
        names = ", ".join(sorted(path.name for path in pointer_siblings))
        raise CoordinatorError(
            f"inconsistent state: possible misnamed activation pointer(s): {names}"
        )

    pointed_target: Path | None = None
    if _entry_exists(pointer):
        resolved_pointer = _safe_project_path(project, pointer, "activation pointer")
        if not resolved_pointer.is_file():
            raise CoordinatorError("inconsistent state: activation pointer is not a regular file")
        try:
            pointer_value = pointer.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise CoordinatorError(
                f"inconsistent state: activation pointer is unreadable: {exc}"
            ) from exc
        pointed_target = _safe_pointer_target(project, pointer_value)
        status = frontmatter_status(pointed_target)
        if status != "ACTIVE":
            raise CoordinatorError(
                "inconsistent state: activation pointer resolves, but the work order "
                f"status is {status!r}, not 'ACTIVE'"
            )
    live_orders = project / "governance" / "work-orders"
    active_orders: list[Path] = []
    if _entry_exists(live_orders):
        resolved_orders = _safe_project_path(
            project, live_orders, "work-order directory"
        )
        if not resolved_orders.is_dir():
            raise CoordinatorError("inconsistent state: work-order path is not a directory")
        for path in live_orders.glob("*.md"):
            safe_path = _safe_project_path(project, path, "work-order record")
            if not safe_path.is_file():
                raise CoordinatorError("inconsistent state: work-order record is not a file")
            if frontmatter_status(safe_path) == "ACTIVE":
                active_orders.append(safe_path)

    if pointed_target is not None:
        extras = [path for path in active_orders if path != pointed_target]
        if extras or pointed_target not in active_orders:
            names = ", ".join(sorted(path.name for path in active_orders)) or "none"
            raise CoordinatorError(
                "inconsistent state: activation pointer does not identify the only ACTIVE "
                f"work order; observed ACTIVE records: {names}"
            )
        relative = pointed_target.relative_to(project).as_posix()
        reject_bootstrap_conflict("active work-order")
        return ObservedState(
            "active_work_order",
            ("activation pointer exists", f"pointed work order is ACTIVE: {relative}"),
            relative,
        )

    if active_orders:
        names = ", ".join(sorted(path.name for path in active_orders))
        raise CoordinatorError(
            "inconsistent state: ACTIVE work order(s) exist without an activation "
            f"pointer: {names}"
        )

    # Distribution evidence describes the source, not authority over this copy.
    # Resolve active work first so these markers never suppress its checks.
    distribution_names = ("PROJECTION-MANIFEST.sha256", "PROJECTION-PROVENANCE.md")
    public_distribution = False
    notice = ""
    if _entry_exists(project / "CLAUDE.md"):
        charter = _safe_project_path(project, project / "CLAUDE.md", "project charter")
        if not charter.is_file():
            raise CoordinatorError("inconsistent state: project charter is not a file")
        try:
            notice = charter.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise CoordinatorError("inconsistent state: project charter is unreadable") from exc
    if (notice.startswith("# Public projection instructions\n")
            or any(_entry_exists(project / name) for name in distribution_names)):
        reject_bootstrap_conflict("public distribution")
        for name in (*distribution_names, "CLAUDE.md"):
            path = _safe_project_path(project, project / name, "public distribution marker")
            if not path.is_file():
                raise CoordinatorError(f"inconsistent public distribution: missing {name}")
        try:
            notice = (project / "CLAUDE.md").read_text(encoding="utf-8-sig")
            provenance = (project / "PROJECTION-PROVENANCE.md").read_text(encoding="utf-8-sig")
            manifest = (project / "PROJECTION-MANIFEST.sha256").read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise CoordinatorError("inconsistent public distribution: unreadable marker") from exc
        if (not notice.startswith("# Public projection instructions\n")
                or "does not govern its own maintenance." not in notice
                or not provenance.startswith("# Projection provenance\n")
                or "This candidate is derived from a private governed source repository." not in provenance
                or not re.search(r"(?m)^[0-9a-f]{64}  CLAUDE\.md$", manifest)
                or not re.search(r"(?m)^[0-9a-f]{64}  PROJECTION-PROVENANCE\.md$", manifest)):
            raise CoordinatorError("inconsistent public distribution: conflicting notice or marker")
        public_distribution = True

    governance = project / "governance"
    if _entry_exists(governance):
        resolved_governance = _safe_project_path(
            project, governance, "governance directory"
        )
        if not resolved_governance.is_dir():
            raise CoordinatorError("inconsistent state: governance is not a directory")
    core = tuple(governance / name for name in ("PLAN.md", "STATE.md", "ROUTING.md"))
    adoption_paths = (
        governance / "decisions" / "DR-001.md",
        governance / "ADOPTION-RECORD.md",
    )
    history = governance / "history"
    closed_records = []
    if _entry_exists(history):
        resolved_history = _safe_project_path(project, history, "history directory")
        if not resolved_history.is_dir():
            raise CoordinatorError("inconsistent state: history is not a directory")
        for path in history.glob("WO-*.md"):
            safe_path = _safe_project_path(project, path, "historical work-order record")
            if not safe_path.is_file():
                raise CoordinatorError(
                    "inconsistent state: historical work-order record is not a file"
                )
            if _bounded_frontmatter_status(safe_path) in {"CLOSED", "COMPLETE"}:
                closed_records.append(safe_path)

    resolved_adoption_paths = []
    for path in (*core, *adoption_paths):
        if _entry_exists(path):
            resolved = _safe_project_path(project, path, "governance control file")
            if not resolved.is_file():
                raise CoordinatorError(
                    "inconsistent state: governance control path is not a file"
                )
            if path in adoption_paths:
                resolved_adoption_paths.append(resolved)

    if public_distribution:
        return ObservedState("public_distribution", (
            "public distribution notice and projection markers observed",
            "retained source governance is evidence, not this checkout's adoption",
            "classification is not a projection-integrity verification",
        ))

    # A filename alone is never adoption authority: read each candidate's own
    # Appendix D title, D.1-D.9 sections, baseline, revision, and Signature.
    adoption_evidence = [
        _classify_adoption_record(project, path) for path in resolved_adoption_paths
    ]
    malformed_evidence = [
        evidence for evidence in adoption_evidence if evidence.status == "malformed"
    ]
    if malformed_evidence:
        reasons = "; ".join(
            evidence.reason
            for evidence in sorted(malformed_evidence, key=lambda item: item.relative)
        )
        raise CoordinatorError(
            "inconsistent state: candidate adoption record does not carry "
            f"recognizable, complete Appendix D adoption evidence: {reasons}"
        )
    ratified_evidence = [evidence for evidence in adoption_evidence if evidence.ratified]
    if len(adoption_evidence) > 1:
        if len(ratified_evidence) != len(adoption_evidence):
            reasons = "; ".join(evidence.reason for evidence in adoption_evidence)
            raise CoordinatorError(
                "inconsistent state: multiple candidate adoption records coexist with "
                f"incompatible ratification evidence: {reasons}"
            )
        revisions = {evidence.revision for evidence in ratified_evidence}
        owners = {evidence.owner for evidence in ratified_evidence}
        baselines = {evidence.baseline for evidence in ratified_evidence}
        if (
            len(revisions) != 1 or None in revisions
            or len(owners) != 1 or None in owners
            or len(baselines) != 1 or None in baselines
        ):
            names = ", ".join(evidence.relative for evidence in ratified_evidence)
            raise CoordinatorError(
                "inconsistent state: multiple candidate adoption records coexist with "
                f"contradictory baseline, revision, or Owner evidence: {names}"
            )
    adopted = bool(ratified_evidence)

    if all(path.is_file() for path in core) and adopted and closed_records:
        reject_bootstrap_conflict("retired lockout")
        return ObservedState(
            "retired_lockout",
            (
                "activation pointer is absent",
                "Plan, State, and Routing exist",
                f"ratified adoption evidence observed: {ratified_evidence[0].relative}",
                f"{len(closed_records)} closed work-order record(s) observed in history",
            ),
        )
    if all(path.is_file() for path in core) and adopted:
        reject_bootstrap_conflict("adopted lockout")
        return ObservedState(
            "adopted_lockout",
            (
                "activation pointer is absent",
                "Plan, State, Routing, and ratified adoption evidence exist: "
                f"{ratified_evidence[0].relative}",
            ),
        )

    writwall_markers = (
        project / OUTPUT_NAME,
        project / ".claude" / "hooks" / "wo_capability_wall.py",
        project / ".claude" / "settings.json",
        governance / "PLAN.md",
        governance / "STATE.md",
        governance / "ROUTING.md",
        project / "START-HERE.md",
        project / "ADOPTING.md",
    )
    found_items = []
    for path in writwall_markers:
        if _entry_exists(path):
            _safe_project_path(project, path, "Writwall marker")
            found_items.append(path.relative_to(project).as_posix())
    found = tuple(found_items)
    if found:
        return ObservedState(
            "partial_bootstrap",
            ("activation pointer is absent", "Writwall-shaped material exists: " + ", ".join(found)),
        )
    return ObservedState(
        "clean_new",
        ("activation pointer is absent", "no Writwall control-plane or governance markers found"),
    )


def portable_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise CoordinatorError(f"external Operator function {value!r} has no portable name")
    slug = slug[:80].rstrip("-")
    if slug in WINDOWS_RESERVED_STEMS:
        slug = f"operator-{slug}"
    return slug


def _canonical_root_block(canonical: str) -> str:
    return f"""## Canonical project root

`{canonical}`

Durable project artifacts, governance records, source, plans, reports, and
work orders belong under this one canonical project root. This bootstrap
directory and any other temporary staging may hold bounded evidence or
atomic publication bytes; they never become the authoritative project tree
and must be removed after use. No agent creates a shadow repository or a
second durable project record outside this canonical root; a portable
relative path or a bare `.` is never a substitute for it.
"""


def _external_operator_root_block(canonical: str) -> str:
    return f"""## Canonical project root

`{canonical}`

This external Operator's own evidence staging is separate from durable
project records. Returned sanitized evidence is incorporated under this
canonical project root by the General or a separately authorized
repository Operator; this external Operator does not create a shadow
repository or any other durable project record elsewhere.
"""


OPERATIONAL_TASK_CLASSIFICATIONS = frozenset({
    "deployment", "migration", "source_freeze", "cutover",
})


def _operational_preflight_block(operational_task: str) -> str:
    return f"""## Operational preflight

Operational task classification: {operational_task}

This bounded inventory is guidance only; it never performs, simulates, or
confirms real host, account, or scheduler discovery. An entry the preparer
cannot verify stays `unknown`, distinct from a verified-absent entry -- never
invented as safe. Unresolved relevant inventory blocks the affected
execution, not planning.

- [ ] Environment/account boundary. Observation time: state the exact
      timestamp this inventory was recorded; do not reuse a stale one.
- [ ] Alternate writers/engines/schedulers with plausible access to the same
      target (name each one, or state `unknown` when inaccessible to inspect).
- [ ] Access limitations preventing a complete inventory.
- [ ] Approval scope: exactly what this operational task authorizes.
- [ ] Revalidate this inventory's evidence at the relevant execution
      transition; no single universal expiry period applies to every task.
- [ ] Rollback: exact restoration procedure.
- [ ] Last safe stop: the last point at which stopping leaves no partial,
      unrecoverable change.
"""


def operation_packet(
    function_name: str, canonical: str, *, operational_task: str | None = None,
) -> str:
    if operational_task is not None and operational_task not in OPERATIONAL_TASK_CLASSIFICATIONS:
        raise CoordinatorError(
            f"unsupported operational task classification {operational_task!r}; "
            "expected one of "
            + ", ".join(sorted(OPERATIONAL_TASK_CLASSIFICATIONS))
        )
    preflight_block = (
        f"\n{_operational_preflight_block(operational_task)}"
        if operational_task is not None else ""
    )
    return f"""# External operations packet: {function_name}

This scaffold is inert. It confers no authority to access or mutate any system.
The Architect or General prepares it from ratified intent; the named Operator
executes only the completed packet and returns evidence.

{_external_operator_root_block(canonical)}
{authorization_continuity_block()}
{preflight_block}
## Preconditions

- [ ] Identify the exact system, account boundary, and observed baseline.
- [ ] Name a stop condition for unexpected state.

## Permitted actions

- [ ] List exact authorized actions; an empty list authorizes nothing.

## Prohibited actions

- No repository-byte edits unless a separate repository work order grants them.
- No credential disclosure, persistence, or transmission through this packet.
- No adjacent-system change merely because it is convenient.

## Verification

- [ ] State exact observations and pass conditions.

## Rollback

- [ ] State the last safe point and exact restoration procedure.

## Evidence to return

- [ ] Return timestamps, sanitized before/after observations, and command or UI results.
- Never return credentials, private keys, mailbox content, or secret record values.

## Credential boundary

Credentials remain in the Operator's approved secret store or interactive
provider session. The Owner may authenticate when unavoidable; authentication
does not transfer decision authority. This external Operator remains outside
the repository capability wall unless it edits repository bytes.
"""


def role_split_recommendation(functions: tuple[str, ...]) -> str:
    external = (
        f" Add {len(functions)} separately bounded external function packet(s); "
        "the Owner may assign multiple packets to one Operator only when the "
        "same account boundary, verification, and rollback apply."
        if functions else
        " Add no external Operator unless the project later names an external system."
    )
    return (
        "Use one human Owner, one Architect, one General, one repository "
        "Operator when repository mutation begins, and one fresh Reviewer."
        + external
    )


def topology_recommendation(
    args: argparse.Namespace, functions: tuple[str, ...]
) -> dict:
    observed_stakes = (
        args.environment,
        getattr(args, "problem", None),
        getattr(args, "why_matters", None),
        getattr(args, "smallest_outcome", None),
        *getattr(args, "constraint", ()),
        *getattr(args, "risk", ()),
        *functions,
    )
    high_impact = args.scenario == "dns-mail-migration" or any(
        token in observation.lower()
        for observation in observed_stakes if observation
        for token in ("production", "identity", "dns", "mail")
    )
    if high_impact:
        tier = "high_impact"
        reason = (
            "Observed production, identity, DNS, or mail boundaries require "
            "separately ratified and verified operation packets."
        )
    elif functions:
        tier = "repository_plus_external"
        reason = (
            "Observed external account boundaries require bounded external "
            "Operators in addition to repository work."
        )
    else:
        tier = "local_only"
        reason = "Only local repository work is currently observed."
    return {
        "tier": tier,
        "authority": "unratified_recommendation",
        "reason": reason,
        "roles": [
            "human Owner", "Architect", "General", "repository Operator",
            "fresh Reviewer", *functions,
        ],
        "sequential_combination": (
            "On a small project, one agent may act sequentially as Architect, "
            "General, and repository Operator only in separate sessions after "
            "Owner ratification."
        ),
        "mandatory_separation": (
            "The human Owner remains the source of ratification; the fresh Reviewer "
            "does not implement corrections; each high-impact external function keeps "
            "its own preconditions, authority, verification, and rollback packet."
        ),
    }


_IGNORED_TOP_LEVEL_NAMES = frozenset({
    "__pycache__", "node_modules", ".venv", "venv", "env", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".tox", ".idea", ".vscode", "target",
    "vendor", ".DS_Store", ".ruff_cache", "site-packages", OUTPUT_NAME,
})

_REFLOG_COMMIT_MESSAGE = re.compile(r"^commit(?: \(initial\)| \(amend\))?:\s*(.+)$")


def _top_level_entries(project: Path) -> tuple[str, ...]:
    """Bounded, one-level, project-relative names only.

    Never recurses, never reads file contents, never follows a link outside
    the project, and skips `.git`, the bootstrap output itself, and common
    dependency/build/cache directories.
    """
    try:
        entries = sorted(project.iterdir(), key=lambda item: item.name.casefold())
    except OSError:
        return ()
    names: list[str] = []
    for entry in entries:
        if entry.name == ".git" or entry.name in _IGNORED_TOP_LEVEL_NAMES:
            continue
        if _is_linklike(entry):
            continue
        names.append(entry.name)
    return tuple(names)


def _read_git_head_branch(project: Path) -> str | None:
    """Read the current branch from an ordinary local `.git` directory only.

    Never chases a linked-worktree `gitdir:` pointer, which typically
    resolves outside the project root; that case simply yields no branch.
    """
    git_dir = project / ".git"
    if _is_linklike(git_dir) or not git_dir.is_dir():
        return None
    head = git_dir / "HEAD"
    if _is_linklike(head) or not head.is_file():
        return None
    try:
        content = head.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if content.startswith("ref:"):
        ref = content[len("ref:"):].strip()
        return ref.rsplit("/", 1)[-1] if ref else None
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", content):
        return f"detached HEAD at {content[:12]}"
    return None


def _read_recent_commit_subjects(project: Path, limit: int = 3) -> tuple[str, ...]:
    """Bounded recent commit subjects from the local HEAD reflog only.

    Reads only the commit subjects Git itself already wrote into
    `.git/logs/HEAD`; never parses the object database, never dumps a diff
    or full commit body, and returns nothing when the reflog is absent.
    """
    git_dir = project / ".git"
    if _is_linklike(git_dir) or not git_dir.is_dir():
        return ()
    reflog = git_dir / "logs" / "HEAD"
    if _is_linklike(reflog) or not reflog.is_file():
        return ()
    try:
        lines = reflog.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ()
    subjects: list[str] = []
    for line in reversed(lines):
        if "\t" not in line:
            continue
        message = line.split("\t", 1)[1].strip()
        match = _REFLOG_COMMIT_MESSAGE.match(message)
        if match:
            subjects.append(match.group(1).strip())
        if len(subjects) >= limit:
            break
    return tuple(subjects)


def _observe_git_cleanliness(project: Path) -> str | None:
    """Best-effort local-only cleanliness label via an available `git`.

    Never contacts a network (plain `status` is local-only) and never lists
    changed file names; returns `None` rather than failing when a `git`
    executable is unavailable on PATH.
    """
    git_executable = shutil.which("git")
    if not git_executable:
        return None
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        result = subprocess.run(
            [git_executable, "-C", str(project), "status", "--porcelain=v1"],
            capture_output=True, text=True, timeout=10, env=environment,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    changed = [line for line in result.stdout.splitlines() if line.strip()]
    return "clean" if not changed else f"{len(changed)} uncommitted change(s)"


@dataclass(frozen=True)
class LocalInventory:
    """A deterministic, local-only, bounded observation of a clean/new target.

    Records project-relative names and non-secret Git metadata only:
    repository presence, branch, cleanliness, and recent commit subjects.
    Never reads file contents, never inspects outside the canonical root,
    and never contacts a network. These are observations, never ratified
    intent.
    """
    has_git: bool
    branch: str | None
    cleanliness: str | None
    recent_commit_subjects: tuple[str, ...]
    top_level_entries: tuple[str, ...]

    @property
    def is_existing(self) -> bool:
        return self.has_git or bool(self.top_level_entries)

    def evidence_lines(self) -> tuple[str, ...]:
        lines: list[str] = []
        if self.has_git:
            lines.append("Git repository observed at the project root")
            if self.branch:
                lines.append(f"Git branch: {self.branch}")
            if self.cleanliness:
                lines.append(f"Git working tree: {self.cleanliness}")
            for subject in self.recent_commit_subjects:
                lines.append(f"Recent commit: {subject}")
        else:
            lines.append("No Git repository observed at the project root")
        if self.top_level_entries:
            lines.append(
                "Top-level project entries: " + ", ".join(self.top_level_entries)
            )
        else:
            lines.append("No top-level project entries observed")
        return tuple(lines)


def gather_local_inventory(
    project: Path, *, observe_cleanliness: bool = True
) -> LocalInventory:
    """Gather bounded local inventory for a clean/new project root.

    ``inspect`` disables cleanliness observation so its read-only contract
    never executes repository-configured Git helpers such as ``core.fsmonitor``.
    """
    git_dir = project / ".git"
    has_git = _entry_exists(git_dir) and not _is_linklike(git_dir)
    ordinary_git_dir = has_git and git_dir.is_dir()
    return LocalInventory(
        has_git=has_git,
        branch=_read_git_head_branch(project) if ordinary_git_dir else None,
        cleanliness=(
            _observe_git_cleanliness(project)
            if ordinary_git_dir and observe_cleanliness else None
        ),
        recent_commit_subjects=(
            _read_recent_commit_subjects(project) if ordinary_git_dir else ()
        ),
        top_level_entries=_top_level_entries(project),
    )


def conversation_first_opening(inventory: LocalInventory) -> tuple[str, str]:
    """The ordinary, conversation-first Architect opening for a clean/new
    target: an existing-project summary-first opening, or one open
    invitation for a genuinely empty project."""
    if inventory.is_existing:
        return ("Fresh Architect (conversation-first)", ARCHITECT_EXISTING_PROJECT_PROMPT)
    return ("Fresh Architect (conversation-first)", ARCHITECT_EMPTY_PROJECT_PROMPT)


def next_prompt(state: ObservedState) -> tuple[str, str]:
    if state.name == "public_distribution":
        return (
            "Select target project",
            "This checkout is the Writwall public distribution. Choose your target project "
            "and run writwall inspect --project-root <target-project> --role architect "
            "for read-only discovery, or writwall start --project-root <target-project> "
            "for a new bootstrap. Retained governance records are source evidence, "
            "not adoption authority for this checkout. To discuss contributing here, "
            "use inspect with --role architect; follow CONTRIBUTING.md.",
        )
    if state.name == "clean_new":
        return (
            "Fresh Architect (prepared intake)",
            ARCHITECT_PREPARED_INTAKE_PROMPT,
        )
    if state.name == "partial_bootstrap":
        return (
            "Fresh external recovery coordinator",
            """Act as a fresh recovery coordinator for this accidental overlay or incomplete
Writwall adoption, not as an Implementer. Begin read-only. Use a complete local
Writwall source or adoption bundle outside the locked session; do not assume a
partial project-local bundle is complete. Inventory only: do not delete,
overwrite, move, install, register, activate, or invent missing intent. Verify
the lifecycle from repository bytes, propose an exact disposition packet, and
ask one question at a time. The prior session stops here.""",
        )
    if state.name in {"adopted_lockout", "retired_lockout"}:
        return (
            "Fresh General",
            GENERAL_PROMPT,
        )
    if state.name == "active_work_order":
        return (
            "Fresh walled repository Operator/Implementer",
            """Act as a fresh Implementer for the active work order only. Re-read the activation
pointer and pointed work order from repository bytes, confirm the active
dispatch and required live-wall canary before mutation, execute only its grant,
write its report, and stop before acceptance or closeout.""",
        )
    raise CoordinatorError(f"inconsistent state: unsupported classification {state.name!r}")


def emit_lifecycle_handoff(state: ObservedState) -> None:
    """Print the next fresh-role handoff without changing target bytes."""
    role, prompt = next_prompt(state)
    print(f"Observed lifecycle state: {state.name}")
    for item in state.evidence:
        print(f"  - {item}")
    if state.active_work_order:
        print(f"Pointed work order: {state.active_work_order}")
    print(f"Next role: {role}")
    print("\nCopy this prompt into a fresh session:\n")
    print(prompt)


def _architect_inspection_prompt(
    state: ObservedState, inventory: LocalInventory | None = None
) -> str:
    if state.name == "public_distribution":
        return """Act as a fresh Architect reviewing the Writwall public distribution.
Begin read-only, follow CONTRIBUTING.md, and ask what the Owner wants to explore.
The retained source governance records do not adopt or govern this checkout.
Do not initiate a General handoff or infer ratification from those records.
For a separate project, ask the Owner to select that target project instead."""
    if state.name == "clean_new" and inventory is not None and not inventory.is_existing:
        return """Act as the Architect for a new, empty project. Begin read-only; do not
implement, install, adopt, activate a work order, or change lifecycle state.
Open with exactly: "Tell me what you are thinking." Let the Owner's words guide
the conversation without imposing a fixed questionnaire. Nothing said becomes
ratified intent until the human Owner ratifies it. This explicit role selection
grants no mutation or lifecycle authority."""
    return f"""Act as a fresh Architect for this existing project. Begin read-only; do not
implement, install, adopt, activate a work order, or change lifecycle state.
The observed lifecycle is {state.name}. Inspect the canonical project in place,
listen to the Owner's current intent, and distinguish preserved authority from
legacy or incomplete material. Explain what the project appears to be doing,
then ask what the Owner wants to explore. This explicit role selection grants
no mutation or lifecycle authority."""


_ROUTING_LINE = re.compile(r"(?m)^Routing:[ \t]*(.+)$")
_OBJECTIVE_HEADING = re.compile(r"(?im)^#{1,6}[ \t]*Objective\b")
_SAFE_ROUTING_SHAPE = re.compile(r"[A-Za-z0-9_.\-/]+\.[A-Za-z0-9]+")
_EXCLUDED_ROUTING_PREFIXES = (
    "governance/history/", "governance/archive/", "governance/rfis/",
    "archive/", "dist/",
)


def _routing_referenced_paths(text: str) -> tuple[str, ...]:
    """Extract whole candidate words from a recognized ``Routing:`` line only.

    This is one narrow, documented syntax, not a prose parser: only
    whitespace-delimited *whole words* on a line beginning with the literal
    prefix ``Routing:`` are considered, with trailing `,;.` sentence
    punctuation stripped. Unlike a substring search, a candidate is always
    judged as one complete word -- an unsupported token (a URL, a
    digest-decorated reference, an escape) is never quietly reduced to a
    regex-matched fragment that happens to look like a valid path. No other
    work-order text is scanned, and no routing or approval semantics are
    inferred from the surrounding prose.
    """
    candidates: list[str] = []
    for match in _ROUTING_LINE.finditer(text):
        for raw_word in match.group(1).split():
            candidate = raw_word.strip(",;").rstrip(".")
            if not candidate:
                continue
            if "/" not in candidate and "." not in candidate:
                continue  # not path-like at all (e.g. "see", "and")
            if candidate not in candidates:
                candidates.append(candidate)
    return tuple(candidates)


def _is_safe_relative_reference_shape(candidate: str) -> bool:
    """A conservative, narrowly documented safe-relative-path shape.

    True only for a plain relative file path: letters/digits/underscore/
    hyphen/dot/slash characters throughout, ending in an extension, not
    absolute, and with no ``.``/``..`` path segment. A URL (``://``), a
    digest or version decoration (``@``), an embedded scheme/port separator
    (``:``), or any other shape is explicit unsupported syntax -- rejected
    outright, never partially matched or guessed at.
    """
    if not candidate or candidate.startswith("/"):
        return False
    if "://" in candidate or "@" in candidate or ":" in candidate:
        return False
    if not _SAFE_ROUTING_SHAPE.fullmatch(candidate):
        return False
    return all(part not in ("", ".", "..") for part in candidate.split("/"))


_EXCLUDED_ROUTING_PREFIX_SEGMENTS = tuple(
    tuple(part.casefold() for part in prefix.strip("/").split("/") if part)
    for prefix in _EXCLUDED_ROUTING_PREFIXES
)


def _normalized_alias_segments(candidate: str) -> tuple[str, ...]:
    """Casefold each path segment and strip a Windows trailing-dot alias.

    This performs alias *rejection* only, comparing normalized segments
    against excluded prefixes; it never rewrites a candidate into a
    different path that is then read or measured, and it touches no
    filesystem I/O -- string normalization only.
    """
    return tuple(
        segment.rstrip(".").casefold()
        for segment in candidate.split("/")
        if segment not in ("", ".")
    )


def _is_excluded_routing_reference(candidate: str) -> bool:
    """True for a path-shaped reference under a read-denied protected prefix.

    Comparison is casefolded and per-segment, with a Windows trailing-dot
    directory alias stripped from each segment before comparison, so a
    differently-cased or dot-decorated alias of an excluded prefix is
    rejected exactly like the canonical form -- entirely before any
    filesystem probe. Such a reference is never stat'd, read, or measured
    for this brief, regardless of whether it happens to exist and be
    readable, because its prefix is excluded evidence, not because of any
    observed I/O outcome.
    """
    segments = _normalized_alias_segments(candidate)
    return any(
        segments[: len(prefix_segments)] == prefix_segments
        for prefix_segments in _EXCLUDED_ROUTING_PREFIX_SEGMENTS
    )


def _safe_relative_stat(project: Path, relative: str) -> int | None:
    """Return a project-relative regular file's byte size, or None.

    Containment and link-safety checks run first: `_safe_project_path` is
    called before any other filesystem probe of the candidate, and its own
    component-wise `_is_linklike` checks run before its `resolve()` call.
    Only a path that has already passed that safety check is ever measured.
    None covers missing, unsafe (symlink/escape/reparse), and non-regular
    paths alike: a referenced-but-absent or unsupported path is a pending
    evidence gap for the caller to report, never a coordinator error.
    """
    candidate = project / relative
    try:
        resolved = _safe_project_path(project, candidate, "referenced evidence path")
    except CoordinatorError:
        return None
    if not resolved.is_file():
        return None
    try:
        return resolved.stat().st_size
    except OSError:
        return None


def _render_active_work_order_brief(
    project: Path, state: ObservedState, selected_role: str
) -> str:
    """The active-work-order compact brief.

    Cites only recognized mandatory sources (charter, Plan, Routing, the
    pointed work order) and paths named on a work order's own ``Routing:``
    line; it never infers an executable grant from status ``ACTIVE`` alone,
    and an unresolved or unsupported reference stays visibly pending rather
    than silently dropped or claimed resolved.
    """
    work_order_relative = state.active_work_order or ""
    try:
        work_order_text = (project / work_order_relative).read_text(
            encoding="utf-8-sig"
        )
    except (OSError, UnicodeError):
        work_order_text = ""

    mandatory = [
        (relative, _safe_relative_stat(project, relative))
        for relative in ("CLAUDE.md", "governance/PLAN.md",
                          "governance/ROUTING.md", "governance/STATE.md",
                          work_order_relative)
    ]
    mandatory_complete = bool(work_order_relative) and all(
        size is not None for _, size in mandatory
    )
    mandatory_lines = "\n".join(
        f"- {relative} ({size} bytes)" if size is not None
        else f"- {relative}: unresolved (not found or unsafe); remains pending"
        for relative, size in mandatory
    )

    objective_line = (
        f"- {work_order_relative} carries a recognized Objective heading "
        "(content not summarized here)."
        if _OBJECTIVE_HEADING.search(work_order_text) else
        f"- {work_order_relative} carries no recognized Objective heading; unresolved."
    )

    routing_candidates = _routing_referenced_paths(work_order_text)
    referenced_lines = []
    routing_fully_resolved = bool(routing_candidates)
    for relative in routing_candidates:
        if not _is_safe_relative_reference_shape(relative):
            referenced_lines.append(
                f"- {relative}: unsupported reference form (not the "
                "documented safe relative-path syntax: no URL, digest/"
                "version decoration, or escape is parsed); remains pending, "
                "not resolved"
            )
            routing_fully_resolved = False
            continue
        if _is_excluded_routing_reference(relative):
            referenced_lines.append(
                f"- {relative}: excluded (protected read-denied path "
                "prefix); never read or measured by this brief"
            )
            routing_fully_resolved = False
            continue
        size = _safe_relative_stat(project, relative)
        if size is not None:
            referenced_lines.append(f"- {relative} ({size} bytes)")
        else:
            referenced_lines.append(
                f"- {relative}: referenced but unresolved (not found or not a "
                "supported reference); remains pending"
            )
            routing_fully_resolved = False
    referenced_block = "\n".join(referenced_lines) or (
        "- none cited on a recognized `Routing:` line; routing remains "
        "explicitly unresolved, not verified complete"
    )

    if not mandatory_complete:
        next_step = (
            "This is an observation snapshot; re-read the mandatory "
            "evidence in the index below before acting. Mandatory evidence "
            "is incomplete, so no role may proceed to execution until every "
            "mandatory source resolves; this brief does not authorize "
            "execution."
        )
    elif routing_fully_resolved:
        next_step = (
            "This is an observation snapshot; re-read the mandatory "
            "evidence in the index below before acting. Every recognized "
            "mandatory source and routed reference currently resolves; "
            f"role eligibility remains the bounded Operator for "
            f"{work_order_relative}, but this brief does not authorize "
            "execution -- re-enter a fresh Operator session, confirm the "
            "actual grant authority, and confirm the required live-wall "
            "canary before any mutation. Status ACTIVE alone is not an "
            "executable grant."
        )
    else:
        next_step = (
            "This is an observation snapshot; re-read the mandatory "
            "evidence in the index below before acting. Role eligibility "
            f"remains the bounded Operator for {work_order_relative}, but "
            "unresolved, unsafe, or unsupported routing reference(s) remain "
            "in the index below, so this brief does not authorize "
            "execution. Re-enter a fresh Operator session, resolve or "
            "dispose every routing reference from current repository "
            "bytes, and confirm the actual grant authority and required "
            "live-wall canary before any mutation."
        )

    return f"""### Compact continuation brief

Prose word budget: 500 words maximum; the evidence index excluded below is not counted against it.

## Observed lifecycle and objective evidence

- Canonical project root: {project.as_posix()}
- Observed lifecycle state: {state.name}
- Selected role: {selected_role}
{objective_line}

## Decision and authority references

- Activation pointer names {work_order_relative}; its frontmatter status is ACTIVE.
- Observed dispatch is evidence of an issued work order, not inferred Owner approval of its contents.

## Proposals (not approval)

None. This brief links evidence only; it proposes nothing and ratifies nothing.

## Next permitted step or unresolved condition

{next_step}

## Evidence index (outside the prose word budget)

### Mandatory evidence

{mandatory_lines}

### Optional references

{referenced_block}

Evidence above is summarized only; bytes do not measure tokens, context, or cost.
"""


_ADOPTION_EVIDENCE_LINE = re.compile(r"ratified adoption evidence (?:exist|observed): (\S+)")


def _lockout_adoption_relative(state: ObservedState) -> str | None:
    for item in state.evidence:
        match = _ADOPTION_EVIDENCE_LINE.search(item)
        if match:
            return match.group(1)
    return None


def _lockout_aggregate_history_line(state: ObservedState) -> str | None:
    for item in state.evidence:
        if "closed work-order record" in item:
            return item
    return None


def _render_lockout_brief(
    project: Path, state: ObservedState, selected_role: str
) -> str:
    """The adopted/retired-lockout compact brief.

    Cites only recognized current-governance mandatory sources (charter,
    Plan, State, Routing, and the current ratified adoption record) with
    exact byte sizes. A retired lockout's closed-history evidence is passed
    through only as the classifier's own already-computed aggregate count --
    never a historical record's own path, filename, or body, which this
    function never reads or indexes. Guidance never instructs a mutation,
    and never instructs an explicitly selected read-only Architect to become
    the General.
    """
    adoption_relative = _lockout_adoption_relative(state)
    history_line = _lockout_aggregate_history_line(state)

    mandatory = [
        (relative, _safe_relative_stat(project, relative))
        for relative in ("CLAUDE.md", "governance/PLAN.md",
                          "governance/STATE.md", "governance/ROUTING.md")
    ]
    if adoption_relative:
        mandatory.append(
            (adoption_relative, _safe_relative_stat(project, adoption_relative))
        )
    else:
        mandatory.append(("(no ratified adoption record path observed)", None))
    mandatory_lines = "\n".join(
        f"- {relative} ({size} bytes)" if size is not None
        else f"- {relative}: unresolved (not found or unsafe); remains pending"
        for relative, size in mandatory
    )

    history_evidence_line = (
        f"- {history_line} (aggregate count only; no historical pathname or "
        "body is read or indexed by this brief)."
        if history_line else ""
    )

    is_architect = selected_role == "Fresh Architect"
    next_step = (
        "This is an observation snapshot; re-read the mandatory evidence in "
        "the index below before acting. Begin read-only as the Architect for "
        "this existing project; this brief confers no mutation authority and "
        "does not instruct a role change to General."
        if is_architect else
        "This is an observation snapshot; re-read the mandatory evidence in "
        "the index below before acting. Prepare, but do not activate, the "
        "smallest genuine next work order or bounded Operator packet for a "
        "fresh General; this brief confers no mutation authority."
    )

    return f"""### Compact continuation brief

Prose word budget: 500 words maximum; the evidence index excluded below is not counted against it.

## Observed lifecycle and objective evidence

- Canonical project root: {project.as_posix()}
- Observed lifecycle state: {state.name}
- Selected role: {selected_role}
{history_evidence_line}

## Decision and authority references

- Ratified adoption evidence was observed for this project; its content is
  not read or summarized here beyond its existence and location. See the
  mandatory evidence index below.
- Unknown: this brief does not infer Owner approval, a resolved routing
  contradiction, or a project objective from any record's mere existence.

## Proposals (not approval)

None. This brief links evidence only; it proposes nothing and ratifies nothing.

## Next permitted step or unresolved condition

{next_step}

## Evidence index (outside the prose word budget)

### Mandatory evidence

{mandatory_lines}

### Optional references

None indexed by this compact brief.

Evidence above is summarized only; bytes do not measure tokens, context, or cost.
"""


_RECOGNIZED_GOVERNANCE_SOURCES = (
    "CLAUDE.md", "governance/PLAN.md", "governance/STATE.md",
    "governance/ROUTING.md",
)


def _entry_state_next_step(state: ObservedState, selected_role: str) -> str:
    """Concrete, state-specific, read-only next-step guidance.

    Every branch states this is an observation snapshot requiring a re-read
    of current bytes, and states plainly that objective/authority remain
    unknown until actually cited or read -- never inferred from a state
    name or from the mere presence or absence of files.
    """
    if state.name == "clean_new":
        return (
            "This is an observation snapshot; re-read current repository "
            "bytes before acting. Objective and authority remain unknown "
            "until the Owner states them in conversation. A new or "
            "existing ungoverned project is not broken and does not "
            "require adoption before this conversation. Listen to the "
            "Owner's project pitch as the fresh Architect; do not infer "
            "intent, an objective, or a problem from the absence of files."
        )
    if state.name == "partial_bootstrap":
        return (
            "This is an observation snapshot; re-read current repository "
            "bytes before acting. Objective and authority remain unknown "
            "until actually read from the existing partial material. "
            "Preserve and reconcile that material; do not reset or "
            "re-adopt from scratch. Obtain the missing Owner decision(s) "
            "and ratify them before any adoption mechanics continue."
        )
    if state.name == "public_distribution":
        return (
            "This is an observation snapshot; re-read current repository "
            "bytes before acting. Objective and authority remain unknown "
            "until read from a specific target project. This checkout is "
            "the Writwall public distribution, not an adopter project; its "
            "retained governance records are source evidence, never this "
            "checkout's own adoption authority. Follow CONTRIBUTING.md to "
            "contribute here, or choose a separate target project to adopt "
            "or explore elsewhere."
        )
    return (
        "This is an observation snapshot; re-read current repository bytes "
        f"before acting. Role eligibility remains {selected_role}; "
        "objective and authority remain unknown until actually cited or "
        "read from current bytes."
    )


def render_compact_brief(project: Path, state: ObservedState, selected_role: str) -> str:
    """Render the opt-in ``--brief`` compact continuation block.

    Replaces the full copy-paste prompt entirely so the emitted brief stays
    inside its own 500-word prose budget; the evidence index below the final
    heading is deliberately excluded from that budget and labeled as such.
    """
    if state.name == "active_work_order":
        return _render_active_work_order_brief(project, state, selected_role)
    if state.name in {"adopted_lockout", "retired_lockout"}:
        return _render_lockout_brief(project, state, selected_role)
    evidence_lines = "\n".join(f"- {item}" for item in state.evidence) or "- none observed"
    active = (
        f"\n- Pointed work order: {state.active_work_order}"
        if state.active_work_order else ""
    )
    governance_lines = ""
    if state.name in {"clean_new", "partial_bootstrap"}:
        governance_lines = "\n".join(
            f"- {relative} ({size} bytes)" if size is not None
            else f"- {relative}: not yet materialized"
            for relative, size in (
                (relative, _safe_relative_stat(project, relative))
                for relative in _RECOGNIZED_GOVERNANCE_SOURCES
            )
        )
        governance_lines = "\n" + governance_lines
    next_step = _entry_state_next_step(state, selected_role)
    return f"""### Compact continuation brief

Prose word budget: 500 words maximum; the evidence index excluded below is not counted against it.

## Observed lifecycle and objective evidence

- Canonical project root: {project.as_posix()}
- Observed lifecycle state: {state.name}
- Selected role: {selected_role}

## Decision and authority references

Unknown: no decision or authority record was read by this compact brief.

## Proposals (not approval)

None. This brief links evidence only; it proposes nothing and ratifies nothing.

## Next permitted step or unresolved condition

{next_step}

## Evidence index (outside the prose word budget)

### Mandatory evidence

{evidence_lines}{active}{governance_lines}

### Optional references

None indexed by this compact brief.

Evidence above is summarized only; bytes do not measure tokens, context, or cost.
"""


def inspect_main(argv: list[str] | None = None) -> int:
    """Print a role handoff without creating repository or profile state."""
    parser = argparse.ArgumentParser(
        description="Inspect one project and print a read-only Writwall handoff."
    )
    parser.add_argument("--project-root", required=True)
    parser.add_argument(
        "--role", choices=("auto", "architect", "general", "recovery"),
        default="auto",
    )
    parser.add_argument("--brief", action="store_true")
    args = parser.parse_args(argv)
    try:
        project = resolve_project_root(args.project_root)
        state = classify_project(project)
        inventory = (
            gather_local_inventory(project, observe_cleanliness=False)
            if state.name == "clean_new" and args.role in {"auto", "architect"}
            else None
        )
        inspection_evidence = (
            (*state.evidence, *inventory.evidence_lines())
            if inventory is not None else state.evidence
        )
        allowed = {
            "architect": {
                "clean_new", "partial_bootstrap", "adopted_lockout",
                "retired_lockout", "public_distribution",
            },
            "general": {"adopted_lockout", "retired_lockout"},
            "recovery": {"partial_bootstrap"},
        }
        if args.role == "auto":
            if state.name == "clean_new":
                selected_role = "Fresh Architect (conversation-first)"
                prompt = _architect_inspection_prompt(state, inventory)
            else:
                selected_role, prompt = next_prompt(state)
        elif state.name not in allowed[args.role]:
            allowed_states = ", ".join(sorted(allowed[args.role]))
            active_detail = (
                "; the bounded Operator remains the only routed execution role"
                if state.name == "active_work_order" else ""
            )
            raise CoordinatorError(
                f"role {args.role!r} is not allowed for lifecycle "
                f"{state.name!r}; allowed lifecycle states: {allowed_states}"
                f"{active_detail}"
            )
        elif args.role == "architect":
            selected_role = "Fresh Architect"
            prompt = _architect_inspection_prompt(state, inventory)
        elif args.role == "general":
            selected_role = "Fresh General"
            prompt = GENERAL_PROMPT
        else:
            selected_role, prompt = next_prompt(state)
    except CoordinatorError as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 2
    print(f"Canonical project root: {project.as_posix()}")
    print(f"Observed lifecycle state: {state.name}")
    if args.brief:
        print(f"Selected role: {selected_role}")
        print()
        print(render_compact_brief(project, state, selected_role))
        return 0
    for item in inspection_evidence:
        print(f"  - {item}")
    print(f"Selected role: {selected_role}")
    print("\nCopy this prompt into a fresh session:\n")
    print(prompt)
    return 0


def render_time(owner_time: str) -> str:
    if owner_time == "yes":
        return """**Owner active-minute capture: ENABLED.** Start when the first intake
question is presented. Stop when the coordinator returns the ratifiable adoption
packet or next-work-order candidate. Human reading, deciding, responding,
authentication, and unavoidable UI work count. Agent execution and waiting do
not. Report the actual total at acceptance; never reconstruct it later."""
    return """**Owner active minutes: NOT REPORTED.** Capture was declined for this
bootstrap. Do not infer or reconstruct a value."""


def render_handoff(args: argparse.Namespace, state: ObservedState,
                   functions: tuple[str, ...], privacy_count: int,
                   canonical: str, inventory: LocalInventory | None = None) -> str:
    if inventory is not None:
        role, prompt = conversation_first_opening(inventory)
    else:
        role, prompt = next_prompt(state)
    evidence_lines = list(state.evidence)
    if inventory is not None:
        evidence_lines.extend(inventory.evidence_lines())
    evidence = "\n".join(f"- {item}" for item in evidence_lines)
    operator_rows = "\n".join(
        f"- **{name}:** give `operations/{portable_slug(name)}.md` to the agent "
        "or administrator that can reach only that external function."
        for name in functions
    ) or "- No external Operator function was named during intake."
    active = (
        f"\nPointed work order: `{state.active_work_order}`."
        if state.active_work_order else ""
    )
    scenario = (
        "\n## Scenario boundary\n\n"
        f"{DNS_MAIL_SCENARIO_CONTEXT}\n"
        if args.scenario == "dns-mail-migration" else ""
    )
    return f"""# Writwall day-zero handoff: {args.project_name}

This directory is temporary bootstrap material. It does not install or adopt
Writwall, ratify intent, activate a work order, or grant external authority.
Remove it before the adoption commit after the authorized recorder no longer
needs it.

{SECRET_WARNING}

{_canonical_root_block(canonical)}
## Observed lifecycle state

**{state.name}**{active}

{evidence}

Repository bytes, not prior chat, determine this state. Re-run the coordinator
if those bytes change before acting.

## Project intake

- Project: {args.project_name}
- Purpose: {args.purpose}
- Preferred primary agent/interface: {args.agent}
- Execution location: {args.location}
- Repository and external environment: {args.environment}

These answers are unratified intake. The Owner must approve material intent.

## Local privacy screen

**Ready ({privacy_count} entries).** Writwall created or refreshed the durable,
project-specific screen outside the repository. Its location and values are
intentionally omitted. Temporary bootstrap or projection cleanup must not
delete it. Add human-known names, codenames, client identifiers, or domains
with `writwall privacy add`; never add credentials or secret values.
{scenario}
## Recommended smallest credible role split

{role_split_recommendation(functions)}

## Who to open next

**{role}**, using **{args.agent}** at **{args.location}**.

Paste exactly:

```text
{prompt}
```

## Authority and mechanics

- The human Owner decides intent, identity, risk acceptance, lifecycle actions,
  provider selection, production cutovers, and acceptance.
- The Architect may interview, challenge, and develop the project before adoption,
  and later judge design conformance when the General routes that question back.
- The General may draft, route, record exact ratified decisions, and perform
  explicitly authorized clerical lifecycle mechanics after adoption.
- A repository Operator works only under the active work order.
- A fresh Reviewer evaluates the order, result, evidence, and report without
  implementing corrections in the same context.
- External Operators receive only bounded packets. The General retains the
  proverbial keys: routing and authority, not passwords or cryptographic keys.

## External Operator routing

{operator_rows}

Provider selection, DNS authority, mail routing, mailbox data, repository work,
and deployment are separate decision or execution boundaries. Do not collapse
them into one broad infrastructure authorization.

## Owner-time measurement

{render_time(args.owner_time)}
"""


def discovery_record(
    args: argparse.Namespace, functions: tuple[str, ...], canonical: str,
    inventory: LocalInventory | None = None,
) -> dict:
    candidate = (
        args.project_name
        if args.project_name not in {"Unnamed idea", "Unnamed existing project"}
        else None
    )
    unresolved_questions: list[str] = []
    if inventory is not None:
        unresolved_questions.append(
            "Does the Owner want to explore this observed existing work, or "
            "start elsewhere with a different idea?"
            if inventory.is_existing else
            "What is the Owner thinking?"
        )
    return {
        "schema": 2,
        "authority": "unratified_discovery_only",
        "project_root": canonical,
        "identity": {
            "state": "working_candidate" if candidate else "unnamed",
            "working_candidate": candidate,
            "canonical_name": None,
        },
        "local_observations": (
            {
                "authority": "observed_local_evidence_only",
                "has_git": inventory.has_git,
                "branch": inventory.branch,
                "git_working_tree": inventory.cleanliness,
                "recent_commit_subjects": list(inventory.recent_commit_subjects),
                "top_level_entries": list(inventory.top_level_entries),
            }
            if inventory is not None else None
        ),
        "unresolved_questions": unresolved_questions,
        "topology": topology_recommendation(args, functions),
        "qualification": {
            "problem_or_opportunity": getattr(args, "problem", None) or args.purpose,
            "intended_user": getattr(args, "intended_user", None),
            "why_outcome_matters": getattr(args, "why_matters", None),
            "evidence_and_assumptions": getattr(args, "evidence", None),
            "smallest_useful_outcome": getattr(args, "smallest_outcome", None),
            "success_signal": getattr(args, "success_signal", None),
            "constraints": list(getattr(args, "constraint", ())),
            "non_goals": list(getattr(args, "non_goal", ())),
            "material_risks": list(getattr(args, "risk", ())),
            "stop_kill_conditions": list(getattr(args, "kill_condition", ())),
            "existing_assets": list(getattr(args, "asset", ())),
            "repository_runtime_deployment_environment": args.environment,
            "preferred_agent_interface": args.agent,
            "external_systems_and_operators": list(functions),
            "owner_time_capture": args.owner_time == "yes",
        },
    }


def architect_packets(
    args: argparse.Namespace, functions: tuple[str, ...], canonical: str,
) -> dict[str, str]:
    common = (
        "This packet is unratified discovery. It confers no authority to implement, "
        "install, publish, configure, or operate an external system.\n"
    )
    root_block = _canonical_root_block(canonical)
    return {
        "ARCHITECT.md": f"""# Architect packet

{common}
{root_block}
The Architect owns pre-adoption discovery and later design-conformance
judgment. Before requesting promotion into adoption mechanics, the Architect
returns a concise project sketch, a recommended Owner/Architect/General/
Operator topology, a provisional first backlog, key uncertainties and risks,
and one explicit Owner promotion decision. If the idea remains exploratory or
is rejected, no adoption, work order, or construction control is created.

Paste exactly into the preferred frontier Architect session:

```text
Act as the Architect. Read discovery.json and every packet in this
directory. Continue qualification one question at a time where evidence is
incomplete or contradictory, using any local observations already recorded
before asking the Owner to restate them. Recommend the smallest credible
project and Owner/Architect/General/Operator role topology, label every
recommendation unratified, prepare the exact Owner ratification choices, and
stop. Do not implement the project, canonicalize its identity, install
tooling, or operate any external system.
```
""",
        "GENERAL.md": f"""# General packet

{common}
{root_block}
The General maintains project continuity after adoption: preparing bounded
dispatch, routing work between the Architect and Operators, and performing
only explicitly authorized recorder mechanics. The General does not ratify
intent, judge design conformance, or adopt a project on the Owner's behalf.

Paste exactly into the preferred frontier session:

```text
{GENERAL_PROMPT}
```
""",
        "OPERATOR.md": f"""# Operator packet

{common}
{root_block}
{authorization_continuity_block()}

## Preconditions
- An Owner-ratified plan and active bounded work order exist.
## Permitted actions
- Only paths and commands granted by that work order.
## Prohibited actions
- No external-system operation or inferred identity decision.
## Verification
- Return exact checks and observed results.
## Evidence to return
- Changed paths, reasons, failures, and remaining boundaries.
""",
        "OWNER-AGENT.md": f"""# Owner-Agent packet (compatibility alias for Architect)

{common}
{root_block}
This is a compatibility alias for the **Architect** role packet
(`ARCHITECT.md`), kept for existing `OWNER-AGENT.md` consumers. New
integrations should read `ARCHITECT.md` directly; both describe the same
Architect role.

Paste exactly into the preferred frontier Architect session:

```text
Act as the Architect. Read discovery.json and every
packet in this directory. Continue qualification one question at a time where
evidence is incomplete or contradictory. Recommend the smallest credible
project and role topology, label every recommendation unratified, prepare the
exact Owner ratification choices, and stop. Do not implement the project,
canonicalize its identity, install tooling, or operate any external system.
```
""",
        "REPOSITORY-OPERATOR.md": f"""# Repository Operator packet (compatibility alias)

{common}
{root_block}
This is a compatibility alias for the **Operator** role packet
(`OPERATOR.md`), kept for existing `REPOSITORY-OPERATOR.md` consumers. New
integrations should read `OPERATOR.md` directly; both describe the same
Operator role.

{authorization_continuity_block()}

## Preconditions
- An Owner-ratified plan and active bounded work order exist.
## Permitted actions
- Only paths and commands granted by that work order.
## Prohibited actions
- No external-system operation or inferred identity decision.
## Verification
- Return exact checks and observed results.
## Evidence to return
- Changed paths, reasons, failures, and remaining boundaries.
""",
        "REVIEWER.md": f"""# Fresh Reviewer packet

{common}
{root_block}
## Preconditions
- Review only after the Architect returns a ratifiable packet or an Operator returns evidence.
## Review
- Challenge intent traceability, boundary fit, name state, topology, failure safety, and evidence.
## Prohibited actions
- Do not implement corrections in the same context.
## Evidence to return
- ACCEPT, ACCEPT WITH NON-BLOCKING POLISH, or RETURN with concrete findings.
""",
        "NAME-CLEARANCE.md": f"""# Name-clearance packet

{common}
{root_block}
No name is canonical, available, cleared, or accepted. A supplied name is only
a `working_candidate`. Before any repository slug, package, domain, logo, or
launch route hardens identity, use
`writwall-adopt/assets/scripts/collect_name_clearance.py` to collect the
canonical ledger, then run the offline
`writwall-adopt/assets/checks/check_name_clearance.py`. The seven required
sources are `github`, `pypi`, `npm`, `crates_io`, `com_rdap`,
`web_common_law`, and `uspto`. Obtain named-human web/common-law and USPTO
review, follow `writwall-adopt/references/name-clearance.md`, and return the
checker-clean evidence to the Owner for an explicit later Owner disposition.

If identity remains internal-only or deferred, the future trigger is exact:
run name clearance before the first public repository slug, package name,
domain, logo, public announcement, customer-facing use, or launch route.
""",
        "OWNER-RATIFICATION.md": f"""# Owner ratification gate

{common}
{root_block}
The Owner must explicitly accept, reject, or revise the qualified problem,
smallest useful outcome, success signal, constraints, non-goals, risks, kill
conditions, role topology, external boundaries, and identity disposition.
Silence, generated files, and repository state are not ratification. Stop here
until the Owner supplies that disposition; no implementation packet is active.
""",
    }


def _atomic_publish(stage: Path, output: Path) -> None:
    """Atomically publish a directory without replacing any destination."""
    if os.name == "nt":
        os.rename(stage, output)
        return

    library = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(stage)
    output_bytes = os.fsencode(output)
    if sys.platform.startswith("linux"):
        rename = getattr(library, "renameat2", None)
        if rename is None:
            raise OSError(
                errno.ENOTSUP,
                "atomic no-replace directory publication is unavailable",
            )
        rename.argtypes = (
            ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
            ctypes.c_uint,
        )
        rename.restype = ctypes.c_int
        result = rename(-100, source_bytes, -100, output_bytes, 1)
    elif sys.platform == "darwin":
        rename = getattr(library, "renamex_np", None)
        if rename is None:
            raise OSError(
                errno.ENOTSUP,
                "atomic no-replace directory publication is unavailable",
            )
        rename.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        rename.restype = ctypes.c_int
        result = rename(source_bytes, output_bytes, 0x00000004)
    else:
        raise OSError(
            errno.ENOTSUP,
            "atomic no-replace directory publication is unavailable",
        )
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), output)


def write_bootstrap(project: Path, args: argparse.Namespace, state: ObservedState,
                    functions: tuple[str, ...], privacy_count: int,
                    inventory: LocalInventory | None = None) -> Path:
    canonical = project.as_posix()
    output = project / OUTPUT_NAME
    if _entry_exists(output):
        raise CoordinatorError(
            f"create-only stop: {OUTPUT_NAME} already exists; nothing was overwritten"
        )
    if _is_linklike(BUNDLE_SOURCE) or not BUNDLE_SOURCE.is_dir():
        raise CoordinatorError("Writwall adoption bundle is missing from this distribution")
    bundle_files = sorted(
        path for path in BUNDLE_SOURCE.rglob("*")
        if path.is_file()
        and not _is_python_bytecode_residue(path, BUNDLE_SOURCE)
    )
    if not bundle_files:
        raise CoordinatorError("Writwall adoption bundle is empty")
    for source in bundle_files:
        current = BUNDLE_SOURCE
        for part in source.relative_to(BUNDLE_SOURCE).parts:
            current = current / part
            if _is_linklike(current):
                raise CoordinatorError(
                    "Writwall adoption bundle contains a symlink, junction, or reparse entry"
                )

    slugs = [portable_slug(name) for name in functions]
    if len(slugs) != len(set(slugs)):
        raise CoordinatorError("external Operator names collapse to duplicate portable filenames")

    stage = project.parent / (
        f".{project.name}-writwall-bootstrap-stage-{uuid.uuid4().hex}"
    )
    try:
        stage.mkdir()
    except OSError as exc:
        raise CoordinatorError(
            f"cannot create same-filesystem bootstrap stage outside the target: {exc}"
        ) from exc
    try:
        bundle_target = stage / "writwall-adopt"
        for source in bundle_files:
            relative = source.relative_to(BUNDLE_SOURCE)
            target = bundle_target / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())

        intake = {
            "schema": 1,
            "observed_state": state.name,
            "state_evidence": list(state.evidence),
            "active_work_order": state.active_work_order,
            "project_name": args.project_name,
            "purpose": args.purpose,
            "preferred_agent": args.agent,
            "execution_location": args.location,
            "repository_external_environment": args.environment,
            "scenario": args.scenario,
            "scenario_context": (
                DNS_MAIL_SCENARIO_CONTEXT
                if args.scenario == "dns-mail-migration" else None
            ),
            "recommended_role_split": role_split_recommendation(functions),
            "external_operator_functions": list(functions),
            "external_operator_tasks": dict(
                getattr(args, "external_operator_tasks", {})
            ),
            "owner_time_capture": args.owner_time == "yes",
            "project_root": canonical,
            "authority": "unratified_intake_only",
            "privacy_screen": {
                "ready": True,
                "entry_count": privacy_count,
                "location_disclosed": False,
            },
        }
        (stage / "intake.json").write_text(
            json.dumps(intake, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        (stage / "HANDOFF.md").write_text(
            render_handoff(args, state, functions, privacy_count, canonical, inventory),
            encoding="utf-8",
            newline="\n",
        )
        (stage / "discovery.json").write_text(
            json.dumps(discovery_record(args, functions, canonical, inventory), indent=2,
                       ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        for name, content in architect_packets(args, functions, canonical).items():
            (stage / name).write_text(content, encoding="utf-8", newline="\n")
        if functions:
            operator_tasks = getattr(args, "external_operator_tasks", {})
            operations = stage / "operations"
            operations.mkdir()
            for name, slug in zip(functions, slugs):
                (operations / f"{slug}.md").write_text(
                    operation_packet(
                        name, canonical, operational_task=operator_tasks.get(name)
                    ),
                    encoding="utf-8", newline="\n",
                )
        residue = sorted(
            path.relative_to(stage).as_posix()
            for path in stage.rglob("*")
            if _is_python_bytecode_residue(path, stage)
        )
        if residue:
            raise CoordinatorError(
                "bootstrap stage contains non-canonical Python bytecode residue: "
                + ", ".join(residue)
            )
        if _entry_exists(output):
            raise CoordinatorError(
                f"create-only stop: {OUTPUT_NAME} appeared during creation; nothing was overwritten"
            )
        _atomic_publish(stage, output)
    except Exception as exc:
        cleanup_error = None
        if _entry_exists(stage):
            try:
                shutil.rmtree(stage)
            except OSError as cleanup_exc:
                cleanup_error = cleanup_exc
        if _entry_exists(stage):
            raise CoordinatorError(
                "bootstrap publication failed and the complete external stage "
                f"could not be removed: {stage} ({cleanup_error})"
            ) from exc
        raise CoordinatorError(
            "bootstrap creation stopped before atomic publication; Writwall "
            "published no target; an independently existing destination may "
            f"remain: {exc}"
        ) from exc
    return output


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or (default or "")


def interactive_args(args: argparse.Namespace) -> argparse.Namespace:
    print(SECRET_WARNING)
    if not args.owner_time:
        args.owner_time = ask(
            "Track Owner active minutes? If yes, start a timer before answering",
            "yes",
        ).lower()
    if args.owner_time == "yes":
        print(
            "Owner timer starts now: count your reading, decisions, responses, "
            "authentication, and unavoidable UI work; exclude agent waiting."
        )
    confirmation = ask("Continue without entering secrets?", "yes").lower()
    if confirmation not in {"y", "yes"}:
        raise CoordinatorError("stopped before reading project intake")
    args.confirm_no_secrets = True
    # `args.project_root` is always already resolved by the caller before
    # `interactive_args` runs; there is no reachable case where it is blank.
    if not args.project_name:
        args.project_name = ask("Working candidate name, or blank for an unnamed idea", "")
    if not args.brief_file and not args.purpose and not args.problem:
        supplied_brief = ask("Existing project brief file path, or blank", "")
        if supplied_brief:
            args.brief_file = supplied_brief
    if args.brief_file:
        args.purpose = ""
    else:
        if not args.purpose:
            args.problem = args.problem or ask("Problem or opportunity")
            args.intended_user = args.intended_user or ask("Intended user")
            args.why_matters = args.why_matters or ask("Why the outcome matters")
            args.evidence = args.evidence or ask("Current evidence and assumptions")
            args.smallest_outcome = args.smallest_outcome or ask("Smallest useful outcome")
            args.success_signal = args.success_signal or ask("Success signal")
            args.constraint = args.constraint or [ask("Constraints")]
            args.non_goal = args.non_goal or [ask("Non-goals")]
            args.risk = args.risk or [ask("Material risks")]
            args.kill_condition = args.kill_condition or [ask("Stop or kill conditions")]
            args.asset = args.asset or [ask("Existing assets")]
            args.purpose = args.problem
    args.agent = args.agent or ask(
        "Preferred primary agent and interface", "Claude Code in VS Code"
    )
    args.location = args.location or ask(
        "Where will that agent run?", "local project workspace"
    )
    args.environment = args.environment or ask(
        "Describe the repository and any external environment it must coordinate with",
        "local repository only",
    )
    print(
        "Recommended minimum: one human Owner, one Architect, one General, "
        "one repository Operator when mutation starts, one fresh Reviewer, "
        "and external Operators only for distinct account or rollback boundaries."
    )
    if not args.external_operator and not args.scenario:
        external = ask(
            "External Operator functions, comma-separated (DNS, mail, VPS), or blank",
            "",
        )
        args.external_operator = [part.strip() for part in external.split(",") if part.strip()]
    print(
        "Optional privacy screen: add private names, codenames, client identifiers, "
        "or domains. Never enter passwords, tokens, keys, recovery codes, or secret values."
    )
    while True:
        try:
            identifier = ask("Private identifier (blank to finish)", "")
        except EOFError:
            identifier = ""
        if not identifier:
            break
        args.private_identifier.append(identifier)
    return args


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Start with an idea and prepare a create-only, project-local "
            "Writwall adoption handoff. "
            "This does not install or adopt Writwall."
        )
    )
    parser.add_argument("--project-root")
    parser.add_argument("--project-name")
    parser.add_argument("--purpose")
    parser.add_argument("--problem")
    parser.add_argument("--intended-user")
    parser.add_argument("--why-matters")
    parser.add_argument("--evidence")
    parser.add_argument("--smallest-outcome")
    parser.add_argument("--success-signal")
    parser.add_argument("--constraint", action="append", default=[])
    parser.add_argument("--non-goal", action="append", default=[])
    parser.add_argument("--risk", action="append", default=[])
    parser.add_argument("--kill-condition", action="append", default=[])
    parser.add_argument("--asset", action="append", default=[])
    parser.add_argument("--brief-file")
    parser.add_argument("--agent")
    parser.add_argument("--location")
    parser.add_argument("--environment")
    parser.add_argument("--external-operator", action="append", default=[])
    parser.add_argument("--external-operator-task", action="append", default=[])
    parser.set_defaults(private_identifier=[])
    parser.add_argument("--scenario", choices=("dns-mail-migration",))
    parser.add_argument("--owner-time", choices=("yes", "no"))
    parser.add_argument("--confirm-no-secrets", action="store_true")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument(
        "--structured-intake", action="store_true",
        help=(
            "run the former full interactive questionnaire instead of the "
            "ordinary, nonblocking conversation-first flow"
        ),
    )
    return parser.parse_args(argv)


def _discover_git_worktree_root(project: Path) -> Path | None:
    """Return the Git worktree top level containing ``project``, if any.

    Walks upward looking for a directory with a `.git` entry: a directory
    for an ordinary repository or the primary worktree, a file for a linked
    worktree. This mirrors how Git itself discovers a repository top level,
    without requiring a `git` executable. Returns `None` for a non-Git
    directory tree.
    """
    current = project
    while True:
        if _entry_exists(current / ".git"):
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def resolve_project_root(value: str | None) -> Path:
    if not value:
        raise CoordinatorError("missing required intake: project root")
    supplied_project = Path(value).expanduser()
    if supplied_project.is_symlink():
        raise CoordinatorError("target project must not be a symlink")
    try:
        project = supplied_project.resolve(strict=True)
    except OSError as exc:
        raise CoordinatorError(f"target project directory is not readable: {exc}") from exc
    if not project.is_dir() or project.is_symlink():
        raise CoordinatorError("target project must be an existing, non-symlink directory")
    worktree_root = _discover_git_worktree_root(project)
    if worktree_root is not None and worktree_root != project:
        raise CoordinatorError(
            "the supplied project directory is nested inside a Git worktree; "
            f"the discovered worktree top level is {worktree_root.as_posix()}. "
            "Rerun this coordinator with --project-root set to that exact "
            "worktree top level. Writwall never silently selects a nested "
            "directory or an ancestor repository the Owner did not name."
        )
    return project


def _validate_idea_qualification(args: argparse.Namespace) -> None:
    """Preserve the explicit ``--problem`` contract in every intake mode."""
    qualification = {
        "problem or opportunity": args.problem,
        "intended user": args.intended_user,
        "why the outcome matters": args.why_matters,
        "evidence and assumptions": args.evidence,
        "smallest useful outcome": args.smallest_outcome,
        "success signal": args.success_signal,
        "constraints": args.constraint,
        "non-goals": args.non_goal,
        "material risks": args.risk,
        "stop or kill conditions": args.kill_condition,
        "existing assets": args.asset,
    }

    def complete_answer(value: object) -> bool:
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, list):
            return bool(value) and all(
                isinstance(item, str) and bool(item.strip()) for item in value
            )
        return False

    missing_qualification = [
        name for name, value in qualification.items()
        if not complete_answer(value)
    ]
    if missing_qualification:
        raise CoordinatorError(
            "missing idea qualification: " + ", ".join(missing_qualification)
        )
    normalized_constraints = {
        re.sub(r"\s+", " ", value).strip().casefold()
        for value in args.constraint if value.strip()
    }
    normalized_non_goals = {
        re.sub(r"\s+", " ", value).strip().casefold()
        for value in args.non_goal if value.strip()
    }
    if normalized_constraints & normalized_non_goals:
        raise CoordinatorError(
            "contradictory idea qualification: the same statement cannot "
            "be both a constraint and a non-goal"
        )


def _parse_external_operator_tasks(
    functions: tuple[str, ...], raw_pairs: list[str],
) -> dict[str, str]:
    """Explicit, opt-in, per-Operator operational-task classification.

    Each entry is exactly ``Name=classification``. A classification is never
    inferred from the Operator function's own free-text name; it must be
    supplied here and must name one already-declared ``--external-operator``
    function exactly. A missing ``=``, an unsupported classification, a name
    matching no declared function, or a repeated name all reject before any
    output mutation.
    """
    tasks: dict[str, str] = {}
    for raw in raw_pairs:
        if "=" not in raw:
            raise CoordinatorError(
                f"malformed --external-operator-task {raw!r}; expected "
                "NAME=classification"
            )
        name, _, classification = raw.partition("=")
        name = name.strip()
        classification = classification.strip()
        if name not in functions:
            raise CoordinatorError(
                f"--external-operator-task names unmatched external Operator "
                f"function {name!r}; declare it with --external-operator first"
            )
        if classification not in OPERATIONAL_TASK_CLASSIFICATIONS:
            raise CoordinatorError(
                f"unsupported operational task classification {classification!r} "
                f"for {name!r}; expected one of "
                + ", ".join(sorted(OPERATIONAL_TASK_CLASSIFICATIONS))
            )
        if name in tasks:
            raise CoordinatorError(
                f"duplicate --external-operator-task classification for {name!r}"
            )
        tasks[name] = classification
    return tasks


def normalize_args(args: argparse.Namespace) -> tuple[argparse.Namespace, Path, tuple[str, ...]]:
    if args.structured_intake and not args.non_interactive:
        args = interactive_args(args)
    idea_mode = bool(args.problem)
    if idea_mode:
        args.project_name = args.project_name or "Unnamed idea"
        args.purpose = args.purpose or args.problem
    required = {
        "project root": args.project_root,
        "project name": args.project_name,
        "primary agent/interface": args.agent,
        "execution location": args.location,
        "repository/external environment": args.environment,
        "Owner-time choice": args.owner_time,
    }
    missing = [name for name, value in required.items() if not value]
    if args.non_interactive and not args.confirm_no_secrets:
        raise CoordinatorError(
            "non-interactive use requires --confirm-no-secrets; secrets must not be supplied"
        )
    if missing:
        raise CoordinatorError("missing required intake: " + ", ".join(missing))
    if idea_mode:
        _validate_idea_qualification(args)

    project = resolve_project_root(args.project_root)

    if args.brief_file:
        brief = Path(args.brief_file).expanduser()
        try:
            purpose = brief.read_text(encoding="utf-8-sig").strip()
        except (OSError, UnicodeError) as exc:
            raise CoordinatorError(f"cannot read supplied brief: {exc}") from exc
        if not purpose:
            raise CoordinatorError("supplied brief is empty")
        args.purpose = purpose
    if not args.purpose:
        raise CoordinatorError("missing project purpose or --brief-file")

    functions = list(args.external_operator)
    if args.scenario == "dns-mail-migration":
        functions.extend(name for name in DNS_MAIL_SCENARIO if name not in functions)
    normalized = tuple(name.strip() for name in functions if name.strip())
    args.external_operator_tasks = _parse_external_operator_tasks(
        normalized, args.external_operator_task
    )
    return args, project, normalized


def normalize_conversation_first_args(
    args: argparse.Namespace, project: Path, inventory: LocalInventory,
) -> tuple[argparse.Namespace, Path, tuple[str, ...]]:
    """Fill required intake fields from defaults and local evidence only.

    Never calls `ask()`/`input()`: the ordinary `--project-root`-only
    invocation must not block on stdin. Any explicitly supplied flag is
    preserved as given; qualification is deliberately deferred to the live
    Architect conversation rather than required up front.
    """
    args.confirm_no_secrets = True
    args.owner_time = args.owner_time or "no"
    args.agent = args.agent or "your preferred agent/interface"
    args.location = args.location or "local project workspace"
    args.environment = args.environment or (
        "existing local repository; environment not yet stated by the Owner"
        if inventory.has_git else
        "local repository only; environment not yet stated by the Owner"
    )
    if not args.project_name:
        args.project_name = (
            "Unnamed existing project" if inventory.is_existing else "Unnamed idea"
        )
    if args.problem:
        _validate_idea_qualification(args)
    if args.brief_file:
        brief = Path(args.brief_file).expanduser()
        try:
            purpose = brief.read_text(encoding="utf-8-sig").strip()
        except (OSError, UnicodeError) as exc:
            raise CoordinatorError(f"cannot read supplied brief: {exc}") from exc
        if not purpose:
            raise CoordinatorError("supplied brief is empty")
        args.purpose = purpose
    elif not args.purpose and not args.problem:
        args.purpose = (
            "An existing local project was observed; its purpose has not yet "
            "been stated by the Owner."
            if inventory.is_existing else
            "An idea has not yet been stated by the Owner."
        )

    functions = list(args.external_operator)
    if args.scenario == "dns-mail-migration":
        functions.extend(name for name in DNS_MAIL_SCENARIO if name not in functions)
    normalized = tuple(name.strip() for name in functions if name.strip())
    args.external_operator_tasks = _parse_external_operator_tasks(
        normalized, args.external_operator_task
    )
    return args, project, normalized


def main(argv: list[str] | None = None) -> int:
    try:
        from scripts.privacy_screen import (
            PrivacyScreenError, add_identifier, initialize,
        )

        args = parse_args(argv)
        project = resolve_project_root(args.project_root)
        state = classify_project(project)
        if state.name != "clean_new":
            emit_lifecycle_handoff(state)
            return 0

        inventory: LocalInventory | None = None
        if args.non_interactive or args.structured_intake:
            args, project, functions = normalize_args(args)
        else:
            # The ordinary, low-friction invocation: only --project-root (and
            # optionally a few explicit flags), no `input()` call, no
            # blocking questionnaire. Local evidence stands in for answers
            # the Owner has not yet given, and qualification is deferred to
            # the live Architect conversation.
            inventory = gather_local_inventory(project)
            args, project, functions = normalize_conversation_first_args(
                args, project, inventory
            )

        current_state = classify_project(project)
        if current_state.name != state.name:
            raise CoordinatorError(
                "lifecycle changed during intake: expected clean_new, observed "
                f"{current_state.name}; no privacy or bootstrap bytes were created"
            )
        if _entry_exists(project / OUTPUT_NAME):
            raise CoordinatorError(
                f"create-only stop: {OUTPUT_NAME} already exists; nothing was overwritten"
            )
        try:
            privacy_count = initialize(project)
            for identifier in args.private_identifier:
                privacy_count = add_identifier(project, identifier)
        except PrivacyScreenError as exc:
            raise CoordinatorError(str(exc)) from exc
        output = write_bootstrap(project, args, state, functions, privacy_count, inventory)
    except CoordinatorError as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        return 2
    print(f"Observed lifecycle state: {state.name}")
    print(f"Created: {output.as_posix()}")
    print(f"Next: read {(output / 'HANDOFF.md').as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
