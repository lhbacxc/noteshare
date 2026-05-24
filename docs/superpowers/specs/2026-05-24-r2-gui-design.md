# R2 本地 GUI 管理工具设计文档

## 1. 背景与目标

当前已经具备 Cloudflare R2 存储桶与相关密钥信息，目标是在本地提供一个基于 Python 3.10 与 `boto3` 的桌面 GUI 工具，方便完成常见对象存储操作，而不需要每次手写脚本或命令。

本工具需要满足以下目标：

- 提供本地桌面 GUI，而不是命令行交互。
- 支持在 GUI 中录入并保存 R2 密钥配置。
- 支持在一套密钥下切换多个 bucket。
- 支持对象上传、下载、删除、预签名 URL 生成。
- 支持按前缀浏览对象、关键字过滤、查看对象大小与修改时间。
- 支持设置预签名 URL 的过期时间。
- 尽量减少依赖，优先保证在本地 `miniconda` 环境中易于运行。

## 2. 非目标

本次实现不包含以下能力：

- 不实现真正的目录树懒加载浏览器，前缀浏览采用输入前缀后刷新列表的方式。
- 不实现多套账号配置档案管理，仅支持一套密钥配置。
- 不实现对象重命名、移动、拖拽上传、分片上传等增强功能。
- 不实现系统密钥链集成或强加密存储。

## 3. 技术选型

### 3.1 GUI

采用 `Tkinter`。

原因：

- Python 3.10 环境通常自带，依赖最少。
- 对本次工具型桌面应用已经足够。
- 比 `PySide6` 更轻量，便于快速在本地环境跑通。

### 3.2 对象存储访问

采用 `boto3`，通过兼容 S3 的方式访问 Cloudflare R2。

### 3.3 配置持久化

采用本地 `config.json` 文件持久化保存配置。

原因：

- 满足“下次打开直接复用”的需求。
- 实现简单、维护成本低。
- 适合单用户本地工具场景。

## 4. 目录结构

```text
.
├─ app.py
├─ gui.py
├─ r2_client.py
├─ config_manager.py
├─ requirements.txt
├─ README.md
└─ docs/
   └─ superpowers/
      └─ specs/
         └─ 2026-05-24-r2-gui-design.md
```

说明：

- `app.py` 为程序入口。
- `gui.py` 负责界面、事件绑定、状态更新。
- `r2_client.py` 封装所有 `boto3` / R2 操作。
- `config_manager.py` 负责本地配置读取与保存。
- `README.md` 提供中文使用说明。

## 5. 核心功能

### 5.1 配置管理

GUI 中提供以下配置项：

- `Account ID`
- `Access Key ID`
- `Secret Access Key`
- `Endpoint URL`
- 默认 bucket
- 预签名 URL 默认过期秒数

功能要求：

- 支持手动填写。
- 支持保存到本地配置文件。
- 下次启动时自动回填。
- 支持点击“测试连接”验证配置是否可用。
- 支持点击“加载 bucket 列表”并更新 bucket 下拉框。

### 5.2 Bucket 切换

在同一套密钥配置下：

- 支持列出当前账号可访问的 bucket。
- 支持在下拉框中切换 bucket。
- 切换后支持刷新对象列表。

### 5.3 对象浏览

对象列表需要展示：

- `Key`
- `Size`
- `Last Modified`
- `Storage Class`（若接口返回则展示，否则留空）

对象浏览需要支持：

- 按前缀输入框过滤远端对象列表。
- 按关键字对当前已加载列表做本地搜索过滤。
- 手动刷新当前 bucket / prefix 下的对象列表。

### 5.4 对象操作

支持以下操作：

- 上传本地文件到当前 bucket。
- 下载选中对象到本地。
- 删除选中对象。
- 批量删除选中对象。
- 为选中对象生成预签名 URL。
- 自定义 URL 过期时间。
- 一键复制生成的 URL。

交互要求：

- 删除前弹出确认框。
- 上传、下载、删除完成后自动刷新列表。
- 批量删除后给出成功/失败统计。

## 6. 界面结构

界面采用单窗口布局，分为 4 个区域：

### 6.1 顶部配置区

包含：

- `Account ID`
- `Access Key ID`
- `Secret Access Key`
- `Endpoint URL`
- bucket 下拉框
- 默认 URL 过期时间
- 保存配置按钮
- 测试连接按钮
- 加载 bucket 按钮

### 6.2 筛选区

包含：

- 前缀输入框
- 搜索输入框
- 刷新列表按钮

### 6.3 对象列表区

采用表格控件展示对象列表，支持多选。

### 6.4 操作与结果区

包含：

- 上传按钮
- 下载按钮
- 删除按钮
- 生成预签名 URL 按钮
- URL 显示框
- 复制 URL 按钮
- 状态栏

## 7. 程序结构设计

### 7.1 `config_manager.py`

职责：

- 提供默认配置。
- 读取 `config.json`。
- 保存 `config.json`。
- 对配置字段做基础清洗。

建议接口：

- `load_config() -> dict`
- `save_config(config: dict) -> None`
- `get_default_config() -> dict`

### 7.2 `r2_client.py`

职责：

- 构建 `boto3` 客户端。
- 封装所有 R2 请求。
- 将底层异常转换为更友好的错误信息。

建议接口：

- `build_client(...)`
- `test_connection()`
- `list_buckets()`
- `list_objects(bucket, prefix="")`
- `upload_file(bucket, local_path, object_key=None)`
- `download_file(bucket, object_key, local_path)`
- `delete_objects(bucket, object_keys)`
- `generate_presigned_url(bucket, object_key, expires_in)`

### 7.3 `gui.py`

职责：

- 创建 `Tkinter` 窗口与控件。
- 管理表单数据与对象列表。
- 绑定按钮行为。
- 执行后台线程任务。
- 根据操作结果更新界面与弹窗提示。

### 7.4 `app.py`

职责：

- 初始化 GUI。
- 启动主循环。

## 8. 数据流

### 8.1 启动流程

1. 启动 `app.py`。
2. `gui.py` 调用 `config_manager.load_config()`。
3. 若存在历史配置，则自动回填表单。
4. 用户可直接测试连接或加载 bucket 列表。

### 8.2 连接验证流程

1. 用户点击“测试连接”。
2. GUI 读取表单值。
3. 构建 `R2Manager` 或 R2 客户端封装对象。
4. 请求 bucket 列表或调用轻量验证接口。
5. 将成功或失败结果展示给用户。

### 8.3 对象列表流程

1. 用户选择 bucket 并输入 prefix。
2. 点击“刷新列表”。
3. GUI 后台调用 `list_objects(bucket, prefix)`。
4. 返回结果后刷新表格。
5. 搜索框对当前结果做本地过滤，不额外发请求。

### 8.4 对象操作流程

1. 用户在列表中选中对象。
2. 点击上传、下载、删除或生成 URL。
3. GUI 在后台线程发起请求。
4. 完成后更新状态栏。
5. 如有必要自动刷新列表。

## 9. 配置文件格式

配置文件使用 JSON，示例：

```json
{
  "account_id": "",
  "access_key_id": "",
  "secret_access_key": "",
  "endpoint_url": "",
  "default_bucket": "",
  "url_expire_seconds": 3600,
  "recent_buckets": []
}
```

说明：

- `recent_buckets` 用于保留最近加载到的 bucket 列表。
- `secret_access_key` 明文保存在本地文件中，本次实现以易用性优先。
- `config.json` 放在工具根目录，便于随项目一起迁移。

## 10. 异常处理

需要覆盖以下错误场景：

### 10.1 配置缺失

- 任意关键字段为空时，阻止连接或对象操作。
- 通过弹窗提示缺少哪些字段。

### 10.2 认证失败

- Access Key、Secret、Endpoint、Account ID 配置错误。
- bucket 不存在或无权限访问。
- 统一展示清晰错误，而不是原始长堆栈。

### 10.3 网络异常

- 请求超时。
- DNS/连接失败。
- 服务端临时错误。

处理方式：

- 提示错误信息。
- 恢复按钮可用状态。
- 保留当前表单与列表状态。

### 10.4 批量删除部分失败

- 删除接口返回部分对象失败时，展示成功数量与失败明细。

## 11. 并发与界面响应

为避免 `Tkinter` 主线程卡死，以下操作必须放入后台线程：

- 测试连接
- 加载 bucket 列表
- 刷新对象列表
- 上传文件
- 下载文件
- 删除对象
- 生成预签名 URL

线程执行期间：

- 禁用对应按钮，防止重复点击。
- 状态栏显示当前任务。
- 任务结束后恢复按钮状态。

界面更新需回到主线程执行。

## 12. 用户体验细节

- `Secret Access Key` 输入框默认隐藏字符。
- URL 生成后自动填入文本框。
- 提供“复制 URL”按钮。
- 未选中对象时，下载、删除、生成 URL 操作直接提示。
- 上传文件时默认对象名使用本地文件名，但允许指定前缀后拼接。

## 13. 环境与运行方式

### 13.1 Conda 环境

目标环境：

- 环境名：`noteshare`
- Python 版本：`3.10`

### 13.2 依赖

最小依赖：

- `boto3`

`Tkinter` 采用 Python 自带版本，不额外写入第三方桌面依赖。

### 13.3 运行方式

预期命令：

```powershell
conda create -n noteshare python=3.10 -y
conda activate noteshare
pip install -r requirements.txt
python app.py
```

## 14. 测试范围

本次至少验证以下内容：

- 配置保存后可重新加载。
- 测试连接成功与失败路径均有合理提示。
- bucket 列表可加载并切换。
- 对象列表可按 prefix 获取并按关键字过滤。
- 上传文件成功后列表刷新。
- 下载文件成功落盘。
- 删除单个与多个对象成功。
- 预签名 URL 可生成并复制。

## 15. 后续可扩展方向

- 多账号配置档案。
- 更安全的密钥存储方式。
- 对象重命名与移动。
- 拖拽上传。
- 分页加载与更大的对象列表处理。
- 更完整的目录树视图。
