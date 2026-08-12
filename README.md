# SEELE Maya Transfer (initial MVP)

这是 SEELE → Maya 2022+ 插件的首版骨架，遵循 `dcc-transfer.v1`：仅 loopback
HTTP receiver、FBX manifest 校验、安全 staging、transfer 状态管理和可替换的
Maya importer。运行时只依赖 Python 标准库；在 Maya 中再由 `maya.cmds` 适配器接管导入。

## 本地运行（不需要 Maya）

```powershell
python -m unittest discover -s tests
python -m seele_maya.bridge.server
```

默认监听 `127.0.0.1:9879`。允许来源和下载 host 可通过环境变量
`SEELE_ALLOWED_ORIGINS`、`SEELE_ALLOWED_DOWNLOAD_HOSTS`（逗号分隔）配置。

提交 manifest 后会自动执行下载、校验和导入；下载地址必须是 HTTPS 且 host
在 `SEELE_ALLOWED_DOWNLOAD_HOSTS` 中。没有 Maya 时使用 mock importer，便于
联调 HTTP 协议；在 Maya 中会自动切换到 `fbxmaya`。

取消任务：`POST /v1/transfers/{transferId}/cancel`。

## Maya 安装

将 `SeeleMaya.mod` 和 `SeeleMaya/` 放入 Maya modules 目录，然后在 Plug-in
Manager 加载 `seele_maya_plugin.py`。插件入口会优雅降级到 mock importer，真实
Maya 环境中可启用 FBX importer。
