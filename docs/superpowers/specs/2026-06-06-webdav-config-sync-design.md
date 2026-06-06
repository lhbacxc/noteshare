# WebDAV 配置同步设计

## 背景

当前应用的 R2 连接信息、Worker 管理信息、URL 状态和日志等级都保存在本地 `config.json` 中。更换电脑、重装应用或需要快速恢复配置时，需要手动复制这个文件，不够方便。

本次目标是增加一个轻量的 WebDAV 同步通道，让用户可以把本地 `config.json` 上传到 WebDAV，也可以从 WebDAV 下载配置并恢复到本地。

## 功能目标

- 在连接配置区增加 WebDAV 账号配置。
- 支持保存以下字段到 `config.json`：
  - `webdav_url`
  - `webdav_username`
  - `webdav_password`
  - `webdav_remote_path`
- 支持点击“上传配置”把当前本地配置同步到 WebDAV。
- 支持点击“下载配置”从 WebDAV 拉取远端配置，校验成功后覆盖本地 `config.json` 并刷新界面。
- WebDAV 同步走后台任务，避免网络请求阻塞界面。

## 同步对象

本轮只同步根目录的本地配置文件：

```text
config.json
```

不同步以下运行期文件：

- `upload_resume_state.json`
- `logs/noteshare.log`
- 打包产物
- 临时缓存

原因是这些文件属于本机运行状态或排查信息，不适合跨设备直接覆盖。

## 交互设计

连接配置区新增四个字段：

- `WebDAV URL`：WebDAV 服务根地址。
- `WebDAV 用户名`：账号名，可为空以支持匿名或 token URL 场景。
- `WebDAV 密码`：密码或应用专用密码，输入框隐藏显示。
- `WebDAV 远端路径`：远端配置文件路径，默认 `noteshare/config.json`。

连接配置区按钮新增：

- `上传配置`
- `下载配置`

上传配置时先保存当前表单到本地 `config.json`，再上传这个文件，保证远端拿到的是当前界面最新配置。

下载配置时先读取远端文件并按现有配置清洗逻辑校验；只有确认是可用 JSON 配置后，才覆盖本地 `config.json` 并刷新界面字段、bucket 下拉框、日志等级和连接配置摘要。

## 实现结构

新增 `webdav_sync.py`，负责：

- WebDAV 字段清洗和校验。
- 拼接远端文件 URL。
- 创建远端目录。
- 上传本地配置文件。
- 下载远端配置文件。
- 将远端 JSON 交给 `config_manager.clean_config_data()` 校验。

`config_manager.py` 负责：

- 给默认配置增加 WebDAV 字段。
- 清洗 WebDAV 字段。
- 暴露 `clean_config_data()`，让下载后的远端配置复用同一套清洗逻辑。

`pyside6_ui/main_window.py` 负责：

- 展示新增 WebDAV 字段和同步按钮。
- 保存和加载 WebDAV 字段。
- 通过现有 `TaskRunner` 执行上传、下载后台任务。
- 下载成功后刷新界面状态。

## 错误处理

- WebDAV URL 或远端路径缺失时，不发起同步并提示用户补全配置。
- 上传失败、下载失败、认证失败、远端文件不存在或 JSON 格式错误时，通过弹窗提示，并写入通用后台任务错误日志。
- 下载到的配置不是 JSON 对象时拒绝覆盖本地文件。
- 下载成功后如果远端配置缺少新字段，会通过默认值自动补齐，兼容旧版本配置。

## 验证方式

- 使用 `python -m py_compile` 验证新增模块和主窗口代码。
- 用本地临时目录模拟配置 JSON 清洗，验证 WebDAV 下载配置校验路径。
- 离屏实例化 `NoteShareMainWindow`，确认新增字段和按钮可加载。
