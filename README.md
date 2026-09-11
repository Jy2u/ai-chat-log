# AI 对话记录器

复制文字或图片后，用悬浮条记成提问 / 回答。会话、文件夹、思维导图都存在本目录的 `data/chatlog.db`。

## 运行

```text
pip install -r requirements.txt
python main.py
```

Windows 下也可以双击 `启动.bat`。关闭窗口会缩到托盘，需在托盘图标上退出。

已开启开机自启时，启动命令已指向本目录的 `main.py`。

## 数据

- `data/chatlog.db`：会话、消息、思维导图
- `data/images/`：聊天里的图片
- `data/view.html`：当前界面缓存，可忽略
