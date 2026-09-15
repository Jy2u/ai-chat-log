"""主窗口：新建/重命名/删除/移动/导出/备份与右键菜单。"""

import os
import re
import shutil
import time
import zipfile
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QInputDialog, QMenu, QMessageBox

import render
from db import DATA_DIR, IMAGES_DIR
from ui.widgets import (
    MATCH_COLORS,
    ROLE_ID,
    ROLE_KIND,
    GlassNoteDialog,
    _safe_export_stem,
    _unique_export_stem,
    norm_session_source,
)

_FOLLOW_CURRENT = object()
_BACKUP_ROOT = os.path.abspath(os.path.expanduser(os.environ.get(
    "AICHAT_BACKUP_ROOT", "~/Documents/AIChatRecord备份"
)))
_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*]')
_AUTO_BACKUP_REASON = "自动备份"
_AUTO_BACKUP_SEC = 6 * 60 * 60
_AUTO_BACKUP_MS = _AUTO_BACKUP_SEC * 1000
_AUTO_BACKUP_RETRY_MS = 30 * 60 * 1000
_LAST_AUTO_BACKUP_KEY = "last_auto_backup_at"
_AUTO_BACKUP_START_KEY = "auto_backup_start_at"


def _fmt_remain(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}小时{minutes}分"
    if minutes:
        return f"{minutes}分{secs}秒"
    return f"{secs}秒"


class OpsMixin:
    def import_external_conversation(self, folder_id: int):
        """选择一个本机 Cursor 对话并导入指定文件夹。"""
        from cursor_import import list_cursor_conversations, load_cursor_conversation
        from ui.cursor_import_dialog import CursorImportDialog

        source_name = "Cursor"
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            conversations = list_cursor_conversations()
        except Exception as exc:
            QMessageBox.critical(self, f"无法读取 {source_name}", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        if not conversations:
            QMessageBox.information(
                self, f"从 {source_name} 导入", f"没有找到本地 {source_name} 对话。"
            )
            return
        dialog = CursorImportDialog(conversations, self, source_name=source_name)
        if dialog.exec() != QDialog.Accepted:
            return
        selected = dialog.selected_conversation()
        if selected is None:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            info, messages = load_cursor_conversation(selected.composer_id)
            if not messages:
                raise RuntimeError("这个对话没有可在本机读取的消息正文。")
            session_id = self._db.import_external_conversation(
                "cursor", info, messages, folder_id
            )
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.reload_sessions(select_id=session_id, select_kind="session")
        self._status.setText(
            f"已从 {source_name} 导入：{info.title}（{info.message_count} 轮）"
        )

    def _item_folder_id(self, item):
        """树节点所在的周期文件夹；根目录为 None。"""
        if item is None:
            return None
        kind = item.data(0, ROLE_KIND)
        iid = item.data(0, ROLE_ID)
        if kind == "folder":
            return iid
        if kind == "session":
            sess = self._db.get_session(iid)
            return None if sess is None else sess.get("folder_id")
        if kind == "mindmap":
            mmap = self._db.get_mindmap(iid)
            if mmap is None:
                return None
            if mmap.get("folder_id") is not None:
                return mmap["folder_id"]
            if mmap.get("session_id") is not None:
                sess = self._db.get_session(mmap["session_id"])
                return None if sess is None else sess.get("folder_id")
        if kind == "document":
            doc = self._db.get_document(iid)
            if doc is None:
                return None
            if doc.get("folder_id") is not None:
                return doc["folder_id"]
            if doc.get("session_id") is not None:
                sess = self._db.get_session(doc["session_id"])
                return None if sess is None else sess.get("folder_id")
        return None

    def _add_sibling_create_actions(self, menu, item):
        """在当前节点同一层新建会话 / 思维导图 / 文档 / 文件夹。"""
        folder_id = self._item_folder_id(item)
        kind = item.data(0, ROLE_KIND)
        under_session = None
        if kind == "mindmap":
            mmap = self._db.get_mindmap(item.data(0, ROLE_ID))
            if mmap and mmap.get("session_id") is not None:
                under_session = mmap["session_id"]
        elif kind == "document":
            doc = self._db.get_document(item.data(0, ROLE_ID))
            if doc and doc.get("session_id") is not None:
                under_session = doc["session_id"]
        menu.addAction(
            "新建会话",
            lambda fid=folder_id: self.new_session(folder_id=fid),
        )
        if under_session is not None:
            menu.addAction(
                "新建思维导图",
                lambda sid=under_session: self.new_mindmap(
                    session_id=sid, folder_id=None
                ),
            )
            menu.addAction(
                "新建文档",
                lambda sid=under_session: self.new_document(
                    session_id=sid, folder_id=None
                ),
            )
        else:
            menu.addAction(
                "新建思维导图",
                lambda fid=folder_id: self.new_mindmap(
                    folder_id=fid, session_id=None
                ),
            )
            menu.addAction(
                "新建文档",
                lambda fid=folder_id: self.new_document(
                    folder_id=fid, session_id=None
                ),
            )
        menu.addAction("新建文件夹", self.new_folder)
        menu.addSeparator()

    def new_session(self, folder_id=_FOLLOW_CURRENT):
        """新建会话。默认建在当前选中项所在的文件夹（或根目录）。"""
        if folder_id is _FOLLOW_CURRENT:
            item = self._tree.currentItem()
            if item is not None:
                folder_id = self._item_folder_id(item)
            elif self._current_sid is not None:
                session = self._db.get_session(self._current_sid)
                folder_id = None if session is None else session["folder_id"]
            else:
                folder_id = None
        default = datetime.now().strftime("%Y-%m-%d")
        name, ok = QInputDialog.getText(
            self, "新建会话", "会话名称（保持默认则以第一条记录自动命名）：",
            text=default,
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        # 用户保持默认日期名 = 仍参与自动命名；自己改了名 = 固定不动
        sid = self._db.create_session(
            name,
            auto_named=(name == default),
            folder_id=folder_id,
            subject_id=self._current_subject_id,
        )
        self._exit_search_mode()
        self.reload_sessions(select_id=sid)

    def new_folder(self):
        name, ok = QInputDialog.getText(
            self, "新建文件夹", "文件夹名称：", text="新文件夹"
        )
        if not ok or not name.strip():
            return
        self._db.create_folder(name.strip(), subject_id=self._current_subject_id)
        self.reload_subjects(select_id=self._current_subject_id)
        self.reload_sessions()

    def new_mindmap(self, folder_id=None, session_id=_FOLLOW_CURRENT):
        """新建思维导图。默认跟当前选中项同一层（会话下或文件夹里）。"""
        if session_id is _FOLLOW_CURRENT:
            item = self._tree.currentItem()
            kind = None if item is None else item.data(0, ROLE_KIND)
            if kind == "folder":
                session_id = None
                folder_id = item.data(0, ROLE_ID)
            elif kind == "mindmap":
                mmap = self._db.get_mindmap(item.data(0, ROLE_ID))
                if mmap and mmap.get("session_id") is not None:
                    session_id = mmap["session_id"]
                    folder_id = None
                elif mmap:
                    session_id = None
                    folder_id = mmap.get("folder_id")
                else:
                    session_id = self._current_sid
                    folder_id = None
            elif kind == "document":
                doc = self._db.get_document(item.data(0, ROLE_ID))
                if doc and doc.get("session_id") is not None:
                    session_id = doc["session_id"]
                    folder_id = None
                elif doc:
                    session_id = None
                    folder_id = doc.get("folder_id")
                else:
                    session_id = self._current_sid
                    folder_id = None
            else:
                session_id = self._current_sid
                folder_id = None
        name, ok = QInputDialog.getText(
            self, "新建思维导图", "导图名称：", text="思维导图"
        )
        if not ok or not name.strip():
            return
        mid = self._db.create_mindmap(
            name.strip(),
            folder_id=folder_id,
            session_id=session_id,
            subject_id=self._current_subject_id,
        )
        if folder_id is not None:
            raw = self._settings.value(self._expanded_folders_key(), None)
            if raw is None:
                raw = self._settings.value("expanded_folders", [])
            if isinstance(raw, str):
                raw = [raw]
            ids = set(raw or [])
            ids.add(str(folder_id))
            self._settings.setValue(self._expanded_folders_key(), list(ids))
        self._exit_search_mode()
        self.reload_sessions(select_id=mid, select_kind="mindmap")

    def new_document(self, folder_id=None, session_id=_FOLLOW_CURRENT):
        """新建 Markdown 文档。默认跟当前选中项同一层。"""
        if session_id is _FOLLOW_CURRENT:
            item = self._tree.currentItem()
            kind = None if item is None else item.data(0, ROLE_KIND)
            if kind == "folder":
                session_id = None
                folder_id = item.data(0, ROLE_ID)
            elif kind == "mindmap":
                mmap = self._db.get_mindmap(item.data(0, ROLE_ID))
                if mmap and mmap.get("session_id") is not None:
                    session_id = mmap["session_id"]
                    folder_id = None
                elif mmap:
                    session_id = None
                    folder_id = mmap.get("folder_id")
                else:
                    session_id = self._current_sid
                    folder_id = None
            elif kind == "document":
                doc = self._db.get_document(item.data(0, ROLE_ID))
                if doc and doc.get("session_id") is not None:
                    session_id = doc["session_id"]
                    folder_id = None
                elif doc:
                    session_id = None
                    folder_id = doc.get("folder_id")
                else:
                    session_id = self._current_sid
                    folder_id = None
            else:
                session_id = self._current_sid
                folder_id = None
        name, ok = QInputDialog.getText(
            self, "新建文档", "文档名称：", text="文档"
        )
        if not ok or not name.strip():
            return
        did = self._db.create_document(
            name.strip(),
            folder_id=folder_id,
            session_id=session_id,
            subject_id=self._current_subject_id,
        )
        self._expand_folder(folder_id)
        self._exit_search_mode()
        self.reload_sessions(select_id=did, select_kind="document")

    def rename_document(self, document_id: int):
        doc = self._db.get_document(document_id)
        if doc is None:
            return
        name, ok = QInputDialog.getText(
            self, "重命名文档", "文档名称：", text=doc["name"]
        )
        if not ok or not name.strip():
            return
        self._db.rename_document(document_id, name.strip())
        self.reload_sessions(select_id=document_id, select_kind="document")

    def delete_document(self, document_id: int):
        doc = self._db.get_document(document_id)
        if doc is None:
            return
        ret = QMessageBox.question(
            self,
            "删除文档",
            f"确定把文档「{doc['name']}」移入回收站吗？\n可稍后在回收站恢复。",
        )
        if ret != QMessageBox.Yes:
            return
        self._db.trash_document(document_id)
        self._current_did = None
        self._current_kind = "session"
        self._exit_search_mode()
        fallback = doc["session_id"]
        self.reload_sessions(select_id=fallback, select_kind="session")

    def show_markdown_help(self):
        from ui.widgets import MarkdownHelpDialog

        MarkdownHelpDialog(self).exec()

    def rename_mindmap(self, mindmap_id: int):
        mmap = self._db.get_mindmap(mindmap_id)
        if mmap is None:
            return
        name, ok = QInputDialog.getText(
            self, "重命名思维导图", "导图名称：", text=mmap["name"]
        )
        if not ok or not name.strip():
            return
        self._db.rename_mindmap(mindmap_id, name.strip())
        self.reload_sessions(select_id=mindmap_id, select_kind="mindmap")

    def delete_mindmap(self, mindmap_id: int):
        mmap = self._db.get_mindmap(mindmap_id)
        if mmap is None:
            return
        ret = QMessageBox.question(
            self,
            "删除思维导图",
            f"确定把思维导图「{mmap['name']}」移入回收站吗？"
            "\n可稍后在回收站恢复。",
        )
        if ret != QMessageBox.Yes:
            return
        self._db.trash_mindmap(mindmap_id)
        self._current_mid = None
        self._current_kind = "session"
        self._exit_search_mode()
        fallback = mmap["session_id"]
        self.reload_sessions(select_id=fallback, select_kind="session")

    def rename_folder(self, folder_id: int):
        folders = {f["id"]: f for f in self._db.list_folders()}
        folder = folders.get(folder_id)
        if folder is None:
            return
        name, ok = QInputDialog.getText(
            self, "重命名文件夹", "文件夹名称：", text=folder["name"]
        )
        if not ok or not name.strip():
            return
        self._db.rename_folder(folder_id, name.strip())
        self.reload_sessions()

    def delete_folder(self, folder_id: int):
        folders = {f["id"]: f for f in self._db.list_folders()}
        folder = folders.get(folder_id)
        if folder is None:
            return
        n_sessions, n_messages = self._db.folder_stats(folder_id)
        ret = QMessageBox.question(
            self,
            "删除文件夹",
            f"确定把文件夹「{folder['name']}」及其中"
            f" {n_sessions} 个会话、{n_messages} 条记录移入回收站吗？"
            "\n可稍后在回收站恢复。",
        )
        if ret != QMessageBox.Yes:
            return
        self._db.trash_folder(folder_id)
        self._ensure_session_exists()
        self._exit_search_mode()
        self._current_sid = None
        self._current_mid = None
        self._current_did = None
        self._current_kind = "session"
        self.reload_sessions(select_id=-1)
        self.reload_subjects(select_id=self._current_subject_id)

    def _expand_folder(self, folder_id):
        if folder_id is None:
            return
        raw = self._settings.value(self._expanded_folders_key(), None)
        if raw is None:
            raw = self._settings.value("expanded_folders", [])
        if isinstance(raw, str):
            raw = [raw]
        ids = set(raw or [])
        ids.add(str(folder_id))
        self._settings.setValue(self._expanded_folders_key(), list(ids))

    def _fill_folder_dest_menu(
        self, menu, on_pick, skip_folder_id=None, skip_root=False
    ):
        if not skip_root:
            menu.addAction("（根目录）", lambda: on_pick(None))
        for f in self._db.list_folders(self._current_subject_id):
            if skip_folder_id is not None and f["id"] == skip_folder_id:
                continue
            menu.addAction(
                f["name"],
                lambda fid=f["id"]: on_pick(fid),
            )
        if not menu.actions():
            menu.setEnabled(False)

    def _fill_subject_dest_menu(self, menu, on_pick, skip_id=None):
        for s in self._db.list_subjects():
            if skip_id is not None and s["id"] == skip_id:
                continue
            menu.addAction(s["name"], lambda i=s["id"]: on_pick(i))
        if not menu.actions():
            menu.setEnabled(False)

    def move_session(self, session_id: int, folder_id):
        self._db.move_session(session_id, folder_id)
        self._expand_folder(folder_id)
        self.reload_sessions(select_id=session_id)

    def copy_session_to(self, session_id: int, folder_id):
        new_id = self._db.copy_session(
            session_id, folder_id, subject_id=self._current_subject_id
        )
        if not new_id:
            return
        self._expand_folder(folder_id)
        self.reload_sessions(select_id=new_id)
        self._status.setText("已复制会话")

    def move_mindmap_to(self, mindmap_id: int, folder_id):
        self._db.move_mindmap(
            mindmap_id,
            folder_id=folder_id,
            session_id=None,
            subject_id=self._current_subject_id,
        )
        self._expand_folder(folder_id)
        self.reload_sessions(select_id=mindmap_id, select_kind="mindmap")
        self._status.setText("已移动思维导图")

    def copy_mindmap_to(self, mindmap_id: int, folder_id):
        new_id = self._db.copy_mindmap(
            mindmap_id,
            folder_id=folder_id,
            session_id=None,
            subject_id=self._current_subject_id,
        )
        if not new_id:
            return
        self._expand_folder(folder_id)
        self.reload_sessions(select_id=new_id, select_kind="mindmap")
        self._status.setText("已复制思维导图")

    def move_document_to(self, document_id: int, folder_id):
        self._db.move_document(
            document_id,
            folder_id=folder_id,
            session_id=None,
            subject_id=self._current_subject_id,
        )
        self._expand_folder(folder_id)
        self.reload_sessions(select_id=document_id, select_kind="document")
        self._status.setText("已移动文档")

    def copy_document_to(self, document_id: int, folder_id):
        new_id = self._db.copy_document(
            document_id,
            folder_id=folder_id,
            session_id=None,
            subject_id=self._current_subject_id,
        )
        if not new_id:
            return
        self._expand_folder(folder_id)
        self.reload_sessions(select_id=new_id, select_kind="document")
        self._status.setText("已复制文档")

    def rename_session(self, session_id=None):
        sid = self._current_sid if session_id is None else session_id
        if sid is None:
            return
        session = self._db.get_session(sid)
        if session is None:
            return
        name, ok = QInputDialog.getText(
            self, "重命名会话", "会话名称：", text=session["name"]
        )
        if not ok or not name.strip():
            return
        self._db.rename_session(sid, name.strip())
        self.reload_sessions(select_id=sid, select_kind="session")

    def edit_session_note(self, session_id=None):
        sid = self._current_sid if session_id is None else session_id
        if sid is None:
            return
        session = self._db.get_session(sid)
        if session is None:
            return
        dlg = GlassNoteDialog(self, session.get("note") or "")
        if dlg.exec() != QDialog.Accepted:
            return
        self._db.set_session_note(sid, dlg.text())
        self.reload_sessions(select_id=sid, select_kind="session")

    def set_session_source(self, session_id: int, source: str):
        session = self._db.get_session(session_id)
        if session is None:
            return
        current = norm_session_source(session.get("source"))
        next_src = "" if current == source else source
        self._db.set_session_source(session_id, next_src)
        self.reload_sessions(select_id=session_id, select_kind="session")

    def toggle_session_done(self, session_id: int):
        session = self._db.get_session(session_id)
        if session is None:
            return
        self._db.set_session_done(session_id, not bool(session.get("done")))
        self.reload_sessions(select_id=session_id, select_kind="session")

    def delete_session(self):
        sid = self._current_sid
        if sid is None:
            return
        session = self._db.get_session(sid)
        count = len(self._db.get_messages(sid))
        ret = QMessageBox.question(
            self,
            "删除会话",
            f"确定把会话「{session['name']}」及其 {count} 条记录移入回收站吗？"
            "\n可稍后在回收站恢复。",
        )
        if ret != QMessageBox.Yes:
            return
        self._db.trash_session(sid)
        self._ensure_session_exists()
        self._exit_search_mode()
        self._current_sid = None
        self._current_mid = None
        self._current_did = None
        self._current_kind = "session"
        self.reload_sessions(select_id=-1)

    def _remove_image_files(self, names: list):
        for name in names:
            try:
                os.remove(os.path.join(IMAGES_DIR, name))
            except OSError:
                pass

    def _ensure_session_exists(self):
        if not self._db.list_sessions(self._current_subject_id):
            self._db.create_session(
                datetime.now().strftime("%Y-%m-%d"),
                subject_id=self._current_subject_id,
            )

    def export_session(self):
        if self._current_kind == "document" and self._current_did is not None:
            self.export_document(self._current_did)
            return
        sid = self.current_session_id()
        if sid is None:
            return
        session = self._db.get_session(sid)
        messages = self._db.get_messages(sid)
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", session["name"])
        path, _ = QFileDialog.getSaveFileName(
            self, "导出会话", safe_name + ".md", "Markdown (*.md)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(render.export_markdown(session, messages))
        self._status.setText(f"已导出到 {path}")

    def _matched_sessions(self, session: dict) -> list:
        """同一课题、同一文件夹、同一匹配色的全部对话。"""
        color = (session or {}).get("match_color") or ""
        if not color:
            return [session] if session else []
        folder_id = session.get("folder_id")
        subject_id = session.get("subject_id")
        peers = []
        for s in self._db.list_sessions(subject_id):
            if (s.get("match_color") or "") != color:
                continue
            if s.get("folder_id") != folder_id:
                continue
            peers.append(s)
        return peers or [session]

    def _unique_export_dir(self, parent: str, stem: str) -> str:
        path = os.path.join(parent, stem)
        if not os.path.exists(path):
            return path
        i = 2
        while os.path.exists(os.path.join(parent, f"{stem} ({i})")):
            i += 1
        return os.path.join(parent, f"{stem} ({i})")

    def export_matched_sessions(self, session_id: int):
        session = self._db.get_session(session_id)
        if session is None:
            return
        peers = self._matched_sessions(session)
        if not peers:
            return
        color = session.get("match_color") or ""
        color_name = MATCH_COLORS.get(color, {}).get("name", "匹配")
        last = self._settings.value("last_export_dir", "")
        parent = QFileDialog.getExistingDirectory(self, "选择导出位置", last)
        if not parent:
            return
        self._settings.setValue("last_export_dir", parent)
        folder_stem = _safe_export_stem(f"匹配-{color_name}") or "匹配对话"
        dest = self._unique_export_dir(parent, folder_stem)
        used = set()
        n_img = 0
        try:
            os.makedirs(dest, exist_ok=True)
            img_dir = os.path.join(dest, "images")
            for s in peers:
                stem = _unique_export_stem(
                    _safe_export_stem(s["name"]) or "会话", used
                )
                messages = self._db.get_messages(s["id"])
                body = render.export_markdown(s, messages, image_rel="images")
                with open(
                    os.path.join(dest, stem + ".md"), "w", encoding="utf-8"
                ) as f:
                    f.write(body)
                for msg in messages:
                    if msg.get("kind") != "image":
                        continue
                    name = msg.get("content") or ""
                    src = os.path.join(IMAGES_DIR, name)
                    if not name or not os.path.isfile(src):
                        continue
                    os.makedirs(img_dir, exist_ok=True)
                    dst = os.path.join(img_dir, os.path.basename(name))
                    if not os.path.isfile(dst):
                        shutil.copy2(src, dst)
                        n_img += 1
        except OSError as e:
            QMessageBox.warning(self, "导出失败", str(e))
            self._status.setText(f"导出失败：{e}")
            return
        self._status.setText(
            f"已导出 {len(peers)} 个匹配对话到 {dest}"
            + (f"（{n_img} 张图片）" if n_img else "")
        )

    def export_document(self, document_id: int):
        doc = self._db.get_document(document_id)
        if doc is None:
            return
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", doc["name"])
        path, _ = QFileDialog.getSaveFileName(
            self, "导出文档", safe_name + ".md", "Markdown (*.md)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(doc.get("content") or "")
        self._status.setText(f"已导出到 {path}")

    def export_folder(self, folder_id: int):
        folders = {f["id"]: f for f in self._db.list_folders()}
        folder = folders.get(folder_id)
        if folder is None:
            return
        safe_root = _safe_export_stem(folder["name"]) or "文件夹"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "下载整个文件夹",
            safe_root + ".zip",
            "ZIP (*.zip)",
        )
        if not path:
            return
        sessions = [
            s for s in self._db.list_sessions() if s["folder_id"] == folder_id
        ]
        session_ids = {s["id"] for s in sessions}
        maps = []
        for m in self._db.list_mindmaps():
            if m["folder_id"] == folder_id:
                maps.append(("folder", m))
            elif m["session_id"] in session_ids:
                maps.append(("session", m))
        docs = []
        for d in self._db.list_documents():
            if d["folder_id"] == folder_id:
                docs.append(("folder", d))
            elif d["session_id"] in session_ids:
                docs.append(("session", d))

        used_chat, used_map, used_doc = set(), set(), set()
        n_chat, n_map, n_doc, n_img = 0, 0, 0, 0
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                if not sessions and not maps and not docs:
                    zf.writestr(
                        f"{safe_root}/说明.txt",
                        "这个文件夹是空的。\n",
                    )
                for s in sessions:
                    stem = _unique_export_stem(
                        _safe_export_stem(s["name"]) or "会话", used_chat
                    )
                    messages = self._db.get_messages(s["id"])
                    body = render.export_markdown(
                        s, messages, image_rel="../images"
                    )
                    zf.writestr(
                        f"{safe_root}/对话/{stem}.md",
                        body.encode("utf-8"),
                    )
                    n_chat += 1
                    for msg in messages:
                        if msg.get("kind") != "image":
                            continue
                        name = msg.get("content") or ""
                        src = os.path.join(IMAGES_DIR, name)
                        if not name or not os.path.isfile(src):
                            continue
                        arc = f"{safe_root}/images/{os.path.basename(name)}"
                        try:
                            zf.getinfo(arc)
                        except KeyError:
                            zf.write(src, arc)
                            n_img += 1
                for src_kind, mmap in maps:
                    base = _safe_export_stem(mmap["name"]) or "思维导图"
                    if src_kind == "session":
                        sess = self._db.get_session(mmap["session_id"])
                        prefix = (
                            _safe_export_stem(sess["name"]) if sess else "会话"
                        )
                        base = f"{prefix}-{base}"
                    stem = _unique_export_stem(base, used_map)
                    body = render.export_mindmap_markdown(
                        mmap,
                        self._db.get_mindmap_nodes(mmap["id"]),
                        self._db.list_mindmap_edges(mmap["id"]),
                    )
                    zf.writestr(
                        f"{safe_root}/思维导图/{stem}.md",
                        body.encode("utf-8"),
                    )
                    n_map += 1
                for src_kind, doc in docs:
                    full = self._db.get_document(doc["id"]) or doc
                    base = _safe_export_stem(full["name"]) or "文档"
                    if src_kind == "session":
                        sess = self._db.get_session(full.get("session_id"))
                        prefix = (
                            _safe_export_stem(sess["name"]) if sess else "会话"
                        )
                        base = f"{prefix}-{base}"
                    stem = _unique_export_stem(base, used_doc)
                    zf.writestr(
                        f"{safe_root}/文档/{stem}.md",
                        (full.get("content") or "").encode("utf-8"),
                    )
                    n_doc += 1
        except OSError as e:
            QMessageBox.warning(self, "下载失败", str(e))
            self._status.setText(f"下载失败：{e}")
            return
        self._status.setText(
            f"已下载到 {path}（{n_chat} 个对话 · {n_map} 张导图"
            f" · {n_doc} 篇文档 · {n_img} 张图片）"
        )

    def backup_data(self):
        reason, ok = QInputDialog.getText(self, "备份整个软件", "备份原因：")
        if not ok:
            return
        self._run_backup(reason, silent=False)

    def _setup_auto_backup(self):
        self._next_auto_backup_at = None
        self._auto_backup_timer = QTimer(self)
        self._auto_backup_timer.setSingleShot(True)
        self._auto_backup_timer.timeout.connect(self._auto_backup)
        self._auto_backup_clock = QTimer(self)
        self._auto_backup_clock.timeout.connect(self._refresh_auto_backup_hint)
        self._auto_backup_clock.start(1000)
        self._schedule_auto_backup()

    def _auto_backup_anchor(self):
        last = self._settings.value(_LAST_AUTO_BACKUP_KEY, 0.0, type=float)
        if last:
            return last
        start = self._settings.value(_AUTO_BACKUP_START_KEY, 0.0, type=float)
        if not start:
            start = time.time()
            self._settings.setValue(_AUTO_BACKUP_START_KEY, start)
            self._settings.sync()
        return start

    def _schedule_auto_backup(self, delay_ms=None):
        now = time.time()
        if delay_ms is None:
            due = self._auto_backup_anchor() + _AUTO_BACKUP_SEC
        else:
            due = now + delay_ms / 1000.0
        self._next_auto_backup_at = due
        wait = max(1000, int((due - now) * 1000))
        self._auto_backup_timer.start(wait)
        self._refresh_auto_backup_hint()

    def _refresh_auto_backup_hint(self):
        label = getattr(self, "_auto_backup_hint", None)
        if label is None:
            return
        last = self._settings.value(_LAST_AUTO_BACKUP_KEY, 0.0, type=float)
        if last:
            last_txt = datetime.fromtimestamp(last).strftime("%Y-%m-%d %H:%M")
            last_part = f"上次自动备份 {last_txt}"
        else:
            start = self._auto_backup_anchor()
            start_txt = datetime.fromtimestamp(start).strftime("%Y-%m-%d %H:%M")
            last_part = f"尚未自动备份（起始 {start_txt}）"
        due = getattr(self, "_next_auto_backup_at", None)
        if due is None:
            due = self._auto_backup_anchor() + _AUTO_BACKUP_SEC
            self._next_auto_backup_at = due
        remain = int(due - time.time())
        remain_part = (
            "正在自动备份" if remain <= 0 else f"下次还有 {_fmt_remain(remain)}"
        )
        label.setText(f"{last_part}  ·  {remain_part}")

    def _auto_backup(self):
        ok = self._run_backup(_AUTO_BACKUP_REASON, silent=True)
        if ok:
            now = time.time()
            self._settings.setValue(_LAST_AUTO_BACKUP_KEY, now)
            self._settings.setValue(_AUTO_BACKUP_START_KEY, now)
            self._settings.sync()
            self._schedule_auto_backup()
            return
        self._schedule_auto_backup(_AUTO_BACKUP_RETRY_MS)

    def _run_backup(self, reason: str, silent: bool = False) -> bool:
        reason = _UNSAFE_NAME.sub("", (reason or "").strip())
        if not reason:
            if not silent:
                QMessageBox.warning(self, "备份整个软件", "请填写备份原因。")
            return False

        stamp = datetime.now().strftime("%Y-%m-%d-%H点%M分")
        folder = f"{stamp}-{reason}"
        dest = os.path.join(_BACKUP_ROOT, folder)
        n = 2
        while os.path.exists(dest):
            dest = os.path.join(_BACKUP_ROOT, f"{folder}-{n}")
            n += 1

        app_dir = os.path.abspath(os.path.dirname(DATA_DIR))
        skip_dirs = {"__pycache__", ".git", ".cursor", ".idea", ".vscode"}
        skip_db = {"chatlog.db", "chatlog.db-wal", "chatlog.db-shm"}

        def ignore(directory, names):
            skipped = []
            for name in names:
                if name in skip_dirs or name in skip_db or name.endswith(".pyc"):
                    skipped.append(name)
            return skipped

        dest_db = os.path.join(dest, "data", "chatlog.db")
        dest_images = os.path.join(dest, "data", "images")
        try:
            os.makedirs(_BACKUP_ROOT, exist_ok=True)
            shutil.copytree(app_dir, dest, ignore=ignore)
            self._db.backup_to(dest_db)
        except OSError as e:
            if not silent:
                QMessageBox.warning(self, "备份失败", str(e))
            self._status.setText(f"备份失败：{e}")
            return False

        n_img = 0
        if os.path.isdir(dest_images):
            n_img = sum(
                1
                for name in os.listdir(dest_images)
                if os.path.isfile(os.path.join(dest_images, name))
            )
        self._status.setText(
            f"已备份到 {dest}（程序文件 + 数据库 + {n_img} 张图片）"
        )
        return True

    def _tree_menu(self, pos):
        item = self._tree.itemAt(pos)
        menu = QMenu(self)

        if item is None:
            menu.addAction(
                "新建会话（根目录）",
                lambda: self.new_session(folder_id=None),
            )
            menu.addAction("新建文件夹", self.new_folder)
            menu.addAction(
                "新建思维导图（根目录）",
                lambda: self.new_mindmap(folder_id=None, session_id=None),
            )
            menu.addAction(
                "新建文档（根目录）",
                lambda: self.new_document(folder_id=None, session_id=None),
            )
            menu.addSeparator()
            menu.addAction("打开回收站", self.open_trash)
        elif item.data(0, ROLE_KIND) == "folder":
            fid = item.data(0, ROLE_ID)
            menu.addAction(
                "在此文件夹新建会话",
                lambda: self.new_session(folder_id=fid),
            )
            menu.addAction(
                "在此文件夹新建思维导图",
                lambda: self.new_mindmap(folder_id=fid, session_id=None),
            )
            menu.addAction(
                "在此文件夹新建文档",
                lambda: self.new_document(folder_id=fid, session_id=None),
            )
            menu.addAction("下载整个文件夹", lambda: self.export_folder(fid))
            menu.addAction("重命名文件夹", lambda: self.rename_folder(fid))
            move_subj = menu.addMenu("移动到课题")
            self._fill_subject_dest_menu(
                move_subj,
                lambda i: self.move_folder_to_subject(fid, i),
                skip_id=self._current_subject_id,
            )
            menu.addSeparator()
            menu.addAction("删除文件夹", lambda: self.delete_folder(fid))
        elif item.data(0, ROLE_KIND) == "mindmap":
            mid = item.data(0, ROLE_ID)
            self._tree.setCurrentItem(item)
            mmap = self._db.get_mindmap(mid)
            self._add_sibling_create_actions(menu, item)
            menu.addAction("重命名", lambda: self.rename_mindmap(mid))
            copy_menu = menu.addMenu("复制到")
            self._fill_folder_dest_menu(
                copy_menu, lambda fid: self.copy_mindmap_to(mid, fid)
            )
            move_menu = menu.addMenu("移动到")
            under_session = bool(mmap and mmap.get("session_id") is not None)
            current_folder = None if mmap is None else mmap.get("folder_id")
            self._fill_folder_dest_menu(
                move_menu,
                lambda fid: self.move_mindmap_to(mid, fid),
                skip_folder_id=None if under_session else current_folder,
                skip_root=not under_session and current_folder is None,
            )
            move_subj = menu.addMenu("移动到课题")
            self._fill_subject_dest_menu(
                move_subj,
                lambda i: self.move_mindmap_to_subject(mid, i),
                skip_id=self._current_subject_id,
            )
            menu.addSeparator()
            menu.addAction("删除思维导图", lambda: self.delete_mindmap(mid))
        elif item.data(0, ROLE_KIND) == "document":
            did = item.data(0, ROLE_ID)
            self._tree.setCurrentItem(item)
            doc = self._db.get_document(did)
            self._add_sibling_create_actions(menu, item)
            menu.addAction("重命名", lambda: self.rename_document(did))
            copy_menu = menu.addMenu("复制到")
            self._fill_folder_dest_menu(
                copy_menu, lambda fid: self.copy_document_to(did, fid)
            )
            move_menu = menu.addMenu("移动到")
            under_session = bool(doc and doc.get("session_id") is not None)
            current_folder = None if doc is None else doc.get("folder_id")
            self._fill_folder_dest_menu(
                move_menu,
                lambda fid: self.move_document_to(did, fid),
                skip_folder_id=None if under_session else current_folder,
                skip_root=not under_session and current_folder is None,
            )
            move_subj = menu.addMenu("移动到课题")
            self._fill_subject_dest_menu(
                move_subj,
                lambda i: self.move_document_to_subject(did, i),
                skip_id=self._current_subject_id,
            )
            menu.addAction("导出 Markdown", lambda: self.export_document(did))
            menu.addSeparator()
            menu.addAction("删除文档", lambda: self.delete_document(did))
        else:
            self._tree.setCurrentItem(item)  # 右键也切换到该会话
            sid = item.data(0, ROLE_ID)
            session = self._db.get_session(sid)
            self._add_sibling_create_actions(menu, item)
            menu.addAction("重命名", self.rename_session)
            has_note = bool(((session or {}).get("note") or "").strip())
            menu.addAction(
                "编辑备注" if has_note else "添加备注",
                lambda: self.edit_session_note(sid),
            )
            source = norm_session_source((session or {}).get("source"))
            done = bool((session or {}).get("done"))
            menu.addSeparator()
            act_cursor = menu.addAction("【cursor】")
            act_cursor.setCheckable(True)
            act_cursor.setChecked(source == "cursor")
            act_cursor.triggered.connect(
                lambda: self.set_session_source(sid, "cursor")
            )
            act_codex = menu.addAction("【codex】")
            act_codex.setCheckable(True)
            act_codex.setChecked(source == "codex")
            act_codex.triggered.connect(
                lambda: self.set_session_source(sid, "codex")
            )
            act_done = menu.addAction("【已完成】")
            act_done.setCheckable(True)
            act_done.setChecked(done)
            act_done.triggered.connect(lambda: self.toggle_session_done(sid))
            menu.addSeparator()

            menu.addAction(
                "在此会话下新建思维导图",
                lambda: self.new_mindmap(session_id=sid, folder_id=None),
            )
            menu.addAction(
                "在此会话下新建文档",
                lambda: self.new_document(session_id=sid, folder_id=None),
            )

            copy_menu = menu.addMenu("复制到")
            self._fill_folder_dest_menu(
                copy_menu, lambda fid: self.copy_session_to(sid, fid)
            )
            move_menu = menu.addMenu("移动到")
            current_folder = None if session is None else session.get("folder_id")
            self._fill_folder_dest_menu(
                move_menu,
                lambda fid: self.move_session(sid, fid),
                skip_folder_id=current_folder,
                skip_root=current_folder is None,
            )
            move_subj = menu.addMenu("移动到课题")
            self._fill_subject_dest_menu(
                move_subj,
                lambda i: self.move_session_to_subject(sid, i),
                skip_id=self._current_subject_id,
            )

            menu.addAction("导出 Markdown", self.export_session)
            if session and session.get("match_color"):
                peers = self._matched_sessions(session)
                color_name = MATCH_COLORS.get(
                    session["match_color"], {}
                ).get("name", "匹配")
                menu.addAction(
                    f"导出匹配的全部对话（{color_name} · {len(peers)} 个）",
                    lambda sid=sid: self.export_matched_sessions(sid),
                )
                menu.addAction(
                    "取消颜色匹配",
                    lambda: self._clear_session_match(sid),
                )
            menu.addSeparator()
            menu.addAction("删除会话", self.delete_session)

        menu.exec(self._tree.mapToGlobal(pos))
