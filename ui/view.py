"""主窗口：聊天页、思维导图、搜索与 app:// 动作。"""

import json
import os

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

import autostart
import render
import render_doc
from db import DATA_DIR, IMAGES_DIR
from ui.widgets import SettingsDialog

VIEW_PATH = os.path.join(DATA_DIR, "view.html")


class ViewMixin:
    # ---------- 聊天视图 ----------

    def _reload_main_view(self):
        if self._trash_mode:
            self.reload_trash()
            return
        if self._current_kind == "mindmap" and self._current_mid is not None:
            self.reload_mindmap()
        elif self._current_kind == "document" and self._current_did is not None:
            self.reload_document()
        else:
            self.reload_chat()

    def open_trash(self):
        self._search_mode = False
        self._search.blockSignals(True)
        self._search.clear()
        self._search.blockSignals(False)
        self._trash_mode = True
        self.reload_trash()

    def reload_trash(self):
        items = self._db.list_trash_items()
        self._write_and_load(render.build_trash_page(items))
        self._web.setContextMenuPolicy(Qt.DefaultContextMenu)
        self._status.setText(
            f"回收站 · {len(items)} 项 · 可恢复到原位置，或彻底删除"
        )

    def reload_chat(self):
        sid = self.current_session_id()
        if sid is None:
            self._write_and_load("<html><body></body></html>")
            self._status.setText("请先新建一个会话")
            return
        session = self._db.get_session(sid)
        messages = self._db.get_messages(sid)
        self._write_and_load(render.build_chat_page(session, messages))
        self._web.setContextMenuPolicy(Qt.DefaultContextMenu)
        self._status.setText(
            f"会话「{session['name']}」 · {len(messages)} 条记录"
            " · 复制文字后点悬浮条即可记录，关闭窗口将最小化到托盘"
        )

    def reload_mindmap(self):
        mid = self._current_mid
        mmap = self._db.get_mindmap(mid) if mid is not None else None
        if mmap is None:
            self._current_kind = "session"
            self._current_mid = None
            self.reload_chat()
            return
        nodes = self._db.get_mindmap_nodes(mid)
        edges = self._db.list_mindmap_edges(mid)
        try:
            page, to_save = render.build_mindmap_page(
                mmap, nodes, self._mm_view.get(mid), edges
            )
        except Exception as e:
            self._status.setText(f"思维导图无法打开：{e}")
            return
        if to_save:
            self._db.set_mindmap_positions(to_save)
        self._write_and_load(page)
        self._web.setContextMenuPolicy(Qt.NoContextMenu)
        self._status.setText(
            f"思维导图「{mmap['name']}」 · {len(nodes)} 个节点"
            " · 中键拖动框选（框到的单元和连线都会选中，可一起拖动）"
            " · 拖动背景移动画面 · Ctrl+滚轮缩放"
        )

    def reload_document(self):
        did = self._current_did
        doc = self._db.get_document(did) if did is not None else None
        if doc is None:
            self._current_kind = "session"
            self._current_did = None
            self.reload_chat()
            return
        self._write_and_load(render_doc.build_document_page(doc))
        self._web.setContextMenuPolicy(Qt.DefaultContextMenu)
        self._status.setText(
            f"文档「{doc['name']}」 · 左侧 Markdown，右侧预览"
            " · 工具栏「markdown语法」可查看写法"
        )

    def _write_and_load(self, html: str):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(VIEW_PATH, "w", encoding="utf-8") as f:
            f.write(html)
        self._web.load(QUrl.fromLocalFile(VIEW_PATH))

    def notify_message_added(self):
        """悬浮条存入新消息后由入口层调用。

        reload_sessions 会重新选中当前会话并触发聊天视图刷新；
        搜索模式下只更新会话列表的计数，不打断搜索结果页。
        """
        self.reload_sessions()

    # ---------- 搜索 ----------

    def _do_search(self):
        keyword = self._search.text().strip()
        if not keyword:
            return
        self._trash_mode = False
        self._search_mode = True
        results = self._db.search(keyword)
        self._write_and_load(render.build_search_page(keyword, results))
        self._web.setContextMenuPolicy(Qt.DefaultContextMenu)
        self._status.setText(
            f"搜索「{keyword}」 · {len(results)} 条结果 · 清空搜索框返回会话"
        )

    def _on_search_text_changed(self, text: str):
        if not text.strip() and self._search_mode:
            self._search_mode = False
            self._reload_main_view()

    def _exit_search_mode(self):
        self._search_mode = False
        self._trash_mode = False
        self._search.blockSignals(True)
        self._search.clear()
        self._search.blockSignals(False)

    # ---------- 气泡上的操作链接 ----------

    def _handle_app_action(self, action: str, arg: str, extra: str = ""):
        if action == "blocked":
            self._status.setText("已拦截记录内容里指向外部文件的链接")
            return
        if action == "restore":
            self._restore_trash_item(arg, extra)
            return
        if action == "purge":
            self._purge_trash_item(arg, extra)
            return
        if action == "emptytrash":
            self._empty_trash()
            return
        if action == "goto":
            self._trash_mode = False
            self._exit_search_mode()
            target_sid = int(arg)
            sess = self._db.get_session(target_sid)
            if sess and sess.get("subject_id") not in (
                None,
                self._current_subject_id,
            ):
                self._remember_subject_view()
                self._current_subject_id = sess["subject_id"]
                self._settings.setValue(
                    "current_subject_id", self._current_subject_id
                )
                self.reload_subjects(select_id=self._current_subject_id)
            self.reload_sessions(select_id=target_sid, select_kind="session")
            return
        if action == "setcam":
            try:
                cam = json.loads(extra) if extra else {}
            except json.JSONDecodeError:
                return
            if self._current_mid is not None and isinstance(cam, dict):
                self._mm_view[self._current_mid] = {
                    "tx": float(cam.get("tx", 0)),
                    "ty": float(cam.get("ty", 0)),
                    "scale": float(cam.get("scale", 1)),
                }
            return
        if action == "savedoc":
            try:
                did = int(arg)
            except (TypeError, ValueError):
                return
            if self._current_did != did:
                return
            text = extra or ""
            self._db.update_document_content(did, text)
            preview = (
                render.md_to_html(text)
                if text.strip()
                else (
                    '<div class="empty">还没有内容，左边写 Markdown，右侧即时预览</div>'
                )
            )
            self._page.runJavaScript(render_doc.document_preview_js(preview))
            return
        if action in (
            "addbox", "addtext", "savenode", "delnode", "delone", "setpos",
            "setsize",
            "edgebox", "edgetext", "editedge", "deledge", "relink", "connect",
            "addfreebox", "addfreetext", "togglehl",
        ):
            nid = int(arg) if arg else 0
            self._handle_mindmap_action(action, nid, extra)
            return

        msg = self._db.get_message(int(arg))
        if msg is None:
            return
        if action == "copy":
            if self._suppress_cb:
                self._suppress_cb()
            if msg["kind"] == "image":
                path = os.path.join(IMAGES_DIR, msg["content"])
                QApplication.clipboard().setImage(QImage(path))
                self._status.setText("已复制图片到剪贴板")
            else:
                QApplication.clipboard().setText(msg["content"])
                self._status.setText("已复制原文到剪贴板")
        elif action == "flip":
            self._db.flip_role(int(arg))
            self.reload_chat()
        elif action == "del":
            ret = QMessageBox.question(self, "删除记录", "确定删除这条记录吗？")
            if ret == QMessageBox.Yes:
                if msg["kind"] == "image":
                    try:
                        os.remove(os.path.join(IMAGES_DIR, msg["content"]))
                    except OSError:
                        pass
                self._db.delete_message(int(arg))
                self.reload_sessions(select_id=msg["session_id"])

    def _handle_mindmap_action(self, action: str, node_id: int, extra: str = ""):
        if action == "setpos":
            try:
                items = json.loads(extra) if extra else []
            except json.JSONDecodeError:
                return
            if items:
                self._db.set_mindmap_positions(items)
            return
        if action == "setsize":
            try:
                box = json.loads(extra) if extra else {}
                self._db.set_mindmap_box(
                    node_id,
                    float(box["x"]),
                    float(box["y"]),
                    float(box["w"]),
                    float(box["h"]),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return
            return
        if action in ("addfreebox", "addfreetext"):
            if self._current_mid is None:
                return
            try:
                pos = json.loads(extra) if extra else {}
                x = float(pos.get("x", 80))
                y = float(pos.get("y", 80))
            except (TypeError, ValueError, json.JSONDecodeError):
                x, y = 80.0, 80.0
            kind = "box" if action == "addfreebox" else "text"
            self._db.add_mindmap_node(
                self._current_mid, None, kind, "", x, y
            )
            self.reload_mindmap()
            return
        if action in ("edgebox", "edgetext", "editedge", "relink", "deledge"):
            edge = self._db.get_mindmap_edge(node_id)
            if edge is None:
                return
            if action == "edgebox":
                self._db.insert_mindmap_node_on_edge(node_id, "box")
            elif action == "edgetext":
                self._db.insert_mindmap_node_on_edge(node_id, "text")
            elif action == "editedge":
                text, ok = QInputDialog.getText(
                    self,
                    "编辑连线标注",
                    "两端单元的关系：",
                    text=edge.get("label") or "",
                )
                if not ok:
                    return
                self._db.update_edge_label(node_id, text)
                self.reload_mindmap()
                return
            elif action == "deledge":
                ret = QMessageBox.question(
                    self,
                    "删除连线",
                    "确定删除这两个单元之间的连线吗？单元本身会保留。",
                )
                if ret != QMessageBox.Yes:
                    return
                self._db.delete_mindmap_edge(node_id)
                self.reload_mindmap()
                return
            elif action == "relink":
                try:
                    payload = json.loads(extra) if extra else {}
                    target_id = int(payload.get("target"))
                    end = str(payload.get("end") or "")
                except (TypeError, ValueError, json.JSONDecodeError):
                    return
                msg = self._db.relink_mindmap_edge(node_id, end, target_id)
                if msg == "noop":
                    return
                if msg:
                    self._status.setText(msg)
                    return
                self.reload_mindmap()
                return
            self.reload_sessions(
                select_id=edge["mindmap_id"], select_kind="mindmap"
            )
            return
        node = self._db.get_mindmap_node(node_id)
        if node is None:
            return
        if action == "addbox":
            self._db.add_mindmap_node(node["mindmap_id"], node_id, "box", "")
        elif action == "addtext":
            self._db.add_mindmap_node(node["mindmap_id"], node_id, "text", "")
        elif action == "togglehl":
            self._db.toggle_mindmap_highlight(node_id)
            self.reload_mindmap()
            return
        elif action == "connect":
            try:
                payload = json.loads(extra) if extra else {}
                target_id = int(payload.get("target"))
                side = str(payload.get("side") or "")
            except (TypeError, ValueError, json.JSONDecodeError):
                return
            if side == "right":
                msg = self._db.add_mindmap_edge(node_id, target_id)
            elif side == "left":
                msg = self._db.add_mindmap_edge(target_id, node_id)
            else:
                return
            if msg == "noop":
                self._status.setText("这两点之间已经有连线了")
                return
            if msg:
                self._status.setText(msg)
                return
            self.reload_mindmap()
            return
        elif action == "savenode":
            self._db.update_mindmap_node(node_id, extra)
            if self._db.is_mindmap_root(node):
                self.reload_sessions(
                    select_id=node["mindmap_id"], select_kind="mindmap"
                )
            else:
                self.reload_mindmap()
            return
        elif action == "delone":
            if self._db.is_mindmap_root(node):
                self._status.setText("中心框请在左侧删除整张导图")
                return
            ret = QMessageBox.question(
                self,
                "只删除此单元",
                "只删除这个单元，它下面的节点会接到上一级。确定吗？",
            )
            if ret != QMessageBox.Yes:
                return
            self._db.delete_mindmap_node_keep_children(node_id)
        elif action == "delnode":
            if self._db.is_mindmap_root(node):
                self._status.setText("中心框请在左侧删除整张导图")
                return
            ret = QMessageBox.question(
                self, "删除此单元及后续", "确定删除这个节点以及它下面的全部分支吗？"
            )
            if ret != QMessageBox.Yes:
                return
            self._db.delete_mindmap_node(node_id)
        else:
            return
        self.reload_sessions(
            select_id=node["mindmap_id"], select_kind="mindmap"
        )

    # ---------- 其他 ----------

    def _parse_trash_target(self, arg: str, extra: str = ""):
        extra = (extra or "").strip()
        kinds = ("subject", "folder", "session", "mindmap", "document")
        if extra in kinds:
            try:
                return extra, int(arg)
            except ValueError:
                return None, 0
        parts = (arg or "").split("/")
        if len(parts) != 2:
            return None, 0
        kind = parts[0]
        try:
            return kind, int(parts[1])
        except ValueError:
            return None, 0

    def _restore_trash_item(self, arg: str, extra: str = ""):
        kind, iid = self._parse_trash_target(arg, extra)
        if not kind or not iid:
            return
        getters = {
            "subject": self._db.get_subject,
            "folder": self._db.get_folder,
            "session": self._db.get_session,
            "mindmap": self._db.get_mindmap,
            "document": self._db.get_document,
        }
        if kind not in getters:
            return
        ok = True
        if kind == "subject":
            ok = self._db.restore_subject(iid)
        elif kind == "folder":
            self._db.restore_folder(iid)
        elif kind == "session":
            ok = self._db.restore_session(iid)
        elif kind == "mindmap":
            ok = self._db.restore_mindmap(iid)
        else:
            ok = self._db.restore_document(iid)
        row = getters[kind](iid)
        if not ok or row is None:
            self._status.setText("这项已经不在回收站里了")
            self.reload_trash()
            return
        self._trash_mode = False
        subject_id = iid if kind == "subject" else row.get("subject_id")
        if subject_id and subject_id != self._current_subject_id:
            self._remember_subject_view()
            self._current_subject_id = subject_id
            self._settings.setValue("current_subject_id", subject_id)
        folder_id = row.get("folder_id") if kind != "subject" else None
        if kind == "folder":
            folder_id = iid
        elif folder_id is None and row.get("session_id"):
            sess = self._db.get_session(row["session_id"])
            if sess:
                folder_id = sess.get("folder_id")
        self._expand_folder(folder_id)
        self.reload_subjects(select_id=self._current_subject_id)
        if kind in ("folder", "subject"):
            self.reload_sessions()
        else:
            self.reload_sessions(select_id=iid, select_kind=kind)
        self._status.setText("已从回收站恢复")

    def _purge_trash_item(self, arg: str, extra: str = ""):
        kind, iid = self._parse_trash_target(arg, extra)
        if not kind or not iid:
            return
        label = {
            "subject": "课题",
            "folder": "文件夹",
            "session": "会话",
            "mindmap": "思维导图",
            "document": "文档",
        }.get(kind, "项目")
        ret = QMessageBox.question(
            self,
            "彻底删除",
            f"确定彻底删除这个{label}吗？此操作不可恢复。",
        )
        if ret != QMessageBox.Yes:
            return
        if kind == "subject":
            images = self._db.subject_image_files(iid, include_deleted=True)
            self._db.delete_subject(iid)
            self._remove_image_files(images)
        elif kind == "folder":
            images = self._db.folder_image_files(iid)
            self._db.delete_folder(iid)
            self._remove_image_files(images)
        elif kind == "session":
            images = self._db.session_image_files(iid)
            self._db.delete_session(iid)
            self._remove_image_files(images)
        elif kind == "mindmap":
            self._mm_view.pop(iid, None)
            self._db.delete_mindmap(iid)
        elif kind == "document":
            self._db.delete_document(iid)
        else:
            return
        self._status.setText("已彻底删除")
        self.reload_trash()

    def _empty_trash(self):
        items = self._db.list_trash_items()
        if not items:
            self._status.setText("回收站已经是空的")
            return
        ret = QMessageBox.question(
            self,
            "清空回收站",
            f"确定彻底删除回收站中的 {len(items)} 项吗？此操作不可恢复。",
        )
        if ret != QMessageBox.Yes:
            return
        images = self._db.empty_trash()
        self._remove_image_files(images)
        self._status.setText("回收站已清空")
        self.reload_trash()

    def set_suppress_callback(self, cb):
        """复制原文/图片时通知剪贴板监听器忽略下一次变化。"""
        self._suppress_cb = cb

    def _open_settings(self):
        dlg = SettingsDialog(self, self.pause_action, self.autostart_action)
        dlg.exec()

    def _on_pause_toggled(self, checked: bool):
        self._status.setText(
            "已暂停记录，复制内容不会弹出悬浮条" if checked else "已恢复记录"
        )

    def _on_autostart_toggled(self, checked: bool):
        try:
            autostart.set_enabled(checked)
        except OSError as e:
            self._status.setText(f"设置开机自启失败：{e}")
            self.autostart_action.blockSignals(True)
            self.autostart_action.setChecked(not checked)
            self.autostart_action.blockSignals(False)
            return
        self._status.setText(
            "已开启开机自启动，开机后自动缩在托盘"
            if checked
            else "已关闭开机自启动"
        )

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.hidden_to_tray.emit()
