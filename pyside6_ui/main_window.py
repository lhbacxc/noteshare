from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, QTimer, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from config_manager import load_config, save_config
from pyside6_ui.state import UiState
from pyside6_ui.tasks import TaskRunner
from pyside6_ui.theme import (
    APP_STYLESHEET,
    AUTO_REFRESH_DELAY_MS,
    COUNTDOWN_REFRESH_MS,
    RESPONSIVE_VERTICAL_SPLIT_WIDTH,
    STORAGE_LIMIT_BYTES,
    WINDOW_DEFAULT_HEIGHT,
    WINDOW_DEFAULT_WIDTH,
    WINDOW_MIN_HEIGHT,
    WINDOW_MIN_WIDTH,
)
from pyside6_ui.widgets.collapsible_section import CollapsibleSection
from pyside6_ui.widgets.detail_panel import DetailPanel
from pyside6_ui.widgets.object_table import ObjectTableWidget
from r2_client import R2Credentials, R2Manager
from worker_client import WorkerClient, WorkerClientError


class NoteShareMainWindow(QMainWindow):
    def __init__(self, icon_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("NoteShare R2 管理工具 - PySide6 预览")
        self.resize(WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.setStyleSheet(APP_STYLESHEET)
        if icon_path and icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.state = UiState(config_data=load_config())
        self.task_runner = TaskRunner()
        self.action_buttons: list[QPushButton] = []

        self._build_ui()
        self._load_config_to_form()
        self._load_bucket_options_from_config()
        self._refresh_storage_summary(reset_loaded_state=True)
        self._wire_events()

        self.startup_timer = QTimer(self)
        self.startup_timer.setSingleShot(True)
        self.startup_timer.timeout.connect(self._auto_refresh_on_startup)
        self.startup_timer.start(AUTO_REFRESH_DELAY_MS)

        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self._refresh_countdown_timer)
        self.countdown_timer.start(COUNTDOWN_REFRESH_MS)

    def _build_ui(self) -> None:
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        central = QWidget()
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(14)

        self.config_section = CollapsibleSection("连接配置")
        config_layout = QGridLayout()
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setHorizontalSpacing(12)
        config_layout.setVerticalSpacing(10)

        self.account_id_edit = self._make_line_edit()
        self.access_key_edit = self._make_line_edit()
        self.secret_key_edit = self._make_line_edit(password=True)
        self.endpoint_edit = self._make_line_edit()
        self.expire_edit = self._make_line_edit()
        self.worker_base_url_edit = self._make_line_edit()
        self.worker_admin_token_edit = self._make_line_edit(password=True)
        self.bucket_combo = QComboBox()
        self.bucket_combo.setEditable(True)
        self.bucket_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.config_field_wrappers = [
            self._make_labeled_wrapper("Account ID", self.account_id_edit),
            self._make_labeled_wrapper("Access Key ID", self.access_key_edit),
            self._make_labeled_wrapper("Secret Access Key", self.secret_key_edit),
            self._make_labeled_wrapper("Endpoint URL", self.endpoint_edit),
            self._make_labeled_wrapper("默认过期秒数", self.expire_edit),
            self._make_labeled_wrapper("Worker Base URL", self.worker_base_url_edit),
            self._make_labeled_wrapper("Worker Admin Token", self.worker_admin_token_edit),
            self._make_labeled_wrapper("Bucket", self.bucket_combo),
        ]
        self.config_fields_layout = QGridLayout()
        self.config_fields_layout.setContentsMargins(0, 0, 0, 0)
        self.config_fields_layout.setHorizontalSpacing(12)
        self.config_fields_layout.setVerticalSpacing(10)

        self.save_button = self._make_button("保存配置")
        self.test_button = self._make_button("测试连接", primary=True)
        self.load_buckets_button = self._make_button("加载 Bucket")
        self.config_action_buttons = [self.save_button, self.test_button, self.load_buckets_button]
        self.config_actions_layout = QGridLayout()
        self.config_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.config_actions_layout.setHorizontalSpacing(10)
        self.config_actions_layout.setVerticalSpacing(10)

        config_layout.addLayout(self.config_fields_layout, 0, 0)
        config_layout.addLayout(self.config_actions_layout, 1, 0)
        self.config_section.set_content_layout(config_layout)

        filter_card = QGroupBox("筛选与浏览")
        filter_card.setObjectName("SurfaceCard")
        self.filter_layout = QGridLayout(filter_card)
        self.filter_layout.setContentsMargins(16, 18, 16, 16)
        self.filter_layout.setHorizontalSpacing(12)
        self.filter_layout.setVerticalSpacing(10)
        self.prefix_edit = self._make_line_edit()
        self.search_edit = self._make_line_edit()
        self.refresh_button = self._make_button("刷新列表", primary=True)
        self.prefix_wrapper = self._make_labeled_wrapper("前缀", self.prefix_edit)
        self.search_wrapper = self._make_labeled_wrapper("搜索", self.search_edit)

        action_card = QGroupBox("对象操作")
        action_card.setObjectName("SurfaceCard")
        self.action_layout = QGridLayout(action_card)
        self.action_layout.setContentsMargins(16, 18, 16, 16)
        self.action_layout.setHorizontalSpacing(10)
        self.action_layout.setVerticalSpacing(10)
        self.upload_button = self._make_button("上传文件", primary=True)
        self.download_button = self._make_button("下载选中对象")
        self.delete_button = self._make_button("删除选中对象", danger=True)
        self.set_expire_button = self._make_button("设置过期秒数")
        self.generate_url_button = self._make_button("生成预签名 URL")
        self.create_share_button = self._make_button("创建可撤销分享")
        self.revoke_share_button = self._make_button("停止分享", danger=True)
        self.object_action_buttons = [
            self.upload_button,
            self.download_button,
            self.delete_button,
            self.set_expire_button,
            self.generate_url_button,
            self.create_share_button,
            self.revoke_share_button,
        ]

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        self.table = ObjectTableWidget()
        left_layout.addWidget(self.table)

        self.detail_panel = DetailPanel()
        self.action_buttons.extend(
            [self.detail_panel.copy_url_button, self.detail_panel.copy_share_button]
        )
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.NoFrame)
        self.detail_scroll.setWidget(self.detail_panel)
        self.detail_scroll.setMinimumWidth(250)
        self.main_splitter.addWidget(left_panel)
        self.main_splitter.addWidget(self.detail_scroll)
        self.main_splitter.setStretchFactor(0, 4)
        self.main_splitter.setStretchFactor(1, 2)
        self.main_splitter.setSizes([820, 320])

        root_layout.addWidget(self.config_section)
        root_layout.addWidget(filter_card)
        root_layout.addWidget(action_card)
        root_layout.addWidget(self.main_splitter, 1)

        scroll_area.setWidget(central)
        self.setCentralWidget(scroll_area)
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self._set_status("就绪")
        self._rebuild_responsive_layouts()
        self.config_section.set_collapsed(self._should_collapse_config_by_default())

    def _wire_events(self) -> None:
        self.save_button.clicked.connect(self.save_current_config)
        self.test_button.clicked.connect(self.test_connection)
        self.load_buckets_button.clicked.connect(self.load_buckets)
        self.refresh_button.clicked.connect(self.refresh_objects)
        self.upload_button.clicked.connect(self.upload_file)
        self.download_button.clicked.connect(self.download_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        self.set_expire_button.clicked.connect(self.set_selected_file_expire_seconds)
        self.generate_url_button.clicked.connect(self.generate_presigned_url)
        self.create_share_button.clicked.connect(self.create_share)
        self.revoke_share_button.clicked.connect(self.revoke_share)
        self.detail_panel.copy_url_button.clicked.connect(self.copy_url)
        self.detail_panel.copy_share_button.clicked.connect(self.copy_share_url)
        self.search_edit.textChanged.connect(self._apply_search_filter)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.bucket_combo.currentTextChanged.connect(self._on_bucket_change)

    def _make_line_edit(self, password: bool = False) -> QLineEdit:
        line_edit = QLineEdit()
        if password:
            line_edit.setEchoMode(QLineEdit.Password)
        return line_edit

    def _make_button(
        self,
        text: str,
        primary: bool = False,
        danger: bool = False,
    ) -> QPushButton:
        button = QPushButton(text)
        if primary:
            button.setObjectName("PrimaryButton")
        elif danger:
            button.setObjectName("DangerButton")
        self.action_buttons.append(button)
        return button

    def _make_labeled_wrapper(self, label: str, widget: QWidget) -> QWidget:
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(6)
        wrapper_layout.addWidget(QLabel(label))
        wrapper_layout.addWidget(widget)
        return wrapper

    def _load_config_to_form(self) -> None:
        config = self.state.config_data
        self.account_id_edit.setText(str(config.get("account_id", "")))
        self.access_key_edit.setText(str(config.get("access_key_id", "")))
        self.secret_key_edit.setText(str(config.get("secret_access_key", "")))
        self.endpoint_edit.setText(str(config.get("endpoint_url", "")))
        self.worker_base_url_edit.setText(str(config.get("worker_base_url", "")))
        self.worker_admin_token_edit.setText(str(config.get("worker_admin_token", "")))
        self.expire_edit.setText(str(config.get("url_expire_seconds", 3600)))
        self.bucket_combo.setCurrentText(str(config.get("default_bucket", "")))

    def _load_bucket_options_from_config(self) -> None:
        buckets = self.state.config_data.get("recent_buckets", [])
        current_bucket = str(self.state.config_data.get("default_bucket", "")).strip()
        with QSignalBlocker(self.bucket_combo):
            self.bucket_combo.clear()
            for bucket in buckets:
                self.bucket_combo.addItem(str(bucket))
            if current_bucket and current_bucket not in buckets:
                self.bucket_combo.addItem(current_bucket)
            if current_bucket:
                self.bucket_combo.setCurrentText(current_bucket)

    def _collect_form_config(self) -> dict[str, object]:
        return {
            "account_id": self.account_id_edit.text().strip(),
            "access_key_id": self.access_key_edit.text().strip(),
            "secret_access_key": self.secret_key_edit.text().strip(),
            "endpoint_url": self.endpoint_edit.text().strip(),
            "worker_base_url": self.worker_base_url_edit.text().strip(),
            "worker_admin_token": self.worker_admin_token_edit.text().strip(),
            "default_bucket": self.bucket_combo.currentText().strip(),
            "url_expire_seconds": self.expire_edit.text().strip(),
            "recent_buckets": [self.bucket_combo.itemText(index) for index in range(self.bucket_combo.count())],
            "object_url_settings": self.state.config_data.get("object_url_settings", {}),
        }

    def _validate_connection_fields(self) -> dict[str, str] | None:
        config = self._collect_form_config()
        required_fields = {
            "account_id": "Account ID",
            "access_key_id": "Access Key ID",
            "secret_access_key": "Secret Access Key",
        }
        missing = [label for key, label in required_fields.items() if not str(config[key]).strip()]
        if missing:
            QMessageBox.critical(self, "配置不完整", f"请先填写以下字段：{', '.join(missing)}")
            return None

        endpoint_url = str(config["endpoint_url"]).strip()
        if not endpoint_url:
            endpoint_url = f'https://{str(config["account_id"]).strip()}.r2.cloudflarestorage.com'
            self.endpoint_edit.setText(endpoint_url)
            config["endpoint_url"] = endpoint_url

        return {key: str(value) for key, value in config.items() if key != "object_url_settings"}

    def _make_manager(self) -> R2Manager | None:
        config = self._validate_connection_fields()
        if not config:
            return None

        credentials = R2Credentials(
            account_id=config["account_id"],
            access_key_id=config["access_key_id"],
            secret_access_key=config["secret_access_key"],
            endpoint_url=config["endpoint_url"],
        )
        return R2Manager(credentials)

    def _make_worker_client(self) -> WorkerClient | None:
        worker_base_url = self.worker_base_url_edit.text().strip()
        worker_admin_token = self.worker_admin_token_edit.text().strip()
        if not worker_base_url:
            QMessageBox.critical(self, "缺少 Worker 配置", "请先填写 Worker Base URL。")
            return None
        if not worker_admin_token:
            QMessageBox.critical(self, "缺少 Worker 配置", "请先填写 Worker Admin Token。")
            return None
        try:
            return WorkerClient(worker_base_url, worker_admin_token)
        except WorkerClientError as exc:
            QMessageBox.critical(self, "Worker 配置错误", str(exc))
            return None

    def _set_status(self, message: str) -> None:
        self.state.status_message = message
        self.statusBar().showMessage(message, 5000)

    def _set_buttons_state(self, disabled: bool) -> None:
        for button in self.action_buttons:
            button.setDisabled(disabled)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._rebuild_responsive_layouts()

    def _run_task(self, status_text: str, task, on_result=None, on_error=None) -> None:
        def handle_error(exc: Exception) -> None:
            self._set_buttons_state(False)
            self._set_status("操作失败")
            if on_error is not None:
                on_error(exc)
                return
            QMessageBox.critical(self, "操作失败", str(exc))

        def handle_result(result) -> None:
            self._set_buttons_state(False)
            self._set_status("操作完成")
            if on_result is not None:
                on_result(result)

        self.task_runner.start(
            task,
            on_started=lambda: (self._set_buttons_state(True), self._set_status(status_text)),
            on_result=handle_result,
            on_error=handle_error,
            on_finished=None,
        )

    def save_current_config(self) -> None:
        try:
            save_config(self._collect_form_config())
            self.state.config_data = load_config()
            self._load_bucket_options_from_config()
            self._set_status("配置已保存")
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))

    def test_connection(self) -> None:
        manager = self._make_manager()
        if not manager:
            return

        def on_success(result: dict[str, object]) -> None:
            bucket_names = list(result.get("buckets", []))
            self._replace_bucket_items(bucket_names)
            if bucket_names and not self.bucket_combo.currentText().strip():
                self.bucket_combo.setCurrentText(bucket_names[0])
            self._save_bucket_history(bucket_names)
            self._set_status(f"连接成功，共检测到 {result.get('bucket_count', 0)} 个 bucket")

        self._run_task("正在测试连接...", manager.test_connection, on_result=on_success)

    def load_buckets(self) -> None:
        manager = self._make_manager()
        if not manager:
            return

        def on_success(bucket_names: list[str]) -> None:
            self._replace_bucket_items(bucket_names)
            current_bucket = self.bucket_combo.currentText().strip()
            if bucket_names and current_bucket not in bucket_names:
                self.bucket_combo.setCurrentText(bucket_names[0])
            self._save_bucket_history(bucket_names)
            self._set_status(f"已加载 {len(bucket_names)} 个 bucket")

        self._run_task("正在加载 bucket 列表...", manager.list_buckets, on_result=on_success)

    def refresh_objects(self) -> None:
        self._refresh_objects(show_error=True, status_text="正在刷新对象列表...")

    def _refresh_objects(self, show_error: bool, status_text: str) -> None:
        manager = self._make_manager()
        if not manager:
            return

        bucket = self.bucket_combo.currentText().strip()
        if not bucket:
            if show_error:
                QMessageBox.critical(self, "缺少 Bucket", "请先选择一个 bucket。")
            else:
                self._set_status("未找到可自动加载的 bucket")
            return

        prefix = self.prefix_edit.text().strip()

        def task() -> dict[str, object]:
            visible_objects = manager.list_objects(bucket, prefix)
            storage_objects = visible_objects if not prefix else manager.list_objects(bucket, "")
            return {"visible_objects": visible_objects, "storage_objects": storage_objects}

        def on_success(result: dict[str, object]) -> None:
            visible_objects = list(result.get("visible_objects", []))
            storage_objects = list(result.get("storage_objects", visible_objects))
            self.state.all_objects = visible_objects
            self._set_storage_snapshot(bucket, storage_objects)
            self._apply_search_filter()
            self._set_status(f"已加载 {len(visible_objects)} 个对象")

        def on_error(exc: Exception) -> None:
            if show_error:
                QMessageBox.critical(self, "操作失败", str(exc))
            else:
                self._set_status(f"自动加载失败：{exc}")

        self._run_task(status_text, task, on_result=on_success, on_error=on_error)

    def upload_file(self) -> None:
        manager = self._make_manager()
        if not manager:
            return

        bucket = self.bucket_combo.currentText().strip()
        if not bucket:
            QMessageBox.critical(self, "缺少 Bucket", "请先选择一个 bucket。")
            return

        local_path, _filter = QFileDialog.getOpenFileName(self, "选择要上传的文件")
        if not local_path:
            return

        default_key = Path(local_path).name
        prefix = self.prefix_edit.text().strip().strip("/")
        if prefix:
            default_key = f"{prefix}/{default_key}"

        object_key, ok = QInputDialog.getText(
            self,
            "对象 Key",
            "请输入上传后的对象 Key：",
            text=default_key,
        )
        if not ok or not object_key.strip():
            return
        object_key = object_key.strip()

        def task() -> None:
            manager.upload_file(bucket, local_path, object_key)

        def on_success(_result: object) -> None:
            self._apply_storage_upload_update(bucket, object_key, local_path)
            self._set_status(f"文件已上传到 {bucket}/{object_key}")
            self.refresh_objects()

        self._run_task("正在上传文件...", task, on_result=on_success)

    def download_selected(self) -> None:
        manager = self._make_manager()
        if not manager:
            return

        bucket = self.bucket_combo.currentText().strip()
        selected_keys = self._get_selected_keys()
        if not bucket:
            QMessageBox.critical(self, "缺少 Bucket", "请先选择一个 bucket。")
            return
        if not selected_keys:
            QMessageBox.warning(self, "未选择对象", "请先在列表中选择要下载的对象。")
            return

        if len(selected_keys) == 1:
            default_name = Path(selected_keys[0]).name or "downloaded_file"
            save_path, _filter = QFileDialog.getSaveFileName(self, "保存下载文件", default_name)
            if not save_path:
                return
            targets = [(selected_keys[0], save_path)]
        else:
            directory = QFileDialog.getExistingDirectory(self, "选择下载目录")
            if not directory:
                return
            targets = [(key, str(Path(directory) / Path(key).name)) for key in selected_keys]

        def task() -> int:
            for key, destination in targets:
                manager.download_file(bucket, key, destination)
            return len(targets)

        def on_success(count: int) -> None:
            self._set_status(f"已下载 {count} 个对象")

        self._run_task("正在下载对象...", task, on_result=on_success)

    def delete_selected(self) -> None:
        manager = self._make_manager()
        if not manager:
            return

        bucket = self.bucket_combo.currentText().strip()
        selected_keys = self._get_selected_keys()
        if not bucket:
            QMessageBox.critical(self, "缺少 Bucket", "请先选择一个 bucket。")
            return
        if not selected_keys:
            QMessageBox.warning(self, "未选择对象", "请先在列表中选择要删除的对象。")
            return

        confirmed = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除选中的 {len(selected_keys)} 个对象吗？此操作不可撤销。",
        )
        if confirmed != QMessageBox.Yes:
            return

        def task() -> dict[str, object]:
            return manager.delete_objects(bucket, selected_keys)

        def on_success(result: dict[str, object]) -> None:
            deleted_keys = list(result.get("deleted", []))
            errors = list(result.get("errors", []))
            self._remove_object_records(bucket, deleted_keys)
            self._apply_storage_delete_update(bucket, deleted_keys)
            self._set_status(f"已删除 {len(deleted_keys)} 个对象")
            if errors:
                QMessageBox.warning(self, "删除完成", "\n".join(errors[:10]))
            self.refresh_objects()

        self._run_task("正在删除对象...", task, on_result=on_success)

    def set_selected_file_expire_seconds(self) -> None:
        bucket = self.bucket_combo.currentText().strip()
        object_key = self._get_selected_single_key()
        if not bucket:
            QMessageBox.critical(self, "缺少 Bucket", "请先选择一个 bucket。")
            return
        if object_key is None:
            QMessageBox.warning(self, "选择数量不正确", "请只选择一个文件来设置过期秒数。")
            return

        current_seconds = self._get_file_expire_seconds(bucket, object_key)
        expire_seconds, ok = QInputDialog.getInt(
            self,
            "设置过期秒数",
            "请输入该文件默认的过期秒数：",
            value=current_seconds,
            minValue=1,
        )
        if not ok:
            return

        self._update_object_record(bucket, object_key, {"default_expire_seconds": expire_seconds})
        self._apply_search_filter()
        self._set_status(f"已为 {object_key} 设置默认过期秒数：{expire_seconds}")

    def generate_presigned_url(self) -> None:
        manager = self._make_manager()
        if not manager:
            return

        bucket = self.bucket_combo.currentText().strip()
        object_key = self._get_selected_single_key()
        if not bucket:
            QMessageBox.critical(self, "缺少 Bucket", "请先选择一个 bucket。")
            return
        if object_key is None:
            QMessageBox.warning(self, "选择数量不正确", "请只选择一个对象来生成预签名 URL。")
            return

        expire_seconds = self._get_file_expire_seconds(bucket, object_key)

        def task() -> dict[str, object]:
            url = manager.generate_presigned_url(bucket, object_key, expire_seconds)
            generated_at = datetime.now().astimezone()
            expires_at = generated_at + timedelta(seconds=expire_seconds)
            return {
                "url": url,
                "generated_at": generated_at.isoformat(),
                "expires_at": expires_at.isoformat(),
                "expire_seconds": expire_seconds,
            }

        def on_success(result: dict[str, object]) -> None:
            self._update_object_record(
                bucket,
                object_key,
                {
                    "default_expire_seconds": int(result["expire_seconds"]),
                    "last_presigned_url": str(result["url"]),
                    "last_generated_at": str(result["generated_at"]),
                    "last_expires_at": str(result["expires_at"]),
                },
            )
            self.detail_panel.set_url(str(result["url"]))
            self._copy_to_clipboard(str(result["url"]))
            self._apply_search_filter()
            self._sync_detail_from_selection()
            self._set_status("预签名 URL 已生成，并已复制到剪贴板")

        self._run_task("正在生成预签名 URL...", task, on_result=on_success)

    def create_share(self) -> None:
        worker_client = self._make_worker_client()
        if not worker_client:
            return

        bucket = self.bucket_combo.currentText().strip()
        object_key = self._get_selected_single_key()
        if not bucket:
            QMessageBox.critical(self, "缺少 Bucket", "请先选择一个 bucket。")
            return
        if object_key is None:
            QMessageBox.warning(self, "选择数量不正确", "请只选择一个对象来创建分享。")
            return

        expire_seconds = self._get_file_expire_seconds(bucket, object_key)

        def task() -> dict[str, object]:
            return worker_client.create_share(bucket, object_key, expire_seconds)

        def on_success(result: dict[str, object]) -> None:
            share_url = str(result.get("share_url", "")).strip()
            token = str(result.get("token", "")).strip()
            status = str(result.get("status", "active")).strip().lower() or "active"
            created_at = str(result.get("created_at", "")).strip()
            expires_at = str(result.get("expires_at", "")).strip()
            self._update_object_record(
                bucket,
                object_key,
                {
                    "default_expire_seconds": expire_seconds,
                    "last_share_token": token,
                    "last_share_url": share_url,
                    "last_share_status": status,
                    "last_share_created_at": created_at,
                    "last_share_expires_at": expires_at,
                },
            )
            self.detail_panel.set_share_url(share_url)
            if share_url:
                self._copy_to_clipboard(share_url)
            self._apply_search_filter()
            self._sync_detail_from_selection()
            self._set_status("可撤销分享链接已创建，并已复制到剪贴板")

        self._run_task("正在创建可撤销分享...", task, on_result=on_success)

    def revoke_share(self) -> None:
        worker_client = self._make_worker_client()
        if not worker_client:
            return

        bucket = self.bucket_combo.currentText().strip()
        object_key = self._get_selected_single_key()
        if not bucket:
            QMessageBox.critical(self, "缺少 Bucket", "请先选择一个 bucket。")
            return
        if object_key is None:
            QMessageBox.warning(self, "选择数量不正确", "请只选择一个对象来停止分享。")
            return

        record = self._get_object_record(bucket, object_key)
        token = self._get_share_token_for_revoke(record)
        if not token:
            QMessageBox.warning(self, "没有可停止的分享", "当前选中的文件没有有效分享记录。")
            return

        def task() -> dict[str, object]:
            return worker_client.revoke_share(token)

        def on_success(result: dict[str, object]) -> None:
            share_status = str(result.get("status", "revoked")).strip().lower() or "revoked"
            self._update_object_record(bucket, object_key, {"last_share_status": share_status})
            self._apply_search_filter()
            self._sync_detail_from_selection()
            self._set_status("当前文件的可撤销分享已停止")

        self._run_task("正在停止分享...", task, on_result=on_success)

    def copy_url(self) -> None:
        url = self.detail_panel.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "没有可复制的 URL", "当前选中的文件没有有效的预签名 URL。")
            return
        self._copy_to_clipboard(url)
        self._set_status("预签名 URL 已复制到剪贴板")

    def copy_share_url(self) -> None:
        share_url = self.detail_panel.share_edit.text().strip()
        if not share_url:
            QMessageBox.warning(self, "没有可复制的分享链接", "当前选中的文件没有有效分享链接。")
            return
        self._copy_to_clipboard(share_url)
        self._set_status("分享链接已复制到剪贴板")

    def _copy_to_clipboard(self, value: str) -> None:
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(value)

    def _on_selection_changed(self) -> None:
        self.state.selected_keys = self._get_selected_keys()
        self._sync_detail_from_selection()

    def _on_bucket_change(self, _value: str) -> None:
        self._refresh_storage_summary(reset_loaded_state=True)
        self._sync_detail_from_selection()

    def _apply_search_filter(self) -> None:
        keyword = self.search_edit.text().strip().lower()
        if not keyword:
            self.state.filtered_objects = list(self.state.all_objects)
        else:
            self.state.filtered_objects = [
                item for item in self.state.all_objects if keyword in str(item["key"]).lower()
            ]
        self._refresh_table()
        self._sync_detail_from_selection()

    def _refresh_table(self) -> None:
        bucket = self.bucket_combo.currentText().strip()
        selected_keys = list(self.state.selected_keys)
        self.table.populate(
            self.state.filtered_objects,
            bucket,
            self._get_file_expire_seconds,
            self._get_url_status_display,
            self._format_size,
            selected_keys=selected_keys,
        )

    def _sync_detail_from_selection(self) -> None:
        bucket = self.bucket_combo.currentText().strip()
        object_key = self._get_selected_single_key()
        if not bucket or object_key is None:
            self.detail_panel.set_object_details(None)
            self.detail_panel.set_url("")
            self.detail_panel.set_share_url("")
            return

        object_item = next((item for item in self.state.filtered_objects if str(item.get("key")) == object_key), None)
        if object_item is None:
            self.detail_panel.set_object_details(None)
            self.detail_panel.set_url("")
            self.detail_panel.set_share_url("")
            return

        self.detail_panel.set_object_details(
            {
                "key": object_key,
                "size": self._format_size(int(object_item.get("size", 0))),
                "last_modified": str(object_item.get("last_modified", "")),
                "storage_class": str(object_item.get("storage_class", "")),
                "expire_seconds": str(self._get_file_expire_seconds(bucket, object_key)),
                "url_status": self._get_url_status_display(bucket, object_key) or "-",
            }
        )
        self.detail_panel.set_url(self._get_valid_historical_url(bucket, object_key))
        self.detail_panel.set_share_url(self._get_valid_share_url(bucket, object_key))

    def _get_selected_keys(self) -> list[str]:
        return self.table.selected_keys()

    def _get_selected_single_key(self) -> str | None:
        keys = self._get_selected_keys()
        return keys[0] if len(keys) == 1 else None

    def _replace_bucket_items(self, buckets: list[str]) -> None:
        current_bucket = self.bucket_combo.currentText().strip()
        with QSignalBlocker(self.bucket_combo):
            self.bucket_combo.clear()
            for bucket in buckets:
                self.bucket_combo.addItem(bucket)
            if current_bucket:
                if current_bucket not in buckets:
                    self.bucket_combo.addItem(current_bucket)
                self.bucket_combo.setCurrentText(current_bucket)

    def _save_bucket_history(self, buckets: list[str]) -> None:
        current = self._collect_form_config()
        current["recent_buckets"] = buckets
        save_config(current)
        self.state.config_data = load_config()

    def _get_file_expire_seconds(self, bucket: str, object_key: str) -> int:
        record = self._get_object_record(bucket, object_key)
        if record and isinstance(record.get("default_expire_seconds"), int):
            return int(record["default_expire_seconds"])
        return self._get_global_default_from_config()

    def _get_global_default_from_config(self) -> int:
        try:
            value = int(self.expire_edit.text().strip())
        except ValueError:
            value = int(self.state.config_data.get("url_expire_seconds", 3600))
        return max(1, value)

    def _get_object_record(self, bucket: str, object_key: str) -> dict[str, object] | None:
        object_url_settings = self.state.config_data.get("object_url_settings", {})
        bucket_settings = object_url_settings.get(bucket, {})
        record = bucket_settings.get(object_key)
        return record if isinstance(record, dict) else None

    def _update_object_record(self, bucket: str, object_key: str, updates: dict[str, object]) -> None:
        object_url_settings = dict(self.state.config_data.get("object_url_settings", {}))
        bucket_settings = dict(object_url_settings.get(bucket, {}))
        record = dict(bucket_settings.get(object_key, {}))
        record.update(updates)
        bucket_settings[object_key] = record
        object_url_settings[bucket] = bucket_settings
        self.state.config_data["object_url_settings"] = object_url_settings
        save_config(self._collect_form_config())
        self.state.config_data = load_config()

    def _remove_object_records(self, bucket: str, object_keys: list[str]) -> None:
        object_url_settings = dict(self.state.config_data.get("object_url_settings", {}))
        bucket_settings = dict(object_url_settings.get(bucket, {}))
        changed = False
        for object_key in object_keys:
            if object_key in bucket_settings:
                bucket_settings.pop(object_key, None)
                changed = True
        if not changed:
            return
        object_url_settings[bucket] = bucket_settings
        self.state.config_data["object_url_settings"] = object_url_settings
        save_config(self._collect_form_config())
        self.state.config_data = load_config()

    def _refresh_storage_summary(self, reset_loaded_state: bool = False) -> None:
        bucket = self.bucket_combo.currentText().strip()
        if reset_loaded_state:
            self.state.current_capacity_bucket = bucket
            self.state.current_capacity_total_bytes = 0
            self.state.current_capacity_sizes = {}
            self.state.current_capacity_loaded = False

        display_bucket = bucket or "未选择"
        used_bytes = (
            self.state.current_capacity_total_bytes
            if self.state.current_capacity_loaded and self.state.current_capacity_bucket == bucket
            else 0
        )
        percent = (used_bytes / STORAGE_LIMIT_BYTES) * 100 if STORAGE_LIMIT_BYTES > 0 else 0.0
        self.detail_panel.set_storage_summary(
            f"当前 bucket：{display_bucket}",
            f"已用空间：{self._format_size(used_bytes)} / {self._format_size(STORAGE_LIMIT_BYTES)}",
            f"已用比例：{self._format_storage_percent(percent, used_bytes)}",
            "所有 bucket 合计：暂未统计",
            used_bytes,
            STORAGE_LIMIT_BYTES,
        )

    def _set_storage_snapshot(self, bucket: str, objects: list[dict[str, object]]) -> None:
        self.state.current_capacity_bucket = bucket
        self.state.current_capacity_sizes = self._build_object_size_index(objects)
        self.state.current_capacity_total_bytes = sum(self.state.current_capacity_sizes.values())
        self.state.current_capacity_loaded = True
        self._refresh_storage_summary()

    def _build_object_size_index(self, objects: list[dict[str, object]]) -> dict[str, int]:
        size_index: dict[str, int] = {}
        for item in objects:
            key = str(item.get("key", "")).strip()
            if key:
                size_index[key] = self._coerce_object_size(item.get("size", 0))
        return size_index

    def _coerce_object_size(self, value: object) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    def _format_storage_percent(self, percent: float, used_bytes: int) -> str:
        if used_bytes <= 0:
            return "0.0%"
        if 0 < percent < 0.1:
            return "<0.1%"
        return f"{percent:.1f}%"

    def _apply_storage_upload_update(self, bucket: str, object_key: str, local_path: str) -> None:
        if not self.state.current_capacity_loaded or self.state.current_capacity_bucket != bucket:
            return
        try:
            new_size = max(0, Path(local_path).stat().st_size)
        except OSError:
            return
        old_size = self.state.current_capacity_sizes.get(object_key, 0)
        self.state.current_capacity_sizes[object_key] = new_size
        self.state.current_capacity_total_bytes = max(
            0,
            self.state.current_capacity_total_bytes + new_size - old_size,
        )
        self._refresh_storage_summary()

    def _apply_storage_delete_update(self, bucket: str, object_keys: list[str]) -> None:
        if not self.state.current_capacity_loaded or self.state.current_capacity_bucket != bucket:
            return
        removed_bytes = 0
        for object_key in object_keys:
            removed_bytes += self.state.current_capacity_sizes.pop(object_key, 0)
        self.state.current_capacity_total_bytes = max(0, self.state.current_capacity_total_bytes - removed_bytes)
        self._refresh_storage_summary()

    def _get_url_status_display(self, bucket: str, object_key: str) -> str:
        record = self._get_object_record(bucket, object_key)
        if not record:
            return ""
        expires_at = self._parse_datetime(str(record.get("last_expires_at", "")))
        if expires_at is None:
            return ""
        expires_text = expires_at.strftime("%Y-%m-%d %H:%M:%S")
        now = datetime.now().astimezone()
        if now >= expires_at:
            return f"{expires_text} | 已过期"
        return f"{expires_text} | 剩余 {self._format_remaining(expires_at - now)}"

    def _get_valid_historical_url(self, bucket: str, object_key: str) -> str:
        record = self._get_object_record(bucket, object_key)
        if not record:
            return ""
        url = str(record.get("last_presigned_url", "")).strip()
        if not url:
            return ""
        expires_at = self._parse_datetime(str(record.get("last_expires_at", "")))
        if expires_at is None or datetime.now().astimezone() >= expires_at:
            return ""
        return url

    def _get_valid_share_url(self, bucket: str, object_key: str) -> str:
        record = self._get_object_record(bucket, object_key)
        if not self._has_active_share_record(record):
            return ""
        return str(record.get("last_share_url", "")).strip()

    def _has_active_share_record(self, record: dict[str, object] | None) -> bool:
        if not record:
            return False
        status = str(record.get("last_share_status", "")).strip().lower()
        if status != "active":
            return False
        share_url = str(record.get("last_share_url", "")).strip()
        token = str(record.get("last_share_token", "")).strip()
        if not share_url or not token:
            return False
        expires_at = self._parse_datetime(str(record.get("last_share_expires_at", "")))
        return bool(expires_at and datetime.now().astimezone() < expires_at)

    def _get_share_token_for_revoke(self, record: dict[str, object] | None) -> str:
        if not self._has_active_share_record(record):
            return ""
        return str(record.get("last_share_token", "")).strip()

    def _parse_datetime(self, value: str) -> datetime | None:
        if not value:
            return None
        normalized = value.strip()
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return parsed.astimezone() if parsed.tzinfo is None else parsed

    def _format_remaining(self, delta) -> str:
        total_seconds = max(0, int(delta.total_seconds()))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}小时{minutes}分钟{seconds}秒"
        if minutes > 0:
            return f"{minutes}分钟{seconds}秒"
        return f"{seconds}秒"

    def _format_size(self, size: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.2f} {unit}"
            value /= 1024
        return f"{size} B"

    def _auto_refresh_on_startup(self) -> None:
        if self._can_auto_refresh_on_startup():
            self._refresh_objects(show_error=False, status_text="正在自动加载当前 bucket 的文件列表...")

    def _can_auto_refresh_on_startup(self) -> bool:
        if not self.bucket_combo.currentText().strip():
            return False
        required_values = [
            self.account_id_edit.text().strip(),
            self.access_key_edit.text().strip(),
            self.secret_key_edit.text().strip(),
        ]
        return all(required_values)

    def _refresh_countdown_timer(self) -> None:
        if self.state.filtered_objects:
            self._refresh_table()
            self._sync_detail_from_selection()

    def _clear_layout(self, layout: QGridLayout) -> None:
        while layout.count():
            layout.takeAt(0)

    def _rebuild_responsive_layouts(self) -> None:
        width = self.width()
        self._rebuild_config_fields(width)
        self._rebuild_config_actions(width)
        self._rebuild_filter_layout(width)
        self._rebuild_action_layout(width)
        self._update_splitter_orientation(width)

    def _rebuild_config_fields(self, width: int) -> None:
        self._clear_layout(self.config_fields_layout)
        columns = 3 if width >= 1320 else 2 if width >= 980 else 1
        for index, wrapper in enumerate(self.config_field_wrappers):
            row = index // columns
            column = index % columns
            self.config_fields_layout.addWidget(wrapper, row, column)
        for column in range(columns):
            self.config_fields_layout.setColumnStretch(column, 1)

    def _rebuild_config_actions(self, width: int) -> None:
        self._clear_layout(self.config_actions_layout)
        columns = 3 if width >= 1120 else 2 if width >= 860 else 1
        for index, button in enumerate(self.config_action_buttons):
            row = index // columns
            column = index % columns
            self.config_actions_layout.addWidget(button, row, column)
        for column in range(columns):
            self.config_actions_layout.setColumnStretch(column, 1)

    def _rebuild_filter_layout(self, width: int) -> None:
        self._clear_layout(self.filter_layout)
        if width >= 1120:
            self.filter_layout.addWidget(self.prefix_wrapper, 0, 0)
            self.filter_layout.addWidget(self.search_wrapper, 0, 1)
            self.filter_layout.addWidget(self.refresh_button, 0, 2, alignment=Qt.AlignBottom)
            self.filter_layout.setColumnStretch(0, 1)
            self.filter_layout.setColumnStretch(1, 1)
        elif width >= 860:
            self.filter_layout.addWidget(self.prefix_wrapper, 0, 0)
            self.filter_layout.addWidget(self.search_wrapper, 0, 1)
            self.filter_layout.addWidget(self.refresh_button, 1, 0, 1, 2, alignment=Qt.AlignRight)
            self.filter_layout.setColumnStretch(0, 1)
            self.filter_layout.setColumnStretch(1, 1)
        else:
            self.filter_layout.addWidget(self.prefix_wrapper, 0, 0)
            self.filter_layout.addWidget(self.search_wrapper, 1, 0)
            self.filter_layout.addWidget(self.refresh_button, 2, 0, alignment=Qt.AlignRight)
            self.filter_layout.setColumnStretch(0, 1)

    def _rebuild_action_layout(self, width: int) -> None:
        self._clear_layout(self.action_layout)
        columns = 4 if width >= 1380 else 3 if width >= 1120 else 2 if width >= 860 else 1
        for index, button in enumerate(self.object_action_buttons):
            row = index // columns
            column = index % columns
            self.action_layout.addWidget(button, row, column)
        for column in range(columns):
            self.action_layout.setColumnStretch(column, 1)

    def _update_splitter_orientation(self, width: int) -> None:
        orientation = Qt.Horizontal if width >= RESPONSIVE_VERTICAL_SPLIT_WIDTH else Qt.Vertical
        if self.main_splitter.orientation() == orientation:
            return
        self.main_splitter.setOrientation(orientation)
        if orientation == Qt.Horizontal:
            self.main_splitter.setSizes([820, 320])
        else:
            self.main_splitter.setSizes([520, 320])

    def _should_collapse_config_by_default(self) -> bool:
        config = self.state.config_data
        required_keys = [
            "account_id",
            "access_key_id",
            "secret_access_key",
            "endpoint_url",
        ]
        return all(str(config.get(key, "")).strip() for key in required_keys)
