# Why Writwall ends with v0.13.0

The Owner designated v0.13.0 as Writwall's final recovery release on
2026-09-21. It provides a way to leave an existing installation. New adoption
is discouraged. The distributed Doctrine remains 0.9; installing recovery
tooling does not migrate a project's adopted Doctrine or ratify new policy.

## What failed

An interrupted project task was handed from one provider to another. The
replacement recovered the active authorization, unfinished files, missing
verification, and prior exceptions. However, the replacement could not run
the builds and tests required by that same authorization.

The canonical Claude adapter explicitly denies Bash and PowerShell even when
`shell.execute` says `restricted` or `allowed`. It cannot prove that arbitrary
shell commands preserve its protected control plane. That implementation is
consistent with its narrow enforcement design, but incompatible with an
ordinary build/test workflow represented as executable by the work order.
The provider switch exposed a capability mismatch; the grant did not make
the missing capability available. A denied canary demonstrated interception,
not the ability to complete authorized work.

Retiring an order only removes its active pointer. The installed hook then
denies mutation without an active order. Retirement was never an uninstall,
and the system lacked an independent Owner-operated exit.

Current truth was duplicated across the charter, state record, work order,
activation record, and session narrative. Those records drifted. Recovering
them took effort, and changing the execution environment generated more
recordkeeping instead of restoring the interrupted workflow.

The installation process did not keep a complete ownership manifest. Settings
were merged manually and project-specific decisions lived alongside Writwall
records. Blanket deletion of the settings file or governance directory is not
a safe general-purpose uninstaller.

## Recovery advice also failed

The assisting Architect supplied a nonexistent integration-branch placeholder,
mixed two worktree sequences, and supplied a PowerShell argument form that
failed when writing a recovery patch. It proposed removing the entire settings
file before checking for unrelated hooks. Those instructions increased the
Owner's burden during an incident. They are not a recovery interface to reuse.

An equal ZIP byte length was also treated as proof of equal payload content.
It is not. Different archive hashes require inspection of member contents and
metadata before assigning the difference to timestamps.

The Owner-provided incident reports support these conclusions. This release
does not independently attest to the affected project's source, tests, cloud
state, or deployment. No adopter's files or private records are shipped here.

## What this release changes

An Owner can run the uninstall tool from a normal terminal outside the blocked
agent session. It does not require an active work order, valid adoption record,
or successful governance parser. Preview, explicit application, external
backups, and restore are separate operations. Only recognized hook entries are
removed from shared settings; unrelated entries remain. Document removal is
explicit and bounded, because filenames cannot establish ownership.

Recovery does not relax the wall to allow arbitrary shell execution, claim a
provider-neutral sandbox, or convert previous UNKNOWN/FAIL evidence to PASS.
The Owner decides which project records to retain. Exit is independent of
Writwall's authorization loop, and no uninstall operation commits, pushes,
deploys, or edits application code on the Owner's behalf.

See [the emergency exit guide](uninstall.md) for the tested command interface,
its limits, and the final manual checks for a fresh agent session.
