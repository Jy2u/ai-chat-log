"""开机自启动开关：写入/移除当前用户注册表的 Run 键。"""

import os
import sys
import winreg

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "AIChatLogger"


def _command() -> str:
    """优先用 pythonw.exe 启动，开机时不会弹出控制台窗口。"""
    exe_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(exe_dir, "pythonw.exe")
    exe = pythonw if os.path.exists(pythonw) else sys.executable
    script = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "main.py"
    )
    # --minimized：开机启动时不弹主窗口，静默缩在托盘
    return f'"{exe}" "{script}" --minimized'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _VALUE_NAME)
        return True
    except OSError:
        return False


def set_enabled(on: bool):
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        if on:
            # 每次开启都重写命令，项目挪了位置只要重新勾选一次即可修正
            winreg.SetValueEx(
                key, _VALUE_NAME, 0, winreg.REG_SZ, _command()
            )
        else:
            try:
                winreg.DeleteValue(key, _VALUE_NAME)
            except FileNotFoundError:
                pass
