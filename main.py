"""AI 对话记录器：复制即记录，悬浮条归档，气泡流回看。

运行：python main.py
依赖：PySide6、markdown-it-py、pygments
"""

import hashlib
import os
import subprocess
import sys
import time
from datetime import datetime


def _crash_log_path():
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "last_error.txt"
    )


def _install_crash_log():
    """pythonw 没有控制台，启动失败时把堆栈写到 data/last_error.txt。"""

    def hook(typ, val, tb):
        try:
            path = _crash_log_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            import traceback

            with open(path, "w", encoding="utf-8") as f:
                traceback.print_exception(typ, val, tb, file=f)
        except Exception:
            pass
        sys.__excepthook__(typ, val, tb)

    sys.excepthook = hook


_install_crash_log()

# 关掉 Chromium 中键自动滚屏，否则思维导图的中键框选会被吞掉
_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
_mid = "--disable-features=MiddleClickAutoscroll"
if _mid not in _flags:
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        (_flags + " " + _mid).strip() if _flags else _mid
    )

# QtWebEngine 要求在创建 QApplication 之前完成导入
import main_window  # noqa: F401

from PySide6.QtCore import QBuffer, QIODevice, QObject, Qt, QUrl, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QImage,
    QLinearGradient,
    QPainter,
    QPixmap,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from db import IMAGES_DIR, Database
from float_bar import FloatBar
from main_window import APP_QSS, MainWindow

SINGLE_INSTANCE_KEY = "ai-chat-logger-single-instance"

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")

# 密码管理器（1Password/KeePass 等）复制敏感内容时会带上这些剪贴板标记，
# 约定俗成：剪贴板工具见到它们就不该记录、不该展示
_PRIVACY_FORMATS = (
    "ExcludeClipboardContentFromMonitorProcessing",
    "Clipboard Viewer Ignore",
)
_HISTORY_OPT_OUT = "CanIncludeInClipboardHistory"


def _mime_marked_private(mime) -> bool:
    """剪贴板内容是否带有"请勿监听/记录"标记。

    Windows 原生格式经 Qt 转换后可能以
    application/x-qt-windows-mime;value="..." 的形式出现，两种都查。
    """
    def variants(name):
        return (name, f'application/x-qt-windows-mime;value="{name}"')

    for name in _PRIVACY_FORMATS:
        for fmt in variants(name):
            if mime.hasFormat(fmt):
                return True
    for fmt in variants(_HISTORY_OPT_OUT):
        if mime.hasFormat(fmt):
            # DWORD 0 表示"不许进剪贴板历史"
            if bytes(mime.data(fmt))[:4] == b"\x00\x00\x00\x00":
                return True
    return False


def make_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    grad = QLinearGradient(0, 0, 64, 64)
    grad.setColorAt(0.0, QColor("#5b7cfa"))
    grad.setColorAt(1.0, QColor("#4a63f0"))
    p.setBrush(QBrush(grad))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(0, 0, 64, 64, 14, 14)
    p.setBrush(QColor(255, 255, 255, 235))
    p.drawRoundedRect(12, 14, 30, 16, 8, 8)
    p.setBrush(QColor(255, 255, 255, 170))
    p.drawRoundedRect(22, 36, 30, 16, 8, 8)
    p.end()
    return QIcon(pm)


class ClipboardWatcher(QObject):
    """监听系统剪贴板的文本/图片变化，带去重与自我复制抑制。"""

    new_text = Signal(str)
    new_image = Signal(QImage)

    def __init__(self, app: QApplication):
        super().__init__()
        self._clipboard = app.clipboard()
        self._clipboard.dataChanged.connect(self._on_change)
        self._last_text = ""
        self._last_time = 0.0
        self._suppress_once = False

    def suppress_next(self):
        """忽略下一次剪贴板变化（应用内"复制原文/图片"时用）。"""
        self._suppress_once = True

    def _on_change(self):
        if self._suppress_once:
            self._suppress_once = False
            return
        mime = self._clipboard.mimeData()
        if mime is None:
            return
        if _mime_marked_private(mime):
            return

        image = self._image_from_mime(mime)
        if image is not None:
            self.new_image.emit(image)
            return

        if not mime.hasText():
            return
        text = self._clipboard.text()
        if len(text.strip()) < 2:
            return
        # 部分应用一次复制会触发多次信号，短时间内的相同内容只处理一次
        now = time.monotonic()
        if text == self._last_text and now - self._last_time < 1.5:
            self._last_time = now
            return
        self._last_text = text
        self._last_time = now
        self.new_text.emit(text)

    def _image_from_mime(self, mime):
        """尽力从剪贴板取出图片。

        兼容三种形式：位图数据（截图工具）、文件 URL（资源管理器/微信）、
        指向图片文件的纯文本路径（微信复制聊天图片时的形式）。
        """
        if mime.hasImage():
            image = self._clipboard.image()
            if not image.isNull():
                return image
        if mime.hasUrls():
            urls = mime.urls()
            if len(urls) == 1 and urls[0].isLocalFile():
                path = urls[0].toLocalFile()
                if path.lower().endswith(IMAGE_EXTS):
                    image = QImage(path)
                    if not image.isNull():
                        return image
        if mime.hasText():
            text = mime.text().strip().strip('"')
            path = None
            if text.lower().startswith("file:///"):
                path = QUrl(text).toLocalFile()
            elif len(text) > 3 and text[1] == ":" and text[0].isalpha():
                path = text
            if path and path.lower().endswith(IMAGE_EXTS):
                image = QImage(path)
                if not image.isNull():
                    return image
        return None


def _allow_set_foreground():
    """把前台权限让给已在运行的实例，否则双击图标后窗口可能被系统挡住。"""
    try:
        import ctypes

        ctypes.windll.user32.AllowSetForegroundWindow(-1)
    except Exception:
        pass


def _bring_to_front(window):
    window.setWindowState(window.windowState() & ~Qt.WindowMinimized)
    window.show()
    window.showNormal()
    window.raise_()
    window.activateWindow()
    try:
        import ctypes

        hwnd = int(window.winId())
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
    except Exception:
        pass


def _spawn_restart():
    """等本进程退出后再拉起 main.py，避免单实例锁还没释放。"""
    app_dir = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(app_dir, "main.py")
    exe = sys.executable
    pid = os.getpid()
    waiter = (
        "import subprocess, time, ctypes\n"
        f"pid = {pid}\n"
        "k = ctypes.windll.kernel32\n"
        "h = k.OpenProcess(0x100000, False, pid)\n"
        "if h:\n"
        "    k.WaitForSingleObject(h, 10000)\n"
        "    k.CloseHandle(h)\n"
        "else:\n"
        "    time.sleep(0.8)\n"
        f"subprocess.Popen({[exe, script]!r}, cwd={app_dir!r})\n"
    )
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    subprocess.Popen(
        [exe, "-c", waiter],
        cwd=app_dir,
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )


def main():
    try:  # 让任务栏使用我们自己的图标而不是 python 的
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "little-tools.ai-chat-logger"
        )
    except Exception:
        pass

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    app.setApplicationName("AI 对话记录器")
    app.setQuitOnLastWindowClosed(False)

    # 单实例：已有实例在运行时，通知它显示主窗口，然后本进程直接退出
    probe = QLocalSocket()
    probe.connectToServer(SINGLE_INSTANCE_KEY)
    if probe.waitForConnected(300):
        _allow_set_foreground()
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(300)
        probe.waitForReadyRead(400)
        probe.disconnectFromServer()
        return
    QLocalServer.removeServer(SINGLE_INSTANCE_KEY)  # 清理异常退出的残留
    single_server = QLocalServer()
    single_server.listen(SINGLE_INSTANCE_KEY)

    app.setStyleSheet(APP_QSS)
    icon = make_icon()
    app.setWindowIcon(icon)

    db = Database()
    if not db.list_sessions():
        db.create_session(datetime.now().strftime("%Y-%m-%d"))

    window = MainWindow(db)
    bar = FloatBar()
    watcher = ClipboardWatcher(app)
    window.set_suppress_callback(watcher.suppress_next)

    def on_new_text(text: str):
        if not window.pause_action.isChecked():
            bar.show_for(text)

    def on_new_image(image: QImage):
        if not window.pause_action.isChecked():
            bar.show_for_image(image)

    watcher.new_text.connect(on_new_text)
    watcher.new_image.connect(on_new_image)

    def save_image_file(image: QImage) -> str:
        """图片存到 data/images/，返回文件名。"""
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        image.save(buf, "PNG")
        raw = bytes(buf.data())
        buf.close()
        name = (
            datetime.now().strftime("%Y%m%d-%H%M%S-")
            + hashlib.md5(raw).hexdigest()[:8]
            + ".png"
        )
        os.makedirs(IMAGES_DIR, exist_ok=True)
        with open(os.path.join(IMAGES_DIR, name), "wb") as f:
            f.write(raw)
        return name

    def on_saved(role: str, kind: str, data):
        sid = window.current_session_id()
        if sid is None:
            sid = db.create_session(
                datetime.now().strftime("%Y-%m-%d"),
                subject_id=window.current_subject_id(),
            )
        if kind == "image":
            mid = db.add_message(sid, role, save_image_file(data), kind="image")
            db.auto_name_if_first(sid, "图片")
        else:
            mid = db.add_message(sid, role, data)
            db.auto_name_if_first(sid, data)
        window.notify_message_added(mid, sid)

    bar.saved.connect(on_saved)

    def show_window():
        _bring_to_front(window)

    def on_second_instance():
        conn = single_server.nextPendingConnection()
        if conn is not None:
            conn.waitForReadyRead(300)
            conn.write(b"ok")
            conn.flush()
            conn.waitForBytesWritten(200)
            conn.close()
        show_window()

    single_server.newConnection.connect(on_second_instance)

    def restart_app():
        _spawn_restart()
        app.quit()

    tray = QSystemTrayIcon(icon)
    tray.setToolTip("AI 对话记录器")
    menu = QMenu()
    menu.addAction("显示主窗口", show_window)
    menu.addAction(window.pause_action)
    menu.addAction(window.autostart_action)
    menu.addSeparator()
    menu.addAction("重启", restart_app)
    menu.addAction("退出", app.quit)
    tray.setContextMenu(menu)

    def on_tray_activated(reason):
        if reason in (
            QSystemTrayIcon.Trigger,
            QSystemTrayIcon.DoubleClick,
        ):
            show_window()

    tray.activated.connect(on_tray_activated)
    tray.show()

    notified = []

    def on_hidden():
        if not notified:
            notified.append(True)
            tray.showMessage(
                "AI 对话记录器仍在运行",
                "复制文字仍会弹出悬浮条，可从托盘图标退出。",
                icon,
            )

    window.hidden_to_tray.connect(on_hidden)

    app.aboutToQuit.connect(db.close)
    if "--minimized" not in sys.argv:
        show_window()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
