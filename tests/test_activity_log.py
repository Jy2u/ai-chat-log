import os
import tempfile
import unittest
from unittest import mock

from db import Database


class ActivityLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.images = mock.patch(
            "db.IMAGES_DIR", os.path.join(self.temp.name, "images")
        )
        self.images.start()
        self.database = Database(os.path.join(self.temp.name, "chatlog.db"))

    def tearDown(self):
        self.database.close()
        self.images.stop()
        self.temp.cleanup()

    def test_records_message_and_lists_newest_first(self):
        session_id = self.database.create_session("实验会话")
        self.database.add_message(session_id, "user", "先问一个足够长的问题")
        self.database.add_todo("2026-09-28-交日志")
        rows = self.database.list_activity()
        self.assertEqual(rows[0]["action"], "添加待办")
        self.assertIn("交日志", rows[0]["detail"])
        recorded = [row for row in rows if row["action"] == "记录对话"]
        self.assertEqual(len(recorded), 1)
        self.assertIn("实验会话", recorded[0]["detail"])
        self.assertIn("先问一个足够长的问题", recorded[0]["detail"])

    def test_key_text_is_not_written_into_the_log(self):
        secret = "super-secret-token-9182"
        self.database.add_stash(secret, "key")
        self.database.add_stash("帮我润色这段话", "prompt")
        blob = "\n".join(
            row["action"] + row["detail"] for row in self.database.list_activity()
        )
        self.assertNotIn(secret, blob)
        self.assertIn("密钥", blob)
        self.assertIn("帮我润色这段话", blob)

    def test_repeated_document_edits_stay_one_row(self):
        document_id = self.database.create_document("笔记")
        self.database.update_document_content(document_id, "第一稿")
        self.database.update_document_content(document_id, "第二稿")
        edits = [
            row for row in self.database.list_activity()
            if row["action"] == "编辑文档"
        ]
        self.assertEqual(len(edits), 1)
        self.assertIn("笔记", edits[0]["detail"])
