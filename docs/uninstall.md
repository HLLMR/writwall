# Emergency exit from Writwall

v0.13.0 is the final recovery release. It adds `writwall uninstall`. Existing
projects do not need to adopt a new Doctrine revision, close their work order,
repair governance records, or install a hook to use it.

## Run as the Owner

Close agents working in the target repository. Run these commands in your own
terminal, outside the agent's blocked tool session. Keep other writers stopped
until apply or restore finishes. This is an Owner-operated maintenance tool,
not a way for an agent to ignore a denied tool call.

Install the recovery CLI into a separate tooling environment, or unpack the
v0.13.0 source distribution outside your project and run its standalone
`scripts/uninstall_writwall.py` with Python 3.10 or newer. Do not unpack a
Writwall distribution over your application's files. The standalone script
uses only the Python standard library and does not require installation,
network access, or imports from the target repository.

The installed entry point and standalone script accept the same arguments.
In the examples below, set the three paths yourself once; the plan and backup
directory must be outside the target project. Use a durable local backup
location, not temporary storage that may be cleared automatically.
Plans and backups can contain private project configuration; keep them local
and do not attach them to a public issue or release.

```powershell
$project = Read-Host 'Full path of the project to remove Writwall from'
$plan = Read-Host 'Full path for a new uninstall plan JSON outside the project'
$backup = Read-Host 'Full path for a new backup directory outside the project'

writwall uninstall --project-root "$project" --plan-output "$plan"
```

Read the plan. Preview does not change the project. It identifies the exact
settings edits, removals, preserved material, and blockers. It never asks an
agent to interpret a grant. Missing, stale, malformed, or oversized work orders
do not determine whether the Owner can leave.

## Apply the reviewed plan

```powershell
writwall uninstall --project-root "$project" --apply --plan "$plan" --backup-root "$backup"
```

Application rechecks the plan against current file bytes. A changed candidate
requires a new preview. Originals and a recovery journal are preserved outside
the repository before changes. Keep the printed journal path for restoration.
Unrelated settings and hook entries are retained. Modified files may be
reformatted JSON; the original bytes are in the backup.

Default recovery removes recognized Writwall hook registrations. It does not
delete an entire settings file just because one Writwall hook was installed.
Unrecognized wrappers or malformed settings require explicit manual review;
the tool must not claim that those registrations have been removed.

For an older or customized installation, preview can explicitly select an
exact Writwall command with `--remove-hook-command`. Copy the entire command
from your settings and pass it as one argument; do not substitute a substring.
The reviewed plan binds that selection and the current settings bytes. This
selection is an Owner decision, not proof that arbitrary custom code belongs
to Writwall. Both `.claude/settings.json` and `.claude/settings.local.json`
are inspected; user-level and enterprise settings remain outside this tool.

If a settings file is malformed, preserve its exact bytes outside the project,
then repair its JSON in an editor while removing only the Writwall hook entry.
Do not delete the whole file to remove one hook. Preview again after that
repair. A process whose project settings cannot be parsed is not a successful
uninstall, even if the hook happens not to execute.

## Remove instructions and documents deliberately

Hook removal frees the provider tool interface; it does not erase instructions
that an agent might still load. Review retained `CLAUDE.md`, `AGENTS.md`, skill
configuration, and project documents before starting a new agent.

Use repeatable `--remove-path` options during preview to select supported
Writwall files for removal, then apply that new reviewed plan. Each selected
file is backed up. Only select files whose complete contents you intend to
remove. A mixed project/Writwall document should instead be edited manually
after retaining its original, preserving the project's build instructions,
architecture decisions, safety constraints, and current work.

The tool intentionally does not recursively delete `governance/`, infer that
all Markdown files are Writwall-owned, or rewrite your project's state. Legacy
installations have no complete ownership manifest. Remaining unknown or mixed
files are reported for Owner disposition rather than silently destroyed.

Retain useful decisions and unresolved tasks in ordinary project documents or
your issue tracker. Preserve original reviews and evidence as local records;
Git does not back up untracked files. The uninstall backup covers only the
files in its plan, not the whole repository or every untracked artifact.

## Restore or recover an interrupted application

Use the journal path printed by apply:

```text
writwall uninstall --restore PATH-TO-JOURNAL
```

Restoration verifies backups and refuses to overwrite unrelated newer edits.
Restoration preserves file bytes, not original ACLs, executable bits, timestamps,
or other filesystem metadata. Check any custom permissions before resuming.
If application was interrupted, keep the complete backup directory and use
its journal. Do not hand-edit journal hashes to force acceptance. Inspect any
reported conflicts before proceeding.

## Verify the exit

Inspect the resulting diff and run your application's normal checks. Start a
fresh agent session and inspect its loaded hooks and instructions. Confirm that
Writwall's hook is absent, then run an ordinary local build or test. Other
provider, user-level, enterprise-managed, or Git hook policies may still apply;
the tool does not disable those. No new session is qualified merely because a
JSON file changed.

The tool never creates a branch, stages, commits, pushes, merges, deploys,
executes application code, or changes cloud resources. Review and commit the
cleanup through your project's normal process. It leaves history and the
installed Python package in place; package-manager removal is optional after
recovery, and removing a Python package alone does not remove project hooks.
