import io
import json
import os
import tarfile
import tempfile
import unittest
from unittest import mock

from codex_import import (
    CodexConversationInfo,
    CodexMessage,
    classify_codex_group,
    codex_snapshot_host,
    list_codex_conversations,
    load_codex_conversation,
    with_host_suffix,
)
from db import Database
import render


SESSION_ID = "01900000-0000-7000-8000-000000000010"
MEMBER_NAME = (
    "sessions/2026/09/23/"
    "rollout-2026-09-23T09-07-05-01900000-0000-7000-8000-000000000010.jsonl"
)


def _record(record_type, payload, timestamp="2026-09-23T01:07:05Z"):
    return {"timestamp": timestamp, "type": record_type, "payload": payload}


def _add_text(tf, name, lines):
    data = "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines).encode()
    member = tarfile.TarInfo(name)
    member.size = len(data)
    tf.addfile(member, io.BytesIO(data))


class CodexSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.archive = os.path.join(self.temp.name, "codex-export-latest.tar.gz")
        user_content = [
            {"type": "input_text", "text": "请看这两张截图"},
            {"type": "input_image", "image_url": "data:image/png;base64,YQ=="},
            {"type": "input_image", "image_url": "data:image/jpeg;base64,Yg=="},
        ]
        lines = [
            _record("session_meta", {
                "id": SESSION_ID,
                "timestamp": "2026-09-23T01:07:05Z",
                "cwd": "/home/test/project",
            }),
            _record("response_item", {
                "type": "message", "role": "developer",
                "content": [{"type": "input_text", "text": "internal instruction"}],
            }),
            _record("response_item", {
                "type": "message", "role": "user", "content": user_content,
            }),
            _record("response_item", {
                "type": "message", "role": "assistant", "phase": "commentary",
                "content": [{"type": "output_text", "text": "working"}],
            }),
            _record("response_item", {
                "type": "message", "role": "assistant", "phase": "final_answer",
                "content": [{"type": "output_text", "text": "最终回答"}],
            }, "2026-09-23T01:08:05Z"),
        ]
        with tarfile.open(self.archive, "w:gz") as tf:
            _add_text(tf, "session_index.jsonl", [{
                "id": SESSION_ID,
                "thread_name": "截图导入测试",
                "updated_at": "2026-09-23T01:08:05Z",
            }])
            _add_text(tf, MEMBER_NAME, lines)

    def tearDown(self):
        self.temp.cleanup()

    def test_internal_records_are_grouped_apart_from_titled_chats(self):
        guardian_id = "01900000-0000-7000-8000-000000000001"
        agents_id = "01900000-0000-7000-8000-000000000002"
        titled_id = "01900000-0000-7000-8000-000000000003"
        plain_id = "01900000-0000-7000-8000-000000000004"
        preamble = "# AGENTS.md instructions\n\n<INSTRUCTIONS>\n不要危险操作。\n</INSTRUCTIONS>"

        def lines(sid, source, texts, timestamp):
            payload = {"id": sid, "cwd": "/home/test/project", "timestamp": timestamp}
            if source is not None:
                payload["source"] = source
            records = [_record("session_meta", payload, timestamp)]
            for text in texts:
                records.append(_record("response_item", {
                    "type": "message", "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                }, timestamp))
            return records

        archive = os.path.join(self.temp.name, "grouped.tar.gz")
        with tarfile.open(archive, "w:gz") as tf:
            _add_text(tf, "session_index.jsonl", [
                {"id": guardian_id, "thread_name": "Guardian review"},
                {"id": titled_id, "thread_name": "简洁概要"},
            ])
            _add_text(
                tf,
                f"sessions/2026/10/03/rollout-2026-10-03T01-00-00-{guardian_id}.jsonl",
                lines(guardian_id, {"subagent": {"other": "guardian"}}, [preamble], "2026-10-03T01:00:00Z"),
            )
            _add_text(
                tf,
                f"sessions/2026/10/03/rollout-2026-10-03T02-00-00-{agents_id}.jsonl",
                lines(agents_id, "vscode", [preamble], "2026-10-03T02:00:00Z"),
            )
            _add_text(
                tf,
                f"sessions/2026/10/03/rollout-2026-10-03T03-00-00-{titled_id}.jsonl",
                lines(titled_id, "vscode", [preamble, "真正的问题"], "2026-10-03T03:00:00Z"),
            )
            _add_text(
                tf,
                f"sessions/2026/10/03/rollout-2026-10-03T04-00-00-{plain_id}.jsonl",
                lines(plain_id, None, ["示例会话知识冲突可做之处"], "2026-10-03T04:00:00Z"),
            )

        grouped = {info.composer_id: info for info in list_codex_conversations(archive)}
        self.assertEqual(grouped[guardian_id].group, "guardian")
        self.assertEqual(grouped[guardian_id].title, "Guardian review")
        self.assertEqual(grouped[agents_id].group, "agents")
        self.assertTrue(grouped[agents_id].title.startswith("# AGENTS.md"))
        self.assertEqual(grouped[titled_id].group, "")
        self.assertEqual(grouped[titled_id].title, "简洁概要")
        self.assertEqual(grouped[plain_id].group, "")
        self.assertTrue(grouped[plain_id].title.startswith("示例会话"))
        self.assertEqual(
            classify_codex_group("vscode", "Guardian review", "普通提问"),
            "guardian",
        )
        self.assertEqual(
            classify_codex_group(None, "简洁概要", preamble),
            "",
        )

    def test_list_reads_title_workspace_and_user_turn_count(self):
        conversations = list_codex_conversations(self.archive)
        self.assertEqual(len(conversations), 1)
        info = conversations[0]
        self.assertEqual(info.composer_id, SESSION_ID)
        self.assertEqual(info.title, "截图导入测试")
        self.assertEqual(info.workspace, "/home/test/project")
        self.assertEqual(info.message_count, 1)

    def test_load_splits_text_and_two_images_and_keeps_only_final_answer(self):
        info = list_codex_conversations(self.archive)[0]
        _, messages = load_codex_conversation(self.archive, info)
        self.assertEqual(
            [(message.role, message.kind) for message in messages],
            [("user", "text"), ("user", "image"), ("user", "image"), ("ai", "text")],
        )
        self.assertEqual(messages[0].content, "请看这两张截图")
        self.assertEqual(messages[-1].content, "最终回答")
        self.assertNotIn("working", [message.content for message in messages])
        self.assertNotIn("internal instruction", [message.content for message in messages])

    def test_database_import_copies_embedded_images(self):
        info = list_codex_conversations(self.archive)[0]
        _, messages = load_codex_conversation(self.archive, info)
        image_dir = os.path.join(self.temp.name, "images")
        with mock.patch("db.IMAGES_DIR", image_dir), mock.patch(
            "render.IMAGES_DIR", image_dir
        ):
            database = Database(os.path.join(self.temp.name, "chatlog.db"))
            try:
                folder_id = database.create_folder("导入目标")
                result = database.import_external_conversation(
                    "codex", info, messages, folder_id
                )
                self.assertFalse(result.merged)
                imported = database.get_messages(result.session_id)
            finally:
                database.close()
        self.assertEqual(len(imported), 4)
        image_names = [row["content"] for row in imported if row["kind"] == "image"]
        self.assertEqual(len(image_names), 2)
        self.assertTrue(all(os.path.isfile(os.path.join(image_dir, name)) for name in image_names))
        with mock.patch("render.IMAGES_DIR", image_dir):
            markdown = render.export_markdown(
                {"name": info.title, "created_at": "2026-09-23 09:07:05"},
                imported,
                embed_images=True,
            )
        self.assertEqual(markdown.count("![图片](data:image/"), 2)
        self.assertIn("data:image/png;base64,YQ==", markdown)
        self.assertIn("data:image/jpeg;base64,Yg==", markdown)
        self.assertNotIn("images/", markdown)

    def test_markdown_image_paths_are_safe_and_url_encoded(self):
        body = render.export_markdown(
            {"name": "导出测试", "created_at": "2026-09-23 09:07:05"},
            [{
                "role": "user",
                "kind": "image",
                "content": r"旧目录\截图 1.png",
                "created_at": "2026-09-23 09:08:05",
            }],
            image_rel="会话 images",
        )
        self.assertIn("![图片](%E4%BC%9A%E8%AF%9D%20images/%E6%88%AA%E5%9B%BE%201.png)", body)
        self.assertNotIn("旧目录", body)

    def test_embedded_image_detects_old_mislabeled_jpeg(self):
        image_dir = os.path.join(self.temp.name, "old-images")
        os.makedirs(image_dir)
        with open(os.path.join(image_dir, "old.png"), "wb") as handle:
            handle.write(b"\xff\xd8\xffold-jpeg")
        with mock.patch("render.IMAGES_DIR", image_dir):
            body = render.export_markdown(
                {"name": "旧图片", "created_at": "2026-09-23 09:07:05"},
                [{
                    "role": "user", "kind": "image", "content": "old.png",
                    "created_at": "2026-09-23 09:08:05",
                }],
                embed_images=True,
            )
        self.assertIn("data:image/jpeg;base64,", body)


def _info(title, composer_id):
    return CodexConversationInfo(
        composer_id=composer_id,
        title=title,
        workspace="/home/test/project",
        created_ms=1_758_600_000_000,
        updated_ms=1_758_600_100_000,
        mode="codex",
        message_count=1,
        member_name="sessions/x.jsonl",
    )


def _text(external_id, role, content):
    return CodexMessage(external_id, role, content, "2026-09-23 09:07:05", "{}", "text")


class CodexIncrementalImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.image_dir = os.path.join(self.temp.name, "images")
        self.images = mock.patch("db.IMAGES_DIR", self.image_dir)
        self.images.start()
        self.database = Database(os.path.join(self.temp.name, "chatlog.db"))
        self.folder_id = self.database.create_folder("导入目标")

    def tearDown(self):
        self.database.close()
        self.images.stop()
        self.temp.cleanup()

    def _import(self, source, info, messages, folder_id=None, host=""):
        return self.database.import_external_conversation(
            source, info, messages, self.folder_id if folder_id is None else folder_id,
            host=host,
        )

    def test_renamed_chat_gets_only_new_messages(self):
        first = [
            _text("1", "user", "请帮我看一下这个报错"),
            _text("2", "ai", "这是空指针，先看第 12 行"),
            _text("3", "user", "改成可选之后呢"),
            _text("4", "ai", "可以，记得补测试"),
        ]
        created = self._import("codex", _info("原始标题", "thread-a"), first)
        self.database.rename_session(created.session_id, "我改过的名字")
        continued = first + [
            _text("5", "user", "测试补在哪"),
            _text("6", "ai", "放在 tests 目录"),
        ]
        updated = self._import("codex", _info("服务器上的新标题", "thread-a"), continued)
        self.assertTrue(updated.merged)
        self.assertEqual(updated.added, 2)
        self.assertEqual(updated.session_id, created.session_id)
        self.assertEqual(updated.name, "我改过的名字")
        stored = self.database.get_messages(created.session_id)
        self.assertEqual(
            [row["content"] for row in stored],
            [msg.content for msg in continued],
        )
        self.assertEqual(len(self.database.list_sessions()), 1)

    def test_same_content_does_not_duplicate(self):
        messages = [
            _text("1", "user", "第一条提问，内容比较具体"),
            _text("2", "ai", "第一条回答，也足够具体"),
        ]
        info = _info("短对话", "thread-b")
        first = self._import("codex", info, messages)
        second = self._import("codex", _info("短对话改名", "thread-b"), messages)
        self.assertTrue(second.merged)
        self.assertEqual(second.added, 0)
        self.assertEqual(second.session_id, first.session_id)
        self.assertEqual(len(self.database.get_messages(first.session_id)), 2)

    def test_keeps_local_notes_and_appends_new_tail(self):
        original = [
            _text("1", "user", "先讨论数据库迁移"),
            _text("2", "ai", "先加列，再回填"),
            _text("3", "user", "回填会锁表吗"),
        ]
        created = self._import("codex", _info("迁移", "thread-c"), original)
        self.database.add_message(created.session_id, "user", "我自己后补的备注")
        continued = original + [_text("4", "ai", "分批回填就不会")]
        updated = self._import("codex", _info("迁移-续", "thread-c"), continued)
        self.assertTrue(updated.merged)
        self.assertEqual(updated.added, 1)
        stored = [row["content"] for row in self.database.get_messages(created.session_id)]
        self.assertEqual(stored, [msg.content for msg in original] + ["我自己后补的备注", "分批回填就不会"])

    def test_low_overlap_creates_a_new_session(self):
        self._import("codex", _info("甲", "thread-d"), [
            _text("1", "user", "这是一段完全不同的长提问甲"),
            _text("2", "ai", "这是一段完全不同的长回答甲"),
            _text("3", "user", "继续问甲"),
            _text("4", "ai", "继续答甲"),
        ])
        created = self._import("codex", _info("乙", "thread-e"), [
            _text("1", "user", "这是一段完全不同的长提问甲"),
            _text("9", "ai", "这是另一段对话的回答"),
            _text("10", "user", "另一段的追问"),
            _text("11", "ai", "另一段的收尾"),
        ])
        self.assertFalse(created.merged)
        self.assertEqual(len(self.database.list_sessions()), 2)

    def test_other_folder_does_not_merge(self):
        messages = [
            _text("1", "user", "文件夹隔离用的提问"),
            _text("2", "ai", "文件夹隔离用的回答"),
            _text("3", "user", "再补一条避免太短"),
        ]
        self._import("codex", _info("甲文件夹", "thread-f"), messages)
        other = self.database.create_folder("另一个文件夹")
        created = self._import("codex", _info("乙文件夹", "thread-f"), messages, other)
        self.assertFalse(created.merged)
        self.assertEqual(len(self.database.list_sessions()), 2)

    def test_cursor_import_still_creates_a_copy(self):
        messages = [
            _text("1", "user", "Cursor 这条不走增量"),
            _text("2", "ai", "每次都是新副本"),
            _text("3", "user", "第三条"),
        ]
        self._import("cursor", _info("Cursor 对话", "composer-1"), messages)
        again = self._import("cursor", _info("Cursor 对话", "composer-1"), messages)
        self.assertFalse(again.merged)
        self.assertEqual(len(self.database.list_sessions()), 2)

    def test_repeated_import_does_not_copy_images_again(self):
        archive = os.path.join(self.temp.name, "snap.tar.gz")
        user_content = [
            {"type": "input_text", "text": "请看这两张截图"},
            {"type": "input_image", "image_url": "data:image/png;base64,YQ=="},
            {"type": "input_image", "image_url": "data:image/jpeg;base64,Yg=="},
        ]
        lines = [
            _record("session_meta", {
                "id": SESSION_ID, "cwd": "/home/test/project",
            }),
            _record("response_item", {
                "type": "message", "role": "user", "content": user_content,
            }),
            _record("response_item", {
                "type": "message", "role": "assistant", "phase": "final_answer",
                "content": [{"type": "output_text", "text": "最终回答"}],
            }),
        ]
        with tarfile.open(archive, "w:gz") as tf:
            _add_text(tf, "session_index.jsonl", [{
                "id": SESSION_ID, "thread_name": "截图",
            }])
            _add_text(tf, MEMBER_NAME, lines)
        info = list_codex_conversations(archive)[0]
        _, messages = load_codex_conversation(archive, info)
        first = self._import("codex", info, messages)
        self.database.rename_session(first.session_id, "截图对话")
        extra = messages + [
            _text("tail", "user", "后来又问了一句"),
            _text("tail-ai", "ai", "后来的回答"),
        ]
        second = self._import("codex", info, extra)
        self.assertTrue(second.merged)
        self.assertEqual(second.added, 2)
        self.assertEqual(second.name, "截图对话")
        self.assertEqual(len(os.listdir(self.image_dir)), 2)
        stored = self.database.get_messages(first.session_id)
        self.assertEqual(sum(row["kind"] == "image" for row in stored), 2)

    def test_new_import_appends_host_from_snapshot_name(self):
        messages = [
            _text("1", "user", "示例服务器上的提问"),
            _text("2", "ai", "示例服务器上的回答"),
        ]
        created = self._import(
            "codex", _info("原始标题", "thread-example"), messages, host="192.0.2.10"
        )
        self.assertFalse(created.merged)
        self.assertEqual(created.name, "原始标题-【192.0.2.10】")
        self.assertEqual(
            self.database.get_session(created.session_id)["name"],
            "原始标题-【192.0.2.10】",
        )
        again = self._import(
            "codex", _info("原始标题", "thread-example"), messages, host="192.0.2.10"
        )
        self.assertTrue(again.merged)
        self.assertEqual(again.name, "原始标题-【192.0.2.10】")

    def test_reimport_adds_suffix_when_title_is_still_original(self):
        messages = [
            _text("1", "user", "以前导入过的提问"),
            _text("2", "ai", "以前导入过的回答"),
        ]
        created = self._import("codex", _info("原始标题", "thread-old"), messages)
        self.assertEqual(created.name, "原始标题")
        updated = self._import(
            "codex", _info("原始标题", "thread-old"), messages, host="192.0.2.20"
        )
        self.assertTrue(updated.merged)
        self.assertEqual(updated.added, 0)
        self.assertEqual(updated.name, "原始标题-【192.0.2.20】")
        self.assertEqual(
            self.database.get_session(created.session_id)["name"],
            "原始标题-【192.0.2.20】",
        )

    def test_reimport_keeps_a_renamed_title(self):
        messages = [
            _text("1", "user", "改名后不应被后缀覆盖的提问"),
            _text("2", "ai", "改名后不应被后缀覆盖的回答"),
        ]
        created = self._import(
            "codex", _info("原始标题", "thread-renamed"), messages, host="192.0.2.10"
        )
        self.database.rename_session(created.session_id, "我改过的名字")
        updated = self._import(
            "codex", _info("原始标题", "thread-renamed"), messages, host="192.0.2.10"
        )
        self.assertEqual(updated.name, "我改过的名字")

    def test_cursor_import_ignores_host_suffix(self):
        messages = [
            _text("1", "user", "Cursor 不加机器后缀"),
            _text("2", "ai", "仍然用原标题"),
        ]
        created = self._import(
            "cursor", _info("Cursor 对话", "composer-host"), messages, host="192.0.2.10"
        )
        self.assertEqual(created.name, "Cursor 对话")


class CodexHostSuffixTests(unittest.TestCase):
    @mock.patch("codex_import._LATEST_SNAPSHOT_HOST", "192.0.2.10")
    def test_latest_archive_uses_configured_host(self):
        self.assertEqual(
            codex_snapshot_host(r"E:\CodexExports\codex-export-latest.tar.gz"),
            "192.0.2.10",
        )
        self.assertEqual(
            codex_snapshot_host(r"E:\CodexExports\Codex-Export-Latest.TAR.GZ"),
            "192.0.2.10",
        )

    @mock.patch("codex_import._LATEST_SNAPSHOT_HOST", "")
    def test_latest_archive_has_no_host_by_default(self):
        self.assertEqual(codex_snapshot_host("codex-export-latest.tar.gz"), "")

    def test_ip_in_filename_wins(self):
        self.assertEqual(
            codex_snapshot_host(r"E:\CodexExports\codex-export-192.0.2.20.tar.gz"),
            "192.0.2.20",
        )
        self.assertEqual(
            codex_snapshot_host(r"E:\CodexExports\codex-export-192.0.2.10.tgz"),
            "192.0.2.10",
        )

    def test_unknown_archive_has_no_host(self):
        self.assertEqual(codex_snapshot_host(r"E:\CodexExports\snap.tar.gz"), "")
        self.assertEqual(codex_snapshot_host(r"E:\notes\2026.09.23.1.tar.gz"), "")

    def test_suffix_is_appended_once(self):
        self.assertEqual(
            with_host_suffix("原始标题", "192.0.2.10"),
            "原始标题-【192.0.2.10】",
        )
        self.assertEqual(
            with_host_suffix("原始标题-【192.0.2.10】", "192.0.2.10"),
            "原始标题-【192.0.2.10】",
        )
        self.assertEqual(with_host_suffix("原始标题", ""), "原始标题")


if __name__ == "__main__":
    unittest.main()
