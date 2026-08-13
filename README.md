# SEELE Maya Transfer 0.2.0

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
默认 exact Origin allowlist 包含
`https://code4agent-feature-maya-dcc-server-web.seele.chat`；环境变量配置只会追加
完整 Origin，不启用通配符或后缀匹配。

提交 manifest 后会自动执行下载、校验和导入；下载地址必须是 HTTPS 且 host
在 approved download host allowlist 中。插件内置 SEELE 官方静态资源、S3、
CloudFront 和 Azure Blob 域名；`SEELE_ALLOWED_DOWNLOAD_HOSTS` 仅用于追加 feature
或测试域名，不支持 `*`。普通 Python 环境使用 mock readiness，
只供 health、CORS 和错误 contract 测试，不接受真实 transfer；Maya 中会使用
`fbxmaya`。P0 格式为 FBX、OBJ、ABC；DAE、USD、USDA、USDC 仅在当前 Maya
runtime 的 importer/translator 真实探测为 ready 时才会出现在 health `formats`。

取消任务：`POST /v1/transfers/{transferId}/cancel`。

`GET /v1/health` 只会在真实 Maya 环境中成功加载 `fbxmaya` 后声明 `fbx`
capability；普通 Python 启动仅用于检查 receiver contract，不接受真实 transfer。

## Maya 安装

将 `SeeleMaya.mod` 和 `SeeleMaya/` 放入 Maya modules 目录，然后在 Plug-in
Manager 加载 `seele_maya_plugin.py`。只有 `fbxmaya` 成功加载时才会声明并接受
FBX transfer。
