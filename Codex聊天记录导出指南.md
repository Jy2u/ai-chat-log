# Codex 聊天记录导出指南

适用于 Codex 插件运行在 SSH 远程服务器、聊天记录保存在服务器 `~/.codex` 目录中的情况。

## 1. 在服务器上打包

通过 SSH 登录服务器后执行。有的机器没有归档目录或附件目录，下面这条会自动跳过不存在的项：

```bash
args=()
for name in sessions archived_sessions attachments session_index.jsonl; do
  [ -e "$HOME/.codex/$name" ] && args+=("$name")
done
tar -czf "$HOME/codex-export-latest.tar.gz" -C "$HOME/.codex" "${args[@]}"
```

该命令会把当前 Codex 会话，以及存在的归档会话、标题索引和附件，打包到：

```text
~/codex-export-latest.tar.gz
```

再次执行会覆盖上一次生成的压缩包。

## 2. 下载到 Windows

在 Windows **CMD** 中执行，将 `your-user` 和 `your-server` 替换为自己的 SSH 账号和服务器地址：

```bat
mkdir "E:\CodexExports" 2>nul & scp your-user@your-server:~/codex-export-latest.tar.gz "E:\CodexExports\codex-export-latest.tar.gz"
```

若从多台服务器下载，请使用不同文件名，避免覆盖。例如 `codex-export-192.0.2.10.tar.gz`（这里使用文档示例地址，请替换为自己的地址）。文件名中的 IP 会用于标记导入来源；不含地址的 `codex-export-latest.tar.gz` 可用本机环境变量 `AICHAT_CODEX_LATEST_HOST` 指定来源，未配置则不加来源后缀。

## 3. 导入软件

1. 打开或重启 AI 对话记录器。
2. 点击目标文件夹旁的“导入”。
3. 点击顶部的“Codex 导入对话”。
4. 软件会自动读取上次用过的压缩包；第一次则读取 `E:\CodexExports\codex-export-latest.tar.gz`。
5. 要导入其他快照时，点「重新选择压缩包」，选择对应文件。
6. 选择一个或多个对话并点击“导入”。

软件会保留用户提问、截图和最终回答，并过滤开发者指令、思考过程、工具调用及中间输出。压缩包包含完整聊天内容和截图，请妥善保管。

## 4. 从软件导出 Markdown

导入完成后，右键会话并选择“导出 Markdown”。会话截图会以 Base64 直接写进 `.md` 文件，不需要额外携带 `images` 文件夹。包含较多截图时，Markdown 文件会相应变大。
