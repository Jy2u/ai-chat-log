"""Read-only importer for Codex snapshot archives created on a remote machine.

The archive is read in place.  Nothing is extracted and the source files are never
modified.  The JSONL shape is intentionally handled defensively because it is an
internal Codex persistence format rather than a public interchange specification.
"""

from __future__ import annotations

import json
import os
import re
import tarfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


_SESSION_MEMBER = re.compile(
    r"^(?:sessions/\d{4}/\d{2}/\d{2}/|archived_sessions/)rollout-.*\.jsonl$"
)
_UUID_AT_END = re.compile(
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$",
    re.IGNORECASE,
)
# 无地址的快照可通过本机环境变量指定来源；公开代码不包含个人服务器地址。
_LATEST_SNAPSHOT_HOST = os.environ.get("AICHAT_CODEX_LATEST_HOST", "").strip()
_IPV4_IN_NAME = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")


# 导入列表里单独成夹的两类内部记录，不和用户自己的对话混在一起。
GROUP_GUARDIAN = "guardian"
GROUP_AGENTS = "agents"
GROUP_LABELS = {
    GROUP_GUARDIAN: "Guardian review",
    GROUP_AGENTS: "AGENTS.md",
}


@dataclass(frozen=True)
class CodexConversationInfo:
    # Keep the common name used by the existing external-session database layer.
    composer_id: str
    title: str
    workspace: str
    created_ms: int | None
    updated_ms: int | None
    mode: str
    message_count: int
    member_name: str
    group: str = ""


@dataclass
class CodexMessage:
    external_id: str
    role: str
    content: str
    created_at: str
    raw_json: str
    kind: str = "text"


def _json_lines(stream) -> Iterator[tuple[int, dict[str, Any]]]:
    for line_number, raw in enumerate(stream, 1):
        try:
            obj = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            continue
        if isinstance(obj, dict):
            yield line_number, obj


def _timestamp_ms(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        number = float(value)
        return int(number if abs(number) >= 100_000_000_000 else number * 1000)
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        return _timestamp_ms(float(value))
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int(parsed.timestamp() * 1000)


def _display_time(value: Any, fallback_ms: int | None = None) -> str:
    milliseconds = _timestamp_ms(value) or fallback_ms
    if not milliseconds:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return datetime.fromtimestamp(milliseconds / 1000).strftime("%Y-%m-%d %H:%M:%S")


def _message_payload(obj: dict[str, Any]) -> dict[str, Any] | None:
    if obj.get("type") != "response_item":
        return None
    payload = obj.get("payload")
    if not isinstance(payload, dict) or payload.get("type") != "message":
        return None
    return payload


def _content_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    content = payload.get("content")
    if not isinstance(content, list):
        return []
    return [item for item in content if isinstance(item, dict)]


def _is_guardian_source(source: Any) -> bool:
    """Codex 把审查子会话标成 source.subagent.other = guardian。"""
    if not isinstance(source, dict):
        return False
    subagent = source.get("subagent")
    if isinstance(subagent, dict):
        return subagent.get("other") == "guardian" or subagent.get("name") == "guardian"
    return subagent == "guardian"


def _is_agents_preamble(text: str) -> bool:
    """Codex 注入的项目说明，开头固定是 # AGENTS.md instructions。"""
    return (text or "").lstrip().startswith("# AGENTS.md")


def classify_codex_group(source: Any, indexed_title: str, first_user_text: str) -> str:
    """没有真实标题的内部记录分成两类，其余留给普通对话列表。"""
    if _is_guardian_source(source) or (indexed_title or "").strip() == "Guardian review":
        return GROUP_GUARDIAN
    if not (indexed_title or "").strip() and _is_agents_preamble(first_user_text):
        return GROUP_AGENTS
    return ""


def _valid_ipv4(text: str) -> bool:
    parts = text.split(".")
    if len(parts) != 4:
        return False
    return all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)


def codex_snapshot_host(path: str | os.PathLike[str]) -> str:
    """从快照文件名认出来源机器。认不出时返回空字符串。"""
    name = Path(path).name
    lower = name.lower()
    if lower.endswith(".tar.gz"):
        stem = name[:-7]
    elif lower.endswith(".tgz"):
        stem = name[:-4]
    else:
        stem = name
    found = ""
    for match in _IPV4_IN_NAME.finditer(stem):
        ip = match.group(0)
        if _valid_ipv4(ip):
            found = ip
    if found:
        return found
    if stem.lower() == "codex-export-latest":
        return _LATEST_SNAPSHOT_HOST
    return ""


def with_host_suffix(title: str, host: str) -> str:
    """在标题末尾加上 -【ip】。已经有同一个后缀时不重复添加。"""
    host = (host or "").strip()
    title = title or ""
    if not host:
        return title
    suffix = f"-【{host}】"
    if title.endswith(suffix):
        return title
    return f"{title}{suffix}"


def _fallback_id(member_name: str) -> str:
    match = _UUID_AT_END.search(member_name)
    return match.group(1) if match else Path(member_name).stem


def _archive(path: str | os.PathLike[str]) -> tarfile.TarFile:
    archive_path = Path(path).expanduser().resolve()
    if not archive_path.is_file():
        raise RuntimeError(f"没有找到 Codex 快照：{archive_path}")
    try:
        return tarfile.open(archive_path, "r:gz")
    except (tarfile.TarError, OSError) as exc:
        raise RuntimeError("所选文件不是可读取的 Codex tar.gz 快照。") from exc


def _thread_index(tf: tarfile.TarFile) -> dict[str, tuple[str, int | None]]:
    member = next(
        (item for item in tf.getmembers() if item.isfile() and item.name.endswith("session_index.jsonl")),
        None,
    )
    if member is None:
        return {}
    stream = tf.extractfile(member)
    if stream is None:
        return {}
    result: dict[str, tuple[str, int | None]] = {}
    for _, obj in _json_lines(stream):
        session_id = obj.get("id")
        if not isinstance(session_id, str) or not session_id:
            continue
        title = obj.get("thread_name")
        result[session_id] = (
            title.strip() if isinstance(title, str) else "",
            _timestamp_ms(obj.get("updated_at")),
        )
    return result


def _scan_info(
    tf: tarfile.TarFile,
    member: tarfile.TarInfo,
    titles: dict[str, tuple[str, int | None]],
) -> CodexConversationInfo | None:
    stream = tf.extractfile(member)
    if stream is None:
        return None
    session_id = ""
    workspace = ""
    created_ms = None
    updated_ms = None
    first_user_text = ""
    user_turns = 0
    source = None
    for _, obj in _json_lines(stream):
        record_ms = _timestamp_ms(obj.get("timestamp"))
        if record_ms:
            updated_ms = max(updated_ms or record_ms, record_ms)
        payload = obj.get("payload")
        if obj.get("type") == "session_meta" and isinstance(payload, dict):
            for key in ("id", "session_id"):
                candidate = payload.get(key)
                if isinstance(candidate, str) and candidate:
                    session_id = candidate
                    break
            candidate_workspace = payload.get("cwd")
            if isinstance(candidate_workspace, str):
                workspace = candidate_workspace
            if "source" in payload:
                source = payload.get("source")
            created_ms = _timestamp_ms(payload.get("timestamp")) or record_ms or created_ms
            continue
        message = _message_payload(obj)
        if not message or message.get("role") != "user":
            continue
        items = _content_items(message)
        visible = [item for item in items if item.get("type") in ("input_text", "input_image")]
        if not visible:
            continue
        user_turns += 1
        if not first_user_text:
            for item in visible:
                text = item.get("text") if item.get("type") == "input_text" else None
                if isinstance(text, str) and text.strip():
                    first_user_text = " ".join(text.strip().split())
                    break

    session_id = session_id or _fallback_id(member.name)
    indexed_title, indexed_updated = titles.get(session_id, ("", None))
    updated_ms = max(x for x in (updated_ms, indexed_updated, created_ms) if x is not None) \
        if any(x is not None for x in (updated_ms, indexed_updated, created_ms)) else None
    title = indexed_title or first_user_text or f"未命名对话 {session_id[:8]}"
    return CodexConversationInfo(
        composer_id=session_id,
        title=title,
        workspace=workspace,
        created_ms=created_ms,
        updated_ms=updated_ms,
        mode="codex",
        message_count=user_turns,
        member_name=member.name,
        group=classify_codex_group(source, indexed_title, first_user_text),
    )


def list_codex_conversations(snapshot_path: str | os.PathLike[str]) -> list[CodexConversationInfo]:
    """List Codex sessions without extracting the snapshot archive."""
    with _archive(snapshot_path) as tf:
        titles = _thread_index(tf)
        members = [
            item for item in tf.getmembers()
            if item.isfile() and _SESSION_MEMBER.match(item.name)
        ]
        infos = [_scan_info(tf, member, titles) for member in members]
    return sorted(
        (info for info in infos if info is not None and info.message_count > 0),
        key=lambda info: info.updated_ms or info.created_ms or 0,
        reverse=True,
    )


def _raw_item(item: dict[str, Any], *, image: bool = False) -> str:
    if image:
        url = item.get("image_url")
        safe = {
            "type": item.get("type"),
            "source": "embedded-data-url" if isinstance(url, str) and url.startswith("data:") else "reference",
            "encoded_length": len(url) if isinstance(url, str) else 0,
        }
        return json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(item, ensure_ascii=False, separators=(",", ":"))


def load_codex_conversation(
    snapshot_path: str | os.PathLike[str], info: CodexConversationInfo
) -> tuple[CodexConversationInfo, list[CodexMessage]]:
    """Load user inputs (one record per text/image) and final assistant answers."""
    messages: list[CodexMessage] = []
    with _archive(snapshot_path) as tf:
        try:
            member = tf.getmember(info.member_name)
        except KeyError as exc:
            raise RuntimeError("快照中已找不到所选 Codex 会话。") from exc
        stream = tf.extractfile(member)
        if stream is None:
            raise RuntimeError("无法读取所选 Codex 会话。")
        for line_number, obj in _json_lines(stream):
            payload = _message_payload(obj)
            if payload is None:
                continue
            role = payload.get("role")
            created_at = _display_time(obj.get("timestamp"), info.updated_ms)
            record_id = payload.get("id")
            prefix = str(record_id) if record_id else str(line_number)
            items = _content_items(payload)
            if role == "user":
                for item_index, item in enumerate(items):
                    kind = item.get("type")
                    if kind == "input_text":
                        text = item.get("text")
                        if isinstance(text, str) and text.strip():
                            messages.append(CodexMessage(
                                f"{prefix}:{item_index}:text", "user", text.strip(),
                                created_at, _raw_item(item), "text",
                            ))
                    elif kind == "input_image":
                        image_url = item.get("image_url")
                        if isinstance(image_url, str) and image_url.startswith("data:image/"):
                            messages.append(CodexMessage(
                                f"{prefix}:{item_index}:image", "user", image_url,
                                created_at, _raw_item(item, image=True), "image",
                            ))
            elif role == "assistant" and payload.get("phase") == "final_answer":
                parts = [
                    item.get("text").strip()
                    for item in items
                    if item.get("type") == "output_text"
                    and isinstance(item.get("text"), str)
                    and item.get("text").strip()
                ]
                if parts:
                    messages.append(CodexMessage(
                        f"{prefix}:final", "ai", "\n\n".join(parts), created_at,
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        "text",
                    ))
    return info, messages
