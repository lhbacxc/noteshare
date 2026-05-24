# NoteShare 可撤销分享链接设计文档

## 1. 变更背景

当前项目已经支持为 R2 对象生成预签名 URL，但该能力存在一个明显限制：

- 预签名 URL 一旦生成并发出，在未过期前无法单独手动失效。

这会带来一个实际使用问题：

- 用户可能在链接尚未过期时，希望立即停止分享。

为解决这个问题，本次新增“可撤销分享链接”能力。该能力不再直接对外暴露 R2 预签名 URL，而是通过 Cloudflare Worker 作为统一分享入口，由 Worker 根据 KV 中记录的分享状态决定是否放行访问。

## 2. 目标

本次变更目标如下：

- 支持为单个 R2 对象创建可撤销分享链接。
- 支持在 GUI 中直接停止某个文件当前最近一次分享。
- 支持分享链接已停用或已过期时统一返回 `404`。
- 支持 Worker 根据文件类型自动决定预览或下载。
- 支持在本地配置中保存每个文件最近一次可撤销分享记录。
- 保留现有预签名 URL 功能，不替换已有能力。

## 3. 非目标

本次不实现以下能力：

- 不支持同一个文件保留多条历史分享记录。
- 不支持批量创建或批量停止分享。
- 不支持分享密码、访问次数统计、备注、访问日志。
- 不支持多用户权限体系。
- 不实现 Cloudflare Access、OAuth 等复杂鉴权方式。
- 不将本地已有预签名 URL 自动迁移为可撤销分享链接。

## 4. 总体方案

采用以下架构：

- 当前仓库新增 `worker/` 目录，存放 Cloudflare Worker 工程。
- GUI 新增 Worker 管理配置，并通过 HTTP 请求直接调用 Worker 管理接口。
- Worker 使用 KV 保存分享记录。
- Worker 使用 R2 读取对象内容并向外返回文件。

核心链路如下：

1. 用户在 GUI 中选中文件。
2. 点击“创建可撤销分享”。
3. GUI 调用 Worker 管理接口创建分享记录。
4. Worker 生成 `token` 并写入 KV。
5. Worker 返回 `share_url`。
6. 用户对外分享 `share_url`。
7. 访问分享链接时，Worker 校验记录状态与过期时间。
8. 若记录有效，则从 R2 读取对象并返回内容。
9. 若用户在 GUI 中点击“停止分享”，GUI 调 Worker 将记录状态改为 `revoked`。
10. 之后访问旧链接统一返回 `404`。

## 5. 目录结构改动

本次预计新增或改动以下路径：

- `gui.py`
- `config_manager.py`
- `requirements.txt`
- `README.md`
- `docs/superpowers/specs/2026-05-24-stop-link-worker-design.md`
- `worker/package.json`
- `worker/tsconfig.json`
- `worker/wrangler.jsonc`
- `worker/src/index.ts`

如有必要，可在 `worker/` 下增加少量辅助文件，但应保持结构简洁。

## 6. GUI 设计

### 6.1 新增全局配置

在 GUI 顶部连接配置区域新增以下字段：

- `Worker Base URL`
- `Worker Admin Token`

含义如下：

- `Worker Base URL` 表示 Worker 的访问根地址，例如 `https://noteshare-worker.example.workers.dev`
- `Worker Admin Token` 表示 GUI 调用 Worker 管理接口时使用的固定管理密钥

### 6.2 新增文件级操作

在当前操作按钮区域新增以下按钮：

- `创建可撤销分享`
- `停止分享`
- `复制分享链接`

按钮行为：

- `创建可撤销分享`
  - 仅支持单选文件
  - 使用当前文件默认过期秒数
  - 调用 Worker 创建分享
- `停止分享`
  - 仅支持单选文件
  - 若当前文件没有最近一次有效分享记录，则直接提示
  - 若存在记录，则调用 Worker 停止分享
- `复制分享链接`
  - 复制当前底部展示的最近一次有效分享链接

### 6.3 底部结果区

为避免与预签名 URL 混淆，底部结果区拆分为两组：

- 当前选中文件有效预签名 URL
- 当前选中文件有效分享链接

其中分享链接输入框仅显示“当前文件最近一次仍有效的可撤销分享链接”：

- 若不存在记录，则显示为空
- 若记录已停用，则显示为空
- 若记录已过期，则显示为空

## 7. 本地配置结构设计

### 7.1 新增全局配置字段

在 `config.json` 中新增：

```json
{
  "worker_base_url": "",
  "worker_admin_token": ""
}
```

### 7.2 扩展文件级记录

在现有 `object_url_settings` 的单文件记录中新增：

```json
{
  "default_expire_seconds": 1800,
  "last_presigned_url": "https://...",
  "last_generated_at": "2026-05-24T16:30:00+08:00",
  "last_expires_at": "2026-05-24T17:00:00+08:00",
  "last_share_token": "abc123",
  "last_share_url": "https://worker.example.com/s/abc123",
  "last_share_status": "active",
  "last_share_created_at": "2026-05-24T18:00:00+08:00",
  "last_share_expires_at": "2026-05-24T19:00:00+08:00"
}
```

字段说明：

- `last_share_token` 表示最近一次分享记录的 token
- `last_share_url` 表示最近一次分享链接
- `last_share_status` 取值仅支持：
  - `active`
  - `revoked`
- `last_share_created_at` 表示创建时间
- `last_share_expires_at` 表示过期时间

第一版只保留“最近一次分享记录”，不保留历史数组。

## 8. Worker 设计

### 8.1 资源绑定

Worker 需要以下绑定：

- 一个 KV 命名空间，用于保存分享记录
- 一个 R2 Bucket 绑定，用于读取对象内容
- 一个环境变量，用于保存管理密钥

### 8.2 路由设计

Worker 暴露以下接口：

- `POST /api/shares`
- `POST /api/shares/revoke`
- `GET /api/shares/:token`
- `GET /s/:token`

### 8.3 管理接口鉴权

`/api/` 下的管理接口统一要求：

- 请求头包含 `Authorization: Bearer <admin-token>`

若鉴权失败，统一返回 `401`。

### 8.4 KV 记录结构

KV 中使用以下 key 格式：

```text
share:<token>
```

KV value 结构如下：

```json
{
  "token": "abc123",
  "bucket": "notelink",
  "object_key": "docs/demo.txt",
  "status": "active",
  "content_mode": "auto",
  "created_at": "2026-05-24T18:00:00+08:00",
  "expires_at": "2026-05-24T19:00:00+08:00"
}
```

说明：

- `status` 第一版仅支持 `active` 和 `revoked`
- `content_mode` 第一版固定写入 `auto`
- `expires_at` 由 Worker 根据请求的 `expire_seconds` 计算生成

### 8.5 创建分享接口

`POST /api/shares`

请求体：

```json
{
  "bucket": "notelink",
  "object_key": "docs/demo.txt",
  "expire_seconds": 1800
}
```

处理流程：

1. 校验鉴权头
2. 校验参数完整性与合法性
3. 生成随机 `token`
4. 计算 `created_at` 与 `expires_at`
5. 将记录写入 KV
6. 返回创建结果

返回体：

```json
{
  "token": "abc123",
  "share_url": "https://worker.example.com/s/abc123",
  "status": "active",
  "created_at": "2026-05-24T18:00:00+08:00",
  "expires_at": "2026-05-24T19:00:00+08:00"
}
```

### 8.6 停止分享接口

`POST /api/shares/revoke`

请求体：

```json
{
  "token": "abc123"
}
```

处理流程：

1. 校验鉴权头
2. 读取 KV
3. 若记录不存在，返回 `404`
4. 若记录存在，将 `status` 改为 `revoked`
5. 回写 KV
6. 返回更新后的状态

### 8.7 查询分享状态接口

`GET /api/shares/:token`

处理流程：

1. 校验鉴权头
2. 查 KV
3. 若不存在，返回 `404`
4. 若存在，返回完整记录

此接口主要用于 GUI 在未来需要主动刷新状态时复用。第一版可先实现基础查询。

### 8.8 对外访问接口

`GET /s/:token`

处理流程：

1. 查 KV
2. 若 KV 中不存在记录，返回 `404`
3. 若 `status != active`，返回 `404`
4. 若当前时间已超过 `expires_at`，返回 `404`
5. 从 R2 读取对象
6. 若对象不存在，返回 `404`
7. 根据对象类型自动决定返回头
8. 返回文件内容

## 9. 内容返回策略

第一版分享访问统一使用 `content_mode = auto`。

判断规则：

- 文本类型、图片类型、`application/pdf`、`image/svg+xml` 等适合预览的内容：
  - `Content-Disposition: inline`
- 其他类型：
  - `Content-Disposition: attachment`

内容类型优先顺序：

1. 优先使用 R2 对象自身的 `Content-Type`
2. 若对象无明确类型，则根据对象 key 后缀推断
3. 若仍无法判断，则退回 `application/octet-stream`

## 10. GUI 与 Worker 交互规则

### 10.1 创建可撤销分享

1. 用户选中单个文件
2. GUI 读取：
   - `bucket`
   - `object_key`
   - `default_expire_seconds`
   - `worker_base_url`
   - `worker_admin_token`
3. 调用 `POST /api/shares`
4. 成功后更新本地文件记录中的：
   - `last_share_token`
   - `last_share_url`
   - `last_share_status`
   - `last_share_created_at`
   - `last_share_expires_at`
5. 刷新底部分享链接显示

### 10.2 停止分享

1. 用户选中单个文件
2. GUI 读取当前文件最近一次 `last_share_token`
3. 调用 `POST /api/shares/revoke`
4. 成功后将本地记录中的：
   - `last_share_status` 更新为 `revoked`
5. 刷新底部分享链接显示为空

### 10.3 复制分享链接

1. 读取当前底部展示的分享链接
2. 若为空，则提示没有可复制的分享链接
3. 若非空，则复制到剪贴板

## 11. 异常处理

需要覆盖以下场景：

- 未配置 `Worker Base URL`
- 未配置 `Worker Admin Token`
- 未选择文件
- 选择了多个文件
- 当前文件没有最近一次分享 token
- Worker 管理接口返回 `401`
- Worker 管理接口返回 `404`
- Worker 管理接口返回 `400`
- Worker 访问 R2 失败
- R2 对象不存在
- 分享已过期
- 分享已停用

错误处理原则：

- GUI 应弹出明确、可读的中文提示
- Worker 不泄露内部堆栈信息
- 对外访问链接的失效结果统一表现为 `404`

## 12. 测试范围

至少验证以下内容：

- GUI 可以保存并重新加载 Worker 配置
- 创建可撤销分享后，本地记录被正确写入
- 停止分享后，本地状态更新为 `revoked`
- 已停用分享不再显示到底部分享链接输入框
- Worker 创建接口鉴权正确
- Worker 停止接口能正确改写状态
- Worker 查询接口能返回记录
- `GET /s/:token` 在以下场景下行为正确：
  - token 不存在
  - 状态为 `revoked`
  - 已过期
  - R2 对象不存在
  - 文本文件预览
  - 二进制文件下载

## 13. 实施边界

本次实现应坚持以下边界：

- 仅实现每个文件最近一次可撤销分享记录
- 不改变现有预签名 URL 功能的基本交互
- Worker 保持单工程、单入口，不拆分多个服务
- 优先保证“创建分享、复制分享、停止分享、访问 404 失效”这条主链路完整可用

## 14. 后续可扩展方向

后续如有需要，可继续扩展：

- 文件多条历史分享记录
- GUI 分享记录列表
- 批量停止分享
- 分享备注
- 访问统计
- 密码访问
- Cloudflare Access 鉴权
