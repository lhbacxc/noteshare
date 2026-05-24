# NoteShare R2 本地 GUI 工具

这是一个基于 `Tkinter` 与 `boto3` 的本地桌面工具，用于管理 Cloudflare R2 中的对象文件。

## 功能

- 保存并加载 R2 连接配置
- 测试连接
- 加载与切换 bucket
- 按前缀浏览对象
- 按关键字过滤对象
- 为单个文件设置默认预签名 URL 过期秒数
- 上传文件
- 下载选中对象
- 删除单个或多个对象
- 生成预签名 URL
- 复制预签名 URL
- 在文件列表显示最近一次 URL 的到期时间与剩余时间
- 选中单个文件时，在底部显示当前仍有效的历史预签名 URL

## 目录说明

```text
.
├─ app.py
├─ gui.py
├─ r2_client.py
├─ config_manager.py
├─ requirements.txt
└─ docs/
```

## 环境准备

建议使用 `miniconda` 创建独立环境：

```powershell
conda create -n noteshare python=3.10 -y
conda activate noteshare
pip install -r requirements.txt
```

## 启动方式

```powershell
python app.py
```

如果你想直接双击运行，也可以使用根目录下的：

```text
启动R2工具.bat
```

说明：

- 双击后会直接查找 `noteshare` 环境中的 `pythonw.exe` 并启动 GUI
- 当前优先检查这些路径：
  `D:\Software\Miniconda\envs\noteshare\pythonw.exe`
  `%USERPROFILE%\miniconda3\envs\noteshare\pythonw.exe`
  `%USERPROFILE%\anaconda3\envs\noteshare\pythonw.exe`
- 如果环境不存在，脚本会停在窗口里提示

## 配置说明

首次打开后，在界面中填写以下内容：

- `Account ID`
- `Access Key ID`
- `Secret Access Key`
- `Endpoint URL`
- `Bucket`
- `URL 过期秒数`

说明：

- 如果 `Endpoint URL` 留空，程序会尝试根据 `Account ID` 自动生成：
  `https://<Account ID>.r2.cloudflarestorage.com`
- 点击“保存配置”后，会在当前工具目录生成 `config.json`
- `Secret Access Key` 会明文保存在 `config.json` 中，适合单机本地使用

## 使用流程

### 1. 连接与加载 bucket

1. 填写配置。
2. 点击“保存配置”。
3. 点击“测试连接”。
4. 点击“加载 Bucket”获取可访问的 bucket 列表。

### 2. 浏览对象

1. 选择 bucket。
2. 如有需要，在“前缀”中输入对象前缀。
3. 点击“刷新列表”。
4. 如需进一步筛选，可在“搜索”中输入关键字。

### 3. 上传文件

1. 点击“上传文件”。
2. 选择本地文件。
3. 确认或修改对象 Key。
4. 上传成功后会自动刷新列表。

### 4. 下载文件

1. 在列表中选择一个或多个对象。
2. 点击“下载选中对象”。
3. 单文件下载时选择保存路径，多文件下载时选择保存目录。

### 5. 删除对象

1. 在列表中选择一个或多个对象。
2. 点击“删除选中对象”。
3. 确认后执行删除。

### 6. 生成预签名 URL

1. 在列表中只选择一个对象。
2. 如有需要，先点击“设置选中文件过期秒数”。
3. 点击“生成预签名 URL”。
4. 生成后 URL 会显示在输入框中，并自动复制到剪贴板。

### 7. 设置单文件过期秒数

1. 在列表中只选择一个对象。
2. 点击“设置选中文件过期秒数”。
3. 输入该文件默认的预签名 URL 过期秒数。
4. 设置后，列表中的“默认过期秒数”列会更新。

### 8. 查看历史 URL 状态

1. 在列表中选中单个文件。
2. 如果该文件存在未过期的历史预签名 URL，底部会直接显示。
3. 如果该文件没有生成过 URL，或该历史 URL 已过期，底部会显示为空。

## 常见问题

### 连接失败

请检查：

- `Access Key ID` 是否正确
- `Secret Access Key` 是否正确
- `Endpoint URL` 是否正确
- 当前密钥是否有访问目标 bucket 的权限

### 无法列出 bucket

可能原因：

- 密钥权限不足
- Endpoint 配置错误
- 当前网络无法访问 R2 S3 API

### 无法生成预签名 URL

请检查：

- 是否只选择了一个对象
- 该文件的过期秒数是否为大于 0 的整数

## 说明

- 本工具当前仅支持一套密钥配置。
- 最近加载到的 bucket 列表会保存在本地配置中，便于下次继续使用。
- 每个文件的默认过期秒数与最近一次 URL 状态会持久化保存在 `config.json` 中。
