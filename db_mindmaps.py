"""SQLite 思维导图相关方法，作为 Database 的 Mixin。"""

from db import _now


class MindmapMixin:
    # ---------- 思维导图 ----------

    def create_mindmap(
        self, name: str, folder_id=None, session_id=None, subject_id=None
    ) -> int:
        subject_id = self._resolve_subject_id(
            folder_id=folder_id, session_id=session_id, subject_id=subject_id
        )
        order = self._mixed_front_sort(
            subject_id, folder_id=folder_id, session_id=session_id
        )
        cur = self.conn.execute(
            "INSERT INTO mindmaps"
            " (name, created_at, folder_id, session_id, subject_id, sort_order)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (name, _now(), folder_id, session_id, subject_id, order),
        )
        mid = cur.lastrowid
        self.conn.execute(
            "INSERT INTO mindmap_nodes"
            " (mindmap_id, parent_id, kind, content, sort_order)"
            " VALUES (?, NULL, 'box', ?, 0)",
            (mid, name),
        )
        self.conn.commit()
        return mid

    def list_mindmaps(self, subject_id=None) -> list:
        sql = """
            SELECT id, name, created_at, folder_id, session_id, subject_id,
                   sort_order
            FROM mindmaps
            WHERE deleted_at IS NULL
        """
        params = []
        if subject_id is not None:
            sql += " AND subject_id = ?"
            params.append(subject_id)
        sql += " ORDER BY sort_order ASC, id DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_mindmap(self, mindmap_id: int):
        row = self.conn.execute(
            "SELECT id, name, created_at, folder_id, session_id, subject_id,"
            " deleted_at FROM mindmaps WHERE id = ?",
            (mindmap_id,),
        ).fetchone()
        return dict(row) if row else None

    def rename_mindmap(self, mindmap_id: int, name: str):
        old = self.get_mindmap(mindmap_id)
        self.conn.execute(
            "UPDATE mindmaps SET name = ? WHERE id = ?", (name, mindmap_id)
        )
        if old and old["name"] != name:
            root = self.conn.execute(
                "SELECT id, content FROM mindmap_nodes"
                " WHERE mindmap_id = ? AND parent_id IS NULL",
                (mindmap_id,),
            ).fetchone()
            if root is not None and root["content"] == old["name"]:
                self.conn.execute(
                    "UPDATE mindmap_nodes SET content = ? WHERE id = ?",
                    (name, root["id"]),
                )
        self.conn.commit()

    def delete_mindmap(self, mindmap_id: int):
        self.conn.execute("DELETE FROM mindmaps WHERE id = ?", (mindmap_id,))
        self.conn.commit()

    def move_mindmap(
        self, mindmap_id: int, folder_id=None, session_id=None, subject_id=None
    ):
        """移到某文件夹或根目录；session_id 为 None 表示不再挂在会话下。"""
        subject_id = self._resolve_subject_id(
            folder_id=folder_id, session_id=session_id, subject_id=subject_id
        )
        order = self._mixed_front_sort(
            subject_id, folder_id=folder_id, session_id=session_id
        )
        self.conn.execute(
            "UPDATE mindmaps"
            " SET folder_id = ?, session_id = ?, subject_id = ?, sort_order = ?"
            " WHERE id = ?",
            (folder_id, session_id, subject_id, order, mindmap_id),
        )
        self.conn.commit()

    def copy_mindmap(
        self,
        mindmap_id: int,
        folder_id=None,
        session_id=None,
        as_copy: bool = True,
        commit: bool = True,
        subject_id=None,
    ) -> int:
        src = self.get_mindmap(mindmap_id)
        if src is None:
            return 0
        name = self._copy_title(src["name"]) if as_copy else src["name"]
        subject_id = self._resolve_subject_id(
            folder_id=folder_id, session_id=session_id, subject_id=subject_id
        )
        order = self._mixed_front_sort(
            subject_id, folder_id=folder_id, session_id=session_id
        )
        cur = self.conn.execute(
            "INSERT INTO mindmaps"
            " (name, created_at, folder_id, session_id, subject_id, sort_order)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (name, _now(), folder_id, session_id, subject_id, order),
        )
        new_mid = cur.lastrowid
        nodes = self.get_mindmap_nodes(mindmap_id)
        id_map = {}
        for n in nodes:
            cur = self.conn.execute(
                "INSERT INTO mindmap_nodes"
                " (mindmap_id, parent_id, kind, content, sort_order,"
                " pos_x, pos_y, edge_label, highlighted, box_w, box_h)"
                " VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_mid,
                    n["kind"],
                    n["content"],
                    n["sort_order"],
                    n.get("pos_x"),
                    n.get("pos_y"),
                    n.get("edge_label") or "",
                    1 if n.get("highlighted") else 0,
                    n.get("box_w"),
                    n.get("box_h"),
                ),
            )
            id_map[n["id"]] = cur.lastrowid
        for n in nodes:
            pid = n["parent_id"]
            if pid is None:
                continue
            new_parent = id_map.get(pid)
            if new_parent is None:
                continue
            self.conn.execute(
                "UPDATE mindmap_nodes SET parent_id = ? WHERE id = ?",
                (new_parent, id_map[n["id"]]),
            )
        for e in self.list_mindmap_edges(mindmap_id):
            a = id_map.get(e["from_id"])
            b = id_map.get(e["to_id"])
            if a and b:
                self._insert_edge(new_mid, a, b, e.get("label") or "")
        if commit:
            self.conn.commit()
        return new_mid

    def get_mindmap_nodes(self, mindmap_id: int) -> list:
        rows = self.conn.execute(
            """
            SELECT id, mindmap_id, parent_id, kind, content, sort_order,
                   pos_x, pos_y, edge_label, highlighted, box_w, box_h
            FROM mindmap_nodes WHERE mindmap_id = ?
            ORDER BY sort_order, id
            """,
            (mindmap_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_mindmap_node(self, node_id: int):
        row = self.conn.execute(
            "SELECT id, mindmap_id, parent_id, kind, content, sort_order,"
            " pos_x, pos_y, edge_label, highlighted, box_w, box_h"
            " FROM mindmap_nodes WHERE id = ?",
            (node_id,),
        ).fetchone()
        return dict(row) if row else None

    def is_mindmap_root(self, node) -> bool:
        """最初那个中心框（同图里无父节点且 id 最小）。"""
        if not node or node["parent_id"] is not None:
            return False
        row = self.conn.execute(
            "SELECT MIN(id) AS i FROM mindmap_nodes"
            " WHERE mindmap_id = ? AND parent_id IS NULL",
            (node["mindmap_id"],),
        ).fetchone()
        return bool(row and row["i"] == node["id"])

    def add_mindmap_node(
        self, mindmap_id: int, parent_id, kind: str, content: str,
        pos_x=None, pos_y=None,
    ) -> int:
        if parent_id is None:
            row = self.conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) AS m FROM mindmap_nodes"
                " WHERE mindmap_id = ? AND parent_id IS NULL",
                (mindmap_id,),
            ).fetchone()
            nxt = int(row["m"]) + 1
            px, py = pos_x, pos_y
        else:
            row = self.conn.execute(
                "SELECT COALESCE(MAX(sort_order), -1) AS m FROM mindmap_nodes"
                " WHERE parent_id = ?",
                (parent_id,),
            ).fetchone()
            nxt = int(row["m"]) + 1
            parent = self.get_mindmap_node(parent_id)
            px, py = pos_x, pos_y
            if px is None and parent is not None and parent.get("pos_x") is not None:
                pw = 230 if parent["kind"] == "text" else 168
                ph = 40 if kind == "text" else 46
                sibs = self.conn.execute(
                    "SELECT COUNT(*) AS c FROM mindmap_nodes WHERE parent_id = ?",
                    (parent_id,),
                ).fetchone()["c"]
                px = float(parent["pos_x"]) + pw + 56
                py = float(parent["pos_y"]) + sibs * (ph + 18)
        cur = self.conn.execute(
            "INSERT INTO mindmap_nodes"
            " (mindmap_id, parent_id, kind, content, sort_order, pos_x, pos_y)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (mindmap_id, parent_id, kind, content, nxt, px, py),
        )
        new_id = cur.lastrowid
        if parent_id is not None:
            self._insert_edge(mindmap_id, parent_id, new_id, "")
        self.conn.commit()
        return new_id

    def list_mindmap_edges(self, mindmap_id: int) -> list:
        rows = self.conn.execute(
            """
            SELECT id, mindmap_id, from_id, to_id, label
            FROM mindmap_edges WHERE mindmap_id = ?
            ORDER BY id
            """,
            (mindmap_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_mindmap_edge(self, edge_id: int):
        row = self.conn.execute(
            "SELECT id, mindmap_id, from_id, to_id, label"
            " FROM mindmap_edges WHERE id = ?",
            (edge_id,),
        ).fetchone()
        return dict(row) if row else None

    def delete_mindmap_edge(self, edge_id: int):
        """只删连线，两端节点都保留；若这是唯一入边，目标节点变为独立单元。"""
        edge = self.get_mindmap_edge(edge_id)
        if edge is None:
            return
        to_id = edge["to_id"]
        self.conn.execute("DELETE FROM mindmap_edges WHERE id = ?", (edge_id,))
        self._refresh_primary_parent(to_id)
        self.conn.commit()

    def _insert_edge(self, mindmap_id: int, from_id: int, to_id: int, label: str = ""):
        self.conn.execute(
            "INSERT OR IGNORE INTO mindmap_edges"
            " (mindmap_id, from_id, to_id, label) VALUES (?, ?, ?, ?)",
            (mindmap_id, from_id, to_id, label),
        )

    def _refresh_primary_parent(self, node_id: int):
        node = self.get_mindmap_node(node_id)
        if node is None:
            return
        rows = self.conn.execute(
            "SELECT from_id FROM mindmap_edges WHERE to_id = ? ORDER BY id",
            (node_id,),
        ).fetchall()
        incoming = [r["from_id"] for r in rows]
        if not incoming:
            self.conn.execute(
                "UPDATE mindmap_nodes SET parent_id = NULL WHERE id = ?",
                (node_id,),
            )
            return
        if node["parent_id"] in incoming:
            return
        self.conn.execute(
            "UPDATE mindmap_nodes SET parent_id = ?, sort_order = ?"
            " WHERE id = ?",
            (incoming[0], self._next_child_sort(incoming[0]), node_id),
        )

    def add_mindmap_edge(self, from_id: int, to_id: int) -> str:
        """新增一条连线，不拆掉已有连线。"""
        a = self.get_mindmap_node(from_id)
        b = self.get_mindmap_node(to_id)
        if a is None or b is None:
            return "找不到单元"
        if a["mindmap_id"] != b["mindmap_id"]:
            return "不能连到其他导图"
        if from_id == to_id:
            return "不能连到自己"
        existed = self.conn.execute(
            "SELECT id FROM mindmap_edges WHERE from_id = ? AND to_id = ?",
            (from_id, to_id),
        ).fetchone()
        if existed:
            return "noop"
        self._insert_edge(a["mindmap_id"], from_id, to_id, "")
        if b["parent_id"] is None and not self.is_mindmap_root(b):
            self.conn.execute(
                "UPDATE mindmap_nodes SET parent_id = ?, sort_order = ?"
                " WHERE id = ?",
                (from_id, self._next_child_sort(from_id), to_id),
            )
        self.conn.commit()
        return ""

    def insert_mindmap_node_on_edge(self, edge_id: int, kind: str) -> int:
        """在指定连线中间插入一个新节点。"""
        edge = self.get_mindmap_edge(edge_id)
        if edge is None:
            return 0
        parent = self.get_mindmap_node(edge["from_id"])
        child = self.get_mindmap_node(edge["to_id"])
        if parent is None or child is None:
            return 0
        nw, nh = (230, 40) if kind == "text" else (168, 46)
        px = py = None
        if (
            parent.get("pos_x") is not None
            and child.get("pos_x") is not None
        ):
            pw = 230 if parent["kind"] == "text" else 168
            ph = 46 if parent["kind"] != "text" else 40
            ch = 46 if child["kind"] != "text" else 40
            x1 = float(parent["pos_x"]) + pw
            y1 = float(parent["pos_y"]) + ph / 2
            x2 = float(child["pos_x"])
            y2 = float(child["pos_y"]) + ch / 2
            px = (x1 + x2) / 2 - nw / 2
            py = (y1 + y2) / 2 - nh / 2
        cur = self.conn.execute(
            "INSERT INTO mindmap_nodes"
            " (mindmap_id, parent_id, kind, content, sort_order, pos_x, pos_y)"
            " VALUES (?, ?, ?, '', ?, ?, ?)",
            (
                child["mindmap_id"],
                parent["id"],
                kind,
                child["sort_order"],
                px,
                py,
            ),
        )
        new_id = cur.lastrowid
        self.conn.execute("DELETE FROM mindmap_edges WHERE id = ?", (edge_id,))
        self._insert_edge(child["mindmap_id"], parent["id"], new_id, "")
        self._insert_edge(
            child["mindmap_id"], new_id, child["id"], edge.get("label") or ""
        )
        if child["parent_id"] == parent["id"]:
            self.conn.execute(
                "UPDATE mindmap_nodes SET parent_id = ?, sort_order = 0"
                " WHERE id = ?",
                (new_id, child["id"]),
            )
        self.conn.commit()
        return new_id

    def update_edge_label(self, edge_id: int, text: str):
        self.conn.execute(
            "UPDATE mindmap_edges SET label = ? WHERE id = ?",
            (text, edge_id),
        )
        self.conn.commit()

    def toggle_mindmap_highlight(self, node_id: int) -> bool:
        node = self.get_mindmap_node(node_id)
        if node is None:
            return False
        nxt = 0 if node.get("highlighted") else 1
        self.conn.execute(
            "UPDATE mindmap_nodes SET highlighted = ? WHERE id = ?",
            (nxt, node_id),
        )
        self.conn.commit()
        return bool(nxt)

    def set_mindmap_positions(self, items: list):
        for it in items:
            self.conn.execute(
                "UPDATE mindmap_nodes SET pos_x = ?, pos_y = ? WHERE id = ?",
                (it["x"], it["y"], it["id"]),
            )
        self.conn.commit()

    def set_mindmap_box(self, node_id: int, x, y, w, h):
        self.conn.execute(
            "UPDATE mindmap_nodes"
            " SET pos_x = ?, pos_y = ?, box_w = ?, box_h = ? WHERE id = ?",
            (x, y, w, h, node_id),
        )
        self.conn.commit()

    def _next_child_sort(self, parent_id: int) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) AS m FROM mindmap_nodes"
            " WHERE parent_id = ?",
            (parent_id,),
        ).fetchone()
        return int(row["m"]) + 1

    def _is_ancestor(self, maybe_anc: int, node_id: int, by_id: dict) -> bool:
        cur = node_id
        seen = set()
        while cur is not None:
            if cur == maybe_anc:
                return True
            if cur in seen:
                return True
            seen.add(cur)
            node = by_id.get(cur)
            cur = node["parent_id"] if node else None
        return False

    def relink_mindmap_edge(self, edge_id: int, end: str, target_id: int) -> str:
        """改指定连线的一端，其它连线保持不动。"""
        edge = self.get_mindmap_edge(edge_id)
        target = self.get_mindmap_node(target_id)
        if edge is None or target is None:
            return "找不到单元"
        if target["mindmap_id"] != edge["mindmap_id"]:
            return "不能连到其他导图"
        new_from = target_id if end == "from" else edge["from_id"]
        new_to = target_id if end == "to" else edge["to_id"]
        if new_from == new_to:
            return "不能连到自己"
        if new_from == edge["from_id"] and new_to == edge["to_id"]:
            return "noop"
        dup = self.conn.execute(
            "SELECT id FROM mindmap_edges WHERE from_id = ? AND to_id = ?"
            " AND id != ?",
            (new_from, new_to, edge_id),
        ).fetchone()
        if dup:
            return "这两点之间已经有连线了"
        old_to = edge["to_id"]
        self.conn.execute(
            "UPDATE mindmap_edges SET from_id = ?, to_id = ? WHERE id = ?",
            (new_from, new_to, edge_id),
        )
        self._refresh_primary_parent(old_to)
        self._refresh_primary_parent(new_to)
        self.conn.commit()
        return ""

    def update_mindmap_node(self, node_id: int, content: str):
        self.conn.execute(
            "UPDATE mindmap_nodes SET content = ? WHERE id = ?",
            (content, node_id),
        )
        node = self.get_mindmap_node(node_id)
        if node and self.is_mindmap_root(node):
            self.conn.execute(
                "UPDATE mindmaps SET name = ? WHERE id = ?",
                (content.strip() or "思维导图", node["mindmap_id"]),
            )
        self.conn.commit()

    def delete_mindmap_node_keep_children(self, node_id: int):
        """只删该节点，子节点接到它的父节点上。"""
        node = self.get_mindmap_node(node_id)
        if node is None or self.is_mindmap_root(node):
            return
        parent_id = node["parent_id"]
        sort = node["sort_order"]
        kids = self.conn.execute(
            "SELECT id FROM mindmap_nodes WHERE parent_id = ?"
            " ORDER BY sort_order, id",
            (node_id,),
        ).fetchall()
        extra = len(kids)
        if extra:
            if parent_id is None:
                for kid in kids:
                    self.conn.execute(
                        "UPDATE mindmap_nodes SET parent_id = NULL WHERE id = ?",
                        (kid["id"],),
                    )
            else:
                self.conn.execute(
                    "UPDATE mindmap_nodes SET sort_order = sort_order + ?"
                    " WHERE parent_id = ? AND sort_order > ?",
                    (extra, parent_id, sort),
                )
                for i, kid in enumerate(kids):
                    self.conn.execute(
                        "UPDATE mindmap_nodes SET parent_id = ?, sort_order = ?"
                        " WHERE id = ?",
                        (parent_id, sort + i, kid["id"]),
                    )
        incoming = self.conn.execute(
            "SELECT from_id FROM mindmap_edges WHERE to_id = ?", (node_id,)
        ).fetchall()
        outgoing = self.conn.execute(
            "SELECT to_id, label FROM mindmap_edges WHERE from_id = ?",
            (node_id,),
        ).fetchall()
        for inn in incoming:
            for out in outgoing:
                self._insert_edge(
                    node["mindmap_id"], inn["from_id"], out["to_id"], out["label"]
                )
        self.conn.execute("DELETE FROM mindmap_nodes WHERE id = ?", (node_id,))
        self.conn.commit()

    def delete_mindmap_node(self, node_id: int):
        kids = self.conn.execute(
            "SELECT id FROM mindmap_nodes WHERE parent_id = ?", (node_id,)
        ).fetchall()
        for kid in kids:
            self.delete_mindmap_node(kid["id"])
        self.conn.execute("DELETE FROM mindmap_nodes WHERE id = ?", (node_id,))
        self.conn.commit()

