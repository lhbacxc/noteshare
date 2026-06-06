# exe 一键打包脚本设计

## 背景

当前项目已经统一为 `PySide6` 桌面应用，打包目标是生成可直接运行的单文件：

```text
dist/NoteShareR2.exe
```

现有 `打包NoteShareR2.bat` 已能调用 `noteshare` conda 环境中的 `PyInstaller`，但仍偏向最小可用脚本：对依赖、关键资源、旧产物清理和最终产物确认的提示不够完整；`NoteShareR2.spec` 也写死了本机 conda 环境路径，后续换环境路径时容易失效。

## 目标

- 保持 `PyInstaller` 单文件打包方案不变。
- 保持桌面入口为 `app.py`。
- 输出文件固定为 `dist/NoteShareR2.exe`。
- 一键脚本优先使用 `noteshare` conda 环境的 `python.exe`。
- 脚本自动校验关键文件、关键依赖和关键 DLL。
- 打包前清理旧 `build/` 与旧 exe，避免旧文件干扰判断。
- 重新打包时保留 `dist/config.json`、`dist/logs/` 等运行期文件，避免误删用户已经在 exe 目录中生成的本地配置和日志。
- 如果旧 `dist/NoteShareR2.exe` 仍在运行，脚本会先停止当前项目路径下的旧进程，再删除旧 exe。
- 打包完成后检查 exe 是否真实存在，并输出完整路径和文件大小。
- `NoteShareR2.spec` 不再硬编码单一本机环境路径，优先读取脚本传入的环境目录。

## 实现方案

### `打包NoteShareR2.bat`

脚本继续作为用户双击入口，主要流程为：

1. 切换到项目根目录。
2. 按固定候选路径查找 `noteshare` 环境中的 `python.exe`。
3. 计算 conda 环境根目录，并写入：
   - `PATH`
   - `CONDA_PREFIX`
   - `NOTESHARE_CONDA_ENV`
4. 校验以下项目文件存在：
   - `app.py`
   - `NoteShareR2.spec`
   - `cf_cloud.ico`
   - `requirements.txt`
5. 校验以下 Python 模块可导入：
   - `PySide6`
   - `boto3`
   - `botocore`
   - `PyInstaller`
6. 如果依赖缺失，自动执行：

```text
python -m pip install -r requirements.txt
```

7. 校验以下运行库 DLL：
   - `libssl-3-x64.dll`
   - `libcrypto-3-x64.dll`
   - `libexpat.dll`
8. 删除旧 `build/`、旧 `dist/NoteShareR2.exe`、`__pycache__/` 和上次打包日志文件；不删除整个 `dist/` 目录。
9. 如果旧 exe 正在运行，只停止路径等于当前项目 `dist/NoteShareR2.exe` 的进程，避免影响其他目录下的同名程序。
10. 删除旧 exe 时进行短重试；如果仍被占用，则提示关闭程序或安全软件扫描后重试。
11. 调用 `python -m PyInstaller --noconfirm --clean NoteShareR2.spec`。
12. 检查 `dist/NoteShareR2.exe` 是否存在，并输出大小。

### `NoteShareR2.spec`

spec 继续负责固定 PyInstaller 分析与打包配置：

- 入口仍为 `app.py`。
- 图标和运行时资源仍为 `cf_cloud.ico`。
- 继续排除 `tkinter`。
- 继续显式加入 `pyexpat` 与 `xml.parsers.expat`。
- 继续固定 SSL 与 XML 相关 DLL。

环境目录解析顺序改为：

1. `NOTESHARE_CONDA_ENV`
2. `CONDA_PREFIX`
3. 当前运行的 `python.exe` 所在目录

这样由 `.bat` 调用时会使用脚本识别到的环境；命令行手动调用时，也能跟随当前 Python 环境。

## 错误处理

- 找不到 `noteshare` 环境时，直接列出已检查路径并退出。
- 缺少关键项目文件时，提示具体缺少的文件并退出。
- 依赖缺失且自动安装失败时，提示手动执行 `python -m pip install -r requirements.txt`。
- 缺少关键 DLL 时，提示检查 conda 环境是否完整。
- PyInstaller 执行失败或 exe 未生成时，保留错误输出并退出。
- 旧 exe 被 Windows 锁定且无法删除时，提示用户关闭正在运行的 `NoteShareR2.exe` 或等待安全软件扫描结束。

## 验证方式

- 执行 `打包NoteShareR2.bat`。
- 确认脚本最终输出 `Build succeeded`。
- 确认 `dist/NoteShareR2.exe` 存在。
- 确认 exe 文件大小非 0。
