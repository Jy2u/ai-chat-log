import os
import tempfile
import unittest
from datetime import datetime
from unittest import mock

from codex_import import CodexConversationInfo, CodexMessage
from db import Database


def _ms(text):
    return int(datetime.strptime(text, "%Y-%m-%d %H:%M:%S").timestamp() * 1000)


def _info(title, composer_id, created):
    return CodexConversationInfo(
        composer_id=composer_id,
        title=title,
        workspace="/home/test/project",
        created_ms=_ms(created),
        updated_ms=_ms("2026-10-08 14:15:00"),
        mode="codex",
        message_count=1,
        member_name="sessions/x.jsonl",
    )


def _text(external_id, content):
    return CodexMessage(external_id, "user", content, "2026-09-23 09:07:05", "{}", "text")


class SessionCreatedOrderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, "chatlog.db")
        self.images = mock.patch(
            "db.IMAGES_DIR", os.path.join(self.temp.name, "images")
        )
        self.images.start()
        self.database = Database(self.path)
        self.folder_id = self.database.create_folder("两周整理")
        self.subject_id = self.database.list_subjects()[0]["id"]

    def tearDown(self):
        self.database.close()
        self.images.stop()
        self.temp.cleanup()

    def _import_at(self, title, composer_id, created, folder_id=None):
        return self.database.import_external_conversation(
            "codex",
            _info(title, composer_id, created),
            [_text(composer_id, title + "的提问内容")],
            self.folder_id if folder_id is None else folder_id,
        )

    def _names(self, folder_id=None):
        folder_id = self.folder_id if folder_id is None else folder_id
        return [
            item["name"]
            for item in self.database.list_tree_items(self.subject_id, folder_id)
            if item["kind"] == "session"
        ]

    def test_later_import_of_older_chat_slots_in_by_created_time(self):
        self._import_at("分支", "new", "2026-10-08 09:12:00")
        self._import_at("qwen", "mid", "2026-10-07 19:18:00")
        self._import_at("早", "old", "2026-09-27 08:33:00")
        self.assertEqual(self._names(), ["分支", "qwen", "早"])

    def test_new_session_goes_after_older_chats(self):
        self._import_at("早", "old", "2026-09-27 08:33:00")
        self.database.create_session("现在", folder_id=self.folder_id)
        self.assertEqual(self._names(), ["现在", "早"])

    def test_moved_session_keeps_created_time_position(self):
        self._import_at("早", "old", "2026-09-27 08:33:00")
        self._import_at("晚", "new", "2026-10-08 09:12:00")
        other = self.database.create_folder("另一个")
        moved = self._import_at("中", "mid", "2026-10-07 19:18:00", other)
        self.database.move_session(moved.session_id, self.folder_id)
        self.assertEqual(self._names(), ["晚", "中", "早"])

    def test_existing_folder_is_repaired_once_and_manual_order_sticks(self):
        self._import_at("早", "old", "2026-09-27 08:33:00")
        self._import_at("中", "mid", "2026-10-07 19:18:00")
        self._import_at("晚", "new", "2026-10-08 09:12:00")
        items = [
            item for item in self.database.list_tree_items(
                self.subject_id, self.folder_id
            )
            if item["kind"] == "session"
        ]
        for index, item in enumerate(reversed(items)):
            self.database.conn.execute(
                "UPDATE sessions SET sort_order = ? WHERE id = ?",
                (index, item["id"]),
            )
        self.database.conn.execute(
            "DELETE FROM app_meta WHERE key = 'sessions_newest_first'"
        )
        self.database.conn.commit()
        self.database.close()

        self.database = Database(self.path)
        self.assertEqual(self._names(), ["晚", "中", "早"])

        ids = [
            item["id"]
            for item in self.database.list_tree_items(self.subject_id, self.folder_id)
            if item["kind"] == "session"
        ]
        self.database.reorder_tree_items(
            self.subject_id,
            [("session", item_id) for item_id in reversed(ids)],
            folder_id=self.folder_id,
        )
        self.database.close()
        self.database = Database(self.path)
        self.assertEqual(self._names(), ["早", "中", "晚"])

    def test_mindmap_stays_between_session_slots(self):
        early = self._import_at("早", "old", "2026-09-27 08:33:00")
        late = self._import_at("晚", "new", "2026-10-08 09:12:00")
        mindmap_id = self.database.create_mindmap("导图", folder_id=self.folder_id)
        self.database.conn.execute(
            "UPDATE sessions SET sort_order = 0 WHERE id = ?", (early.session_id,)
        )
        self.database.conn.execute(
            "UPDATE mindmaps SET sort_order = 1 WHERE id = ?", (mindmap_id,)
        )
        self.database.conn.execute(
            "UPDATE sessions SET sort_order = 2 WHERE id = ?", (late.session_id,)
        )
        self.database._rewrite_container_session_order(
            self.subject_id, self.folder_id
        )
        self.database.conn.commit()
        kinds = [
            (item["kind"], item["name"])
            for item in self.database.list_tree_items(self.subject_id, self.folder_id)
        ]
        self.assertEqual(
            kinds,
            [("session", "晚"), ("mindmap", "导图"), ("session", "早")],
        )
