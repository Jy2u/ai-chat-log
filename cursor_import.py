"""Cursor 本地会话读取器：只读 state.vscdb，不依赖 Cursor 插件。"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


TOOL_LABELS = {
    15: "工具调用", 19: "终端", 30: "思考", 33: "计划",
    40: "读取文件", 41: "编辑文件", 42: "创建文件",
    50: "搜索", 60: "浏览器",
}


@dataclass(frozen=True)
class CursorConversationInfo:
    composer_id: str
    title: str
    workspace: str
    created_ms: int | None
    updated_ms: int | None
    mode: str
    message_count: int


@dataclass
class CursorMessage:
    external_id: str
    role: str
    content: str
    created_at: str
    raw_json: str
    kind: str = "text"


def cursor_db_path() -> Path:
    override = os.environ.get("CURSOR_APPDATA")
    if override:
        base = Path(override).expanduser()
        user = base if base.name.lower() == "user" else base / "User"
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise RuntimeError("没有找到 Windows APPDATA 环境变量")
        user = Path(appdata) / "Cursor" / "User"
    elif sys.platform == "darwin":
        user = Path.home() / "Library" / "Application Support" / "Cursor" / "User"
    else:
        user = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "Cursor" / "User"
    return user / "globalStorage" / "state.vscdb"


class _SnapshotDb:
    def __init__(self, source: Path):
        if not source.is_file():
            raise RuntimeError(f"没有找到 Cursor 数据库：{source}")
        # SQLite 的只读连接会读取 Cursor 当前 WAL 的一致快照，不复制数 GB 数据库，
        # 也不会对数据库执行写入。Cursor 正在聊天时，新消息可能要到下次打开列表才出现。
        uri = source.resolve().as_uri() + "?mode=ro"
        self.conn = sqlite3.connect(uri, uri=True, timeout=3)

    def __enter__(self):
        return self.conn

    def __exit__(self, *_):
        self.conn.close()


def _json(value: Any) -> dict[str, Any] | None:
    try:
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except (TypeError, ValueError, UnicodeDecodeError):
        return None


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None


def _workspace(data: dict) -> str:
    ident = data.get("workspaceIdentifier")
    uri = ident.get("uri") if isinstance(ident, dict) else None
    if not isinstance(uri, dict):
        return ""
    value = next((uri.get(k) for k in ("fsPath", "external", "path") if uri.get(k)), "")
    if isinstance(value, str) and value.startswith("file:"):
        parsed = urlparse(value)
        value = unquote(parsed.path)
        if sys.platform == "win32":
            value = value.lstrip("/")
    return str(value or "")


def _headers(data: dict) -> list[dict]:
    raw = data.get("fullConversationHeadersOnly")
    result = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not item.get("bubbleId"):
            continue
        group = item.get("grouping") if isinstance(item.get("grouping"), dict) else {}
        result.append({
            "id": str(item["bubbleId"]),
            "type": item.get("type", 0),
            "renderable": group.get("isRenderable") is not False,
            "has_text": group.get("hasText") is True,
            "simulated": group.get("isSimulatedMsg") is True,
            "capability": group.get("capabilityType") if isinstance(group.get("capabilityType"), int) else None,
            "call_id": str(group.get("toolCallId") or ""),
        })
    return result


def _info(data: dict) -> CursorConversationInfo | None:
    cid = data.get("composerId")
    if not isinstance(cid, str) or not cid:
        return None
    headers = _headers(data)
    # Cursor 的 headers 还包含 thinking、工具调用和内部状态，不能作为用户
    # 看到的消息数。按本软件“一问一答”的展示方式，以真实用户提问计轮数。
    turn_count = sum(
        1 for header in headers
        if header["type"] == 1
        and not header["simulated"]
        and header["renderable"]
    )
    name = data.get("name") if isinstance(data.get("name"), str) else ""
    return CursorConversationInfo(
        cid, name.strip() or f"未命名对话 {cid[:8]}", _workspace(data),
        _int(data.get("createdAt")), _int(data.get("lastUpdatedAt")),
        str(data.get("unifiedMode") or "composer"), turn_count,
    )


def list_cursor_conversations() -> list[CursorConversationInfo]:
    """快速读取会话头，不加载消息正文。"""
    with _SnapshotDb(cursor_db_path()) as conn:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='cursorDiskKV'"
        ).fetchone()
        if not table:
            raise RuntimeError("Cursor 数据库里没有 cursorDiskKV 表")
        rows = conn.execute(
            "SELECT value FROM cursorDiskKV WHERE key LIKE 'composerData:%'"
        ).fetchall()
        infos = [_info(data) for (value,) in rows if (data := _json(value))]
    return sorted(
        (x for x in infos if x),
        key=lambda x: x.updated_ms or x.created_ms or 0,
        reverse=True,
    )


def _lexical_text(value: Any) -> str:
    try:
        root = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return ""
    parts = []
    def walk(node, depth=0):
        if depth > 32 or not isinstance(node, dict):
            return
        if node.get("type") == "text" and isinstance(node.get("text"), str):
            parts.append(node["text"]); return
        if node.get("type") == "linebreak":
            parts.append("\n"); return
        if node.get("root"):
            walk(node["root"], depth + 1)
        if isinstance(node.get("children"), list):
            for child in node["children"]:
                walk(child, depth + 1)
            if node.get("type") in ("paragraph", "heading"):
                parts.append("\n")
    walk(root)
    return "".join(parts).strip()


def _time(ms: int | None) -> str:
    if not ms:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def load_cursor_conversation(composer_id: str) -> tuple[CursorConversationInfo, list[CursorMessage]]:
    """加载一个会话，并把 Cursor 结构转成现有软件可显示的消息。"""
    with _SnapshotDb(cursor_db_path()) as conn:
        row = conn.execute(
            "SELECT value FROM cursorDiskKV WHERE key = ?",
            (f"composerData:{composer_id}",),
        ).fetchone()
        data = _json(row[0]) if row else None
        info = _info(data) if data else None
        if not info or not data:
            raise RuntimeError("所选 Cursor 对话已经不存在")
        headers = _headers(data)
        ids = [h["id"] for h in headers]
        bubbles = {}
        for offset in range(0, len(ids), 300):
            chunk = ids[offset:offset + 300]
            marks = ",".join("?" for _ in chunk)
            keys = [f"bubbleId:{composer_id}:{bid}" for bid in chunk]
            for value, in conn.execute(
                f"SELECT value FROM cursorDiskKV WHERE key IN ({marks})", keys
            ):
                bubble = _json(value)
                if bubble and bubble.get("bubbleId"):
                    bubbles[str(bubble["bubbleId"])] = bubble

    messages = []
    for header in headers:
        bubble = bubbles.get(header["id"])
        if not bubble:
            continue
        if not header["renderable"]:
            continue
        text = bubble.get("text") if isinstance(bubble.get("text"), str) else ""
        if not text.strip():
            text = _lexical_text(bubble.get("richText"))
        capability = header["capability"]
        if capability is None and isinstance(bubble.get("capabilityType"), int):
            capability = bubble["capabilityType"]
        sections = []
        # 只保留普通对话气泡；thinking、计划及所有工具卡全部忽略。
        if capability is not None:
            continue
        # 一些 Cursor 版本把思考片段序列化进 text，例如
        # {"text":"...","isLastThinkingChunk":true}，它不是最终回答。
        try:
            embedded = json.loads(text) if text.lstrip().startswith("{") else None
        except (TypeError, ValueError):
            embedded = None
        if isinstance(embedded, dict) and "isLastThinkingChunk" in embedded:
            continue
        type_num = bubble.get("type", header["type"])
        role = "user" if type_num == 1 and not header["simulated"] else "ai"
        if text.strip():
            sections.append(text.strip())
        has_image = False
        if role == "user":
            selected_images = bubble.get("selectedImages")
            if isinstance(selected_images, list):
                for image_index, image in enumerate(selected_images):
                    if not isinstance(image, dict):
                        continue
                    image_path = image.get("path")
                    if isinstance(image_path, str) and image_path:
                        has_image = True
                        messages.append(CursorMessage(
                            f"{header['id']}:image:{image_index}",
                            "user", image_path, _time(_int(bubble.get("createdAt"))),
                            json.dumps(image, ensure_ascii=False, separators=(",", ":")),
                            "image",
                        ))
        if sections:
            messages.append(CursorMessage(
                f"{header['id']}:text", role, "\n\n".join(sections),
                _time(_int(bubble.get("createdAt"))),
                json.dumps(bubble, ensure_ascii=False, separators=(",", ":")),
            ))
        elif not has_image:
            continue
    # 每轮只保留用户原文和下一条用户消息前最后一个 AI 输出。Cursor 的
    # 中间过程可能没有稳定字段标记，用轮次边界收敛比枚举内部类型可靠。
    final_messages = []
    pending_users = []
    pending_ai = None
    for message in messages:
        if message.role == "user":
            if pending_ai is not None and pending_users:
                final_messages.extend(pending_users)
                final_messages.append(pending_ai)
                pending_users = []
                pending_ai = None
            pending_users.append(message)
        else:
            pending_ai = message
    if pending_users and pending_ai is not None:
        final_messages.extend(pending_users)
        final_messages.append(pending_ai)
    return info, final_messages
