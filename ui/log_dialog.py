"""操作日志查看窗口。"""

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


class ActivityLogDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db
        self.setObjectName("glassNoteDialog")
        self.setWindowTitle("操作日志")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.resize(860, 560)
        self._drag_pos = None

        panel = QFrame()
        panel.setObjectName("glassNotePanel")
        panel.setAttribute(Qt.WA_StyledBackground, True)
        apply_glass_shadow(panel, "dialog")

        title = QLabel("操作日志")
        title.setObjectName("glassNoteTitle")
        title.setAlignment(Qt.AlignCenter)

        hint = QLabel(
            "新建、修改、导入、导出、备份、待办和常用栏都会记在这里。"
            "连续编辑文档或拖动导图会合并成一条。"
            "密钥和账号密码的正文不会写入日志。"
        )
        hint.setObjectName("importHintText")
        hint.setWordWrap(True)

        table = QTableWidget(0, 3)
        table.setObjectName("importTable")
        table.setHorizontalHeaderLabels(["时间", "操作", "详情"])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setShowGrid(False)
        table.setFrameShape(QFrame.NoFrame)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(32)
        table.horizontalHeader().setHighlightSections(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.setColumnWidth(0, 168)
        table.setColumnWidth(1, 128)
        self._table = table

        wrap = QFrame()
        wrap.setObjectName("importTableWrap")
        wrap.setAttribute(Qt.WA_StyledBackground, True)
        apply_glass_shadow(wrap)
        wrap_lay = QVBoxLayout(wrap)
        wrap_lay.setContentsMargins(6, 6, 6, 6)
        wrap_lay.addWidget(table)

        refresh = QPushButton("刷新")
        refresh.setObjectName("importSelectAll")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.clicked.connect(self.reload)

        close = QPushButton("关闭")
        close.setObjectName("glassNoteOk")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.accept)
        apply_glass_shadow(close, "button")

        btns = QHBoxLayout()
        btns.addWidget(refresh)
        btns.addStretch(1)
        btns.addWidget(close)

        inner = QVBoxLayout(panel)
        inner.setContentsMargins(20, 18, 20, 18)
        inner.setSpacing(12)
        inner.addWidget(title, 0, Qt.AlignHCenter)
        inner.addWidget(hint)
        inner.addWidget(wrap, 1)
        inner.addLayout(btns)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 34)
        outer.addWidget(panel)
        self.reload()

    def reload(self):
        rows = self._db.list_activity(500)
        self._table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            values = (row["created_at"], row["action"], row["detail"])
            for col, value in enumerate(values):
                item = QTableWidgetItem(value or "")
                if col < 2:
                    item.setTextAlignment(Qt.AlignCenter)
                self._table.setItem(index, col, item)
        if not rows:
            self._table.setRowCount(1)
            empty = QTableWidgetItem("还没有操作记录")
            empty.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(0, 2, empty)

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
        widget = self.childAt(pos)
        while widget is not None and widget is not self:
            if widget is self._table:
                return True
            widget = widget.parentWidget()
        return False
