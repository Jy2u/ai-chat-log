"""Cursor 会话选择弹窗。"""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class CursorImportDialog(QDialog):
    def __init__(self, conversations, parent=None, source_name="Cursor"):
        super().__init__(parent)
        self.setWindowTitle(f"从 {source_name} 导入对话")
        self.resize(920, 600)
        self._conversations = list(conversations)

        layout = QVBoxLayout(self)
        hint = QLabel(
            f"选择一个 {source_name} 对话导入到当前文件夹。列表只读取本机缓存，"
            "不会修改原始数据。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        table = QTableWidget(len(self._conversations), 4)
        table.setHorizontalHeaderLabels(["标题", "工作区", "更新时间", "对话轮数"])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
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
                table.setItem(row, col, item)
        table.horizontalHeader().setStretchLastSection(True)
        table.setColumnWidth(0, 280)
        table.setColumnWidth(1, 330)
        table.setColumnWidth(2, 145)
        table.setColumnWidth(3, 90)
        table.doubleClicked.connect(self._accept_available)
        table.itemSelectionChanged.connect(self._sync_accept)
        layout.addWidget(table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("导入")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._accept_available)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._table = table
        self._buttons = buttons
        if self._conversations:
            table.selectRow(0)
        self._sync_accept()

    def selected_conversation(self):
        row = self._table.currentRow()
        return self._conversations[row] if 0 <= row < len(self._conversations) else None

    def _sync_accept(self):
        info = self.selected_conversation()
        self._buttons.button(QDialogButtonBox.Ok).setEnabled(info is not None)

    def _accept_available(self, *_):
        if self._buttons.button(QDialogButtonBox.Ok).isEnabled():
            self.accept()
