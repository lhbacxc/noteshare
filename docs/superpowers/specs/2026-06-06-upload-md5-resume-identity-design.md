# 上传断点续传 MD5 身份设计

## 背景

当前断点续传状态保存在 `upload_resume_state.json`，会按 `endpoint + bucket + object key + 本地路径 + 文件大小 + 文件修改时间` 生成本地 session key。这个设计能避免误续传被修改过的文件，但也带来两个问题：

- 本地文件移动到新路径后，再次拖拽会被当成新上传。
- 本地文件内容不变但改了文件名后，再次上传会被当成新上传。

用户期望上传前计算文件 MD5，并用内容身份查找本地是否已有对应断点；如果有则续传，没有则从头上传。

## 目标

- 上传前在后台线程计算本地文件 MD5，不阻塞 GUI 主线程。
- 新断点状态使用 `endpoint + bucket + object key + 文件大小 + MD5` 作为主要身份。
- 保留旧的路径/mtime 维度作为兼容能力，避免已有断点状态立即失效。
- 本地路径变化但文件内容不变时，可以继续使用原断点上传。
- 本地文件改名但内容不变时，可以通过 MD5 找回旧断点。

## 关键约束

Cloudflare R2 的 multipart upload 遵循 S3 兼容语义，`upload_id` 绑定创建时的 `bucket + object key`。因此 MD5 只能证明本地文件内容一致，不能把一个未完成 multipart upload 改续到另一个对象 Key。

所以当新上传文件的 MD5 命中已有断点，但用户当前默认对象 Key 与断点中的 `object_key` 不一致时，程序会沿用断点中的原 `object_key` 继续上传，并在上传状态区提示正在续传原对象 Key。

## 设计

### 断点状态

`upload_resume_store.py` 增加：

- `calculate_file_md5(local_path, cancel_check=None)`：分块计算文件 MD5，可被暂停/取消逻辑中断。
- `make_upload_session_key(..., content_md5=None, local_size=None)`：当传入 MD5 时生成内容身份 key；未传入时保持旧路径身份 key。
- `find_upload_session_by_content(...)`：先查同对象 Key 的 MD5 断点，再回退查同 endpoint/bucket/size/MD5 的最新断点。
- `delete_upload_sessions_for_file(...)`：取消上传时同时清理内容身份 key 与旧路径身份 key。

新保存的 session 会继续记录 `local_path`、`local_size`、`local_mtime_ns`，并新增：

- `content_md5`
- `content_hash_algorithm`

### 上传流程

`pyside6_ui/main_window.py` 的后台上传任务在每个文件开始时：

1. 计算当前本地文件 MD5。
2. 使用 MD5 查找本地断点。
3. 如果命中断点，则使用断点中的 `object_key`、`upload_id`、`part_size` 和已完成 part 信息继续上传。
4. 如果没有命中断点，则创建新的 multipart upload。
5. 保存断点状态时同步写入 MD5，后续路径变化或文件名变化仍可识别。

### R2 上传层

`r2_client.py` 的 `upload_resumable_file()` 增加可选 `content_md5` 参数，并把它写入 `_build_resume_session()` 返回的 session。R2 上传本身仍按 multipart part 继续，不改变分片大小、进度回调和暂停/取消语义。

## 错误处理

- MD5 计算过程中如果用户点击暂停/取消，走已有 `UploadInterrupted` 逻辑。
- 如果 MD5 命中的远端 multipart upload 已失效，继续沿用现有逻辑：远端 `list_parts` 查不到时创建新的 multipart upload。
- 如果旧断点没有 MD5，仍可通过旧路径身份继续一次；续传过程中会把新 MD5 写回状态。

## 验证

- `python -m py_compile app.py r2_client.py upload_resume_store.py upload_control.py pyside6_ui/main_window.py pyside6_ui/tasks.py pyside6_ui/theme.py`
- 用临时文件验证相同内容在不同路径下能查到同一个 MD5 断点。
- 用临时文件验证同内容但不同对象 Key 时会回退使用断点中的原对象 Key。
- 离屏实例化 `NoteShareMainWindow`，确认 UI 初始化不受影响。
