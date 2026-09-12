"""主窗口：课题树、会话树刷新与拖拽。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QInputDialog,
    QMenu,
    QMessageBox,
    QTreeWidgetItem,
)

from ui.widgets import (
    ROLE_CREATED,
    ROLE_ID,
    ROLE_KIND,
    ROLE_LABEL,
    ROLE_MATCH_COLOR,
    ROLE_UPDATED,
    MATCH_COLORS,
    MatchColorPopup,
    _ordered_insert,
)


class TreeMixin:
    # ---------- 会话与文件夹管理 ----------

    def current_session_id(self):
        return self._current_sid

    def current_subject_id(self):
        return self._current_subject_id

    def _expanded_folders_key(self):
        sid = self._current_subject_id
        if sid is None:
            return "expanded_folders"
        return f"expanded_folders_{sid}"

    def _init_subject_selection(self):
        subjects = self._db.list_subjects()
        if not subjects:
            self._current_subject_id = self._db.create_subject("未分组")
            return
        saved = self._settings.value("current_subject_id", type=int)
        ids = {s["id"] for s in subjects}
        if saved in ids:
            self._current_subject_id = saved
        else:
            self._current_subject_id = subjects[0]["id"]

    def _remember_subject_view(self):
        sid = self._current_subject_id
        if sid is None:
            return
        self._settings.setValue(f"subject_{sid}_session", self._current_sid or 0)
        self._settings.setValue(f"subject_{sid}_mindmap", self._current_mid or 0)
        self._settings.setValue(f"subject_{sid}_document", self._current_did or 0)
        self._settings.setValue(f"subject_{sid}_kind", self._current_kind)

    def _restore_subject_view(self, subject_id):
        kind = self._settings.value(f"subject_{subject_id}_kind", "session")
        sess = self._settings.value(f"subject_{subject_id}_session", type=int)
        mid = self._settings.value(f"subject_{subject_id}_mindmap", type=int)
        did = self._settings.value(f"subject_{subject_id}_document", type=int)
        if kind == "mindmap" and mid:
            return mid, "mindmap"
        if kind == "document" and did:
            return did, "document"
        if sess:
            return sess, "session"
        return None, "session"

    def reload_subjects(self, select_id=None):
        if select_id is None:
            select_id = self._current_subject_id
        self._loading_subjects = True
        self._subject_tree.clear()
        target = None
        for s in self._db.list_subjects():
            item = QTreeWidgetItem([f"{s['name']}（{s['count']}）"])
            item.setIcon(0, self._subject_icon)
            item.setData(0, ROLE_KIND, "subject")
            item.setData(0, ROLE_ID, s["id"])
            item.setToolTip(0, f"课题 · 创建于 {s['created_at']} · 拖动可调整顺序")
            item.setFlags(
                Qt.ItemIsEnabled
                | Qt.ItemIsSelectable
                | Qt.ItemIsDragEnabled
                | Qt.ItemIsDropEnabled
            )
            self._subject_tree.addTopLevelItem(item)
            if s["id"] == select_id:
                target = item
        if target is None:
            target = self._subject_tree.topLevelItem(0)
        if target is not None:
            self._subject_tree.setCurrentItem(target)
            self._current_subject_id = target.data(0, ROLE_ID)
            self._settings.setValue("current_subject_id", self._current_subject_id)
        self._loading_subjects = False
        self._fit_sidebars_to_oneline()

    def _on_subject_current_changed(self, current, _previous):
        if self._loading_subjects or current is None:
            return
        sid = current.data(0, ROLE_ID)
        if sid == self._current_subject_id:
            return
        self._remember_subject_view()
        self._exit_match_mode(silent=True)
        self._current_subject_id = sid
        self._settings.setValue("current_subject_id", sid)
        if self._search_mode:
            self._exit_search_mode()
        self._trash_mode = False
        select_id, select_kind = self._restore_subject_view(sid)
        self.reload_sessions(select_id=select_id, select_kind=select_kind)

    def _on_subject_double_clicked(self, item, _col):
        if item is None:
            return
        self.rename_subject(item.data(0, ROLE_ID))

    def _subject_menu(self, pos):
        item = self._subject_tree.itemAt(pos)
        menu = QMenu(self)
        menu.addAction("新建课题", self.new_subject)
        if item is not None:
            sid = item.data(0, ROLE_ID)
            self._subject_tree.setCurrentItem(item)
            menu.addAction("重命名课题", lambda: self.rename_subject(sid))
            menu.addSeparator()
            menu.addAction("删除课题", lambda: self.delete_subject(sid))
        menu.exec(self._subject_tree.mapToGlobal(pos))

    def new_subject(self):
        name, ok = QInputDialog.getText(
            self, "新建课题", "课题名称：", text="新课题"
        )
        if not ok or not name.strip():
            return
        sid = self._db.create_subject(name.strip())
        self._remember_subject_view()
        self._current_subject_id = sid
        self._settings.setValue("current_subject_id", sid)
        self._current_sid = None
        self._current_mid = None
        self._current_did = None
        self._current_kind = "session"
        self._exit_search_mode()
        self.reload_subjects(select_id=sid)
        self.reload_sessions(select_id=-1)

    def rename_subject(self, subject_id: int):
        subject = self._db.get_subject(subject_id)
        if subject is None:
            return
        name, ok = QInputDialog.getText(
            self, "重命名课题", "课题名称：", text=subject["name"]
        )
        if not ok or not name.strip():
            return
        self._db.rename_subject(subject_id, name.strip())
        self.reload_subjects(select_id=subject_id)

    def delete_subject(self, subject_id: int):
        subject = self._db.get_subject(subject_id)
        if subject is None:
            return
        if len(self._db.list_subjects()) <= 1:
            QMessageBox.information(
                self, "删除课题", "至少需要保留一个课题。"
            )
            return
        n_folders, n_sessions, n_messages = self._db.subject_stats(subject_id)
        ret = QMessageBox.question(
            self,
            "删除课题",
            f"确定把课题「{subject['name']}」及其中"
            f" {n_folders} 个文件夹、{n_sessions} 个会话、{n_messages} 条记录"
            "移入回收站吗？\n可稍后在回收站恢复。",
        )
        if ret != QMessageBox.Yes:
            return
        if not self._db.trash_subject(subject_id):
            QMessageBox.information(
                self, "删除课题", "至少需要保留一个课题。"
            )
            return
        self._current_sid = None
        self._current_mid = None
        self._current_did = None
        self._current_kind = "session"
        self._current_subject_id = None
        self._exit_search_mode()
        self.reload_subjects()
        self._ensure_session_exists()
        self.reload_sessions(select_id=-1)

    def move_folder_to_subject(self, folder_id: int, subject_id: int):
        folder = self._db.get_folder(folder_id)
        if folder is None or folder.get("subject_id") == subject_id:
            return
        self._db.move_folder(folder_id, subject_id)
        dest = self._db.get_subject(subject_id)
        name = dest["name"] if dest else ""
        self._status.setText(f"已将文件夹移到课题「{name}」")
        self.reload_subjects(select_id=self._current_subject_id)
        self.reload_sessions(select_id=-1)

    def move_session_to_subject(self, session_id: int, subject_id: int):
        self._db.move_session(session_id, None, subject_id=subject_id)
        dest = self._db.get_subject(subject_id)
        name = dest["name"] if dest else ""
        self._status.setText(f"已将会话移到课题「{name}」")
        self.reload_subjects(select_id=self._current_subject_id)
        self.reload_sessions(select_id=-1)

    def move_mindmap_to_subject(self, mindmap_id: int, subject_id: int):
        self._db.move_mindmap(
            mindmap_id, folder_id=None, session_id=None, subject_id=subject_id
        )
        dest = self._db.get_subject(subject_id)
        name = dest["name"] if dest else ""
        self._status.setText(f"已将思维导图移到课题「{name}」")
        self.reload_subjects(select_id=self._current_subject_id)
        self.reload_sessions(select_id=-1)

    def move_document_to_subject(self, document_id: int, subject_id: int):
        self._db.move_document(
            document_id, folder_id=None, session_id=None, subject_id=subject_id
        )
        dest = self._db.get_subject(subject_id)
        name = dest["name"] if dest else ""
        self._status.setText(f"已将文档移到课题「{name}」")
        self.reload_subjects(select_id=self._current_subject_id)
        self.reload_sessions(select_id=-1)

    def _iter_all_items(self):
        def walk(item):
            yield item
            for i in range(item.childCount()):
                yield from walk(item.child(i))

        for i in range(self._tree.topLevelItemCount()):
            yield from walk(self._tree.topLevelItem(i))

    def _iter_session_items(self):
        for item in self._iter_all_items():
            if item.data(0, ROLE_KIND) == "session":
                yield item

    def _make_session_item(self, s: dict) -> QTreeWidgetItem:
        item = QTreeWidgetItem([f"{s['name']}（{s['count']}）"])
        item.setIcon(0, self._chat_icon)
        item.setData(0, ROLE_KIND, "session")
        item.setData(0, ROLE_ID, s["id"])
        item.setData(0, ROLE_MATCH_COLOR, s.get("match_color") or "")
        item.setData(0, ROLE_CREATED, s.get("created_at") or "")
        item.setData(0, ROLE_UPDATED, s.get("updated_at") or s.get("created_at") or "")
        item.setFlags(
            Qt.ItemIsEnabled
            | Qt.ItemIsSelectable
            | Qt.ItemIsDragEnabled
            | Qt.ItemIsDropEnabled
        )
        return item

    def _make_mindmap_item(self, m: dict) -> QTreeWidgetItem:
        item = QTreeWidgetItem([m["name"]])
        item.setIcon(0, self._map_icon)
        item.setData(0, ROLE_KIND, "mindmap")
        item.setData(0, ROLE_ID, m["id"])
        item.setData(0, ROLE_CREATED, m.get("created_at") or "")
        item.setData(0, ROLE_UPDATED, m.get("updated_at") or m.get("created_at") or "")
        item.setFlags(
            Qt.ItemIsEnabled
            | Qt.ItemIsSelectable
            | Qt.ItemIsDragEnabled
            | Qt.ItemIsDropEnabled
        )
        return item

    def _make_doc_item(self, d: dict) -> QTreeWidgetItem:
        item = QTreeWidgetItem([d["name"]])
        item.setIcon(0, self._doc_icon)
        item.setData(0, ROLE_KIND, "document")
        item.setData(0, ROLE_ID, d["id"])
        item.setData(0, ROLE_CREATED, d.get("created_at") or "")
        item.setData(0, ROLE_UPDATED, d.get("updated_at") or d.get("created_at") or "")
        item.setFlags(
            Qt.ItemIsEnabled
            | Qt.ItemIsSelectable
            | Qt.ItemIsDragEnabled
            | Qt.ItemIsDropEnabled
        )
        return item

    def _attach_session_maps(self, sitem: QTreeWidgetItem, kids_by_session: dict):
        sid = sitem.data(0, ROLE_ID)
        for child in kids_by_session.get(sid, []):
            if child["kind"] == "document":
                sitem.addChild(self._make_doc_item(child))
            else:
                sitem.addChild(self._make_mindmap_item(child))

    def _expand_sessions_with_maps(self, folder_item=None):
        """会话必须先挂到树上再展开，否则 setExpanded 会被 Qt 丢掉。"""
        if folder_item is None:
            sessions = self._iter_session_items()
        else:
            sessions = [
                folder_item.child(i)
                for i in range(folder_item.childCount())
                if folder_item.child(i).data(0, ROLE_KIND) == "session"
            ]
        for item in sessions:
            if item.childCount():
                item.setExpanded(True)

    def reload_sessions(self, select_id=None, select_kind=None):
        if select_kind is None:
            select_kind = self._current_kind
        if select_id is None:
            if select_kind == "mindmap":
                select_id = self._current_mid
            elif select_kind == "document":
                select_id = self._current_did
            else:
                select_id = self._current_sid
        if select_id is None and select_kind not in ("mindmap", "document"):
            select_id = self._settings.value("current_session_id", type=int)

        raw = self._settings.value(self._expanded_folders_key(), None)
        if raw is None:
            raw = self._settings.value("expanded_folders", [])
        if isinstance(raw, str):
            raw = [raw]
        expanded_ids = {int(x) for x in raw} if raw else set()

        self._loading = True
        self._tree.clear()
        kids_by_session = {}
        for m in self._db.list_mindmaps(self._current_subject_id):
            if m["session_id"] is not None:
                kids_by_session.setdefault(m["session_id"], []).append(
                    dict(m, kind="mindmap")
                )
        for d in self._db.list_documents(self._current_subject_id):
            if d["session_id"] is not None:
                kids_by_session.setdefault(d["session_id"], []).append(
                    dict(d, kind="document")
                )
        for kids in kids_by_session.values():
            kids.sort(
                key=lambda x: (x.get("sort_order") or 0, -x["id"])
            )
        bold = QFont()
        bold.setBold(True)

        def add_session(parent, s):
            sitem = self._make_session_item(s)
            self._attach_session_maps(sitem, kids_by_session)
            if parent is None:
                self._tree.addTopLevelItem(sitem)
            else:
                parent.addChild(sitem)
            return sitem

        def add_mindmap(parent, m):
            item = self._make_mindmap_item(m)
            if parent is None:
                self._tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            return item

        def add_document(parent, d):
            item = self._make_doc_item(d)
            if parent is None:
                self._tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            return item

        def add_folder(f):
            label = f"{f['name']}（{f['count']}）"
            expanded = f["id"] in expanded_ids
            arrow = "\u25be" if expanded else "\u25b8"  # ▾ / ▸
            fitem = QTreeWidgetItem([f"{arrow}  {label}"])
            fitem.setIcon(0, self._folder_icon)
            fitem.setFont(0, bold)
            fitem.setData(0, ROLE_KIND, "folder")
            fitem.setData(0, ROLE_ID, f["id"])
            fitem.setData(0, ROLE_LABEL, label)
            fitem.setToolTip(0, "拖动可调整顺序 · 点选展开 · 右侧【匹配】可把对话用同色高亮")
            fitem.setFlags(
                Qt.ItemIsEnabled
                | Qt.ItemIsSelectable
                | Qt.ItemIsDragEnabled
                | Qt.ItemIsDropEnabled
            )
            self._tree.addTopLevelItem(fitem)
            for child in self._db.list_tree_items(
                self._current_subject_id, folder_id=f["id"]
            ):
                if child["kind"] == "session":
                    add_session(fitem, child)
                elif child["kind"] == "document":
                    add_document(fitem, child)
                else:
                    add_mindmap(fitem, child)
            fitem.setExpanded(expanded)
            return fitem

        for entry in self._db.list_tree_items(self._current_subject_id):
            if entry["kind"] == "folder":
                add_folder(entry)
            elif entry["kind"] == "session":
                add_session(None, entry)
            elif entry["kind"] == "document":
                add_document(None, entry)
            else:
                add_mindmap(None, entry)

        self._expand_sessions_with_maps()

        target = None
        if select_kind in ("mindmap", "document") and select_id is not None:
            for it in self._iter_all_items():
                if (
                    it.data(0, ROLE_KIND) == select_kind
                    and it.data(0, ROLE_ID) == select_id
                ):
                    target = it
                    break
        if target is None:
            for it in self._iter_session_items():
                if it.data(0, ROLE_ID) == select_id:
                    target = it
                    select_kind = "session"
                    break
        if target is None:
            target = next(self._iter_session_items(), None)
            select_kind = "session" if target is not None else select_kind
        if target is not None:
            if target.childCount():
                target.setExpanded(True)
            parent = target.parent()
            while parent is not None:
                parent.setExpanded(True)
                parent = parent.parent()
            self._tree.setCurrentItem(target)
            self._apply_tree_selection(target)
        else:
            self._current_sid = None
            self._current_mid = None
            self._current_did = None
            self._current_kind = "session"
        self._loading = False

        if self._current_sid is not None:
            self._settings.setValue("current_session_id", self._current_sid)
        if not self._search_mode:
            self._reload_main_view()
        self._fit_sidebars_to_oneline()

    def _exit_match_mode(self, silent=False):
        if self._tree.match_folder_id is None and not self._tree.match_selected:
            return
        self._tree.match_folder_id = None
        self._tree.match_selected = set()
        if self._match_popup is not None and self._match_popup.isVisible():
            self._match_popup.hide()
        self._tree.viewport().update()
        if not silent:
            self._status.setText("已退出匹配")

    def _on_match_clicked(self, folder_id, global_pos):
        if self._tree.match_folder_id == folder_id:
            if not self._tree.match_selected:
                self._exit_match_mode()
                return
            self._show_match_color_popup(global_pos)
            return
        self._enter_match_mode(folder_id)

    def _enter_match_mode(self, folder_id):
        item = self._find_tree_item("folder", folder_id)
        if item is None:
            return
        n = sum(
            1
            for i in range(item.childCount())
            if item.child(i).data(0, ROLE_KIND) == "session"
        )
        if n == 0:
            self._status.setText("这个文件夹里还没有对话可以匹配")
            return
        if self._match_popup is not None and self._match_popup.isVisible():
            self._match_popup.hide()
        self._tree.match_folder_id = folder_id
        self._tree.match_selected = set()
        if not item.isExpanded():
            item.setExpanded(True)
        self._expand_sessions_with_maps(item)
        self._tree.viewport().update()
        self._tree.setFocus()
        self._status.setText("正在匹配：点选要绑定的对话，再点【匹配】选择颜色")

    def _toggle_match_session(self, sid):
        sel = self._tree.match_selected
        if sid in sel:
            sel.discard(sid)
        else:
            sel.add(sid)
        n = len(sel)
        self._tree.viewport().update()
        self._status.setText(
            f"已选 {n} 个对话，再点【匹配】选择颜色"
            if n
            else "正在匹配：点选要绑定的对话，再点【匹配】选择颜色"
        )

    def _on_match_session_toggled(self, sid):
        self._toggle_match_session(sid)

    def _show_match_color_popup(self, global_pos):
        if self._match_popup is None:
            self._match_popup = MatchColorPopup(self)
            self._match_popup.color_picked.connect(self._apply_match_color)
        self._match_popup.popup_at(global_pos)

    def _apply_match_color(self, color):
        ids = list(self._tree.match_selected)
        if not ids:
            return
        self._db.set_sessions_match_color(ids, color)
        n = len(ids)
        self._exit_match_mode(silent=True)
        self.reload_sessions()
        if color is None:
            self._status.setText(f"已清除 {n} 个对话的匹配颜色")
        else:
            name = MATCH_COLORS.get(color, {}).get("name", color)
            self._status.setText(f"已用{name}绑定 {n} 个对话")

    def _clear_session_match(self, session_id):
        self._db.set_sessions_match_color([session_id], None)
        self.reload_sessions(select_id=session_id, select_kind="session")
        self._status.setText("已取消该对话的颜色匹配")

    def _apply_tree_selection(self, item):
        kind = item.data(0, ROLE_KIND)
        iid = item.data(0, ROLE_ID)
        if kind == "session":
            self._current_kind = "session"
            self._current_sid = iid
            self._current_mid = None
            self._current_did = None
            self._settings.setValue("current_session_id", iid)
        elif kind == "mindmap":
            self._current_kind = "mindmap"
            self._current_mid = iid
            self._current_did = None
            mmap = self._db.get_mindmap(iid)
            if mmap and mmap["session_id"] is not None:
                self._current_sid = mmap["session_id"]
                self._settings.setValue("current_session_id", self._current_sid)
        elif kind == "document":
            self._current_kind = "document"
            self._current_did = iid
            self._current_mid = None
            doc = self._db.get_document(iid)
            if doc and doc["session_id"] is not None:
                self._current_sid = doc["session_id"]
                self._settings.setValue("current_session_id", self._current_sid)

    def _on_tree_current_changed(self, current, _previous):
        """用户点击会话 / 导图节点时触发（程序化刷新被 _loading 挡住）。"""
        if self._loading or current is None:
            return
        if self._tree.match_folder_id is not None:
            kind = current.data(0, ROLE_KIND)
            if kind == "session":
                parent = current.parent()
                if (
                    parent is not None
                    and parent.data(0, ROLE_KIND) == "folder"
                    and parent.data(0, ROLE_ID) == self._tree.match_folder_id
                ):
                    return
            self._exit_match_mode(silent=True)
        kind = current.data(0, ROLE_KIND)
        if kind not in ("session", "mindmap", "document"):
            return
        if self._search_mode:
            self._exit_search_mode()
        self._trash_mode = False
        self._apply_tree_selection(current)
        if kind == "session" and current.childCount():
            current.setExpanded(True)
        self._reload_main_view()

    def _on_tree_clicked(self, item, _col):
        if self._tree.match_folder_id is not None:
            kind = item.data(0, ROLE_KIND)
            if kind == "session":
                parent = item.parent()
                if (
                    parent is not None
                    and parent.data(0, ROLE_KIND) == "folder"
                    and parent.data(0, ROLE_ID) == self._tree.match_folder_id
                ):
                    return
                self._exit_match_mode(silent=True)
            elif kind in ("mindmap", "document"):
                self._exit_match_mode(silent=True)
        kind = item.data(0, ROLE_KIND)
        if self._trash_mode and kind in ("session", "mindmap", "document"):
            self._trash_mode = False
            self._apply_tree_selection(item)
            self._reload_main_view()
            return
        if kind != "folder":
            return
        if item.childCount() == 0:
            self._status.setText(
                "这个文件夹还是空的：右键在此新建会话、思维导图或文档，或把条目拖进来"
            )
            return
        collapsing = item.isExpanded()
        item.setExpanded(not collapsing)
        if collapsing:
            # 选中态若还在子项上，Qt 会立刻把文件夹再展开
            return
        self._expand_sessions_with_maps(item)
        if self._current_content_is_under(item):
            self._reselect_current_content()

    def _find_current_content_item(self):
        if self._current_kind == "mindmap" and self._current_mid is not None:
            return self._find_tree_item("mindmap", self._current_mid)
        if self._current_kind == "document" and self._current_did is not None:
            return self._find_tree_item("document", self._current_did)
        if self._current_sid is not None:
            return self._find_tree_item("session", self._current_sid)
        return None

    def _current_content_is_under(self, folder_item) -> bool:
        target = self._find_current_content_item()
        cur = target
        while cur is not None:
            if cur is folder_item:
                return True
            cur = cur.parent()
        return False

    def _reselect_current_content(self):
        """点文件夹只展开/收起，把选中态还回当前会话、导图或文档。"""
        target = self._find_current_content_item()
        if target is None:
            return
        self._loading = True
        self._tree.setCurrentItem(target)
        self._loading = False

    def _on_tree_double_clicked(self, item, _col):
        kind = item.data(0, ROLE_KIND)
        if kind == "folder":
            self.rename_folder(item.data(0, ROLE_ID))
        elif kind == "session":
            self.rename_session(item.data(0, ROLE_ID))
        elif kind == "mindmap":
            self.rename_mindmap(item.data(0, ROLE_ID))
        elif kind == "document":
            self.rename_document(item.data(0, ROLE_ID))

    def _on_folder_toggled(self, item):
        """展开/收起时更新箭头文字，并持久化展开状态。"""
        if item.data(0, ROLE_KIND) == "folder":
            arrow = "\u25be" if item.isExpanded() else "\u25b8"
            item.setText(0, f"{arrow}  {item.data(0, ROLE_LABEL)}")
            if item.isExpanded() and not self._loading:
                self._expand_sessions_with_maps(item)
        self._save_expanded_state()

    def _find_tree_item(self, kind, iid):
        if kind is None or iid is None:
            return None
        for it in self._iter_all_items():
            if it.data(0, ROLE_KIND) == kind and it.data(0, ROLE_ID) == iid:
                return it
        return None

    def _move_entry_to(self, kind, iid, folder_id=None, session_id=None):
        if kind == "session":
            sess = self._db.get_session(iid)
            if sess and sess.get("folder_id") == folder_id:
                return
            self._db.move_session(iid, folder_id)
        elif kind == "mindmap":
            mmap = self._db.get_mindmap(iid)
            if (
                mmap
                and mmap.get("folder_id") == folder_id
                and mmap.get("session_id") == session_id
            ):
                return
            self._db.move_mindmap(
                iid, folder_id=folder_id, session_id=session_id
            )
        elif kind == "document":
            doc = self._db.get_document(iid)
            if (
                doc
                and doc.get("folder_id") == folder_id
                and doc.get("session_id") == session_id
            ):
                return
            self._db.move_document(
                iid, folder_id=folder_id, session_id=session_id
            )

    def _apply_sibling_order(
        self, src_kind, src_id, dest_folder, dest_session, target_key, place
    ):
        siblings = self._db.list_tree_items(
            self._current_subject_id, dest_folder, dest_session
        )
        keys = [(x["kind"], x["id"]) for x in siblings]
        new_keys = _ordered_insert(
            keys, (src_kind, src_id), target_key, place
        )
        if new_keys != keys:
            self._db.reorder_tree_items(
                self._current_subject_id, new_keys, dest_folder, dest_session
            )

    def _on_entry_dropped(
        self, src_kind, src_id, target_kind, target_id, place
    ):
        src_key = (src_kind, src_id)
        if target_kind == src_kind and target_id == src_id:
            return
        insert_place = "below" if place == "on" else place

        if src_kind == "folder":
            target_item = self._find_tree_item(target_kind, target_id)
            target_key = None
            if target_item is not None:
                while target_item.parent() is not None:
                    target_item = target_item.parent()
                    insert_place = "below"
                target_key = (
                    target_item.data(0, ROLE_KIND),
                    target_item.data(0, ROLE_ID),
                )
            if target_key == (src_kind, src_id):
                return
            self._apply_sibling_order(
                src_kind, src_id, None, None, target_key, insert_place
            )
            self.reload_sessions()
            return

        if place == "on" and target_kind == "folder":
            self._move_entry_to(src_kind, src_id, folder_id=target_id)
            keys = [
                (x["kind"], x["id"])
                for x in self._db.list_tree_items(
                    self._current_subject_id, folder_id=target_id
                )
            ]
            keys = [k for k in keys if k != src_key]
            keys.insert(0, src_key)
            self._db.reorder_tree_items(
                self._current_subject_id, keys, folder_id=target_id
            )
            self.reload_sessions(select_id=src_id, select_kind=src_kind)
            return

        if place == "on" and target_kind == "session" and src_kind in (
            "mindmap",
            "document",
        ):
            self._move_entry_to(
                src_kind, src_id, folder_id=None, session_id=target_id
            )
            keys = [
                (x["kind"], x["id"])
                for x in self._db.list_tree_items(
                    self._current_subject_id, session_id=target_id
                )
            ]
            keys = [k for k in keys if k != src_key]
            keys.insert(0, src_key)
            self._db.reorder_tree_items(
                self._current_subject_id, keys, session_id=target_id
            )
            self.reload_sessions(select_id=src_id, select_kind=src_kind)
            return

        target_item = self._find_tree_item(target_kind, target_id)
        dest_folder = None
        dest_session = None
        target_key = None
        if target_item is None:
            insert_place = "below"
        else:
            parent = target_item.parent()
            target_key = (target_kind, target_id)
            if parent is None:
                dest_folder = None
            elif parent.data(0, ROLE_KIND) == "folder":
                dest_folder = parent.data(0, ROLE_ID)
            elif parent.data(0, ROLE_KIND) == "session":
                if src_kind == "session":
                    dest_folder = self._item_folder_id(parent)
                    target_key = ("session", parent.data(0, ROLE_ID))
                    insert_place = "below"
                else:
                    dest_session = parent.data(0, ROLE_ID)

        self._move_entry_to(
            src_kind, src_id, folder_id=dest_folder, session_id=dest_session
        )
        self._apply_sibling_order(
            src_kind,
            src_id,
            dest_folder,
            dest_session,
            target_key,
            insert_place,
        )
        self.reload_sessions(select_id=src_id, select_kind=src_kind)

    def _on_subject_dropped(self, subject_id: int, target_id, place: str):
        subjects = self._db.list_subjects()
        ids = [s["id"] for s in subjects]
        new_ids = _ordered_insert(ids, subject_id, target_id, place)
        if new_ids == ids:
            return
        self._db.reorder_subjects(new_ids)
        self.reload_subjects(select_id=subject_id)

    def _save_expanded_state(self, *_):
        if self._loading:
            return
        ids = []
        for i in range(self._tree.topLevelItemCount()):
            top = self._tree.topLevelItem(i)
            if top.data(0, ROLE_KIND) == "folder" and top.isExpanded():
                ids.append(str(top.data(0, ROLE_ID)))
        self._settings.setValue(self._expanded_folders_key(), ids)

