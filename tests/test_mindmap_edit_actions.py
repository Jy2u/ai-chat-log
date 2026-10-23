import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from db import Database
from ui.view import ViewMixin


class MindmapEditActionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Database(os.path.join(self.temp.name, "chatlog.db"))
        self.map_id = self.database.create_mindmap("原始标题")
        self.root = self.database.get_mindmap_nodes(self.map_id)[0]
        self.harness = SimpleNamespace(
            _db=self.database, reload_sessions=mock.Mock()
        )

    def tearDown(self):
        self.database.close()
        self.temp.cleanup()

    def test_buttons_save_edited_parent_and_create_the_requested_child(self):
        for action, kind, content in (
            ("addbox", "box", "修改后的标题"),
            ("addtext", "text", ""),
        ):
            payload = json.dumps({
                "content": content,
                "positions": [{"id": self.root["id"], "x": 160, "y": 90}],
            })
            ViewMixin._handle_mindmap_action(self.harness, action, self.root["id"], payload)
            root = self.database.get_mindmap_node(self.root["id"])
            self.assertEqual(root["content"], content)
            self.assertEqual((root["pos_x"], root["pos_y"]), (160, 90))
            child = self.database.get_mindmap_nodes(self.map_id)[-1]
            self.assertEqual(child["parent_id"], self.root["id"])
            self.assertEqual(child["kind"], kind)
            self.assertTrue(any(
                edge["from_id"] == self.root["id"] and edge["to_id"] == child["id"]
                for edge in self.database.list_mindmap_edges(self.map_id)
            ))
        self.harness.reload_sessions.assert_called_with(
            select_id=self.map_id, select_kind="mindmap"
        )

    def test_context_menu_creation_preserves_parent_content(self):
        ViewMixin._handle_mindmap_action(
            self.harness, "addbox", self.root["id"], '{"positions": []}'
        )
        self.assertEqual(
            self.database.get_mindmap_node(self.root["id"])["content"],
            self.root["content"],
        )

    def test_invalid_payload_keeps_existing_fallback(self):
        ViewMixin._handle_mindmap_action(self.harness, "addtext", self.root["id"], "{")
        self.assertEqual(len(self.database.get_mindmap_nodes(self.map_id)), 2)


if __name__ == "__main__":
    unittest.main()
