"""SQLite 文档相关方法，作为 Database 的 Mixin。"""

from db import _now


class DocumentMixin:
    def _ensure_documents_table(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                folder_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
                session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
                subject_id INTEGER REFERENCES subjects(id) ON DELETE CASCADE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                deleted_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_documents_subject
                ON documents(subject_id);
            """
        )

    def create_document(
        self, name: str, folder_id=None, session_id=None, subject_id=None
    ) -> int:
        subject_id = self._resolve_subject_id(
            folder_id=folder_id, session_id=session_id, subject_id=subject_id
        )
        order = self._mixed_front_sort(
            subject_id, folder_id=folder_id, session_id=session_id
        )
        now = _now()
        cur = self.conn.execute(
            "INSERT INTO documents"
            " (name, content, created_at, updated_at, folder_id,"
            " session_id, subject_id, sort_order)"
            " VALUES (?, '', ?, ?, ?, ?, ?, ?)",
            (name, now, now, folder_id, session_id, subject_id, order),
        )
        self.conn.commit()
        return cur.lastrowid

    def list_documents(self, subject_id=None) -> list:
        sql = """
            SELECT id, name, created_at, updated_at, folder_id, session_id,
                   subject_id, sort_order
            FROM documents
            WHERE deleted_at IS NULL
        """
        params = []
        if subject_id is not None:
            sql += " AND subject_id = ?"
            params.append(subject_id)
        sql += " ORDER BY sort_order ASC, id DESC"
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def get_document(self, document_id: int):
        row = self.conn.execute(
            "SELECT id, name, content, created_at, updated_at, folder_id,"
            " session_id, subject_id, deleted_at FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
        return dict(row) if row else None

    def rename_document(self, document_id: int, name: str):
        self.conn.execute(
            "UPDATE documents SET name = ?, updated_at = ? WHERE id = ?",
            (name, _now(), document_id),
        )
        self.conn.commit()

    def update_document_content(self, document_id: int, content: str):
        self.conn.execute(
            "UPDATE documents SET content = ?, updated_at = ? WHERE id = ?",
            (content, _now(), document_id),
        )
        self.conn.commit()

    def delete_document(self, document_id: int):
        self.conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        self.conn.commit()

    def move_document(
        self, document_id: int, folder_id=None, session_id=None, subject_id=None
    ):
        subject_id = self._resolve_subject_id(
            folder_id=folder_id, session_id=session_id, subject_id=subject_id
        )
        order = self._mixed_front_sort(
            subject_id, folder_id=folder_id, session_id=session_id
        )
        self.conn.execute(
            "UPDATE documents"
            " SET folder_id = ?, session_id = ?, subject_id = ?, sort_order = ?,"
            " updated_at = ?"
            " WHERE id = ?",
            (folder_id, session_id, subject_id, order, _now(), document_id),
        )
        self.conn.commit()

    def copy_document(
        self,
        document_id: int,
        folder_id=None,
        session_id=None,
        as_copy: bool = True,
        commit: bool = True,
        subject_id=None,
    ) -> int:
        src = self.get_document(document_id)
        if src is None:
            return 0
        name = self._copy_title(src["name"]) if as_copy else src["name"]
        subject_id = self._resolve_subject_id(
            folder_id=folder_id, session_id=session_id, subject_id=subject_id
        )
        order = self._mixed_front_sort(
            subject_id, folder_id=folder_id, session_id=session_id
        )
        now = _now()
        cur = self.conn.execute(
            "INSERT INTO documents"
            " (name, content, created_at, updated_at, folder_id,"
            " session_id, subject_id, sort_order)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                name,
                src.get("content") or "",
                now,
                now,
                folder_id,
                session_id,
                subject_id,
                order,
            ),
        )
        if commit:
            self.conn.commit()
        return cur.lastrowid
