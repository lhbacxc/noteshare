# PySide6 UI 当前实现说明

## 1. 目标

当前桌面端已经统一使用 `PySide6`，本说明文档用于描述现行 GUI 结构、职责划分与界面特性，作为后续继续迭代桌面工具的参考基线。

## 2. 当前入口

当前桌面应用唯一入口为：

- `app.py`

该入口负责：

- 创建 `QApplication`
- 加载程序图标
- 启动 `NoteShareMainWindow`

## 3. 当前目录结构

```text
.
├── app.py
├── r2_client.py
├── config_manager.py
├── worker_client.py
├── requirements.txt
├── NoteShareR2.spec
├── 启动R2工具.bat
├── 打包NoteShareR2.bat
└── pyside6_ui/
    ├── main_window.py
    ├── state.py
    ├── tasks.py
    ├── theme.py
    └── widgets/
        ├── collapsible_section.py
        ├── detail_panel.py
        ├── object_table.py
        └── storage_ring.py
```

## 4. 界面结构

当前桌面界面由以下四个主要区域组成：

1. 连接配置区
2. 筛选与浏览区
3. 对象操作区
4. 主内容区

其中主内容区继续拆分为：

- 左侧对象表格
- 右侧链接与容量侧栏

## 5. 当前交互特点

### 5.1 连接配置区

- 支持折叠与展开
- 当本地已存在完整连接配置时，默认折叠
- 缩小窗口后会自动从多列改为更紧凑的排列

### 5.2 对象表格

- 支持关键字过滤
- 支持多选
- 支持点击表头按列排序
- 支持升序与降序切换
- 在刷新和倒计时更新后保留当前排序状态

### 5.3 右侧侧栏

当前只保留两块内容：

- 链接与分享
- bucket 容量概览

不再重复展示左侧表格中已经可直接看到的对象基础信息。

### 5.4 响应式布局

- 窗口缩小时，配置区和按钮区会自动换行重排
- 主内容区会在较窄窗口下从左右分栏切换为上下分栏
- 右侧侧栏放入滚动容器，避免被直接挤压裁切

## 6. 代码职责

### `pyside6_ui/main_window.py`

负责：

- 主窗口布局
- 全局状态刷新
- 响应式重排
- 业务按钮事件绑定
- 与共享业务层的协调

### `pyside6_ui/state.py`

负责保存当前窗口状态，包括：

- 当前配置
- 当前对象列表
- 当前筛选结果
- 当前选中对象
- 当前容量快照
- 当前状态文本

### `pyside6_ui/tasks.py`

负责后台任务封装。

当前耗时操作统一走后台执行，包括：

- 测试连接
- 加载 bucket
- 刷新列表
- 上传
- 下载
- 删除
- 生成预签名 URL
- 创建分享
- 停止分享

### `pyside6_ui/widgets/object_table.py`

负责对象表格展示与排序行为。

### `pyside6_ui/widgets/detail_panel.py`

负责右侧侧栏内容。

### `pyside6_ui/widgets/collapsible_section.py`

负责可折叠区域组件。

### `pyside6_ui/widgets/storage_ring.py`

负责容量圆环绘制。

## 7. 当前共享业务层

桌面界面继续复用以下共享模块：

- `r2_client.py`
- `config_manager.py`
- `worker_client.py`

这样可以将 GUI 层与 R2 / Worker 交互逻辑保持分离。

## 8. 当前已知边界

- 当前仍只支持一套本地账号配置
- 当前仍未实现对象重命名、移动和拖拽上传
- 当前分享记录仍只保留最近一次
- 当前“所有 bucket 合计”仍未实现真实统计
- 当前总空间上限仍固定为免费层暂定值 `10GB`

## 9. 后续继续迭代时的约束

- 不再新增或恢复旧 `Tkinter` UI 文件
- 所有桌面端交互改动都应落在 `PySide6` 结构内
- 高层说明文档应默认以当前 `PySide6` 实现为准
