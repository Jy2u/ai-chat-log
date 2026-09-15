"""Cursor 会话选择弹窗（液态玻璃风）。"""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ui.style import apply_glass_shadow


class CursorImportDialog(QDialog):
    def __init__(self, conversations, parent=None, source_name="Cursor"):
        super().__init__(parent)
        self.setObjectName("glassNoteDialog")
        self.setWindowTitle(f"从 {source_name} 导入对话")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.resize(960, 620)
        self._conversations = list(conversations)
        self._drag_pos = None

        panel = QFrame()
        panel.setObjectName("glassNotePanel")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        apply_glass_shadow(panel, "dialog")

        title = QLabel(f"从 {source_name} 导入对话")
        title.setObjectName("glassNoteTitle")
        title.setAlignment(Qt.AlignCenter)

        hint = QLabel(
            f"选择一个 {source_name} 对话导入到当前文件夹。列表只读取本机缓存，"
            "不会修改原始数据。"
        )
        hint.setObjectName("importHint")
        hint.setWordWrap(True)

        table = QTableWidget(len(self._conversations), 4)
        table.setObjectName("importTable")
        table.setHorizontalHeaderLabels(["标题", "工作区", "更新时间", "对话轮数"])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setShowGrid(False)
        table.setFrameShape(QFrame.NoFrame)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(34)
        table.horizontalHeader().setHighlightSections(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        table.horizontalHeader().setStretchLastSection(True)
        for row, info in enumerate(self._conversations):
            updated = "—"
            if info.updated_ms or info.created_ms:
                updated = datetime.fromtimestamp(
                    (info.updated_ms or info.created_ms) / 1000
                ).strftime("%Y-%m-%d %H:%M")
            values = (
                info.title,
                info.workspace or "未知工作区",
                updated,
                str(info.message_count),
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, row)
                if col >= 2:
                    item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, col, item)
        table.setColumnWidth(0, 280)
        table.setColumnWidth(1, 330)
        table.setColumnWidth(2, 145)
        table.setColumnWidth(3, 90)
        table.doubleClicked.connect(self._accept_available)
        table.itemSelectionChanged.connect(self._sync_accept)

        table_wrap = QFrame()
        table_wrap.setObjectName("importTableWrap")
        table_wrap.setAttribute(Qt.WA_StyledBackground, True)
        apply_glass_shadow(table_wrap)
        wrap_layout = QVBoxLayout(table_wrap)
        wrap_layout.setContentsMargins(6, 6, 6, 6)
        wrap_layout.addWidget(table)

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
        btns.addStretch(1)
        btns.addWidget(self._cancel)
        btns.addWidget(self._ok)

        inner = QVBoxLayout(panel)
        inner.setContentsMargins(20, 18, 20, 18)
        inner.setSpacing(13)
        inner.addWidget(title, 0, Qt.AlignHCenter)
        inner.addWidget(hint)
        inner.addWidget(table_wrap, 1)
        inner.addLayout(btns)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 34)
        outer.addWidget(panel)

        self._table = table
        if self._conversations:
            table.selectRow(0)
            table.setFocus()
        self._sync_accept()

    def selected_conversation(self):
        row = self._table.currentRow()
        return self._conversations[row] if 0 <= row < len(self._conversations) else None

    def _sync_accept(self):
        self._ok.setEnabled(self.selected_conversation() is not None)

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
            if w is self._table:
                return True
            w = w.parentWidget()
        return False
