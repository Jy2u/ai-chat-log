"""SQLite 存储层：会话与消息。"""

import os
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


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


from db_mindmaps import MindmapMixin
from db_documents import DocumentMixin
from db_trash import TrashMixin


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
            CREATE TABLE IF NOT EXISTS mindmaps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
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
                highlighted INTEGER NOT NULL DEFAULT 0
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
        self._ensure_todos_table()
        self.conn.commit()

    def _table_cols(self, table: str) -> list:
        return [
            r["name"]
            for r in self.conn.execute(f"PRAGMA table_info({table})")
        ]

    def _migrate_match_color(self):
        """会话可按文件夹内分组高亮。"""
        if "match_color" not in self._table_cols("sessions"):
            self.conn.execute(
                "ALTER TABLE sessions ADD COLUMN match_color TEXT"
            )

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
        self.conn.commit()

    def reorder_subjects(self, ids: list):
        for i, sid in enumerate(ids):
            self.conn.execute(
                "UPDATE subjects SET sort_order = ? WHERE id = ?", (i, sid)
            )
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
        self.conn.execute(
            "UPDATE subjects SET name = ? WHERE id = ?", (name, subject_id)
        )
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
        self.conn.execute(
            "UPDATE folders SET name = ? WHERE id = ?", (name, folder_id)
        )
        self.conn.commit()

    def delete_folder(self, folder_id: int):
        """级联删除夹内所有会话及消息。"""
        self.conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
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
        order = self._mixed_front_sort(subject_id, folder_id=folder_id)
        cur = self.conn.execute(
            "INSERT INTO sessions"
            " (name, created_at, auto_named, folder_id, subject_id, sort_order)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (name, _now(), int(auto_named), folder_id, subject_id, order),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_sessions(self, subject_id=None) -> list:
        """返回 [{id, name, created_at, folder_id, subject_id, count}]，新建的在前。"""
        sql = """
            SELECT s.id, s.name, s.created_at, s.folder_id, s.subject_id,
                   s.sort_order, s.match_color, COUNT(m.id) AS count
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
            "SELECT id, name, created_at, folder_id, subject_id, deleted_at,"
            " match_color FROM sessions WHERE id = ?",
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
        self.conn.commit()

    def move_session(self, session_id: int, folder_id, subject_id=None):
        """把会话移入某文件夹；folder_id 为 None 表示移到课题根目录。"""
        if folder_id is not None:
            folder = self.get_folder(folder_id)
            if folder:
                subject_id = folder["subject_id"]
        if subject_id is None:
            sess = self.get_session(session_id)
            subject_id = None if sess is None else sess.get("subject_id")
        order = self._mixed_front_sort(subject_id, folder_id=folder_id)
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
        new_id = self.create_session(
            self._copy_title(src["name"]),
            auto_named=False,
            folder_id=folder_id,
            subject_id=subject_id if folder_id is None else None,
        )
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
        self.conn.commit()
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
            "UPDATE sessions SET name = ?, auto_named = 0 WHERE id = ?",
            (name, session_id),
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
        self.conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
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
        self.conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        self.conn.commit()

    def flip_role(self, message_id: int):
        self.conn.execute(
            "UPDATE messages SET role = CASE role WHEN 'user' THEN 'ai'"
            " ELSE 'user' END WHERE id = ?",
            (message_id,),
        )
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
        self.conn.commit()
        return cur.lastrowid

    def set_todo_done(self, todo_id: int, done: bool):
        self.conn.execute(
            "UPDATE todos SET done = ? WHERE id = ?",
            (1 if done else 0, todo_id),
        )
        self.conn.commit()

    def set_todo_note(self, todo_id: int, note: str):
        self.conn.execute(
            "UPDATE todos SET note = ? WHERE id = ?",
            ((note or "").strip(), todo_id),
        )
        self.conn.commit()

    def set_todo_mark(self, todo_id: int, mark: str):
        mark = (mark or "").strip()
        if mark not in ("", "later", "skip"):
            mark = ""
        self.conn.execute(
            "UPDATE todos SET mark = ? WHERE id = ?",
            (mark, todo_id),
        )
        self.conn.commit()

    def delete_todo(self, todo_id: int):
        self.conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
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
