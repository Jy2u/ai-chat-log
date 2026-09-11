"""回收站：会话 / 文件夹 / 导图 / 文档软删除与恢复。"""

from db import _now


class TrashMixin:
    def _migrate_deleted_at(self):
        for table in (
            "subjects",
            "folders",
            "sessions",
            "mindmaps",
            "documents",
        ):
            if "deleted_at" not in self._table_cols(table):
                self.conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN deleted_at TEXT"
                )

    def _stamp_deleted(self, table: str, where: str, params):
        sql = (
            f"UPDATE {table} SET deleted_at = ?"
            f" WHERE deleted_at IS NULL AND ({where})"
        )
        self.conn.execute(sql, (_now(),) + tuple(params))

    def trash_subject(self, subject_id: int) -> bool:
        n = self.conn.execute(
            "SELECT COUNT(*) AS c FROM subjects WHERE deleted_at IS NULL"
        ).fetchone()["c"]
        if n <= 1:
            return False
        self._stamp_deleted("subjects", "id = ?", (subject_id,))
        self._stamp_deleted("folders", "subject_id = ?", (subject_id,))
        self._stamp_deleted("sessions", "subject_id = ?", (subject_id,))
        self._stamp_deleted("mindmaps", "subject_id = ?", (subject_id,))
        self._stamp_deleted("documents", "subject_id = ?", (subject_id,))
        self.conn.commit()
        return True

    def trash_folder(self, folder_id: int):
        self._stamp_deleted("folders", "id = ?", (folder_id,))
        self._stamp_deleted("sessions", "folder_id = ?", (folder_id,))
        self._stamp_deleted(
            "mindmaps",
            "folder_id = ? OR session_id IN"
            " (SELECT id FROM sessions WHERE folder_id = ?)",
            (folder_id, folder_id),
        )
        self._stamp_deleted(
            "documents",
            "folder_id = ? OR session_id IN"
            " (SELECT id FROM sessions WHERE folder_id = ?)",
            (folder_id, folder_id),
        )
        self.conn.commit()

    def trash_session(self, session_id: int):
        self._stamp_deleted("sessions", "id = ?", (session_id,))
        self._stamp_deleted("mindmaps", "session_id = ?", (session_id,))
        self._stamp_deleted("documents", "session_id = ?", (session_id,))
        self.conn.commit()

    def trash_mindmap(self, mindmap_id: int):
        self._stamp_deleted("mindmaps", "id = ?", (mindmap_id,))
        self.conn.commit()

    def trash_document(self, document_id: int):
        self._stamp_deleted("documents", "id = ?", (document_id,))
        self.conn.commit()

    def restore_subject(self, subject_id: int) -> bool:
        row = self.get_subject(subject_id)
        if row is None:
            return False
        self.conn.execute(
            "UPDATE subjects SET deleted_at = NULL WHERE id = ?",
            (subject_id,),
        )
        self.conn.execute(
            "UPDATE folders SET deleted_at = NULL WHERE subject_id = ?",
            (subject_id,),
        )
        self.conn.execute(
            "UPDATE sessions SET deleted_at = NULL WHERE subject_id = ?",
            (subject_id,),
        )
        self.conn.execute(
            "UPDATE mindmaps SET deleted_at = NULL WHERE subject_id = ?",
            (subject_id,),
        )
        self.conn.execute(
            "UPDATE documents SET deleted_at = NULL WHERE subject_id = ?",
            (subject_id,),
        )
        self.conn.commit()
        return True

    def restore_folder(self, folder_id: int):
        folder = self.get_folder(folder_id)
        if folder is None:
            return
        self._restore_subject_row(folder.get("subject_id"))
        self.conn.execute(
            "UPDATE folders SET deleted_at = NULL WHERE id = ?", (folder_id,)
        )
        self.conn.execute(
            "UPDATE sessions SET deleted_at = NULL WHERE folder_id = ?",
            (folder_id,),
        )
        self.conn.execute(
            """
            UPDATE mindmaps SET deleted_at = NULL
            WHERE folder_id = ? OR session_id IN (
                SELECT id FROM sessions WHERE folder_id = ?
            )
            """,
            (folder_id, folder_id),
        )
        self.conn.execute(
            """
            UPDATE documents SET deleted_at = NULL
            WHERE folder_id = ? OR session_id IN (
                SELECT id FROM sessions WHERE folder_id = ?
            )
            """,
            (folder_id, folder_id),
        )
        self.conn.commit()

    def restore_session(self, session_id: int) -> bool:
        sess = self.get_session(session_id)
        if sess is None:
            return False
        folder_id = sess.get("folder_id")
        self._restore_subject_row(sess.get("subject_id"))
        if folder_id is not None:
            folder = self.get_folder(folder_id)
            if folder and folder.get("deleted_at"):
                self.conn.execute(
                    "UPDATE folders SET deleted_at = NULL WHERE id = ?",
                    (folder_id,),
                )
        self.conn.execute(
            "UPDATE sessions SET deleted_at = NULL WHERE id = ?",
            (session_id,),
        )
        self.conn.execute(
            "UPDATE mindmaps SET deleted_at = NULL WHERE session_id = ?",
            (session_id,),
        )
        self.conn.execute(
            "UPDATE documents SET deleted_at = NULL WHERE session_id = ?",
            (session_id,),
        )
        self.conn.commit()
        return True

    def restore_mindmap(self, mindmap_id: int) -> bool:
        mmap = self.get_mindmap(mindmap_id)
        if mmap is None:
            return False
        self._restore_ancestors(
            mmap.get("folder_id"), mmap.get("session_id")
        )
        self._restore_subject_row(mmap.get("subject_id"))
        self.conn.execute(
            "UPDATE mindmaps SET deleted_at = NULL WHERE id = ?",
            (mindmap_id,),
        )
        self.conn.commit()
        return True

    def restore_document(self, document_id: int) -> bool:
        doc = self.get_document(document_id)
        if doc is None:
            return False
        self._restore_ancestors(doc.get("folder_id"), doc.get("session_id"))
        self._restore_subject_row(doc.get("subject_id"))
        self.conn.execute(
            "UPDATE documents SET deleted_at = NULL WHERE id = ?",
            (document_id,),
        )
        self.conn.commit()
        return True

    def _restore_subject_row(self, subject_id):
        if subject_id is None:
            return
        sub = self.get_subject(subject_id)
        if sub and sub.get("deleted_at"):
            self.conn.execute(
                "UPDATE subjects SET deleted_at = NULL WHERE id = ?",
                (subject_id,),
            )

    def _restore_ancestors(self, folder_id, session_id):
        subject_id = None
        if session_id is not None:
            sess = self.get_session(session_id)
            if sess:
                subject_id = sess.get("subject_id")
                if sess.get("deleted_at"):
                    self.conn.execute(
                        "UPDATE sessions SET deleted_at = NULL WHERE id = ?",
                        (session_id,),
                    )
                folder_id = sess.get("folder_id") or folder_id
        if folder_id is not None:
            folder = self.get_folder(folder_id)
            if folder:
                subject_id = folder.get("subject_id") or subject_id
                if folder.get("deleted_at"):
                    self.conn.execute(
                        "UPDATE folders SET deleted_at = NULL WHERE id = ?",
                        (folder_id,),
                    )
        self._restore_subject_row(subject_id)

    def list_trash_items(self) -> list:
        """回收站里「顶层」条目：夹在里面的子项随父级一起恢复，不单独列出。"""
        items = []
        for r in self.conn.execute(
            """
            SELECT sub.id, sub.name, sub.deleted_at, sub.id AS subject_id,
                   sub.name AS subject_name,
                   NULL AS folder_name, NULL AS session_name,
                   'subject' AS kind,
                   (SELECT COUNT(*) FROM sessions s
                    WHERE s.subject_id = sub.id) AS extra
            FROM subjects sub
            WHERE sub.deleted_at IS NOT NULL
            """
        ).fetchall():
            items.append(dict(r))
        for r in self.conn.execute(
            """
            SELECT f.id, f.name, f.deleted_at, f.subject_id,
                   sub.name AS subject_name,
                   NULL AS folder_name, NULL AS session_name,
                   'folder' AS kind,
                   (SELECT COUNT(*) FROM sessions s
                    WHERE s.folder_id = f.id) AS extra
            FROM folders f
            JOIN subjects sub ON sub.id = f.subject_id
            WHERE f.deleted_at IS NOT NULL
              AND sub.deleted_at IS NULL
            """
        ).fetchall():
            items.append(dict(r))
        for r in self.conn.execute(
            """
            SELECT s.id, s.name, s.deleted_at, s.subject_id,
                   sub.name AS subject_name,
                   fol.name AS folder_name, NULL AS session_name,
                   'session' AS kind,
                   (SELECT COUNT(*) FROM messages m
                    WHERE m.session_id = s.id) AS extra
            FROM sessions s
            JOIN subjects sub ON sub.id = s.subject_id
            LEFT JOIN folders fol ON fol.id = s.folder_id
            WHERE s.deleted_at IS NOT NULL
              AND sub.deleted_at IS NULL
              AND (s.folder_id IS NULL OR fol.deleted_at IS NULL)
            """
        ).fetchall():
            items.append(dict(r))
        for r in self.conn.execute(
            """
            SELECT m.id, m.name, m.deleted_at, m.subject_id,
                   sub.name AS subject_name,
                   fol.name AS folder_name,
                   sess.name AS session_name,
                   'mindmap' AS kind,
                   0 AS extra
            FROM mindmaps m
            JOIN subjects sub ON sub.id = m.subject_id
            LEFT JOIN sessions sess ON sess.id = m.session_id
            LEFT JOIN folders fol ON fol.id = COALESCE(
                m.folder_id, sess.folder_id
            )
            WHERE m.deleted_at IS NOT NULL
              AND sub.deleted_at IS NULL
              AND (m.session_id IS NULL OR sess.deleted_at IS NULL)
              AND (fol.id IS NULL OR fol.deleted_at IS NULL)
            """
        ).fetchall():
            items.append(dict(r))
        for r in self.conn.execute(
            """
            SELECT d.id, d.name, d.deleted_at, d.subject_id,
                   sub.name AS subject_name,
                   fol.name AS folder_name,
                   sess.name AS session_name,
                   'document' AS kind,
                   0 AS extra
            FROM documents d
            JOIN subjects sub ON sub.id = d.subject_id
            LEFT JOIN sessions sess ON sess.id = d.session_id
            LEFT JOIN folders fol ON fol.id = COALESCE(
                d.folder_id, sess.folder_id
            )
            WHERE d.deleted_at IS NOT NULL
              AND sub.deleted_at IS NULL
              AND (d.session_id IS NULL OR sess.deleted_at IS NULL)
              AND (fol.id IS NULL OR fol.deleted_at IS NULL)
            """
        ).fetchall():
            items.append(dict(r))
        items.sort(key=lambda x: x["deleted_at"] or "", reverse=True)
        return items

    def trash_image_files(self) -> list:
        rows = self.conn.execute(
            """
            SELECT m.content FROM messages m
            JOIN sessions s ON s.id = m.session_id
            WHERE s.deleted_at IS NOT NULL AND m.kind = 'image'
            """
        ).fetchall()
        return [r["content"] for r in rows]

    def empty_trash(self) -> list:
        images = self.trash_image_files()
        self.conn.execute("DELETE FROM mindmaps WHERE deleted_at IS NOT NULL")
        self.conn.execute("DELETE FROM documents WHERE deleted_at IS NOT NULL")
        self.conn.execute("DELETE FROM sessions WHERE deleted_at IS NOT NULL")
        self.conn.execute("DELETE FROM folders WHERE deleted_at IS NOT NULL")
        self.conn.execute("DELETE FROM subjects WHERE deleted_at IS NOT NULL")
        self.conn.commit()
        return images
