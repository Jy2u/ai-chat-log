"""SQLite 存储层：会话与消息。"""

import os
import json
import base64
import binascii
import hashlib
import re
import shutil
import sqlite3
import uuid
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "chatlog.db")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

ROLE_USER = "user"
ROLE_AI = "ai"

# 续导入：按顺序对上的消息至少这么多，并且至少盖住已有对话的一半，
# 才认为是同一段聊天（标题可以已经被改掉）。整段都被新记录包含时，
# 两条也够，避免很短的对话只能删了重导。
_OVERLAP_MIN_MATCHED = 2
_OVERLAP_MIN_COVERAGE = 0.5
_OVERLAP_STRONG_MATCHED = 3


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clip(text: str, limit: int = 42) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


_STASH_KIND_NAMES = {
    "key": "密钥",
    "account": "账号密码",
    "prompt": "提示词",
}
_ACTIVITY_COALESCE_SEC = 120


from codex_import import with_host_suffix
from db_mindmaps import MindmapMixin
from db_documents import DocumentMixin
from db_trash import TrashMixin


class ExternalImportResult:
    """一次外部导入的结果。merged 为真时写进了已有会话，没有新建。"""

    def __init__(self, session_id: int, added: int, merged: bool, name: str):
        self.session_id = session_id
        self.added = added
        self.merged = merged
        self.name = name


def _external_metadata(info) -> str:
    metadata = {
        "composerId": info.composer_id,
        "workspace": info.workspace,
        "createdAt": info.created_ms,
        "updatedAt": info.updated_ms,
        "mode": info.mode,
        "turnCount": info.message_count,
    }
    return json.dumps(metadata, ensure_ascii=False)


def _ordered_new_indexes(existing: list, incoming: list) -> tuple[int, list]:
    """按顺序把 incoming 对到 existing 上。返回对上的条数，以及 incoming 里对不上的下标。"""
    cursor = 0
    matched = 0
    new_indexes = []
    for index, key in enumerate(incoming):
        found = None
        for pos in range(cursor, len(existing)):
            if existing[pos] == key:
                found = pos
                break
        if found is None:
            new_indexes.append(index)
        else:
            matched += 1
            cursor = found + 1
    return matched, new_indexes


def _same_chat(matched: int, existing_count: int) -> bool:
    if existing_count <= 0 or matched < _OVERLAP_MIN_MATCHED:
        return False
    if matched / existing_count < _OVERLAP_MIN_COVERAGE:
        return False
    return matched >= _OVERLAP_STRONG_MATCHED or matched == existing_count


class Database(MindmapMixin, DocumentMixin, TrashMixin):
    def __init__(self, path: str = DB_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT '',
                auto_named INTEGER NOT NULL DEFAULT 1,
                folder_id INTEGER REFERENCES folders(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL
                    REFERENCES sessions(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK (role IN ('user', 'ai')),
                content TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'text',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id);
            CREATE TABLE IF NOT EXISTS external_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                session_id INTEGER NOT NULL
                    REFERENCES sessions(id) ON DELETE CASCADE,
                workspace TEXT NOT NULL DEFAULT '',
                raw_metadata TEXT NOT NULL DEFAULT '',
                imported_at TEXT NOT NULL,
                UNIQUE(source, external_id)
            );
            CREATE TABLE IF NOT EXISTS external_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                external_session_id TEXT NOT NULL,
                external_message_id TEXT NOT NULL,
                message_id INTEGER NOT NULL
                    REFERENCES messages(id) ON DELETE CASCADE,
                raw_json TEXT NOT NULL DEFAULT '',
                UNIQUE(source, external_session_id, external_message_id)
            );
            CREATE TABLE IF NOT EXISTS mindmaps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT '',
                folder_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
                session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS mindmap_nodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mindmap_id INTEGER NOT NULL
                    REFERENCES mindmaps(id) ON DELETE CASCADE,
                parent_id INTEGER REFERENCES mindmap_nodes(id),
                kind TEXT NOT NULL CHECK (kind IN ('box', 'text')),
                content TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                pos_x REAL,
                pos_y REAL,
                edge_label TEXT NOT NULL DEFAULT '',
                highlighted INTEGER NOT NULL DEFAULT 0,
                box_w REAL,
                box_h REAL,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_mindmap_nodes_map
                ON mindmap_nodes(mindmap_id);
            CREATE TABLE IF NOT EXISTS mindmap_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mindmap_id INTEGER NOT NULL
                    REFERENCES mindmaps(id) ON DELETE CASCADE,
                from_id INTEGER NOT NULL
                    REFERENCES mindmap_nodes(id) ON DELETE CASCADE,
                to_id INTEGER NOT NULL
                    REFERENCES mindmap_nodes(id) ON DELETE CASCADE,
                label TEXT NOT NULL DEFAULT ''
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_mindmap_edges_pair
                ON mindmap_edges(from_id, to_id);
            """
        )
        # 老库迁移：补上后加的列
        cols = [
            r["name"]
            for r in self.conn.execute("PRAGMA table_info(sessions)")
        ]
        if "auto_named" not in cols:
            self.conn.execute(
                "ALTER TABLE sessions ADD COLUMN"
                " auto_named INTEGER NOT NULL DEFAULT 1"
            )
        if "folder_id" not in cols:
            self.conn.execute(
                "ALTER TABLE sessions ADD COLUMN folder_id INTEGER"
                " REFERENCES folders(id) ON DELETE CASCADE"
            )
        msg_cols = [
            r["name"]
            for r in self.conn.execute("PRAGMA table_info(messages)")
        ]
        if "kind" not in msg_cols:
            self.conn.execute(
                "ALTER TABLE messages ADD COLUMN"
                " kind TEXT NOT NULL DEFAULT 'text'"
            )
        map_cols = [
            r["name"]
            for r in self.conn.execute("PRAGMA table_info(mindmap_nodes)")
        ]
        if "pos_x" not in map_cols:
            self.conn.execute("ALTER TABLE mindmap_nodes ADD COLUMN pos_x REAL")
            self.conn.execute("ALTER TABLE mindmap_nodes ADD COLUMN pos_y REAL")
        if "edge_label" not in map_cols:
            self.conn.execute(
                "ALTER TABLE mindmap_nodes ADD COLUMN"
                " edge_label TEXT NOT NULL DEFAULT ''"
            )
        if "highlighted" not in map_cols:
            self.conn.execute(
                "ALTER TABLE mindmap_nodes ADD COLUMN"
                " highlighted INTEGER NOT NULL DEFAULT 0"
            )
        if "box_w" not in map_cols:
            self.conn.execute("ALTER TABLE mindmap_nodes ADD COLUMN box_w REAL")
            self.conn.execute("ALTER TABLE mindmap_nodes ADD COLUMN box_h REAL")
        if "created_at" not in map_cols:
            self.conn.execute(
                "ALTER TABLE mindmap_nodes ADD COLUMN"
                " created_at TEXT NOT NULL DEFAULT ''"
            )
            self.conn.execute(
                "ALTER TABLE mindmap_nodes ADD COLUMN"
                " updated_at TEXT NOT NULL DEFAULT ''"
            )
            now = _now()
            self.conn.execute(
                """
                UPDATE mindmap_nodes
                SET created_at = COALESCE(
                    NULLIF((
                        SELECT created_at FROM mindmaps
                        WHERE mindmaps.id = mindmap_nodes.mindmap_id
                    ), ''),
                    ?
                ),
                updated_at = COALESCE(
                    NULLIF((
                        SELECT created_at FROM mindmaps
                        WHERE mindmaps.id = mindmap_nodes.mindmap_id
                    ), ''),
                    ?
                )
                WHERE created_at = '' OR updated_at = ''
                """,
                (now, now),
            )
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS mindmap_edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mindmap_id INTEGER NOT NULL
                    REFERENCES mindmaps(id) ON DELETE CASCADE,
                from_id INTEGER NOT NULL
                    REFERENCES mindmap_nodes(id) ON DELETE CASCADE,
                to_id INTEGER NOT NULL
                    REFERENCES mindmap_nodes(id) ON DELETE CASCADE,
                label TEXT NOT NULL DEFAULT ''
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_mindmap_edges_pair
                ON mindmap_edges(from_id, to_id);
            """
        )
        n_edges = self.conn.execute(
            "SELECT COUNT(*) AS c FROM mindmap_edges"
        ).fetchone()["c"]
        if n_edges == 0:
            self.conn.execute(
                """
                INSERT INTO mindmap_edges (mindmap_id, from_id, to_id, label)
                SELECT mindmap_id, parent_id, id, COALESCE(edge_label, '')
                FROM mindmap_nodes
                WHERE parent_id IS NOT NULL
                """
            )
        self._migrate_subjects()
        self._migrate_sort_order()
        self._ensure_documents_table()
        self._migrate_deleted_at()
        self._migrate_match_color()
        self._migrate_updated_at()
        self._migrate_session_note()
        self._migrate_session_tags()
        self._ensure_todos_table()
        self._ensure_stash_table()
        self._ensure_activity_log()
        self._cleanup_cursor_import_noise()
        self._ensure_sessions_time_order()
        self.conn.commit()

    def _cleanup_cursor_import_noise(self):
        """旧导入数据也收敛为：用户原文 + 每轮最后一条 AI 输出。"""
        labels = (
            "工具调用", "终端", "思考", "计划", "读取文件", "编辑文件",
            "创建文件", "搜索", "浏览器",
        )
        rows = self.conn.execute(
            "SELECT m.id, m.content FROM messages m"
            " JOIN external_messages e ON e.message_id = m.id"
            " WHERE e.source = 'cursor'"
        ).fetchall()
        pure_label = re.compile(
            r"^\*\*(?:" + "|".join(map(re.escape, labels))
            + r")\*\*(?:\s+(?:`[^`]+`|(?:call-|tool_|fc_)[^\n]*))?\s*$",
            re.IGNORECASE,
        )
        ids = [r["id"] for r in rows if pure_label.match((r["content"] or "").strip())]
        if ids:
            marks = ",".join("?" for _ in ids)
            self.conn.execute(f"DELETE FROM messages WHERE id IN ({marks})", ids)
        sessions = self.conn.execute(
            "SELECT session_id FROM external_sessions WHERE source = 'cursor'"
        ).fetchall()
        for session in sessions:
            messages = self.conn.execute(
                "SELECT m.id, m.role FROM messages m"
                " JOIN external_messages e ON e.message_id = m.id"
                " WHERE m.session_id = ? AND e.source = 'cursor' ORDER BY m.id",
                (session["session_id"],),
            ).fetchall()
            remove = []
            pending_ai = None
            for message in messages:
                if message["role"] == "user":
                    if pending_ai is not None:
                        pending_ai = None
                    continue
                if pending_ai is not None:
                    remove.append(pending_ai)
                pending_ai = message["id"]
            if remove:
                marks = ",".join("?" for _ in remove)
                self.conn.execute(
                    f"DELETE FROM messages WHERE id IN ({marks})", remove
                )

    def _table_cols(self, table: str) -> list:
        return [
            r["name"]
            for r in self.conn.execute(f"PRAGMA table_info({table})")
        ]

    def _migrate_session_note(self):
        if "note" not in self._table_cols("sessions"):
            self.conn.execute(
                "ALTER TABLE sessions ADD COLUMN note TEXT NOT NULL DEFAULT ''"
            )

    def _migrate_session_tags(self):
        cols = self._table_cols("sessions")
        if "source" not in cols:
            self.conn.execute(
                "ALTER TABLE sessions ADD COLUMN"
                " source TEXT NOT NULL DEFAULT ''"
            )
        if "done" not in cols:
            self.conn.execute(
                "ALTER TABLE sessions ADD COLUMN"
                " done INTEGER NOT NULL DEFAULT 0"
            )

    def _migrate_match_color(self):
        """会话可按文件夹内分组高亮。"""
        if "match_color" not in self._table_cols("sessions"):
            self.conn.execute(
                "ALTER TABLE sessions ADD COLUMN match_color TEXT"
            )

    def _migrate_updated_at(self):
        """会话 / 导图补最后编辑时间。"""
        if "updated_at" not in self._table_cols("sessions"):
            self.conn.execute(
                "ALTER TABLE sessions ADD COLUMN"
                " updated_at TEXT NOT NULL DEFAULT ''"
            )
            self.conn.execute(
                """
                UPDATE sessions SET updated_at = COALESCE(
                    (
                        SELECT MAX(created_at) FROM messages
                        WHERE messages.session_id = sessions.id
                    ),
                    created_at
                )
                WHERE updated_at = ''
                """
            )
        if "updated_at" not in self._table_cols("mindmaps"):
            self.conn.execute(
                "ALTER TABLE mindmaps ADD COLUMN"
                " updated_at TEXT NOT NULL DEFAULT ''"
            )
            self.conn.execute(
                """
                UPDATE mindmaps SET updated_at = COALESCE(
                    NULLIF((
                        SELECT MAX(updated_at) FROM mindmap_nodes
                        WHERE mindmap_nodes.mindmap_id = mindmaps.id
                    ), ''),
                    created_at
                )
                WHERE updated_at = ''
                """
            )

    def _stamp_session(self, session_id: int):
        if not session_id:
            return
        self.conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (_now(), session_id),
        )

    def _ensure_activity_log(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                action TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                coalesce_key TEXT NOT NULL DEFAULT ''
            )
            """
        )

    def _activity(self, action: str, detail: str = "", coalesce_key: str = ""):
        """写入一条操作日志。不单独提交，跟当前修改一起生效。"""
        if getattr(self, "_mute_activity", 0):
            return
        action = (action or "").strip() or "操作"
        detail = _clip(detail, 180)
        now = _now()
        key = (coalesce_key or "").strip()
        if key:
            row = self.conn.execute(
                "SELECT id, created_at FROM activity_log"
                " WHERE coalesce_key = ? ORDER BY id DESC LIMIT 1",
                (key,),
            ).fetchone()
            if row:
                try:
                    prev = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
                    recent = (datetime.now() - prev).total_seconds() <= _ACTIVITY_COALESCE_SEC
                except ValueError:
                    recent = False
                if recent:
                    self.conn.execute(
                        "UPDATE activity_log SET created_at = ?, action = ?, detail = ?"
                        " WHERE id = ?",
                        (now, action, detail, row["id"]),
                    )
                    return
        self.conn.execute(
            "INSERT INTO activity_log (created_at, action, detail, coalesce_key)"
            " VALUES (?, ?, ?, ?)",
            (now, action, detail, key),
        )

    def record_activity(self, action: str, detail: str = ""):
        """记下一次不走数据库修改的操作，例如导出、备份、搜索。"""
        self._activity(action, detail)
        self.conn.commit()

    def list_activity(self, limit: int = 500) -> list:
        rows = self.conn.execute(
            "SELECT id, created_at, action, detail FROM activity_log"
            " ORDER BY created_at DESC, id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
        return [dict(row) for row in rows]

    def _session_name(self, session_id) -> str:
        row = self.get_session(session_id) if session_id else None
        return row["name"] if row else "会话"

    def _named(self, getter, item_id, fallback: str) -> str:
        row = getter(item_id) if item_id else None
        return row["name"] if row else fallback

    def _ensure_todos_table(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                mark TEXT NOT NULL DEFAULT '',
                done INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        if "note" not in self._table_cols("todos"):
            self.conn.execute(
                "ALTER TABLE todos ADD COLUMN note TEXT NOT NULL DEFAULT ''"
            )
        if "mark" not in self._table_cols("todos"):
            self.conn.execute(
                "ALTER TABLE todos ADD COLUMN mark TEXT NOT NULL DEFAULT ''"
            )

    def _ensure_stash_table(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stash (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'key',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        if "kind" not in self._table_cols("stash"):
            self.conn.execute(
                "ALTER TABLE stash ADD COLUMN kind TEXT NOT NULL DEFAULT 'key'"
            )

    def _migrate_subjects(self):
        """补课题表，并把已有文件夹/会话/导图归到默认课题。"""
        folder_cols = self._table_cols("folders")
        if "subject_id" not in folder_cols:
            self.conn.execute(
                "ALTER TABLE folders ADD COLUMN subject_id INTEGER"
                " REFERENCES subjects(id) ON DELETE CASCADE"
            )
        sess_cols = self._table_cols("sessions")
        if "subject_id" not in sess_cols:
            self.conn.execute(
                "ALTER TABLE sessions ADD COLUMN subject_id INTEGER"
                " REFERENCES subjects(id) ON DELETE CASCADE"
            )
        map_cols = self._table_cols("mindmaps")
        if "subject_id" not in map_cols:
            self.conn.execute(
                "ALTER TABLE mindmaps ADD COLUMN subject_id INTEGER"
                " REFERENCES subjects(id) ON DELETE CASCADE"
            )
        n = self.conn.execute(
            "SELECT COUNT(*) AS c FROM subjects"
        ).fetchone()["c"]
        if n == 0:
            cur = self.conn.execute(
                "INSERT INTO subjects (name, created_at) VALUES (?, ?)",
                ("未分组", _now()),
            )
            default_id = cur.lastrowid
        else:
            default_id = self.conn.execute(
                "SELECT id FROM subjects ORDER BY id LIMIT 1"
            ).fetchone()["id"]
        self.conn.execute(
            "UPDATE folders SET subject_id = ? WHERE subject_id IS NULL",
            (default_id,),
        )
        self.conn.execute(
            """
            UPDATE sessions SET subject_id = (
                SELECT f.subject_id FROM folders f WHERE f.id = sessions.folder_id
            )
            WHERE folder_id IS NOT NULL AND subject_id IS NULL
            """
        )
        self.conn.execute(
            "UPDATE sessions SET subject_id = ? WHERE subject_id IS NULL",
            (default_id,),
        )
        self.conn.execute(
            """
            UPDATE mindmaps SET subject_id = (
                SELECT s.subject_id FROM sessions s
                WHERE s.id = mindmaps.session_id
            )
            WHERE session_id IS NOT NULL AND subject_id IS NULL
            """
        )
        self.conn.execute(
            """
            UPDATE mindmaps SET subject_id = (
                SELECT f.subject_id FROM folders f
                WHERE f.id = mindmaps.folder_id
            )
            WHERE folder_id IS NOT NULL AND subject_id IS NULL
            """
        )
        self.conn.execute(
            "UPDATE mindmaps SET subject_id = ? WHERE subject_id IS NULL",
            (default_id,),
        )

    def _migrate_sort_order(self):
        """课题、文件夹可拖动排序。已有记录按原来的新建在前初始化。"""
        added_subjects = False
        if "sort_order" not in self._table_cols("subjects"):
            self.conn.execute(
                "ALTER TABLE subjects ADD COLUMN"
                " sort_order INTEGER NOT NULL DEFAULT 0"
            )
            added_subjects = True
        added_folders = False
        if "sort_order" not in self._table_cols("folders"):
            self.conn.execute(
                "ALTER TABLE folders ADD COLUMN"
                " sort_order INTEGER NOT NULL DEFAULT 0"
            )
            added_folders = True
        if added_subjects:
            rows = self.conn.execute(
                "SELECT id FROM subjects ORDER BY id DESC"
            ).fetchall()
            for i, row in enumerate(rows):
                self.conn.execute(
                    "UPDATE subjects SET sort_order = ? WHERE id = ?",
                    (i, row["id"]),
                )
        if added_folders:
            groups = {}
            rows = self.conn.execute(
                "SELECT id, subject_id FROM folders ORDER BY id DESC"
            ).fetchall()
            for row in rows:
                groups.setdefault(row["subject_id"], []).append(row["id"])
            for ids in groups.values():
                for i, fid in enumerate(ids):
                    self.conn.execute(
                        "UPDATE folders SET sort_order = ? WHERE id = ?",
                        (i, fid),
                    )
        added_sessions = "sort_order" not in self._table_cols("sessions")
        if added_sessions:
            self.conn.execute(
                "ALTER TABLE sessions ADD COLUMN"
                " sort_order INTEGER NOT NULL DEFAULT 0"
            )
        added_maps = "sort_order" not in self._table_cols("mindmaps")
        if added_maps:
            self.conn.execute(
                "ALTER TABLE mindmaps ADD COLUMN"
                " sort_order INTEGER NOT NULL DEFAULT 0"
            )
        if added_sessions or added_maps:
            self._init_mixed_tree_sort()

    def _ensure_sessions_time_order(self):
        """已有会话按创建时间从新到旧排一次，新的在上。之后手动拖动的顺序会保留。"""
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        done = self.conn.execute(
            "SELECT value FROM app_meta WHERE key = 'sessions_newest_first'"
        ).fetchone()
        if done:
            return
        subjects = self.conn.execute(
            "SELECT id FROM subjects WHERE deleted_at IS NULL"
        ).fetchall()
        for subject in subjects:
            self._order_subject_sessions(subject["id"])
        self.conn.execute(
            "INSERT INTO app_meta (key, value) VALUES ('sessions_newest_first', '1')"
        )

    def _order_subject_sessions(self, subject_id):
        folders = self.conn.execute(
            "SELECT id FROM folders WHERE subject_id = ? AND deleted_at IS NULL",
            (subject_id,),
        ).fetchall()
        for folder in folders:
            self._rewrite_container_session_order(subject_id, folder["id"])
        self._rewrite_container_session_order(subject_id, None)

    def _container_members(self, subject_id, folder_id):
        """同一层正在显示的条目，顺序与侧栏一致。"""
        items = []
        if folder_id is None:
            rows = self.conn.execute(
                """
                SELECT id, created_at, sort_order FROM folders
                WHERE subject_id = ? AND deleted_at IS NULL
                """,
                (subject_id,),
            ).fetchall()
            items.extend(dict(row, kind="folder") for row in rows)
        for kind, table, extra in (
            ("session", "sessions", ""),
            ("mindmap", "mindmaps", " AND session_id IS NULL"),
            ("document", "documents", " AND session_id IS NULL"),
        ):
            rows = self.conn.execute(
                f"""
                SELECT id, created_at, sort_order FROM {table}
                WHERE subject_id = ? AND folder_id IS ?
                  AND deleted_at IS NULL{extra}
                """,
                (subject_id, folder_id),
            ).fetchall()
            items.extend(dict(row, kind=kind) for row in rows)
        items.sort(
            key=lambda item: (
                item["sort_order"] if item["sort_order"] is not None else 0,
                -item["id"],
            )
        )
        return items

    def _rewrite_container_session_order(self, subject_id, folder_id):
        """会话按创建时间从新到旧占用原来的会话位置，导图和文档位置不动。"""
        items = self._container_members(subject_id, folder_id)
        if not items:
            return
        sessions = sorted(
            (item for item in items if item["kind"] == "session"),
            key=lambda item: (item["created_at"] or "", item["id"]),
            reverse=True,
        )
        upcoming = iter(sessions)
        ordered = [
            next(upcoming) if item["kind"] == "session" else item
            for item in items
        ]
        for index, item in enumerate(ordered):
            self._set_sort_order(item["kind"], item["id"], index)

    def _set_sort_order(self, kind, item_id, order):
        table = {
            "folder": "folders",
            "session": "sessions",
            "mindmap": "mindmaps",
            "document": "documents",
        }.get(kind)
        if table is None:
            return
        self.conn.execute(
            f"UPDATE {table} SET sort_order = ? WHERE id = ?",
            (order, item_id),
        )

    def _place_session_by_created(
        self, subject_id, folder_id, created_at, exclude_id=None
    ) -> int:
        """在同层腾出空位，让更新的会话排在更旧的会话上面。"""
        if subject_id is None:
            return 0
        sql = """
            SELECT id, created_at, sort_order FROM sessions
            WHERE subject_id = ? AND folder_id IS ? AND deleted_at IS NULL
        """
        params = [subject_id, folder_id]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        sql += " ORDER BY created_at DESC, id DESC"
        anchor = None
        for row in self.conn.execute(sql, params).fetchall():
            if (row["created_at"] or "") < (created_at or ""):
                anchor = row
                break
        if anchor is None:
            members = self._container_members(subject_id, folder_id)
            if exclude_id is not None:
                members = [
                    item for item in members
                    if not (item["kind"] == "session" and item["id"] == exclude_id)
                ]
            if not members:
                return 0
            return max(item["sort_order"] or 0 for item in members) + 1
        order = int(anchor["sort_order"] or 0)
        self._shift_container_sort(subject_id, folder_id, order, exclude_id)
        return order

    def _shift_container_sort(self, subject_id, folder_id, from_order, exclude_id=None):
        if folder_id is None:
            self.conn.execute(
                """
                UPDATE folders SET sort_order = sort_order + 1
                WHERE subject_id = ? AND deleted_at IS NULL AND sort_order >= ?
                """,
                (subject_id, from_order),
            )
        session_sql = """
            UPDATE sessions SET sort_order = sort_order + 1
            WHERE subject_id = ? AND folder_id IS ? AND deleted_at IS NULL
              AND sort_order >= ?
        """
        session_params = [subject_id, folder_id, from_order]
        if exclude_id is not None:
            session_sql += " AND id != ?"
            session_params.append(exclude_id)
        self.conn.execute(session_sql, session_params)
        for table in ("mindmaps", "documents"):
            self.conn.execute(
                f"""
                UPDATE {table} SET sort_order = sort_order + 1
                WHERE subject_id = ? AND folder_id IS ? AND session_id IS NULL
                  AND deleted_at IS NULL AND sort_order >= ?
                """,
                (subject_id, folder_id, from_order),
            )

    def _front_sort(self, table: str, where: str = "", params=()):
        sql = f"SELECT COALESCE(MIN(sort_order), 0) AS m FROM {table}"
        if where:
            sql += " WHERE " + where
        return int(self.conn.execute(sql, params).fetchone()["m"]) - 1

    def _init_mixed_tree_sort(self):
        """按当前界面顺序初始化：文件夹 → 根目录会话 → 根目录导图。"""
        subjects = [
            r["id"]
            for r in self.conn.execute("SELECT id FROM subjects").fetchall()
        ]
        for sid in subjects:
            order = 0
            folders = self.conn.execute(
                "SELECT id FROM folders WHERE subject_id = ?"
                " ORDER BY sort_order ASC, id DESC",
                (sid,),
            ).fetchall()
            for f in folders:
                self.conn.execute(
                    "UPDATE folders SET sort_order = ? WHERE id = ?",
                    (order, f["id"]),
                )
                order += 1
                child = 0
                sessions = self.conn.execute(
                    "SELECT id FROM sessions WHERE folder_id = ?"
                    " ORDER BY id DESC",
                    (f["id"],),
                ).fetchall()
                for s in sessions:
                    self.conn.execute(
                        "UPDATE sessions SET sort_order = ? WHERE id = ?",
                        (child, s["id"]),
                    )
                    child += 1
                    morder = 0
                    for m in self.conn.execute(
                        "SELECT id FROM mindmaps WHERE session_id = ?"
                        " ORDER BY id DESC",
                        (s["id"],),
                    ).fetchall():
                        self.conn.execute(
                            "UPDATE mindmaps SET sort_order = ? WHERE id = ?",
                            (morder, m["id"]),
                        )
                        morder += 1
                for m in self.conn.execute(
                    "SELECT id FROM mindmaps"
                    " WHERE folder_id = ? AND session_id IS NULL"
                    " ORDER BY id DESC",
                    (f["id"],),
                ).fetchall():
                    self.conn.execute(
                        "UPDATE mindmaps SET sort_order = ? WHERE id = ?",
                        (child, m["id"]),
                    )
                    child += 1
            for s in self.conn.execute(
                "SELECT id FROM sessions"
                " WHERE subject_id = ? AND folder_id IS NULL"
                " ORDER BY id DESC",
                (sid,),
            ).fetchall():
                self.conn.execute(
                    "UPDATE sessions SET sort_order = ? WHERE id = ?",
                    (order, s["id"]),
                )
                order += 1
                morder = 0
                for m in self.conn.execute(
                    "SELECT id FROM mindmaps WHERE session_id = ?"
                    " ORDER BY id DESC",
                    (s["id"],),
                ).fetchall():
                    self.conn.execute(
                        "UPDATE mindmaps SET sort_order = ? WHERE id = ?",
                        (morder, m["id"]),
                    )
                    morder += 1
            for m in self.conn.execute(
                "SELECT id FROM mindmaps"
                " WHERE subject_id = ? AND folder_id IS NULL"
                " AND session_id IS NULL ORDER BY id DESC",
                (sid,),
            ).fetchall():
                self.conn.execute(
                    "UPDATE mindmaps SET sort_order = ? WHERE id = ?",
                    (order, m["id"]),
                )
                order += 1

    def _mixed_front_sort(self, subject_id, folder_id=None, session_id=None):
        mins = []
        if session_id is not None:
            queries = [
                (
                    "SELECT COALESCE(MIN(sort_order), 0) AS m"
                    " FROM mindmaps WHERE session_id = ?"
                    " AND deleted_at IS NULL",
                    (session_id,),
                ),
                (
                    "SELECT COALESCE(MIN(sort_order), 0) AS m"
                    " FROM documents WHERE session_id = ?"
                    " AND deleted_at IS NULL",
                    (session_id,),
                ),
            ]
            mins = [
                int(self.conn.execute(sql, params).fetchone()["m"])
                for sql, params in queries
            ]
            return (min(mins) if mins else 0) - 1
        if folder_id is not None:
            queries = [
                (
                    "SELECT COALESCE(MIN(sort_order), 0) AS m"
                    " FROM sessions WHERE folder_id = ?"
                    " AND deleted_at IS NULL",
                    (folder_id,),
                ),
                (
                    "SELECT COALESCE(MIN(sort_order), 0) AS m"
                    " FROM mindmaps WHERE folder_id = ? AND session_id IS NULL"
                    " AND deleted_at IS NULL",
                    (folder_id,),
                ),
                (
                    "SELECT COALESCE(MIN(sort_order), 0) AS m"
                    " FROM documents WHERE folder_id = ? AND session_id IS NULL"
                    " AND deleted_at IS NULL",
                    (folder_id,),
                ),
            ]
        else:
            queries = [
                (
                    "SELECT COALESCE(MIN(sort_order), 0) AS m"
                    " FROM folders WHERE subject_id = ?"
                    " AND deleted_at IS NULL",
                    (subject_id,),
                ),
                (
                    "SELECT COALESCE(MIN(sort_order), 0) AS m"
                    " FROM sessions WHERE subject_id = ? AND folder_id IS NULL"
                    " AND deleted_at IS NULL",
                    (subject_id,),
                ),
                (
                    "SELECT COALESCE(MIN(sort_order), 0) AS m FROM mindmaps"
                    " WHERE subject_id = ? AND folder_id IS NULL"
                    " AND session_id IS NULL AND deleted_at IS NULL",
                    (subject_id,),
                ),
                (
                    "SELECT COALESCE(MIN(sort_order), 0) AS m FROM documents"
                    " WHERE subject_id = ? AND folder_id IS NULL"
                    " AND session_id IS NULL AND deleted_at IS NULL",
                    (subject_id,),
                ),
            ]
        for sql, params in queries:
            mins.append(int(self.conn.execute(sql, params).fetchone()["m"]))
        return (min(mins) if mins else 0) - 1

    def list_tree_items(self, subject_id, folder_id=None, session_id=None):
        """同一层的文件夹 / 会话 / 导图 / 文档，按 sort_order 排列。"""
        items = []
        if session_id is not None:
            for m in self.list_mindmaps(subject_id):
                if m["session_id"] == session_id:
                    items.append(dict(m, kind="mindmap"))
            for d in self.list_documents(subject_id):
                if d["session_id"] == session_id:
                    items.append(dict(d, kind="document"))
        elif folder_id is not None:
            for s in self.list_sessions(subject_id):
                if s["folder_id"] == folder_id:
                    items.append(dict(s, kind="session"))
            for m in self.list_mindmaps(subject_id):
                if m["folder_id"] == folder_id and m["session_id"] is None:
                    items.append(dict(m, kind="mindmap"))
            for d in self.list_documents(subject_id):
                if d["folder_id"] == folder_id and d["session_id"] is None:
                    items.append(dict(d, kind="document"))
        else:
            for f in self.list_folders(subject_id):
                items.append(dict(f, kind="folder"))
            for s in self.list_sessions(subject_id):
                if s["folder_id"] is None:
                    items.append(dict(s, kind="session"))
            for m in self.list_mindmaps(subject_id):
                if m["folder_id"] is None and m["session_id"] is None:
                    items.append(dict(m, kind="mindmap"))
            for d in self.list_documents(subject_id):
                if d["folder_id"] is None and d["session_id"] is None:
                    items.append(dict(d, kind="document"))
        items.sort(
            key=lambda x: (
                x["sort_order"] if x.get("sort_order") is not None else 0,
                -x["id"],
            )
        )
        return items

    def reorder_tree_items(
        self, subject_id, keys, folder_id=None, session_id=None
    ):
        """keys 为 [(kind, id), ...]，写入同一层的 sort_order。"""
        for i, (kind, iid) in enumerate(keys):
            if kind == "folder":
                self.conn.execute(
                    "UPDATE folders SET sort_order = ? WHERE id = ? AND subject_id = ?",
                    (i, iid, subject_id),
                )
            elif kind == "session":
                self.conn.execute(
                    "UPDATE sessions SET sort_order = ? WHERE id = ?",
                    (i, iid),
                )
            elif kind == "mindmap":
                self.conn.execute(
                    "UPDATE mindmaps SET sort_order = ? WHERE id = ?",
                    (i, iid),
                )
            elif kind == "document":
                self.conn.execute(
                    "UPDATE documents SET sort_order = ? WHERE id = ?",
                    (i, iid),
                )
        self._activity("调整排序", "侧栏条目", coalesce_key="reorder-tree")
        self.conn.commit()

    def reorder_subjects(self, ids: list):
        for i, sid in enumerate(ids):
            self.conn.execute(
                "UPDATE subjects SET sort_order = ? WHERE id = ?", (i, sid)
            )
        self._activity("调整排序", "课题", coalesce_key="reorder-subjects")
        self.conn.commit()

    def reorder_folders(self, subject_id, ids: list):
        for i, fid in enumerate(ids):
            self.conn.execute(
                "UPDATE folders SET sort_order = ? WHERE id = ? AND subject_id = ?",
                (i, fid, subject_id),
            )
        self.conn.commit()

    def ensure_default_subject(self) -> int:
        row = self.conn.execute(
            "SELECT id FROM subjects WHERE deleted_at IS NULL"
            " ORDER BY id LIMIT 1"
        ).fetchone()
        if row:
            return row["id"]
        return self.create_subject("未分组")

    def _resolve_subject_id(self, folder_id=None, session_id=None, subject_id=None):
        if session_id is not None:
            sess = self.get_session(session_id)
            if sess and sess.get("subject_id") is not None:
                return sess["subject_id"]
        if folder_id is not None:
            folder = self.get_folder(folder_id)
            if folder and folder.get("subject_id") is not None:
                return folder["subject_id"]
        if subject_id is not None:
            return subject_id
        return self.ensure_default_subject()

    # ---------- 课题 ----------

    def create_subject(self, name: str) -> int:
        order = self._front_sort("subjects", "deleted_at IS NULL")
        cur = self.conn.execute(
            "INSERT INTO subjects (name, created_at, sort_order)"
            " VALUES (?, ?, ?)",
            (name, _now(), order),
        )
        self._activity("新建课题", f"「{name}」")
        self.conn.commit()
        return cur.lastrowid

    def list_subjects(self) -> list:
        """返回 [{id, name, created_at, count}]，count 为课题下文件夹数。"""
        rows = self.conn.execute(
            """
            SELECT sub.id, sub.name, sub.created_at,
                   COUNT(DISTINCT f.id) AS count
            FROM subjects sub
            LEFT JOIN folders f ON f.subject_id = sub.id
                AND f.deleted_at IS NULL
            WHERE sub.deleted_at IS NULL
            GROUP BY sub.id
            ORDER BY sub.sort_order ASC, sub.id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def get_subject(self, subject_id: int):
        row = self.conn.execute(
            "SELECT id, name, created_at, deleted_at FROM subjects WHERE id = ?",
            (subject_id,),
        ).fetchone()
        return dict(row) if row else None

    def rename_subject(self, subject_id: int, name: str):
        old = self._named(self.get_subject, subject_id, "课题")
        self.conn.execute(
            "UPDATE subjects SET name = ? WHERE id = ?", (name, subject_id)
        )
        self._activity("重命名课题", f"「{old}」改为「{name}」")
        self.conn.commit()

    def subject_stats(self, subject_id: int):
        """返回 (文件夹数, 会话数, 消息数)。"""
        row = self.conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM folders
                 WHERE subject_id = ? AND deleted_at IS NULL) AS nf,
                (SELECT COUNT(*) FROM sessions
                 WHERE subject_id = ? AND deleted_at IS NULL) AS ns,
                (
                    SELECT COUNT(*) FROM messages m
                    JOIN sessions s ON s.id = m.session_id
                    WHERE s.subject_id = ? AND s.deleted_at IS NULL
                ) AS nm
            """,
            (subject_id, subject_id, subject_id),
        ).fetchone()
        return row["nf"], row["ns"], row["nm"]

    def subject_image_files(self, subject_id: int, include_deleted=False) -> list:
        sql = """
            SELECT m.content FROM messages m
            JOIN sessions s ON s.id = m.session_id
            WHERE s.subject_id = ? AND m.kind = 'image'
        """
        if not include_deleted:
            sql += " AND s.deleted_at IS NULL"
        rows = self.conn.execute(sql, (subject_id,)).fetchall()
        return [r["content"] for r in rows]

    def delete_subject(self, subject_id: int) -> bool:
        """彻底删除课题及其下文件夹、会话、导图、文档。"""
        name = self._named(self.get_subject, subject_id, "课题")
        self.conn.execute(
            "DELETE FROM sessions WHERE subject_id = ?", (subject_id,)
        )
        self.conn.execute(
            "DELETE FROM documents WHERE subject_id = ?", (subject_id,)
        )
        self.conn.execute(
            "DELETE FROM mindmaps WHERE subject_id = ?", (subject_id,)
        )
        self.conn.execute(
            "DELETE FROM folders WHERE subject_id = ?", (subject_id,)
        )
        self.conn.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
        self._activity("彻底删除", f"课题「{name}」")
        self.conn.commit()
        return True

    def move_folder(self, folder_id: int, subject_id: int):
        """把周期文件夹连同夹内会话、导图一起换到另一个课题。"""
        self.conn.execute(
            "UPDATE folders SET subject_id = ? WHERE id = ?",
            (subject_id, folder_id),
        )
        self.conn.execute(
            "UPDATE sessions SET subject_id = ? WHERE folder_id = ?",
            (subject_id, folder_id),
        )
        self.conn.execute(
            "UPDATE mindmaps SET subject_id = ? WHERE folder_id = ?",
            (subject_id, folder_id),
        )
        self.conn.execute(
            """
            UPDATE mindmaps SET subject_id = ?
            WHERE session_id IN (
                SELECT id FROM sessions WHERE folder_id = ?
            )
            """,
            (subject_id, folder_id),
        )
        self.conn.execute(
            "UPDATE documents SET subject_id = ? WHERE folder_id = ?",
            (subject_id, folder_id),
        )
        self.conn.execute(
            """
            UPDATE documents SET subject_id = ?
            WHERE session_id IN (
                SELECT id FROM sessions WHERE folder_id = ?
            )
            """,
            (subject_id, folder_id),
        )
        self._activity(
            "移动文件夹",
            f"「{self._named(self.get_folder, folder_id, '文件夹')}」",
        )
        self.conn.commit()

    # ---------- 文件夹 ----------

    def create_folder(self, name: str, subject_id=None) -> int:
        subject_id = self._resolve_subject_id(subject_id=subject_id)
        order = self._mixed_front_sort(subject_id)
        cur = self.conn.execute(
            "INSERT INTO folders (name, created_at, subject_id, sort_order)"
            " VALUES (?, ?, ?, ?)",
            (name, _now(), subject_id, order),
        )
        self._activity("新建文件夹", f"「{name}」")
        self.conn.commit()
        return cur.lastrowid

    def list_folders(self, subject_id=None) -> list:
        """返回 [{id, name, created_at, subject_id, count}]，count 为夹内会话数。"""
        sql = """
            SELECT f.id, f.name, f.created_at, f.subject_id, f.sort_order,
                   COUNT(s.id) AS count
            FROM folders f
            LEFT JOIN sessions s ON s.folder_id = f.id
                AND s.deleted_at IS NULL
            WHERE f.deleted_at IS NULL
        """
        params = []
        if subject_id is not None:
            sql += " AND f.subject_id = ?"
            params.append(subject_id)
        sql += " GROUP BY f.id ORDER BY f.sort_order ASC, f.id DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_folder(self, folder_id: int):
        row = self.conn.execute(
            "SELECT id, name, created_at, subject_id, deleted_at"
            " FROM folders WHERE id = ?",
            (folder_id,),
        ).fetchone()
        return dict(row) if row else None

    def rename_folder(self, folder_id: int, name: str):
        old = self._named(self.get_folder, folder_id, "文件夹")
        self.conn.execute(
            "UPDATE folders SET name = ? WHERE id = ?", (name, folder_id)
        )
        self._activity("重命名文件夹", f"「{old}」改为「{name}」")
        self.conn.commit()

    def delete_folder(self, folder_id: int):
        """级联删除夹内所有会话及消息。"""
        name = self._named(self.get_folder, folder_id, "文件夹")
        self.conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
        self._activity("彻底删除", f"文件夹「{name}」")
        self.conn.commit()

    def folder_stats(self, folder_id: int):
        """返回 (会话数, 消息数)，供删除确认提示用。"""
        row = self.conn.execute(
            """
            SELECT COUNT(DISTINCT s.id) AS ns, COUNT(m.id) AS nm
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id
            WHERE s.folder_id = ? AND s.deleted_at IS NULL
            """,
            (folder_id,),
        ).fetchone()
        return row["ns"], row["nm"]

    def folder_image_files(self, folder_id: int) -> list:
        rows = self.conn.execute(
            """
            SELECT m.content FROM messages m
            JOIN sessions s ON s.id = m.session_id
            WHERE s.folder_id = ? AND m.kind = 'image'
            """,
            (folder_id,),
        ).fetchall()
        return [r["content"] for r in rows]

    # ---------- 会话 ----------

    def create_session(
        self, name: str, auto_named: bool = True, folder_id=None, subject_id=None
    ) -> int:
        subject_id = self._resolve_subject_id(
            folder_id=folder_id, subject_id=subject_id
        )
        created = _now()
        order = self._place_session_by_created(subject_id, folder_id, created)
        cur = self.conn.execute(
            "INSERT INTO sessions"
            " (name, created_at, updated_at, auto_named, folder_id, subject_id, sort_order)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, created, created, int(auto_named), folder_id, subject_id, order),
        )
        self._activity("新建会话", f"「{name}」")
        self.conn.commit()
        return cur.lastrowid

    def imported_external_ids(self, source: str) -> set:
        rows = self.conn.execute(
            "SELECT external_id FROM external_sessions WHERE source = ?",
            ((source or "").strip().lower(),),
        ).fetchall()
        return {r["external_id"] for r in rows}

    def import_cursor_conversation(self, info, messages, folder_id: int) -> ExternalImportResult:
        return self.import_external_conversation("cursor", info, messages, folder_id)

    def import_external_conversation(
        self, source: str, info, messages, folder_id: int, host: str = ""
    ) -> ExternalImportResult:
        """写入指定文件夹。Codex 若与夹内某段对话大量重合，则只补新消息。

        host 是来源机器 IP。新建会话会在标题末尾加上 -【ip】。
        续导入时，标题仍是原来的原文才会补上这个后缀；改过名的保持原名。
        """
        source = (source or "").strip().lower()
        if source not in ("cursor", "codex"):
            raise ValueError("不支持的导入来源")
        folder = self.get_folder(folder_id)
        if not folder:
            raise ValueError("目标文件夹不存在")
        host = (host or "").strip() if source == "codex" else ""
        display_title = with_host_suffix(info.title, host)
        if source == "codex":
            match = self._matching_codex_session(folder_id, messages)
            if match is not None:
                session_id, new_indexes = match
                added = self._append_imported_messages(
                    source, info, messages, session_id, new_indexes
                )
                name = self.get_session(session_id)["name"]
                renamed = False
                if host and name == (info.title or "") and display_title != name:
                    self.conn.execute(
                        "UPDATE sessions SET name = ? WHERE id = ?",
                        (display_title, session_id),
                    )
                    self.conn.commit()
                    name = display_title
                    renamed = True
                label = "Codex" if source == "codex" else "Cursor"
                if added:
                    detail = f"把 {added} 条新消息补进「{name}」（{label}）"
                elif renamed:
                    detail = f"「{name}」已补上来源标记，没有新消息"
                else:
                    detail = f"「{name}」已有这份 {label} 对话，没有新消息"
                self.record_activity("导入对话", detail)
                return ExternalImportResult(session_id, added, True, name)
        session_id = self._insert_imported_session(
            source, info, messages, folder, name=display_title
        )
        label = "Codex" if source == "codex" else "Cursor"
        self.record_activity(
            "导入对话",
            f"从 {label} 新建「{display_title}」，{len(messages)} 条",
        )
        return ExternalImportResult(session_id, len(messages), False, display_title)

    def _message_fingerprint(self, role: str, kind: str, content: str, cache: dict):
        """文本按原文比较；图片按文件内容比较，这样改过标题也能认出同一段对话。"""
        role = "ai" if role == "ai" else "user"
        if kind != "image":
            return ("text", role, (content or "").strip())
        cache_key = ("image", content)
        if cache_key not in cache:
            raw = self._image_payload_bytes(content)
            cache[cache_key] = hashlib.sha256(raw).hexdigest() if raw else None
        digest = cache[cache_key]
        if digest is None:
            return ("image", role, "unreadable", content)
        return ("image", role, digest)

    def _image_payload_bytes(self, content: str):
        if not isinstance(content, str) or not content:
            return None
        if content.startswith("data:image/"):
            try:
                _, encoded = content.split(",", 1)
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                return None
            return raw or None
        path = content if os.path.isfile(content) else os.path.join(IMAGES_DIR, content)
        if not os.path.isfile(path):
            return None
        with open(path, "rb") as handle:
            return handle.read()

    def _matching_codex_session(self, folder_id: int, messages):
        """在目标文件夹里找内容大量重合的会话。重合一样多时，取最近编辑的那份。"""
        if len(messages) < _OVERLAP_MIN_MATCHED:
            return None
        cache = {}
        incoming = [
            self._message_fingerprint(
                msg.role, getattr(msg, "kind", "text") or "text", msg.content, cache
            )
            for msg in messages
        ]
        rows = self.conn.execute(
            "SELECT id, updated_at FROM sessions"
            " WHERE folder_id = ? AND deleted_at IS NULL",
            (folder_id,),
        ).fetchall()
        best = None
        for row in rows:
            stored = self.get_messages(row["id"])
            if len(stored) < _OVERLAP_MIN_MATCHED:
                continue
            existing = [
                self._message_fingerprint(msg["role"], msg["kind"], msg["content"], cache)
                for msg in stored
            ]
            matched, new_indexes = _ordered_new_indexes(existing, incoming)
            if not _same_chat(matched, len(existing)):
                continue
            candidate = (matched, matched / len(existing), row["updated_at"] or "", row["id"])
            if best is None or candidate > best[0]:
                best = (candidate, new_indexes)
        if best is None:
            return None
        return best[0][3], best[1]

    def _append_imported_messages(
        self, source: str, info, messages, session_id: int, new_indexes: list
    ) -> int:
        """把对不上的消息补到已有会话末尾，不改标题。"""
        pending = [messages[index] for index in new_indexes]
        if not pending:
            return 0
        written_images = []
        try:
            external_id = self._ensure_external_session(source, info, session_id)
            self._write_imported_messages(
                session_id, source, external_id, pending, written_images
            )
            self._stamp_session(session_id)
            self.conn.commit()
            return len(pending)
        except Exception:
            self.conn.rollback()
            self._discard_images(written_images)
            raise

    def _insert_imported_session(
        self, source: str, info, messages, folder, name: str = None
    ) -> int:
        created = (
            datetime.fromtimestamp(info.created_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
            if info.created_ms else _now()
        )
        updated = (
            datetime.fromtimestamp(info.updated_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")
            if info.updated_ms else created
        )
        written_images = []
        try:
            order = self._place_session_by_created(
                folder["subject_id"], folder["id"], created
            )
            # 表结构保留唯一键以兼容旧数据库；每次新建使用独立实例键，
            # 原始 composerId 仍完整保存在 metadata 中。
            external_id = self._fresh_external_id(source, info.composer_id)
            cur = self.conn.execute(
                "INSERT INTO sessions"
                " (name, created_at, updated_at, auto_named, folder_id, subject_id,"
                " sort_order, source) VALUES (?, ?, ?, 0, ?, ?, ?, ?)",
                (
                    name or info.title, created, updated, folder["id"], folder["subject_id"],
                    order, source,
                ),
            )
            session_id = cur.lastrowid
            self.conn.execute(
                "INSERT INTO external_sessions"
                " (source, external_id, session_id, workspace, raw_metadata, imported_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    source, external_id, session_id, info.workspace or "",
                    _external_metadata(info), _now(),
                ),
            )
            self._write_imported_messages(
                session_id, source, external_id, messages, written_images
            )
            self.conn.commit()
            return session_id
        except Exception:
            self.conn.rollback()
            self._discard_images(written_images)
            raise

    def _ensure_external_session(self, source: str, info, session_id: int) -> str:
        row = self.conn.execute(
            "SELECT external_id FROM external_sessions"
            " WHERE session_id = ? AND source = ? ORDER BY id LIMIT 1",
            (session_id, source),
        ).fetchone()
        metadata = _external_metadata(info)
        if row:
            self.conn.execute(
                "UPDATE external_sessions SET workspace = ?, raw_metadata = ?"
                " WHERE source = ? AND external_id = ?",
                (info.workspace or "", metadata, source, row["external_id"]),
            )
            return row["external_id"]
        external_id = self._fresh_external_id(source, info.composer_id)
        self.conn.execute(
            "INSERT INTO external_sessions"
            " (source, external_id, session_id, workspace, raw_metadata, imported_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                source, external_id, session_id, info.workspace or "",
                metadata, _now(),
            ),
        )
        self.conn.execute(
            "UPDATE sessions SET source = ? WHERE id = ? AND source = ''",
            (source, session_id),
        )
        return external_id

    def _fresh_external_id(self, source: str, composer_id: str) -> str:
        external_id = composer_id
        exists = self.conn.execute(
            "SELECT 1 FROM external_sessions WHERE source = ? AND external_id = ?",
            (source, external_id),
        ).fetchone()
        if exists:
            external_id = f"{composer_id}#{uuid.uuid4().hex}"
        return external_id

    def _write_imported_messages(
        self, session_id: int, source: str, external_session_id: str,
        messages, written_images: list,
    ):
        for msg in messages:
            content = msg.content
            kind = getattr(msg, "kind", "text") or "text"
            if kind == "image":
                content = self._save_external_image(content)
                written_images.append(content)
            created = getattr(msg, "created_at", None) or _now()
            mcur = self.conn.execute(
                "INSERT INTO messages"
                " (session_id, role, content, kind, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (session_id, msg.role, content, kind, created),
            )
            external_message_id = self._unique_external_message_id(
                source, external_session_id, msg.external_id
            )
            self.conn.execute(
                "INSERT INTO external_messages"
                " (source, external_session_id, external_message_id, message_id, raw_json)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    source, external_session_id, external_message_id,
                    mcur.lastrowid, msg.raw_json,
                ),
            )

    def _unique_external_message_id(
        self, source: str, external_session_id: str, external_id: str
    ) -> str:
        candidate = external_id or uuid.uuid4().hex
        number = 2
        while self.conn.execute(
            "SELECT 1 FROM external_messages"
            " WHERE source = ? AND external_session_id = ? AND external_message_id = ?",
            (source, external_session_id, candidate),
        ).fetchone():
            candidate = f"{external_id}#{number}"
            number += 1
        return candidate

    def _discard_images(self, names: list):
        for name in names:
            try:
                os.remove(os.path.join(IMAGES_DIR, name))
            except OSError:
                pass

    def _save_external_image(self, source: str) -> str:
        """把本地图片或 data URL 安全复制到 data/images。"""
        raw = None
        ext = ".png"
        if source.startswith("data:image/"):
            try:
                header, encoded = source.split(",", 1)
                mime = header[len("data:image/"):].split(";", 1)[0].lower()
                ext = {"jpeg": ".jpg", "jpg": ".jpg", "gif": ".gif", "webp": ".webp", "bmp": ".bmp"}.get(mime, ".png")
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("Codex 图片数据损坏") from exc
        else:
            path = os.path.abspath(os.path.expanduser(source))
            if not os.path.isfile(path):
                raise ValueError(f"Cursor 图片文件不存在：{path}")
            ext = os.path.splitext(path)[1].lower()
            if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
                ext = ".png"
            with open(path, "rb") as handle:
                raw = handle.read()
        if not raw:
            raise ValueError("图片内容为空")
        if len(raw) > 50 * 1024 * 1024:
            raise ValueError("单张图片超过 50 MB，已拒绝导入")
        os.makedirs(IMAGES_DIR, exist_ok=True)
        name = uuid.uuid4().hex + ext
        with open(os.path.join(IMAGES_DIR, name), "xb") as handle:
            handle.write(raw)
        return name

    def list_sessions(self, subject_id=None) -> list:
        """返回 [{id, name, created_at, folder_id, subject_id, count}]。"""
        sql = """
            SELECT s.id, s.name, s.created_at, s.updated_at, s.folder_id,
                   s.subject_id, s.sort_order, s.match_color, s.note,
                   s.source, s.done,
                   COUNT(m.id) AS count
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id
            WHERE s.deleted_at IS NULL
        """
        params = []
        if subject_id is not None:
            sql += " AND s.subject_id = ?"
            params.append(subject_id)
        sql += " GROUP BY s.id ORDER BY s.sort_order ASC, s.id DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: int):
        row = self.conn.execute(
            "SELECT id, name, created_at, updated_at, folder_id, subject_id,"
            " deleted_at, match_color, note, source, done"
            " FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None

    def set_sessions_match_color(self, session_ids, color):
        """给一组会话写上（或清除）匹配颜色。"""
        ids = [int(i) for i in session_ids]
        if not ids:
            return
        for sid in ids:
            self.conn.execute(
                "UPDATE sessions SET match_color = ? WHERE id = ?",
                (color, sid),
            )
        if color:
            self._activity("颜色匹配", f"{len(ids)} 个会话")
        else:
            self._activity("取消颜色匹配", f"{len(ids)} 个会话")
        self.conn.commit()

    def move_session(self, session_id: int, folder_id, subject_id=None):
        """把会话移入某文件夹；folder_id 为 None 表示移到课题根目录。"""
        if folder_id is not None:
            folder = self.get_folder(folder_id)
            if folder:
                subject_id = folder["subject_id"]
        sess = self.get_session(session_id)
        if subject_id is None:
            subject_id = None if sess is None else sess.get("subject_id")
        created = "" if sess is None else (sess.get("created_at") or "")
        order = self._place_session_by_created(
            subject_id, folder_id, created, exclude_id=session_id
        )
        self.conn.execute(
            "UPDATE sessions SET folder_id = ?, subject_id = ?, sort_order = ?,"
            " match_color = NULL WHERE id = ?",
            (folder_id, subject_id, order, session_id),
        )
        self.conn.execute(
            "UPDATE mindmaps SET subject_id = ? WHERE session_id = ?",
            (subject_id, session_id),
        )
        self.conn.execute(
            "UPDATE documents SET subject_id = ? WHERE session_id = ?",
            (subject_id, session_id),
        )
        self._activity("移动会话", f"「{self._session_name(session_id)}」")
        self.conn.commit()

    def _copy_title(self, name: str) -> str:
        name = (name or "").strip() or "未命名"
        return name if name.endswith(" 副本") else name + " 副本"

    def _duplicate_image_file(self, filename: str) -> str:
        if not filename:
            return filename
        src = os.path.join(IMAGES_DIR, filename)
        if not os.path.isfile(src):
            return filename
        ext = os.path.splitext(filename)[1]
        dest_name = uuid.uuid4().hex + ext
        os.makedirs(IMAGES_DIR, exist_ok=True)
        shutil.copy2(src, os.path.join(IMAGES_DIR, dest_name))
        return dest_name

    def copy_session(self, session_id: int, folder_id, subject_id=None) -> int:
        """复制会话（含消息、图片文件、挂在该会话下的思维导图）到目标文件夹。"""
        src = self.get_session(session_id)
        if src is None:
            return 0
        self._mute_activity = getattr(self, "_mute_activity", 0) + 1
        try:
            new_id = self._copy_session_body(
                src, session_id, folder_id, subject_id
            )
        finally:
            self._mute_activity -= 1
        self._activity("复制会话", f"「{src['name']}」")
        self.conn.commit()
        return new_id

    def _copy_session_body(self, src, session_id, folder_id, subject_id) -> int:
        new_id = self.create_session(
            self._copy_title(src["name"]),
            auto_named=False,
            folder_id=folder_id,
            subject_id=subject_id if folder_id is None else None,
        )
        note = (src.get("note") or "").strip()
        if note:
            self.set_session_note(new_id, note)
        source = (src.get("source") or "").strip().lower()
        if source in ("cursor", "codex"):
            self.set_session_source(new_id, source, commit=False)
        if src.get("done"):
            self.set_session_done(new_id, True, commit=False)
        for m in self.get_messages(session_id):
            content = m["content"]
            if m.get("kind") == "image":
                content = self._duplicate_image_file(content)
            self.conn.execute(
                "INSERT INTO messages"
                " (session_id, role, content, kind, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (new_id, m["role"], content, m["kind"], m["created_at"]),
            )
        for mmap in self.list_mindmaps():
            if mmap["session_id"] == session_id:
                self.copy_mindmap(
                    mmap["id"],
                    folder_id=None,
                    session_id=new_id,
                    as_copy=False,
                    commit=False,
                )
        for doc in self.list_documents():
            if doc["session_id"] == session_id:
                self.copy_document(
                    doc["id"],
                    folder_id=None,
                    session_id=new_id,
                    as_copy=False,
                    commit=False,
                )
        return new_id

    def session_image_files(self, session_id: int) -> list:
        rows = self.conn.execute(
            "SELECT content FROM messages"
            " WHERE session_id = ? AND kind = 'image'",
            (session_id,),
        ).fetchall()
        return [r["content"] for r in rows]

    def rename_session(self, session_id: int, name: str):
        """用户手动命名后，该会话不再参与自动命名。"""
        self.conn.execute(
            "UPDATE sessions SET name = ?, auto_named = 0, updated_at = ?"
            " WHERE id = ?",
            (name, _now(), session_id),
        )
        self._activity("重命名会话", f"「{name}」")
        self.conn.commit()

    def set_session_note(self, session_id: int, note: str):
        note = (note or "").strip()
        self.conn.execute(
            "UPDATE sessions SET note = ? WHERE id = ?",
            (note, session_id),
        )
        name = self._session_name(session_id)
        detail = f"「{name}」" + (f"：{_clip(note)}" if note else "：清空备注")
        self._activity("修改备注", detail)
        self.conn.commit()

    def set_session_source(self, session_id: int, source: str, commit: bool = True):
        key = (source or "").strip().lower()
        if key not in ("cursor", "codex"):
            key = ""
        self.conn.execute(
            "UPDATE sessions SET source = ? WHERE id = ?",
            (key, session_id),
        )
        if commit:
            name = self._session_name(session_id)
            label = {"cursor": "Cursor", "codex": "Codex"}.get(key, "")
            if label:
                self._activity("设置来源标签", f"「{name}」标为 {label}")
            else:
                self._activity("设置来源标签", f"取消「{name}」的来源标签")
            self.conn.commit()

    def set_session_done(self, session_id: int, done: bool, commit: bool = True):
        self.conn.execute(
            "UPDATE sessions SET done = ? WHERE id = ?",
            (1 if done else 0, session_id),
        )
        if commit:
            name = self._session_name(session_id)
            self._activity(
                "标记完成" if done else "取消完成",
                f"会话「{name}」",
            )
            self.conn.commit()

    def auto_name_if_first(self, session_id: int, content: str):
        """会话还是默认名且刚收到第一条记录时，命名为「日期-内容前缀」。"""
        row = self.conn.execute(
            """
            SELECT s.auto_named, COUNT(m.id) AS cnt
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id
            WHERE s.id = ?
            GROUP BY s.id
            """,
            (session_id,),
        ).fetchone()
        if row is None or not row["auto_named"] or row["cnt"] != 1:
            return
        prefix = re.sub(r"\s+", " ", content).strip()
        prefix = re.sub(r"^[#>*`\-\s]+", "", prefix)[:10].strip()
        name = datetime.now().strftime("%Y-%m-%d")
        if prefix:
            name = f"{name}-{prefix}"
        self.conn.execute(
            "UPDATE sessions SET name = ? WHERE id = ?", (name, session_id)
        )
        self.conn.commit()

    def delete_session(self, session_id: int):
        name = self._session_name(session_id)
        self.conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._activity("彻底删除", f"会话「{name}」")
        self.conn.commit()

    # ---------- 消息 ----------

    def add_message(
        self, session_id: int, role: str, content: str, kind: str = "text"
    ) -> int:
        cur = self.conn.execute(
            "INSERT INTO messages"
            " (session_id, role, content, kind, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, kind, _now()),
        )
        self._stamp_session(session_id)
        sname = self._session_name(session_id)
        if kind == "image":
            detail = f"在「{sname}」记下{'提问' if role == 'user' else '回答'}图片"
        else:
            who = "提问" if role == "user" else "回答"
            detail = f"在「{sname}」记下{who}：{_clip(content)}"
        self._activity("记录对话", detail)
        self.conn.commit()
        return cur.lastrowid

    def get_messages(self, session_id: int) -> list:
        rows = self.conn.execute(
            "SELECT id, session_id, role, content, kind, created_at"
            " FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_message(self, message_id: int):
        row = self.conn.execute(
            "SELECT id, session_id, role, content, kind, created_at"
            " FROM messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        return dict(row) if row else None

    def delete_message(self, message_id: int):
        msg = self.get_message(message_id)
        self.conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        if msg:
            self._stamp_session(msg["session_id"])
            preview = "图片" if msg["kind"] == "image" else _clip(msg["content"])
            self._activity("删除记录", preview)
        self.conn.commit()

    def flip_role(self, message_id: int):
        msg = self.get_message(message_id)
        self.conn.execute(
            "UPDATE messages SET role = CASE role WHEN 'user' THEN 'ai'"
            " ELSE 'user' END WHERE id = ?",
            (message_id,),
        )
        if msg:
            self._stamp_session(msg["session_id"])
            new_role = "回答" if msg["role"] == "user" else "提问"
            preview = "图片" if msg["kind"] == "image" else _clip(msg["content"])
            self._activity("修改记录", f"改成{new_role}：{preview}")
        self.conn.commit()

    # ---------- 搜索 ----------

    def search(self, keyword: str, limit: int = 200) -> list:
        """跨会话按内容模糊搜索，返回带会话名的消息列表。"""
        rows = self.conn.execute(
            """
            SELECT m.id, m.session_id, m.role, m.content, m.kind,
                   m.created_at, s.name AS session_name
            FROM messages m
            JOIN sessions s ON s.id = m.session_id
            WHERE m.content LIKE ? ESCAPE '\\'
              AND s.deleted_at IS NULL
            ORDER BY m.id DESC
            LIMIT ?
            """,
            ("%" + _escape_like(keyword) + "%", limit),
        ).fetchall()
        return [dict(r) for r in rows]


    # ---------- 待办 ----------

    def list_todos(self) -> list:
        rows = self.conn.execute(
            """
            SELECT id, content, note, mark, done, sort_order, created_at
            FROM todos
            ORDER BY done ASC, sort_order ASC, id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def add_todo(self, content: str) -> int:
        content = (content or "").strip()
        if not content:
            return 0
        order = self._front_sort("todos")
        cur = self.conn.execute(
            "INSERT INTO todos (content, done, sort_order, created_at)"
            " VALUES (?, 0, ?, ?)",
            (content, order, _now()),
        )
        self._activity("添加待办", _clip(content))
        self.conn.commit()
        return cur.lastrowid

    def _todo_text(self, todo_id: int) -> str:
        row = self.conn.execute(
            "SELECT content FROM todos WHERE id = ?", (todo_id,)
        ).fetchone()
        return _clip(row["content"]) if row else "待办"

    def set_todo_done(self, todo_id: int, done: bool):
        text = self._todo_text(todo_id)
        self.conn.execute(
            "UPDATE todos SET done = ? WHERE id = ?",
            (1 if done else 0, todo_id),
        )
        self._activity("完成待办" if done else "恢复待办", text)
        self.conn.commit()

    def set_todo_note(self, todo_id: int, note: str):
        note = (note or "").strip()
        text = self._todo_text(todo_id)
        self.conn.execute(
            "UPDATE todos SET note = ? WHERE id = ?",
            (note, todo_id),
        )
        detail = text + (f"：{_clip(note)}" if note else "：清空备注")
        self._activity("修改待办备注", detail)
        self.conn.commit()

    def set_todo_mark(self, todo_id: int, mark: str):
        mark = (mark or "").strip()
        if mark not in ("", "later", "skip"):
            mark = ""
        self.conn.execute(
            "UPDATE todos SET mark = ? WHERE id = ?",
            (mark, todo_id),
        )
        labels = {"": "取消标记", "later": "标为延后", "skip": "标为不做了"}
        self._activity(labels.get(mark, "标记待办"), self._todo_text(todo_id))
        self.conn.commit()

    def delete_todo(self, todo_id: int):
        text = self._todo_text(todo_id)
        self.conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        self._activity("删除待办", text)
        self.conn.commit()

    # ---------- 常用（密钥 / 账号 / 提示词）----------

    def list_stash(self, kind: str = None) -> list:
        sql = """
            SELECT id, title, body, kind, sort_order, created_at
            FROM stash
        """
        params = []
        if kind:
            sql += " WHERE kind = ?"
            params.append(kind)
        sql += " ORDER BY sort_order ASC, id DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def add_stash(self, title: str, kind: str = "key") -> int:
        title = (title or "").strip()
        if not title:
            return 0
        if kind not in ("key", "account", "prompt"):
            kind = "key"
        order = self._front_sort("stash")
        cur = self.conn.execute(
            "INSERT INTO stash (title, body, kind, sort_order, created_at)"
            " VALUES (?, '', ?, ?, ?)",
            (title, kind, order, _now()),
        )
        self._activity("添加常用", self._stash_log_detail(kind, title))
        self.conn.commit()
        return cur.lastrowid

    def _stash_kind(self, stash_id: int) -> str:
        row = self.conn.execute(
            "SELECT kind, title FROM stash WHERE id = ?", (stash_id,)
        ).fetchone()
        if row is None:
            return "key", ""
        return row["kind"] or "key", row["title"] or ""

    def _stash_log_detail(self, kind: str, title: str = "") -> str:
        name = _STASH_KIND_NAMES.get(kind, "常用")
        if kind == "prompt" and title:
            return f"{name}「{_clip(title)}」"
        return name

    def set_stash_title(self, stash_id: int, title: str):
        title = (title or "").strip()
        if not title:
            return
        kind, _old = self._stash_kind(stash_id)
        self.conn.execute(
            "UPDATE stash SET title = ?, body = '' WHERE id = ?",
            (title, stash_id),
        )
        self._activity("修改常用", self._stash_log_detail(kind, title))
        self.conn.commit()

    def set_stash_body(self, stash_id: int, body: str):
        kind, title = self._stash_kind(stash_id)
        self.conn.execute(
            "UPDATE stash SET body = ? WHERE id = ?",
            ((body or "").strip(), stash_id),
        )
        self._activity("修改常用", self._stash_log_detail(kind, title))
        self.conn.commit()

    def delete_stash(self, stash_id: int):
        kind, title = self._stash_kind(stash_id)
        self.conn.execute("DELETE FROM stash WHERE id = ?", (stash_id,))
        self._activity("删除常用", self._stash_log_detail(kind, title))
        self.conn.commit()

    def backup_to(self, dest_path: str):
        """把当前打开的库热备份到 dest_path，避免直接拷文件导致损坏。"""
        self.conn.commit()
        parent = os.path.dirname(dest_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        dest = sqlite3.connect(dest_path)
        try:
            self.conn.backup(dest)
        finally:
            dest.close()

    def close(self):
        self.conn.close()


def _escape_like(text: str) -> str:
    return (
        text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
