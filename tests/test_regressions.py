import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unittest
from unittest import mock

import render
import ui.ops as ops


class ChatRefreshTests(unittest.TestCase):
    def setUp(self):
        self.session = {
            "id": 1,
            "name": "长会话",
            "created_at": "2026-09-23 10:00:00",
        }
        self.messages = [
            {
                "id": 7,
                "session_id": 1,
                "role": "user",
                "content": "新增问题",
                "kind": "text",
                "created_at": "2026-09-23 10:01:00",
            }
        ]

    def test_full_chat_is_hidden_until_bottom_is_positioned(self):
        page = render.build_chat_page(self.session, self.messages)
        self.assertIn('<html class="preposition-bottom">', page)
        self.assertIn("html.preposition-bottom body { visibility: hidden; }", page)
        self.assertIn("positionAndReveal", page)

    def test_empty_chat_installs_dynamic_navigation_hook(self):
        page = render.build_chat_page(self.session, [])
        self.assertIn("window.__refreshChatNav", page)

    def test_message_patch_updates_dom_without_navigation(self):
        script = render.chat_patch_js(
            self.session,
            self.messages,
            upsert_id=7,
            focus_id=7,
        )
        self.assertIn('document.getElementById("msg-" + upsertId)', script)
        self.assertIn("window.__refreshChatNav", script)
        self.assertIn("return true", script)
        self.assertNotIn("location.reload", script)

    def test_generated_patch_is_valid_javascript(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed")
        script = render.chat_patch_js(
            self.session,
            self.messages,
            upsert_id=7,
            focus_id=7,
        )
        checked = subprocess.run(
            [node, "--check", "-"],
            input=script,
            text=True,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)


class _Status:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = text


class _FailingDb:
    def backup_to(self, _path):
        raise sqlite3.OperationalError("database or disk is full")


class _WritingDb:
    def backup_to(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(b"backup")


class _BackupHarness(ops.OpsMixin):
    def __init__(self, db):
        self._db = db
        self._status = _Status()
        self._last_auto_backup_error = ""
        self.hint_refreshes = 0

    def _refresh_auto_backup_hint(self):
        self.hint_refreshes += 1


def _fake_copytree(_src, dest, ignore=None):
    os.makedirs(os.path.join(dest, "data"), exist_ok=False)
    return dest


class BackupRecoveryTests(unittest.TestCase):
    def test_unexpected_auto_backup_error_still_schedules_retry(self):
        class Harness:
            _status = _Status()
            _last_auto_backup_error = ""
            scheduled = None

            def _run_backup(self, *_args, **_kwargs):
                raise RuntimeError("unexpected failure")

            def _schedule_auto_backup(self, delay_ms=None):
                self.scheduled = delay_ms

        harness = Harness()
        ops.OpsMixin._auto_backup(harness)
        self.assertEqual(harness.scheduled, ops._AUTO_BACKUP_RETRY_MS)
        self.assertIn("unexpected failure", harness._last_auto_backup_error)

    def test_sqlite_failure_returns_false_and_removes_partial(self):
        with tempfile.TemporaryDirectory() as td:
            harness = _BackupHarness(_FailingDb())
            with mock.patch.object(ops, "_BACKUP_ROOT", td), mock.patch.object(
                ops.shutil, "copytree", side_effect=_fake_copytree
            ):
                self.assertFalse(harness._run_backup("自动备份", silent=True))
            self.assertIn("database or disk is full", harness._last_auto_backup_error)
            self.assertEqual(os.listdir(td), [])

    def test_success_is_published_atomically_with_current_timestamp(self):
        with tempfile.TemporaryDirectory() as td:
            harness = _BackupHarness(_WritingDb())
            before = time.time() - 2
            with mock.patch.object(ops, "_BACKUP_ROOT", td), mock.patch.object(
                ops.shutil, "copytree", side_effect=_fake_copytree
            ):
                self.assertTrue(harness._run_backup("测试", silent=True))
            folders = os.listdir(td)
            self.assertEqual(len(folders), 1)
            self.assertNotIn(".partial", folders[0])
            dest = os.path.join(td, folders[0])
            self.assertTrue(os.path.isfile(os.path.join(dest, "data", "chatlog.db")))
            self.assertGreaterEqual(os.path.getmtime(dest), before)
            self.assertEqual(harness._last_auto_backup_error, "")


class _MemorySettings:
    def __init__(self):
        self.values = {}

    def value(self, key, default=None, **_kwargs):
        return self.values.get(key, default)

    def setValue(self, key, value):
        self.values[key] = value


class _FolderExportDb:
    def list_folders(self):
        return [{"id": 1, "name": "项目导出"}]

    def list_sessions(self):
        return [{
            "id": 7,
            "name": "图片会话",
            "folder_id": 1,
            "created_at": "2026-09-24 00:00:00",
        }]

    def get_messages(self, _session_id):
        return [{
            "role": "user",
            "kind": "image",
            "content": "shot.png",
            "created_at": "2026-09-24 00:01:00",
        }]

    def list_mindmaps(self):
        return []

    def list_documents(self):
        return []


class _FolderExportHarness(ops.OpsMixin):
    def __init__(self):
        self._db = _FolderExportDb()
        self._settings = _MemorySettings()
        self._status = _Status()


class FolderExportTests(unittest.TestCase):
    def test_export_creates_plain_folder_with_embedded_image(self):
        with tempfile.TemporaryDirectory() as td:
            image_dir = os.path.join(td, "source-images")
            os.makedirs(image_dir)
            with open(os.path.join(image_dir, "shot.png"), "wb") as handle:
                handle.write(b"\x89PNG\r\n\x1a\nimage")
            harness = _FolderExportHarness()
            with mock.patch.object(
                ops.QFileDialog, "getExistingDirectory", return_value=td
            ), mock.patch.object(render, "IMAGES_DIR", image_dir):
                harness.export_folder(1)

            exported = os.path.join(td, "项目导出")
            markdown_path = os.path.join(exported, "对话", "图片会话.md")
            self.assertTrue(os.path.isdir(exported))
            self.assertTrue(os.path.isfile(markdown_path))
            self.assertFalse(os.path.exists(os.path.join(td, "项目导出.zip")))
            self.assertFalse(os.path.exists(exported + ".partial"))
            with open(markdown_path, encoding="utf-8") as handle:
                markdown = handle.read()
            self.assertIn("data:image/png;base64,", markdown)
            self.assertIn("已导出文件夹到", harness._status.text)


class _Result:
    def __init__(self, name, merged=False, added=0):
        self.name = name
        self.merged = merged
        self.added = added


class ImportSummaryTests(unittest.TestCase):
    def test_single_outcomes_keep_the_short_status(self):
        self.assertEqual(
            ops.summarize_imports("Codex", [_Result("截图")], turns=4),
            "已从 Codex 导入：截图（4 轮）",
        )
        self.assertEqual(
            ops.summarize_imports("Codex", [_Result("改过的名字", merged=True, added=2)]),
            "已把 2 条新消息补进「改过的名字」",
        )
        self.assertEqual(
            ops.summarize_imports("Codex", [_Result("改过的名字", merged=True)]),
            "「改过的名字」里已经有这些内容，没有新消息",
        )

    def test_batch_status_counts_each_outcome(self):
        text = ops.summarize_imports("Cursor", [
            _Result("甲"),
            _Result("乙"),
            _Result("丙", merged=True, added=3),
            _Result("丁", merged=True),
        ], failure_count=1)
        self.assertEqual(
            text,
            "已处理 4 个 Cursor 对话：新建 2 个，1 个补进 3 条，1 个没有新消息，1 个失败",
        )


class _Conv:
    def __init__(self, title):
        self.title = title
        self.workspace = "ws"
        self.updated_ms = 1_700_000_000_000
        self.created_ms = 1_700_000_000_000
        self.message_count = 2


class ImportSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def test_extended_selection_returns_rows_from_top_to_bottom(self):
        from PySide6.QtCore import QItemSelectionModel, Qt
        from PySide6.QtWidgets import QAbstractItemView

        from ui.cursor_import_dialog import CursorImportDialog

        dialog = CursorImportDialog([_Conv("甲"), _Conv("乙"), _Conv("丙")])
        dialog.setAttribute(Qt.WA_DontShowOnScreen, True)
        dialog.show()
        try:
            self.assertEqual(
                dialog._table.selectionMode(),
                QAbstractItemView.ExtendedSelection,
            )
            self.assertEqual(dialog._ok.text(), "导入")
            selection = dialog._table.selectionModel()
            selection.clearSelection()
            flags = (
                QItemSelectionModel.SelectionFlag.Select
                | QItemSelectionModel.SelectionFlag.Rows
            )
            for row in (2, 0):
                selection.select(dialog._table.model().index(row, 0), flags)
            self.assertEqual(
                [item.title for item in dialog.selected_conversations()],
                ["甲", "丙"],
            )
            self.assertEqual(dialog._ok.text(), "导入 2 个")
            dialog._toggle_select_all()
            self.assertEqual(
                [item.title for item in dialog.selected_conversations()],
                ["甲", "乙", "丙"],
            )
            self.assertEqual(dialog._select_all.text(), "取消全选")
            self.assertEqual(dialog._ok.text(), "导入 3 个")
            self.assertFalse(dialog._grouped)
        finally:
            dialog.close()

    def test_codex_internal_records_show_in_two_folders(self):
        from PySide6.QtCore import Qt

        from ui.cursor_import_dialog import CursorImportDialog

        class _Grouped:
            def __init__(self, title, group):
                self.title = title
                self.workspace = "/work"
                self.updated_ms = 1_700_000_000_000
                self.created_ms = 1_700_000_000_000
                self.message_count = 4
                self.group = group

        dialog = CursorImportDialog([
            _Grouped("示例会话", ""),
            _Grouped("Guardian review", "guardian"),
            _Grouped("另一条审查", "guardian"),
            _Grouped("# AGENTS.md instructions…", "agents"),
        ], source_name="codex")
        dialog.setAttribute(Qt.WA_DontShowOnScreen, True)
        dialog.show()
        try:
            self.assertTrue(dialog._grouped)
            self.assertFalse(dialog._table.isVisible())
            self.assertTrue(dialog._tree.isVisible())
            self.assertEqual(dialog._tree.topLevelItemCount(), 3)
            self.assertTrue(dialog._tree.topLevelItem(0).text(0).startswith("Guardian review（2）"))
            self.assertTrue(dialog._tree.topLevelItem(1).text(0).startswith("AGENTS.md（1）"))
            self.assertEqual(dialog._tree.topLevelItem(2).text(0), "示例会话")
            dialog._source_context = r"E:\CodexExports\codex-export-192.0.2.20.tar.gz"
            dialog._populate()
            self.assertEqual(
                dialog._tree.topLevelItem(2).text(0),
                "示例会话-【192.0.2.20】",
            )
            self.assertEqual(
                [item.title for item in dialog.selected_conversations()],
                ["示例会话"],
            )
            self.assertEqual(dialog._tree.topLevelItem(0).childCount(), 2)
            self.assertEqual(dialog._tree.topLevelItem(1).childCount(), 1)
            self.assertFalse(dialog._tree.topLevelItem(0).isExpanded())
            self.assertFalse(dialog._tree.topLevelItem(1).isExpanded())
            self.assertIn("两个文件夹", dialog._hint.text())
            self.assertEqual(
                [item.title for item in dialog.selected_conversations()],
                ["示例会话"],
            )

            dialog._tree.clearSelection()
            dialog._tree.topLevelItem(0).setSelected(True)
            self.assertEqual(
                [item.title for item in dialog.selected_conversations()],
                ["Guardian review", "另一条审查"],
            )
            dialog._toggle_select_all()
            self.assertEqual(
                [item.title for item in dialog.selected_conversations()],
                ["Guardian review", "另一条审查", "# AGENTS.md instructions…", "示例会话"],
            )
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
