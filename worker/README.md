# NoteShare Worker 部署说明

这个目录用于部署“可撤销分享链接”对应的 Cloudflare Worker。

## 1. 功能说明

当前 Worker 提供两类能力：

- 管理接口
  - 创建分享
  - 停止分享
  - 查询分享状态
- 对外分享访问
  - 访问有效分享链接时返回文件
  - 分享被停用、已过期、对象不存在时统一返回 `404`

## 2. 前置准备

需要先在 Cloudflare 中准备：

- 一个 KV Namespace
- 一个 R2 bucket
- 一个 Worker

同时需要本地安装 Node.js。

## 3. 安装依赖

在 `worker/` 目录执行：

```powershell
npm install
```

## 4. 配置 `wrangler.jsonc`

编辑 `worker/wrangler.jsonc`，替换以下占位值：

- `YOUR_KV_NAMESPACE_ID`
- `YOUR_KV_PREVIEW_NAMESPACE_ID`
- `YOUR_R2_BUCKET_NAME`

说明：

- 当前 Worker 只绑定一个 R2 bucket。
- 如果 GUI 当前操作的 bucket 与 Worker 绑定的 bucket 不一致，创建分享时会返回错误。

## 5. 设置管理密钥

在 `worker/` 目录执行：

```powershell
npx wrangler secret put ADMIN_TOKEN
```

输入后保存你的管理密钥。

这个值需要和 GUI 里的 `Worker Admin Token` 保持一致。

## 6. 本地调试

在 `worker/` 目录执行：

```powershell
npm run dev
```

## 7. 部署

在 `worker/` 目录执行：

```powershell
npm run deploy
```

部署完成后，拿到 Worker 地址，填入 GUI 的：

- `Worker Base URL`
- `Worker Admin Token`

## 8. Worker 接口

管理接口：

- `POST /api/shares`
- `POST /api/shares/revoke`
- `GET /api/shares/:token`

公开访问接口：

- `GET /s/:token`

## 9. GUI 使用方式

在桌面工具中：

1. 填写并保存 `Worker Base URL`
2. 填写并保存 `Worker Admin Token`
3. 选中单个文件
4. 点击“创建可撤销分享”
5. 复制分享链接发给别人
6. 如需失效，点击“停止分享”

## 10. 注意事项

- `config.json` 中会保存 `Worker Admin Token`，仅适合个人本地使用。
- 当前实现只保留每个文件最近一次可撤销分享记录。
- 当前实现不会替换已有预签名 URL 功能，两套能力可以并行使用。
