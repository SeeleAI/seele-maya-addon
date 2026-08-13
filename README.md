# SEELE Maya Transfer 0.2.0

SEELE → Maya 2022+ 的 `dcc-transfer.v1` 接收插件。它提供仅监听 loopback 的 HTTP receiver、manifest 校验、安全 staging、任务状态管理，以及在 Maya 主线程执行的资产导入与回滚。

## 当前格式范围

- FBX、OBJ、ABC：P0 格式；只有真实 Maya runtime probe 通过后才会在 health 中声明 ready。
- DAE：实验性 P1 格式；仅在对应插件、translator 和实际导入入口均通过探测后启用。
- USD、USDA、USDC：0.2.0 明确禁用。当前没有导入 handler 或可启用路径，即使安装了 `mayaUsdPlugin` 也不会声明 ready。
- 普通 Python 环境只提供 mock health、CORS 和 contract 测试，不接受真实 transfer，也不会降级为 mock importer。

OBJ 引用的 MTL 未提供时，插件仍导入几何，并以 `OBJ_MTL_NOT_PROVIDED` 完成 warning；已声明文件的 hash、大小、路径或安全校验失败仍是致命错误。

## Maya 安装

将 `SeeleMaya.mod` 和 `SeeleMaya/` 一起复制到 Maya modules 目录；目录不存在时可以手动创建。例如 Windows：

```text
%USERPROFILE%\Documents\maya\modules\
```

重启 Maya，在 Plug-in Manager 中加载并按需勾选自动加载 `seele_maya_plugin.py`。默认监听 `127.0.0.1:9879`。

## 配置

默认 exact Origin allowlist 包含：

```text
https://code4agent-feature-maya-dcc-server-web.seele.chat
```

`SEELE_ALLOWED_ORIGINS` 和 `SEELE_ALLOWED_DOWNLOAD_HOSTS` 使用逗号分隔，只用于追加可信来源或下载域名；不支持 `*`。插件已经内置 SEELE 官方静态资源、S3、CloudFront 和 Azure Blob 下载域名。下载只允许 HTTPS，且每次 redirect 都必须继续满足 allowlist 和网络安全检查。

## 本地测试（无需 Maya）

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest discover -s tests -v
```

这些测试不等同于 Maya 真机验证。发布前仍需在 Maya 2022+ 的 Windows/macOS 环境运行 load/unload、FBX/OBJ/ABC golden assets、取消/回滚和路径安全测试。
