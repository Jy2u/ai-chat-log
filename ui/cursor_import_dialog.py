"""Cursor / Codex 会话选择弹窗（液态玻璃风）。"""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from codex_import import (
    GROUP_AGENTS,
    GROUP_GUARDIAN,
    GROUP_LABELS,
    codex_snapshot_host,
    with_host_suffix,
)
from ui.icons import _make_folder_icon

from ui.style import apply_glass_shadow


class CursorImportDialog(QDialog):
    def __init__(
        self,
        conversations,
        parent=None,
        source_name="Cursor",
        source_loader=None,
        initial_hint="",
    ):
        super().__init__(parent)
        self.setObjectName("glassNoteDialog")
        self.setWindowTitle("导入对话")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.resize(960, 620)
        self._source = source_name.strip().lower() or "cursor"
        self._source_loader = source_loader
        self._source_context = None
        self._conversations = list(conversations)
        self._source_states = {
            self._source: (self._conversations, None, initial_hint),
        }
        self._drag_pos = None

        panel = QFrame()
        panel.setObjectName("glassNotePanel")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        apply_glass_shadow(panel, "dialog")

        source_switch = QFrame()
        source_switch.setObjectName("importSourceSwitch")
        source_switch.setAttribute(Qt.WA_StyledBackground, True)
        source_layout = QHBoxLayout(source_switch)
        source_layout.setContentsMargins(3, 3, 3, 3)
        source_layout.setSpacing(0)
        self._source_group = QButtonGroup(self)
        self._source_group.setExclusive(True)
        self._source_buttons = {}
        for source, label in (("cursor", "Cursor 导入对话"), ("codex", "Codex 导入对话")):
            button = QPushButton(label)
            button.setObjectName("importSourceButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, selected=source: self._switch_source(selected)
            )
            self._source_group.addButton(button)
            self._source_buttons[source] = button
            source_layout.addWidget(button)
        self._source_buttons.get(self._source, self._source_buttons["cursor"]).setChecked(True)

        hint_wrap = QFrame()
        hint_wrap.setObjectName("importHint")
        hint_wrap.setAttribute(Qt.WA_StyledBackground, True)
        hint_layout = QHBoxLayout(hint_wrap)
        hint_layout.setContentsMargins(15, 7, 9, 7)
        hint_layout.setSpacing(10)
        self._hint = QLabel()
        self._hint.setObjectName("importHintText")
        self._hint.setWordWrap(True)
        hint_layout.addWidget(self._hint, 1)
        self._choose_snapshot = QPushButton("重新选择压缩包")
        self._choose_snapshot.setObjectName("importChooseSnapshot")
        self._choose_snapshot.setCursor(Qt.PointingHandCursor)
        self._choose_snapshot.clicked.connect(
            lambda: self._switch_source("codex", force_reload=True)
        )
        hint_layout.addWidget(self._choose_snapshot)

        table = QTableWidget(0, 4)
        table.setObjectName("importTable")
        table.setHorizontalHeaderLabels(["标题", "工作区", "更新时间", "对话轮数"])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setShowGrid(False)
        table.setFrameShape(QFrame.NoFrame)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(34)
        table.horizontalHeader().setHighlightSections(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        table.horizontalHeader().setStretchLastSection(True)
        table.setColumnWidth(0, 280)
        table.setColumnWidth(1, 330)
        table.setColumnWidth(2, 145)
        table.setColumnWidth(3, 90)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.setTextElideMode(Qt.ElideNone)
        table.doubleClicked.connect(self._accept_available)
        table.itemSelectionChanged.connect(self._sync_accept)

        tree = QTreeWidget()
        tree.setObjectName("importTree")
        tree.setColumnCount(4)
        tree.setHeaderLabels(["标题", "工作区", "更新时间", "对话轮数"])
        tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tree.setFrameShape(QFrame.NoFrame)
        tree.setIndentation(18)
        tree.setRootIsDecorated(True)
        tree.setUniformRowHeights(True)
        tree.setAllColumnsShowFocus(True)
        tree.setAnimated(False)
        tree.header().setHighlightSections(False)
        tree.header().setStretchLastSection(True)
        tree.header().setSectionResizeMode(QHeaderView.Fixed)
        tree.setColumnWidth(0, 280)
        tree.setColumnWidth(1, 330)
        tree.setColumnWidth(2, 145)
        tree.setColumnWidth(3, 90)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        tree.setTextElideMode(Qt.ElideNone)
        tree.setVisible(False)
        tree.itemDoubleClicked.connect(self._on_tree_double_clicked)
        tree.itemSelectionChanged.connect(self._sync_accept)

        table_wrap = QFrame()
        table_wrap.setObjectName("importTableWrap")
        table_wrap.setAttribute(Qt.WA_StyledBackground, True)
        apply_glass_shadow(table_wrap)
        wrap_layout = QVBoxLayout(table_wrap)
        wrap_layout.setContentsMargins(6, 6, 6, 6)
        wrap_layout.addWidget(table)
        wrap_layout.addWidget(tree)

        self._select_all = QPushButton("全选")
        self._select_all.setObjectName("importSelectAll")
        self._select_all.setCursor(Qt.PointingHandCursor)
        self._select_all.clicked.connect(self._toggle_select_all)

        self._cancel = QPushButton("取消")
        self._cancel.setObjectName("glassNoteCancel")
        self._cancel.setCursor(Qt.PointingHandCursor)
        self._cancel.clicked.connect(self.reject)

        self._ok = QPushButton("导入")
        self._ok.setObjectName("glassNoteOk")
        self._ok.setCursor(Qt.PointingHandCursor)
        self._ok.setDefault(True)
        self._ok.clicked.connect(self._accept_available)
        apply_glass_shadow(self._ok, "button")

        btns = QHBoxLayout()
        btns.setContentsMargins(0, 0, 0, 0)
        btns.setSpacing(10)
        btns.addWidget(self._select_all)
        btns.addStretch(1)
        btns.addWidget(self._cancel)
        btns.addWidget(self._ok)

        inner = QVBoxLayout(panel)
        inner.setContentsMargins(20, 18, 20, 18)
        inner.setSpacing(13)
        inner.addWidget(source_switch, 0, Qt.AlignHCenter)
        inner.addWidget(hint_wrap)
        inner.addWidget(table_wrap, 1)
        inner.addLayout(btns)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 34)
        outer.addWidget(panel)

        self._table = table
        self._tree = tree
        self._grouped = False
        self._apply_source_state()

    def selected_source(self):
        return self._source

    def source_context(self):
        return self._source_context

    def selected_conversations(self) -> list:
        """按当前列表从上到下返回选中的对话。选中文件夹时包含其中全部对话。"""
        if self._grouped:
            return self._selected_from_tree()
        if self._table.selectionModel() is None:
            return []
        rows = sorted({
            index.row() for index in self._table.selectionModel().selectedRows()
        })
        return [
            self._conversations[row]
            for row in rows
            if 0 <= row < len(self._conversations)
        ]

    def _conversation_group(self, info) -> str:
        group = getattr(info, "group", "") or ""
        return group if group in GROUP_LABELS else ""

    def _selected_from_tree(self) -> list:
        picked = self._tree.selectedItems()
        chosen = []
        for item in self._iter_conversation_items():
            parent = item.parent()
            if item in picked or (parent is not None and parent in picked):
                row = item.data(0, Qt.UserRole)
                if isinstance(row, int) and 0 <= row < len(self._conversations):
                    chosen.append(self._conversations[row])
        return chosen

    def _iter_conversation_items(self):
        root = self._tree.invisibleRootItem()
        for index in range(root.childCount()):
            item = root.child(index)
            if item.data(0, Qt.UserRole + 1) == "folder":
                for child_index in range(item.childCount()):
                    yield item.child(child_index)
            else:
                yield item

    def selected_conversation(self):
        chosen = self.selected_conversations()
        return chosen[0] if chosen else None

    def _default_hint(self) -> str:
        if self._source == "codex":
            if self._source_context:
                return (
                    f"已读取本地 Codex 快照：{self._source_context}。"
                    "按住 Ctrl 或 Shift 可多选，然后一次导入到当前文件夹，不会修改压缩包。"
                    "若夹内已有内容大量重合的对话，只会补上新消息，并保留你改过的标题。"
                )
            return (
                "选择服务器下载到本机的 Codex tar.gz 快照。"
                "按住 Ctrl 或 Shift 可多选，然后一次导入。"
                "若当前文件夹里已有内容大量重合的对话，只会补上新消息。"
            )
        return (
            "按住 Ctrl 或 Shift 可多选 Cursor 对话，然后一次导入到当前文件夹。"
            "列表只读取本机缓存，不会修改原始数据。"
        )

    def _display_title(self, info) -> str:
        title = getattr(info, "title", "") or ""
        if self._source == "codex" and self._source_context:
            return with_host_suffix(title, codex_snapshot_host(self._source_context))
        return title

    def _row_values(self, info) -> tuple:
        updated = "—"
        if info.updated_ms or info.created_ms:
            updated = datetime.fromtimestamp(
                (info.updated_ms or info.created_ms) / 1000
            ).strftime("%Y-%m-%d %H:%M")
        return (
            self._display_title(info),
            info.workspace or "未知工作区",
            updated,
            str(info.message_count),
        )

    def _populate_table(self):
        self._table.clearContents()
        self._table.setRowCount(len(self._conversations))
        for row, info in enumerate(self._conversations):
            for col, value in enumerate(self._row_values(info)):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                item.setData(Qt.UserRole, row)
                if col >= 2:
                    item.setTextAlignment(Qt.AlignCenter)
                self._table.setItem(row, col, item)
        if self._conversations:
            self._table.selectRow(0)
            self._table.setFocus()

    def _add_conversation_item(self, parent, row: int, info) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent, [str(value) for value in self._row_values(info)])
        item.setData(0, Qt.UserRole, row)
        item.setData(0, Qt.UserRole + 1, "conversation")
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        for column in range(item.columnCount()):
            item.setToolTip(column, item.text(column))
        item.setTextAlignment(2, Qt.AlignCenter)
        item.setTextAlignment(3, Qt.AlignCenter)
        return item

    def _populate_tree(self):
        self._tree.clear()
        buckets = {GROUP_GUARDIAN: [], GROUP_AGENTS: [], "": []}
        for row, info in enumerate(self._conversations):
            buckets[self._conversation_group(info)].append((row, info))
        icon = _make_folder_icon()
        for key in (GROUP_GUARDIAN, GROUP_AGENTS):
            rows = buckets[key]
            if not rows:
                continue
            folder = QTreeWidgetItem(self._tree, [f"{GROUP_LABELS[key]}（{len(rows)}）", "", "", ""])
            folder.setData(0, Qt.UserRole + 1, "folder")
            folder.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            folder.setIcon(0, icon)
            font = folder.font(0)
            font.setBold(True)
            folder.setFont(0, font)
            for row, info in rows:
                self._add_conversation_item(folder, row, info)
            folder.setExpanded(False)
        first = None
        for row, info in buckets[""]:
            item = self._add_conversation_item(self._tree, row, info)
            if first is None:
                first = item
        if first is not None:
            self._tree.setCurrentItem(first)
            first.setSelected(True)
            self._tree.setFocus()

    def _populate(self):
        self._grouped = any(self._conversation_group(info) for info in self._conversations)
        self._table.setVisible(not self._grouped)
        self._tree.setVisible(self._grouped)
        if self._grouped:
            self._populate_tree()
        else:
            self._tree.clear()
            self._populate_table()

    def _apply_source_state(self):
        conversations, context, hint = self._source_states.get(
            self._source, ([], None, "")
        )
        self._conversations = list(conversations)
        self._source_context = context
        self.setWindowTitle(f"从 {self._source.title()} 导入对话")
        self._source_buttons[self._source].setChecked(True)
        self._choose_snapshot.setVisible(self._source == "codex")
        text = hint or self._default_hint()
        if any(self._conversation_group(info) for info in self._conversations):
            text += " Guardian review 和 AGENTS.md 分开展示在两个文件夹里。"
        self._hint.setText(text)
        self._populate()
        self._sync_accept()

    def _switch_source(self, source: str, force_reload: bool = False):
        source = source.lower()
        previous = self._source
        if source == previous and not force_reload:
            return
        if force_reload or source not in self._source_states:
            if self._source_loader is None:
                self._source_states[source] = ([], None, "")
            else:
                try:
                    loaded = self._source_loader(source, self, force_reload)
                except Exception as exc:
                    QMessageBox.critical(self, f"无法读取 {source.title()}", str(exc))
                    self._source_buttons[previous].setChecked(True)
                    return
                if loaded is None:
                    self._source_buttons[previous].setChecked(True)
                    return
                conversations, context, hint = loaded
                self._source_states[source] = (list(conversations), context, hint)
        self._source = source
        self._apply_source_state()

    def _toggle_select_all(self):
        if not self._conversations:
            return
        everything = len(self.selected_conversations()) == len(self._conversations)
        if self._grouped:
            self._tree.clearSelection()
            if not everything:
                for item in self._iter_conversation_items():
                    item.setSelected(True)
            return
        if everything:
            self._table.clearSelection()
        else:
            self._table.selectAll()

    def _on_tree_double_clicked(self, item, _column):
        if item is not None and item.data(0, Qt.UserRole + 1) == "conversation":
            self._accept_available()

    def _sync_accept(self):
        count = len(self.selected_conversations())
        total = len(self._conversations)
        self._ok.setEnabled(count > 0)
        self._ok.setText("导入" if count <= 1 else f"导入 {count} 个")
        self._select_all.setEnabled(total > 0)
        self._select_all.setText("取消全选" if total and count == total else "全选")

    def _accept_available(self, *_):
        if self._ok.isEnabled():
            self.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._over_table(event):
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def _over_table(self, event) -> bool:
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        w = self.childAt(pos)
        while w is not None and w is not self:
            if w is self._table or w is self._tree:
                return True
            w = w.parentWidget()
        return False
