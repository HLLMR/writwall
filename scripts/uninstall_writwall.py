#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 HLLMR Ventures LLC
# SPDX-License-Identifier: Apache-2.0
"""Standalone, reversible Writwall hook off-ramp. No governance dependencies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import uuid

SETTINGS = '.claude/settings.json'
LOCAL_SETTINGS = '.claude/settings.local.json'
POINTER = '.claude/active-wo.txt'
HOOK = '.claude/hooks/wo_capability_wall.py'
COMMANDS = {f'{exe} "${{CLAUDE_PROJECT_DIR}}/{HOOK}"' for exe in ('py -3', 'python3')}
CANONICAL_HOOK_SHA256 = 'dd29af2a39d25e0270ad9acc23ee912f81e39c674e1179759f4a3010c6a0c1a0'


class RecoveryError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def safe_path(path):
    """Reject redirections in every existing path component, including junctions."""
    path = Path(os.path.abspath(path))
    for part in (*reversed(path.parents), path):
        if part.is_symlink():
            raise RecoveryError(f'Link refused: {part}')
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if getattr(info, 'st_file_attributes', 0) & 0x400:
            raise RecoveryError(f'Reparse point refused: {part}')
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise RecoveryError(f'Hardlink refused: {part}')
    return path


def read_file(path):
    path = safe_path(path)
    if not path.exists():
        return None
    if not path.is_file():
        raise RecoveryError(f'Expected regular file: {path}')
    return path.read_bytes()


def decode_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RecoveryError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(data.decode('utf-8-sig'), object_pairs_hook=unique)


def canonical_digest():
    return CANONICAL_HOOK_SHA256


def relative_target(root, rel):
    if not isinstance(rel, str) or '\\' in rel or ':' in rel:
        raise RecoveryError('Invalid relative target')
    parts = rel.split('/')
    reserved = {'con', 'prn', 'aux', 'nul', 'clock$', 'conin$', 'conout$'}
    reserved.update(f'{prefix}{digit}' for prefix in ('com', 'lpt') for digit in '123456789¹²³')
    if any(p.casefold() in ('', '.', '..', '.git') or p.endswith((' ', '.'))
           or p.split('.')[0].casefold() in reserved
           or any(ord(c) < 32 or c in '<>"|?*' for c in p) for p in parts):
        raise RecoveryError('Invalid relative target')
    return safe_path(root / rel)


def target_key(path):
    # Reject Windows aliases on every host so a portable plan keeps its meaning.
    return str(path).casefold()


def root_identity(root):
    info = root.stat()
    return [info.st_dev, info.st_ino]


def preview(project_root, remove_paths=(), remove_hook_commands=()):
    root = safe_path(project_root)
    if not root.is_dir() or root == root.parent:
        raise RecoveryError('Project root must be an existing non-filesystem-root directory')
    selected_commands = sorted(set(remove_hook_commands))
    if any(not isinstance(c, str) or 'wo_capability_wall' not in c for c in selected_commands):
        raise RecoveryError('Explicit hook selection must name an exact Writwall hook command')
    removals = sorted(set(remove_paths))
    selected_targets = set()
    for rel in removals:
        target = relative_target(root, rel)
        key = target_key(target)
        if key in selected_targets:
            raise RecoveryError('Duplicate or aliased removal target')
        selected_targets.add(key)
        data = read_file(target)
        if data is None or (rel not in (HOOK, POINTER) and (target.suffix.lower() != '.md' or b'writwall' not in data.lower())):
            raise RecoveryError('Selected removal must be a regular Writwall-identified Markdown document or canonical hook')
    original = read_file(root / SETTINGS)
    local_original = read_file(root / LOCAL_SETTINGS)
    hook = read_file(root / HOOK)
    known = hook is not None and digest(hook.replace(b'\r\n', b'\n')) == canonical_digest()
    warnings = []
    removed = 0
    changes = []
    matched_commands = set()
    for settings_rel, settings_bytes in ((SETTINGS, original), (LOCAL_SETTINGS, local_original)):
        if settings_bytes is None:
            continue
        count = 0
        obj = decode_json(settings_bytes)
        if not isinstance(obj, dict):
            raise RecoveryError('Settings must be a JSON object')
        hooks = obj.get('hooks', {})
        if not isinstance(hooks, dict):
            raise RecoveryError('Settings hooks must be an object')
        for event, entries in hooks.items():
            if not isinstance(entries, list):
                raise RecoveryError('Hook events must contain arrays')
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get('hooks'), list):
                    raise RecoveryError('Malformed hook registration')
                kept = []
                for registration in entry['hooks']:
                    if not isinstance(registration, dict):
                        raise RecoveryError('Malformed hook command')
                    command = registration.get('command', '')
                    if (registration.get('type') == 'command' and isinstance(command, str)
                            and ((event == 'PreToolUse' and command in COMMANDS and known) or command in selected_commands)):
                        removed += 1
                        count += 1
                        matched_commands.add(command)
                    else:
                        kept.append(registration)
                        if isinstance(command, str) and 'wo_capability_wall' in command:
                            warnings.append('Unrecognized or modified Writwall registration preserved: ' + command)
                entry['hooks'] = kept
        if count:
            result = (json.dumps(obj, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
            changes.append({'path': settings_rel, 'before': digest(settings_bytes), 'after': digest(result),
                            'content': result.decode('utf-8')})
    if set(selected_commands) - matched_commands:
        raise RecoveryError('Explicit hook command selection did not match a registration')
    if not (root / '.git').exists() and not (known or removed or warnings or removals):
        raise RecoveryError('Non-Git directory has no recognized Writwall artifacts')
    if HOOK in removals and (not known or warnings):
        raise RecoveryError('Cannot remove unverified hook or hook with preserved registrations')
    for rel in removals:
        changes.append({'path': rel, 'before': digest(read_file(root / rel)), 'after': None, 'content': None})
    residual = [rel for rel in ('CLAUDE.md', 'AGENTS.md', '.claude/CLAUDE.md')
                if rel not in removals and read_file(root / rel) is not None]
    return {'version': 1, 'project_root': str(root), 'root_identity': root_identity(root),
            'residual_instruction_files': residual, 'fully_removed': False,
            'status': 'manual_attention_required' if warnings or residual else 'known_registration_disable_only',
            'settings_sha256': digest(original),
            'local_settings_sha256': digest(local_original), 'remove_hook_commands': selected_commands,
            'hook_sha256': digest(hook), 'canonical_hook_sha256': canonical_digest(),
            'remove_paths': removals, 'registrations_removed': removed, 'warnings': warnings,
            'changes': changes}


def outside(path, root):
    path = safe_path(path)
    if path == root or root in path.parents:
        raise RecoveryError('Backup and journal must be outside the project')
    return path


def atomic_write(path, data):
    path = safe_path(path)
    descriptor, temporary = tempfile.mkstemp(prefix='.ww-recovery-', dir=str(path.parent))
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply_plan(plan, backup_root):
    root = safe_path(plan['project_root'])
    current = preview(root, plan['remove_paths'], plan['remove_hook_commands'])
    if current != plan:
        raise RecoveryError('Plan drift detected; generate and inspect a fresh preview')
    backup = outside(backup_root, root)
    backup.mkdir(parents=True, exist_ok=True)
    session = backup / ('writwall-recovery-' + uuid.uuid4().hex)
    session.mkdir()
    entries = []
    for index, change in enumerate(plan['changes']):
        data = read_file(root / change['path'])
        target = session / f'{index}.original'
        atomic_write(target, data)
        if digest(read_file(target)) != change['before']:
            raise RecoveryError('Backup did not match approved original; no targets changed')
        entries.append({'path': change['path'], 'backup': target.name,
                        'before': digest(data), 'after': change['after']})
    journal = session / 'journal.json'
    record = {'version': 1, 'project_root': str(root), 'root_identity': root_identity(root), 'entries': entries}
    atomic_write(journal, (json.dumps(record, indent=2) + '\n').encode())
    # All original bytes and the recovery journal exist before the first mutation.
    try:
        for change in plan['changes']:
            path = root / change['path']
            if digest(read_file(path)) != change['before']:
                raise RecoveryError(f'Late drift detected; recover using {journal}')
            if change['content'] is None:
                path.unlink()
            else:
                atomic_write(path, change['content'].encode('utf-8'))
    except (OSError, KeyboardInterrupt) as exc:
        raise RecoveryError(f'Apply interrupted ({type(exc).__name__}); recovery journal: {journal}') from exc
    return {'journal': str(journal), 'changed_paths': [c['path'] for c in plan['changes']],
            'warnings': plan['warnings'], 'status': plan['status'],
            'residual_instruction_files': plan['residual_instruction_files'], 'fully_removed': False}


def restore(journal_path):
    journal_path = safe_path(journal_path)
    record = decode_json(read_file(journal_path))
    root = safe_path(record['project_root'])
    if root_identity(root) != record['root_identity']:
        raise RecoveryError('Project root identity changed')
    outside(journal_path, root)
    pending = []
    seen = set()
    for entry in record['entries']:
        rel = entry['path']
        target = relative_target(root, rel)
        key = target_key(target)
        if (rel not in (SETTINGS, LOCAL_SETTINGS, HOOK, POINTER) and target.suffix.lower() != '.md') or key in seen:
            raise RecoveryError('Invalid journal target')
        seen.add(key)
        name = entry['backup']
        if not isinstance(name, str) or Path(name).name != name or '/' in name or '\\' in name:
            raise RecoveryError('Invalid backup name')
        original = read_file(journal_path.parent / name)
        if original is None or digest(original) != entry['before']:
            raise RecoveryError('Backup missing or hash mismatch')
        actual = digest(read_file(root / rel))
        if actual not in (entry['before'], entry['after']):
            raise RecoveryError(f'Restore refused: changed since uninstall: {rel}')
        if actual != entry['before']:
            pending.append((root / rel, original, actual))
    for path, original, expected in pending:
        if digest(read_file(path)) != expected:
            raise RecoveryError('Late drift during restore')
        atomic_write(path, original)
    return {'restored_paths': [str(p.relative_to(root)) for p, _, _ in pending],
            'journal': str(journal_path)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--remove-path', action='append', default=[])
    parser.add_argument('--remove-hook-command', action='append', default=[])
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--plan')
    parser.add_argument('--plan-output', help='Write preview JSON as UTF-8 to a new external file')
    parser.add_argument('--backup-root')
    parser.add_argument('--restore')
    args = parser.parse_args(argv)
    try:
        if args.restore:
            if args.apply or args.plan or args.remove_path or args.backup_root or args.plan_output or args.remove_hook_command:
                raise RecoveryError('Restore cannot be combined with apply or preview options')
            result = restore(args.restore)
        elif args.apply:
            if args.plan_output or args.remove_path or args.remove_hook_command:
                raise RecoveryError('Apply consumes the exact plan; no additional preview options allowed')
            if not args.plan or not args.backup_root:
                raise RecoveryError('Apply requires --plan and external --backup-root')
            plan = decode_json(read_file(args.plan))
            if safe_path(args.project_root) != safe_path(plan['project_root']):
                raise RecoveryError('Plan belongs to another project root')
            result = apply_plan(plan, args.backup_root)
        else:
            if args.plan or args.backup_root:
                raise RecoveryError('--plan and --backup-root require --apply')
            result = preview(args.project_root, args.remove_path, args.remove_hook_command)
            if args.plan_output:
                output = outside(args.plan_output, safe_path(args.project_root))
                with output.open('x', encoding='utf-8', newline='\n') as stream:
                    stream.write(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
