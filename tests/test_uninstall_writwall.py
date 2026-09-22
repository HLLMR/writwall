# SPDX-FileCopyrightText: 2026 HLLMR Ventures LLC
# SPDX-License-Identifier: Apache-2.0
"""Behavioral recovery tests; no lifecycle activation is required."""
import contextlib
import io
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('uninstall', SOURCE / 'scripts/uninstall_writwall.py')
uninstall = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uninstall)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'project'
        self.root.mkdir()
        (self.root / '.git').write_text('gitdir: elsewhere')
        (self.root / '.claude/hooks').mkdir(parents=True)
        self.hook = self.root / uninstall.HOOK
        self.hook.write_bytes((SOURCE / 'adapters/claude-code/wo_capability_wall.py').read_bytes())
        self.settings = self.root / uninstall.SETTINGS
        self.obj = {'permissions': {'allow': ['Read']}, 'hooks': {'PreToolUse': [{'matcher': '*', 'hooks': [
            {'type': 'command', 'command': sorted(uninstall.COMMANDS)[0], 'timeout': 10},
            {'type': 'command', 'command': 'echo unrelated'}]}]}}
        self.save()

    def save(self):
        self.settings.write_text(json.dumps(self.obj), encoding='utf-8')

    def apply(self, removals=()):
        return uninstall.apply_plan(uninstall.preview(self.root, removals), self.base / 'backup')

    def test_disable_preserves_other_settings_and_restores_exact_bytes(self):
        before = self.settings.read_bytes()
        (self.root / 'CLAUDE.md').write_text('Writwall legacy instructions')
        plan = uninstall.preview(self.root)
        self.assertEqual(self.settings.read_bytes(), before)
        self.assertEqual(plan['residual_instruction_files'], ['CLAUDE.md'])
        result = self.apply()
        obj = json.loads(self.settings.read_text())
        self.assertEqual(obj['permissions'], self.obj['permissions'])
        self.assertEqual(obj['hooks']['PreToolUse'][0]['hooks'], [{'type': 'command', 'command': 'echo unrelated'}])
        self.assertTrue(self.hook.exists())
        uninstall.restore(result['journal'])
        self.assertEqual(self.settings.read_bytes(), before)

    def test_unknown_mixed_and_modified_hook_are_preserved(self):
        for command in ['echo ' + sorted(uninstall.COMMANDS)[0], sorted(uninstall.COMMANDS)[0] + ' && echo next']:
            self.obj['hooks']['PreToolUse'][0]['hooks'][0]['command'] = command
            self.save()
            self.assertEqual(uninstall.preview(self.root)['changes'], [])
            self.assertTrue(uninstall.preview(self.root)['warnings'])
        self.obj['hooks']['PreToolUse'][0]['hooks'][0]['command'] = sorted(uninstall.COMMANDS)[0]
        self.save()
        self.hook.write_text('modified')
        self.assertEqual(uninstall.preview(self.root)['changes'], [])

    def test_crlf_hook_recognized_but_raw_digest_pinned(self):
        self.hook.write_bytes(self.hook.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
        plan = uninstall.preview(self.root)
        self.assertEqual(plan['registrations_removed'], 1)
        self.assertEqual(plan['hook_sha256'], uninstall.digest(self.hook.read_bytes()))

    def test_malformed_duplicate_json_and_plan_drift_fail_unchanged(self):
        for invalid in (b'{', b'{"hooks":{},"hooks":{}}'):
            self.settings.write_bytes(invalid)
            with self.assertRaises(ValueError):
                uninstall.preview(self.root)
            self.assertEqual(self.settings.read_bytes(), invalid)
        self.save()
        plan = uninstall.preview(self.root)
        self.settings.write_bytes(self.settings.read_bytes() + b' ')
        with self.assertRaises(uninstall.RecoveryError):
            uninstall.apply_plan(plan, self.base / 'backup')

    def test_explicit_document_and_hook_removal_and_restore(self):
        (self.root / 'CLAUDE.md').write_text('Writwall instructions')
        result = self.apply(['CLAUDE.md', uninstall.HOOK])
        self.assertFalse(self.hook.exists())
        self.assertFalse((self.root / 'CLAUDE.md').exists())
        uninstall.restore(result['journal'])
        self.assertTrue(self.hook.exists())
        self.assertEqual((self.root / 'CLAUDE.md').read_text(), 'Writwall instructions')

    def test_restore_detects_drift_and_corrupt_backup(self):
        result = self.apply()
        changed = self.settings.read_bytes()
        self.settings.write_text('new owner settings')
        with self.assertRaises(uninstall.RecoveryError):
            uninstall.restore(result['journal'])
        self.assertEqual(self.settings.read_text(), 'new owner settings')
        self.settings.write_bytes(changed)
        journal = Path(result['journal'])
        (journal.parent / '0.original').write_bytes(b'bad')
        with self.assertRaises(uninstall.RecoveryError):
            uninstall.restore(journal)

    def test_invalid_paths_backup_and_journal_escape(self):
        for rel in ('../outside.md', '/outside.md', 'C:/outside.md', '.git/config', 'src/app.py'):
            with self.assertRaises(uninstall.RecoveryError):
                uninstall.preview(self.root, [rel])
        with self.assertRaises(uninstall.RecoveryError):
            uninstall.apply_plan(uninstall.preview(self.root), self.root / 'backup')
        result = self.apply()
        journal = Path(result['journal'])
        record = json.loads(journal.read_text())
        record['entries'][0]['path'] = '../outside.md'
        journal.write_text(json.dumps(record))
        with self.assertRaises(uninstall.RecoveryError):
            uninstall.restore(journal)

    def test_hardlinked_target_rejected(self):
        try:
            os.link(self.settings, self.base / 'linked.json')
        except OSError:
            self.skipTest('hardlinks unavailable')
        with self.assertRaises(uninstall.RecoveryError):
            uninstall.preview(self.root)

    def test_descendant_symlink_target_rejected(self):
        real = self.base / 'real-settings.json'
        real.write_bytes(self.settings.read_bytes())
        self.settings.unlink()
        try:
            self.settings.symlink_to(real)
        except OSError:
            self.skipTest('symlink creation unavailable')
        before = real.read_bytes()
        with self.assertRaises(uninstall.RecoveryError):
            uninstall.preview(self.root)
        self.assertEqual(real.read_bytes(), before)

    def test_active_order_does_not_control_emergency_exit(self):
        (self.root / '.claude/active-wo.txt').write_text('../../malformed')
        (self.root / 'governance').mkdir()
        (self.root / 'governance/broken.md').write_bytes(b'X' * 100000)
        self.assertEqual(uninstall.preview(self.root)['registrations_removed'], 1)

    def test_plan_output_utf8_exclusive_and_external(self):
        output = self.base / 'plan.json'
        args = ['--project-root', str(self.root), '--plan-output', str(output)]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(uninstall.main(args), 0)
            self.assertEqual(uninstall.main(args), 2)
            self.assertEqual(uninstall.main(['--project-root', str(self.root), '--plan-output', str(self.root / 'plan.json')]), 2)
        self.assertEqual(json.loads(output.read_text(encoding='utf-8')), uninstall.preview(self.root))

    def test_local_settings_surgically_disabled_and_restored(self):
        local = self.root / uninstall.LOCAL_SETTINGS
        local.write_bytes(self.settings.read_bytes())
        before = local.read_bytes()
        self.assertEqual(uninstall.preview(self.root)['registrations_removed'], 2)
        result = self.apply()
        self.assertNotEqual(local.read_bytes(), before)
        uninstall.restore(result['journal'])
        self.assertEqual(local.read_bytes(), before)

    def test_nongit_and_explicit_malformed_pointer_removal(self):
        (self.root / '.git').unlink()
        pointer = self.root / uninstall.POINTER
        pointer.write_bytes(b'\xff../../broken')
        result = self.apply([uninstall.POINTER])
        self.assertFalse(pointer.exists())
        uninstall.restore(result['journal'])
        self.assertEqual(pointer.read_bytes(), b'\xff../../broken')

    def test_custom_command_requires_exact_explicit_selection(self):
        custom = 'custom wrapper wo_capability_wall.py --flag'
        self.obj['hooks']['PreToolUse'][0]['hooks'][0]['command'] = custom
        self.save()
        self.assertEqual(uninstall.preview(self.root)['registrations_removed'], 0)
        plan = uninstall.preview(self.root, remove_hook_commands=[custom])
        self.assertEqual(plan['registrations_removed'], 1)
        result = uninstall.apply_plan(plan, self.base / 'backup')
        uninstall.restore(result['journal'])
        self.assertIn(custom, self.settings.read_text())

    def test_windows_dangerous_names_rejected_on_every_host(self):
        for rel in ('.GIT/private.md', '.git./private.md', 'docs./file.md',
                    'docs /file.md', 'CON.md', 'com1.md', 'LPT9/file.md', 'aux.txt/file.md'):
            with self.subTest(rel=rel), self.assertRaises(uninstall.RecoveryError):
                uninstall.relative_target(self.root, rel)

    def test_case_aliases_rejected_before_preview_mutation(self):
        (self.root / 'Doc.md').write_text('Writwall record')
        (self.root / 'doc.md').write_text('Writwall record')
        with self.assertRaises(uninstall.RecoveryError):
            uninstall.preview(self.root, ['Doc.md', 'doc.md'])
        self.assertTrue((self.root / 'Doc.md').exists())

    def test_restore_rejects_aliases_and_git_case_before_writes(self):
        (self.root / 'Doc.md').write_text('Writwall record')
        result = self.apply(['Doc.md'])
        journal = Path(result['journal'])
        record = json.loads(journal.read_text())
        duplicate = dict(record['entries'][-1])
        duplicate['path'] = 'doc.md'
        record['entries'].append(duplicate)
        journal.write_text(json.dumps(record))
        with self.assertRaises(uninstall.RecoveryError):
            uninstall.restore(journal)
        self.assertFalse((self.root / 'Doc.md').exists())
        record['entries'][-1]['path'] = '.GIT/private.md'
        journal.write_text(json.dumps(record))
        with self.assertRaises(uninstall.RecoveryError):
            uninstall.restore(journal)

    def test_second_mutation_failure_returns_recoverable_journal(self):
        before = self.settings.read_bytes()
        hook_before = self.hook.read_bytes()
        original_unlink = Path.unlink
        def fail_hook(path, *args, **kwargs):
            if path == self.hook:
                raise OSError('injected second mutation failure')
            return original_unlink(path, *args, **kwargs)
        with mock.patch.object(Path, 'unlink', fail_hook):
            with self.assertRaisesRegex(uninstall.RecoveryError, 'recovery journal:') as raised:
                self.apply([uninstall.HOOK])
        journal = Path(str(raised.exception).split('recovery journal: ', 1)[1])
        self.assertTrue(journal.is_file())
        self.assertNotEqual(self.settings.read_bytes(), before)
        self.assertEqual(self.hook.read_bytes(), hook_before)
        uninstall.restore(journal)
        self.assertEqual(self.settings.read_bytes(), before)
        self.assertEqual(self.hook.read_bytes(), hook_before)


if __name__ == '__main__':
    unittest.main()
