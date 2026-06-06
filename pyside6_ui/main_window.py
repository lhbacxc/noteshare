from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from threading import Event, Lock
from time import monotonic

from PySide6.QtCore import QEvent, QObject, QSignalBlocker, QTimer, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
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
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app_logger import LOG_LEVEL_LABELS, clean_log_level, configure_app_logger
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
from upload_control import UploadInterrupted
from upload_resume_store import (
    calculate_file_md5,
    delete_upload_sessions_for_file,
    find_upload_session_by_content,
    find_upload_sessions_for_file,
    list_upload_sessions,
    load_upload_session,
    make_upload_session_key,
    save_upload_session,
)
from webdav_sync import (
    download_config_from_webdav as download_config_file_from_webdav,
    upload_config_to_webdav as upload_config_file_to_webdav,
)
from worker_client import WorkerClient, WorkerClientError


UploadCancelled = UploadInterrupted

ACTION_BUTTON_MAX_COLUMNS = 5
ACTION_BUTTON_TARGET_COLUMN_WIDTH = 240


class NoteShareMainWindow(QMainWindow):
    def __init__(self, icon_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("NoteShare R2 管理工具")
        self.resize(WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.setStyleSheet(APP_STYLESHEET)
        if icon_path and icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.state = UiState(config_data=load_config())
        self.logger = configure_app_logger(self.state.config_data.get("log_level", "error"))
        self.task_runner = TaskRunner()
        self.action_buttons: list[QPushButton] = []
        self.drop_upload_targets: list[QWidget] = []
        self._upload_in_progress = False
        self._upload_cancel_event: Event | None = None
        self._upload_stop_reason: str | None = None
        self._resume_upload_bucket = ""
        self._resume_upload_items: list[tuple[str, str, int]] = []
        self._resume_upload_reason: str | None = None
        self._pending_close_after_upload_stop = False
        self._upload_progress_last_value = 0

        self._build_ui()
        self._load_config_to_form()
        self._load_bucket_options_from_config()
        self._refresh_storage_summary(reset_loaded_state=True)
        self._wire_events()
        self._enable_drag_upload()
        self._load_resumable_upload_task_from_store()

        self.startup_timer = QTimer(self)
        self.startup_timer.setSingleShot(True)
        self.startup_timer.timeout.connect(self._auto_refresh_on_startup)
        self.startup_timer.start(AUTO_REFRESH_DELAY_MS)

        self.countdown_timer = QTimer(self)
        self.countdown_timer.timeout.connect(self._refresh_countdown_timer)
        self.countdown_timer.start(COUNTDOWN_REFRESH_MS)

    def _build_ui(self) -> None:
        self.app_scroll_area = QScrollArea()
        self.app_scroll_area.setObjectName("AppScrollArea")
        self.app_scroll_area.setWidgetResizable(True)
        self.app_scroll_area.setFrameShape(QFrame.NoFrame)

        self.app_canvas = QWidget()
        self.app_canvas.setObjectName("AppCanvas")
        root_layout = QVBoxLayout(self.app_canvas)
        root_layout.setContentsMargins(24, 24, 24, 24)
        root_layout.setSpacing(18)

        self.config_section = CollapsibleSection("连接配置")
        config_layout = QGridLayout()
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setHorizontalSpacing(14)
        config_layout.setVerticalSpacing(12)

        self.account_id_edit = self._make_line_edit()
        self.access_key_edit = self._make_line_edit()
        self.secret_key_edit = self._make_line_edit(password=True)
        self.endpoint_edit = self._make_line_edit()
        self.expire_edit = self._make_line_edit()
        self.worker_base_url_edit = self._make_line_edit()
        self.worker_admin_token_edit = self._make_line_edit(password=True)
        self.webdav_url_edit = self._make_line_edit()
        self.webdav_username_edit = self._make_line_edit()
        self.webdav_password_edit = self._make_line_edit(password=True)
        self.webdav_remote_path_edit = self._make_line_edit()
        self.bucket_combo = QComboBox()
        self.bucket_combo.setEditable(True)
        self.bucket_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.bucket_combo.setInsertPolicy(QComboBox.NoInsert)
        self.log_level_combo = QComboBox()
        self.log_level_combo.setEditable(False)
        for level_value, level_label in LOG_LEVEL_LABELS.items():
            self.log_level_combo.addItem(level_label, level_value)

        self.config_field_wrappers = [
            self._make_labeled_wrapper("Account ID", self.account_id_edit),
            self._make_labeled_wrapper("Access Key ID", self.access_key_edit),
            self._make_labeled_wrapper("Secret Access Key", self.secret_key_edit),
            self._make_labeled_wrapper("Endpoint URL", self.endpoint_edit),
            self._make_labeled_wrapper("默认过期秒数", self.expire_edit),
            self._make_labeled_wrapper("Worker Base URL", self.worker_base_url_edit),
            self._make_labeled_wrapper("Worker Admin Token", self.worker_admin_token_edit),
            self._make_labeled_wrapper("WebDAV URL", self.webdav_url_edit),
            self._make_labeled_wrapper("WebDAV 用户名", self.webdav_username_edit),
            self._make_labeled_wrapper("WebDAV 密码", self.webdav_password_edit),
            self._make_labeled_wrapper("WebDAV 远端路径", self.webdav_remote_path_edit),
            self._make_labeled_wrapper("Bucket", self.bucket_combo),
            self._make_labeled_wrapper("日志等级", self.log_level_combo),
        ]
        self.config_fields_layout = QGridLayout()
        self.config_fields_layout.setContentsMargins(0, 0, 0, 0)
        self.config_fields_layout.setHorizontalSpacing(14)
        self.config_fields_layout.setVerticalSpacing(12)

        self.save_button = self._make_button("保存配置")
        self.test_button = self._make_button("测试连接", primary=True)
        self.load_buckets_button = self._make_button("加载 Bucket")
        self.upload_config_button = self._make_button("上传配置")
        self.download_config_button = self._make_button("下载配置", primary=True)
        self.config_action_buttons = [
            self.save_button,
            self.test_button,
            self.load_buckets_button,
            self.upload_config_button,
            self.download_config_button,
        ]
        self.config_actions_layout = QGridLayout()
        self.config_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.config_actions_layout.setHorizontalSpacing(12)
        self.config_actions_layout.setVerticalSpacing(12)

        config_layout.addLayout(self.config_fields_layout, 0, 0)
        config_layout.addLayout(self.config_actions_layout, 1, 0)
        self.config_section.set_content_layout(config_layout)

        filter_card = QGroupBox("筛选与浏览")
        filter_card.setObjectName("SurfaceCard")
        self.filter_layout = QGridLayout(filter_card)
        self.filter_layout.setContentsMargins(18, 20, 18, 18)
        self.filter_layout.setHorizontalSpacing(14)
        self.filter_layout.setVerticalSpacing(12)
        self.prefix_edit = self._make_line_edit()
        self.prefix_edit.setPlaceholderText("输入前缀，例如 notes/ 或 images/")
        self.search_edit = self._make_line_edit()
        self.search_edit.setPlaceholderText("搜索对象 key")
        self.refresh_button = self._make_button("刷新列表", primary=True)
        self.prefix_wrapper = self._make_labeled_wrapper("前缀", self.prefix_edit)
        self.search_wrapper = self._make_labeled_wrapper("搜索", self.search_edit)

        self.action_card = QGroupBox("对象操作")
        self.action_card.setObjectName("SurfaceCard")
        self.action_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.action_layout = QGridLayout(self.action_card)
        self.action_layout.setContentsMargins(18, 14, 18, 14)
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
        self.upload_progress_panel = QWidget()
        self.upload_progress_panel.setObjectName("UploadProgressPanel")
        self.upload_progress_layout = QVBoxLayout(self.upload_progress_panel)
        self.upload_progress_layout.setContentsMargins(12, 10, 12, 10)
        self.upload_progress_layout.setSpacing(6)
        self.upload_progress_title = QLabel("上传状态")
        self.upload_progress_title.setObjectName("UploadProgressTitle")
        self.pause_upload_button = QPushButton("暂停上传")
        self.pause_upload_button.setObjectName("SecondaryButton")
        self.pause_upload_button.setEnabled(False)
        self.resume_upload_button = QPushButton("继续上传")
        self.resume_upload_button.setObjectName("PrimaryButton")
        self.resume_upload_button.setEnabled(False)
        self.cancel_upload_button = QPushButton("取消上传")
        self.cancel_upload_button.setObjectName("DangerButton")
        self.cancel_upload_button.setEnabled(False)
        self.upload_progress_bar = QProgressBar()
        self.upload_progress_bar.setObjectName("UploadProgressBar")
        self.upload_progress_bar.setRange(0, 1000)
        self.upload_progress_bar.setValue(0)
        self.upload_progress_bar.setTextVisible(False)
        self.upload_progress_detail = QLabel("待上传")
        self.upload_progress_detail.setObjectName("UploadProgressDetail")
        self.upload_progress_detail.setWordWrap(True)
        upload_progress_header = QWidget()
        upload_progress_header.setObjectName("UploadProgressHeader")
        upload_progress_header_layout = QHBoxLayout(upload_progress_header)
        upload_progress_header_layout.setContentsMargins(0, 0, 0, 0)
        upload_progress_header_layout.setSpacing(8)
        upload_progress_header_layout.addWidget(self.upload_progress_title, 1)
        upload_progress_header_layout.addWidget(self.resume_upload_button)
        upload_progress_header_layout.addWidget(self.pause_upload_button)
        upload_progress_header_layout.addWidget(self.cancel_upload_button)
        self.upload_progress_layout.addWidget(upload_progress_header)
        self.upload_progress_layout.addWidget(self.upload_progress_bar)
        self.upload_progress_layout.addWidget(self.upload_progress_detail)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        self.table_header = QWidget()
        self.table_header.setObjectName("PaneHeader")
        table_header_layout = QHBoxLayout(self.table_header)
        table_header_layout.setContentsMargins(0, 0, 0, 0)
        table_header_layout.setSpacing(8)
        self.table_title_label = QLabel("对象列表")
        self.table_title_label.setObjectName("PaneTitle")
        self.inline_status_label = QLabel("就绪")
        self.inline_status_label.setObjectName("InlineStatusText")
        self.inline_status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.inline_status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.table = ObjectTableWidget()
        table_header_layout.addWidget(self.table_title_label)
        table_header_layout.addWidget(self.inline_status_label, 1)
        left_layout.addWidget(self.table_header)
        left_layout.addWidget(self.table, 1)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self.detail_title_spacer = QWidget()
        self.detail_title_spacer.setObjectName("PaneTitleSpacer")
        self.detail_title_spacer.setFixedHeight(9)

        self.detail_panel = DetailPanel()
        self.action_buttons.extend(
            [self.detail_panel.copy_url_button, self.detail_panel.copy_share_button]
        )
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setObjectName("DetailScrollArea")
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.NoFrame)
        self.detail_scroll.setWidget(self.detail_panel)
        self.detail_scroll.setMinimumWidth(280)
        self.detail_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout.addWidget(self.detail_title_spacer)
        right_layout.addWidget(self.detail_scroll, 1)
        self.main_splitter.addWidget(left_panel)
        self.main_splitter.addWidget(right_panel)
        self.main_splitter.setStretchFactor(0, 4)
        self.main_splitter.setStretchFactor(1, 2)
        self.main_splitter.setSizes([860, 340])

        root_layout.addWidget(self.config_section)
        root_layout.addWidget(filter_card)
        root_layout.addWidget(self.main_splitter, 1)
        root_layout.addWidget(self.action_card)

        self.app_scroll_area.setWidget(self.app_canvas)
        self.setCentralWidget(self.app_scroll_area)
        self._set_status("就绪")
        self._rebuild_responsive_layouts()
        self.config_section.set_collapsed(self._should_collapse_config_by_default())
        self._sync_config_section_summary()

    def _wire_events(self) -> None:
        self.save_button.clicked.connect(self.save_current_config)
        self.test_button.clicked.connect(self.test_connection)
        self.load_buckets_button.clicked.connect(self.load_buckets)
        self.upload_config_button.clicked.connect(self.upload_config_to_webdav)
        self.download_config_button.clicked.connect(self.download_config_from_webdav)
        self.refresh_button.clicked.connect(self.refresh_objects)
        self.upload_button.clicked.connect(self.upload_file)
        self.pause_upload_button.clicked.connect(self._request_pause_upload)
        self.resume_upload_button.clicked.connect(self._resume_paused_upload)
        self.cancel_upload_button.clicked.connect(self._request_cancel_upload)
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

    def _enable_drag_upload(self) -> None:
        candidates = [
            self,
            self.centralWidget(),
            self.app_scroll_area,
            self.app_scroll_area.viewport(),
            self.app_canvas,
            self.main_splitter,
            self.table,
            self.table.viewport(),
            self.action_card,
        ]
        seen_targets: set[int] = set()
        for target in candidates:
            if target is None:
                continue
            target_id = id(target)
            if target_id in seen_targets:
                continue
            seen_targets.add(target_id)
            target.setAcceptDrops(True)
            target.installEventFilter(self)
            self.drop_upload_targets.append(target)

    def _make_line_edit(self, password: bool = False) -> QLineEdit:
        line_edit = QLineEdit()
        line_edit.setClearButtonEnabled(not password)
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
        title_label = QLabel(label)
        title_label.setObjectName("FieldLabel")
        wrapper_layout.addWidget(title_label)
        wrapper_layout.addWidget(widget)
        return wrapper

    def _make_section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionLabel")
        return label

    def _prompt_object_key(self, default_key: str) -> str | None:
        dialog = QInputDialog(self)
        dialog.setInputMode(QInputDialog.TextInput)
        dialog.setWindowTitle("对象 Key")
        dialog.setLabelText("请输入上传后的对象 Key：")
        dialog.setTextValue(default_key)
        dialog.setOkButtonText("上传")
        dialog.setCancelButtonText("取消")
        dialog.setStyleSheet(APP_STYLESHEET)
        dialog.resize(460, 180)
        if dialog.exec() != QDialog.Accepted:
            return None

        value = dialog.textValue().strip()
        return value or None

    def _load_config_to_form(self) -> None:
        config = self.state.config_data
        self.account_id_edit.setText(str(config.get("account_id", "")))
        self.access_key_edit.setText(str(config.get("access_key_id", "")))
        self.secret_key_edit.setText(str(config.get("secret_access_key", "")))
        self.endpoint_edit.setText(str(config.get("endpoint_url", "")))
        self.worker_base_url_edit.setText(str(config.get("worker_base_url", "")))
        self.worker_admin_token_edit.setText(str(config.get("worker_admin_token", "")))
        self.webdav_url_edit.setText(str(config.get("webdav_url", "")))
        self.webdav_username_edit.setText(str(config.get("webdav_username", "")))
        self.webdav_password_edit.setText(str(config.get("webdav_password", "")))
        self.webdav_remote_path_edit.setText(str(config.get("webdav_remote_path", "noteshare/config.json")))
        self.expire_edit.setText(str(config.get("url_expire_seconds", 3600)))
        self.bucket_combo.setCurrentText(str(config.get("default_bucket", "")))
        self._set_log_level_combo(str(config.get("log_level", "error")))
        self._sync_config_section_summary()

    def _set_log_level_combo(self, level: str) -> None:
        cleaned_level = clean_log_level(level)
        index = self.log_level_combo.findData(cleaned_level)
        if index >= 0:
            self.log_level_combo.setCurrentIndex(index)

    def _current_log_level(self) -> str:
        return clean_log_level(self.log_level_combo.currentData())

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
        self._sync_config_section_summary()

    def _load_resumable_upload_task_from_store(self) -> None:
        sessions = list_upload_sessions()
        upload_items: list[tuple[str, str, int]] = []
        latest_bucket = ""
        latest_updated_at = ""

        for session in sessions.values():
            bucket = str(session.get("bucket", "")).strip()
            object_key = str(session.get("object_key", "")).strip()
            local_path = str(session.get("local_path", "")).strip()
            updated_at = str(session.get("updated_at", "")).strip()
            try:
                expected_size = int(session.get("local_size", 0))
            except (TypeError, ValueError):
                expected_size = 0
            if not bucket or not object_key or not local_path:
                continue
            path = Path(local_path)
            try:
                actual_size = path.stat().st_size
            except OSError:
                continue
            if expected_size > 0 and actual_size != expected_size:
                continue
            if updated_at >= latest_updated_at:
                latest_updated_at = updated_at
                latest_bucket = bucket

        if not latest_bucket:
            return

        for session in sessions.values():
            if str(session.get("bucket", "")).strip() != latest_bucket:
                continue
            object_key = str(session.get("object_key", "")).strip()
            local_path = str(session.get("local_path", "")).strip()
            try:
                expected_size = int(session.get("local_size", 0))
            except (TypeError, ValueError):
                expected_size = 0
            path = Path(local_path)
            try:
                actual_size = path.stat().st_size
            except OSError:
                continue
            if expected_size > 0 and actual_size != expected_size:
                continue
            upload_items.append((str(path), object_key, max(0, actual_size)))

        if not upload_items:
            return

        if latest_bucket and self.bucket_combo.findText(latest_bucket) < 0:
            self.bucket_combo.addItem(latest_bucket)
        self.bucket_combo.setCurrentText(latest_bucket)
        self._resume_upload_bucket = latest_bucket
        self._resume_upload_items = upload_items
        self._resume_upload_reason = "stored"
        self.resume_upload_button.setEnabled(True)
        self.cancel_upload_button.setEnabled(True)
        total_bytes = sum(item_size for _item_path, _item_key, item_size in upload_items)
        names = ", ".join(Path(item_path).name for item_path, _item_key, _item_size in upload_items[:3])
        if len(upload_items) > 3:
            names = f"{names} 等 {len(upload_items)} 个文件"
        self._set_upload_progress_value(0)
        self.upload_progress_title.setText("发现可继续上传")
        self.upload_progress_detail.setText(
            f"{names} · {self._format_size(total_bytes)} · 可点击继续上传"
        )

    def _collect_form_config(self) -> dict[str, object]:
        return {
            "account_id": self.account_id_edit.text().strip(),
            "access_key_id": self.access_key_edit.text().strip(),
            "secret_access_key": self.secret_key_edit.text().strip(),
            "endpoint_url": self.endpoint_edit.text().strip(),
            "worker_base_url": self.worker_base_url_edit.text().strip(),
            "worker_admin_token": self.worker_admin_token_edit.text().strip(),
            "webdav_url": self.webdav_url_edit.text().strip(),
            "webdav_username": self.webdav_username_edit.text().strip(),
            "webdav_password": self.webdav_password_edit.text().strip(),
            "webdav_remote_path": self.webdav_remote_path_edit.text().strip(),
            "default_bucket": self.bucket_combo.currentText().strip(),
            "url_expire_seconds": self.expire_edit.text().strip(),
            "log_level": self._current_log_level(),
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
        if hasattr(self, "inline_status_label"):
            self.inline_status_label.setText(message)
            self.inline_status_label.setToolTip(message)
        self._sync_config_section_summary(status_override=message)

    def _set_buttons_state(self, disabled: bool) -> None:
        for button in self.action_buttons:
            button.setDisabled(disabled)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._rebuild_responsive_layouts()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._upload_in_progress:
            super().closeEvent(event)
            return

        if self._upload_stop_reason == "pause":
            event.ignore()
            self._pending_close_after_upload_stop = True
            self._set_status("正在暂停上传，完成后将关闭窗口...")
            return

        choice = QMessageBox.question(
            self,
            "上传仍在进行",
            "当前仍有文件上传中。是否取消上传并关闭窗口？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if choice == QMessageBox.Yes:
            event.ignore()
            self._pending_close_after_upload_stop = True
            self._request_cancel_upload()
            return

        event.ignore()
        self._set_status("上传仍在继续")

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched in self.drop_upload_targets:
            if event.type() in {QEvent.Type.DragEnter, QEvent.Type.DragMove}:
                return self._handle_drag_upload_preview(event)
            if event.type() == QEvent.Type.Drop:
                return self._handle_drag_upload_drop(event)
        return super().eventFilter(watched, event)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        self._handle_drag_upload_preview(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        self._handle_drag_upload_preview(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        self._handle_drag_upload_drop(event)

    def _handle_drag_upload_preview(self, event) -> bool:
        if self._upload_in_progress:
            event.ignore()
            return False
        if self._local_file_paths_from_event(event):
            event.acceptProposedAction()
            return True
        event.ignore()
        return False

    def _handle_drag_upload_drop(self, event) -> bool:
        if self._upload_in_progress:
            QMessageBox.information(self, "上传进行中", "请等待当前上传完成，或先取消当前上传。")
            event.ignore()
            return False
        local_paths = self._local_file_paths_from_event(event)
        if not local_paths:
            QMessageBox.warning(self, "无法拖拽上传", "拖拽上传目前只支持本地文件，暂不支持文件夹或远程链接。")
            event.ignore()
            return False
        event.acceptProposedAction()
        self._upload_local_paths(local_paths, status_text="正在拖拽上传文件...")
        return True

    def _request_cancel_upload(self) -> None:
        if self._upload_in_progress:
            self._stop_upload("cancel")
            return
        if self._resume_upload_items and self._resume_upload_bucket:
            self._cancel_stored_resumable_upload()
            return
        self.cancel_upload_button.setEnabled(False)

    def _request_pause_upload(self) -> None:
        self._stop_upload("pause")

    def _stop_upload(self, reason: str) -> None:
        if not self._upload_in_progress or self._upload_cancel_event is None:
            self.cancel_upload_button.setEnabled(False)
            self.pause_upload_button.setEnabled(False)
            return
        self._upload_stop_reason = reason
        self._upload_cancel_event.set()
        self.cancel_upload_button.setEnabled(False)
        self.pause_upload_button.setEnabled(False)
        if reason == "pause":
            self._set_upload_progress_busy()
            self.upload_progress_title.setText("正在暂停上传")
            self.upload_progress_detail.setText("正在等待当前分片响应并保存断点，完成后可继续上传。")
            self._set_status("正在暂停上传...")
        else:
            self.resume_upload_button.setEnabled(False)
            self._set_upload_progress_busy()
            self.upload_progress_title.setText("正在取消上传")
            self.upload_progress_detail.setText("正在停止上传并清理本次断点，完成后下次会重新上传。")
            self._set_status("正在取消上传...")

    def _resume_paused_upload(self) -> None:
        if self._upload_in_progress:
            QMessageBox.information(self, "上传进行中", "请等待当前上传完成。")
            return
        if not self._resume_upload_items or not self._resume_upload_bucket:
            QMessageBox.information(self, "没有可继续的上传", "当前没有暂停中的上传任务。")
            self.resume_upload_button.setEnabled(False)
            return
        self._start_confirmed_upload(
            self._resume_upload_bucket,
            list(self._resume_upload_items),
            status_text="正在继续上传文件...",
        )

    def _cancel_stored_resumable_upload(self) -> None:
        manager = self._make_manager()
        if not manager:
            return

        bucket = self._resume_upload_bucket
        upload_items = list(self._resume_upload_items)
        if not bucket or not upload_items:
            self.cancel_upload_button.setEnabled(False)
            return

        self.resume_upload_button.setEnabled(False)
        self.cancel_upload_button.setEnabled(False)
        self.pause_upload_button.setEnabled(False)
        self._set_upload_progress_busy()
        self.upload_progress_title.setText("正在取消上传")
        self.upload_progress_detail.setText("正在清理已暂停任务的本地断点，并尝试停止远端未完成上传。")

        def task() -> None:
            self._cleanup_upload_sessions(manager, bucket, upload_items, ignore_abort_errors=False)

        def on_success(_result: object) -> None:
            self._resume_upload_bucket = ""
            self._resume_upload_items = []
            self._resume_upload_reason = None
            self.resume_upload_button.setEnabled(False)
            self.cancel_upload_button.setEnabled(False)
            self.pause_upload_button.setEnabled(False)
            self._mark_upload_cancelled()
            self._set_status("已取消暂停中的上传任务")

        def on_error(exc: Exception) -> None:
            self.resume_upload_button.setEnabled(True)
            self.cancel_upload_button.setEnabled(True)
            self.pause_upload_button.setEnabled(False)
            self._restore_upload_progress_range()
            self.upload_progress_title.setText("取消上传失败")
            self.upload_progress_detail.setText(f"{exc}。本地断点仍保留，可稍后重试取消或继续上传。")
            self.logger.error(
                "取消已暂停上传失败：bucket=%s, 文件=%s",
                bucket,
                self._format_upload_items_for_log(upload_items),
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            QMessageBox.critical(self, "取消上传失败", str(exc))

        self._run_task(
            "正在取消暂停中的上传任务...",
            task,
            on_result=on_success,
            on_error=on_error,
        )

    def _local_file_paths_from_event(self, event) -> list[str]:
        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            return []
        local_paths: list[str] = []
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            local_path = url.toLocalFile()
            if Path(local_path).is_file():
                local_paths.append(local_path)
        return local_paths

    def _run_task(
        self,
        status_text: str,
        task,
        on_result=None,
        on_error=None,
        on_finished=None,
        on_progress=None,
        task_accepts_progress: bool = False,
    ) -> None:
        def handle_error(exc: Exception) -> None:
            self._set_buttons_state(False)
            self._set_status("操作失败")
            if on_error is not None:
                on_error(exc)
                return
            self.logger.error(
                "后台任务失败：%s",
                status_text,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
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
            on_finished=on_finished,
            on_progress=on_progress,
            task_accepts_progress=task_accepts_progress,
        )

    def save_current_config(self) -> None:
        try:
            save_config(self._collect_form_config())
            self._reload_config_state(load_into_form=False)
            self._set_status("配置已保存")
        except OSError as exc:
            self.logger.error(
                "保存配置失败",
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            QMessageBox.critical(self, "保存失败", str(exc))

    def upload_config_to_webdav(self) -> None:
        try:
            save_config(self._collect_form_config())
            self._reload_config_state(load_into_form=False)
        except OSError as exc:
            self.logger.error(
                "上传配置前保存本地配置失败",
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            QMessageBox.critical(self, "保存失败", str(exc))
            return

        config = dict(self.state.config_data)

        def task() -> str:
            return upload_config_file_to_webdav(config)

        def on_success(remote_path: str) -> None:
            self._set_status(f"配置已上传到 WebDAV：{remote_path}")
            QMessageBox.information(self, "上传完成", f"本地配置已上传到 WebDAV：\n{remote_path}")

        self._run_task("正在上传配置到 WebDAV...", task, on_result=on_success)

    def download_config_from_webdav(self) -> None:
        config = self._collect_form_config()

        def task() -> dict[str, object]:
            return download_config_file_from_webdav(config)

        def on_success(_config: dict[str, object]) -> None:
            self._reload_config_state(load_into_form=True)
            self._refresh_storage_summary(reset_loaded_state=True)
            self._set_status("已从 WebDAV 下载并恢复配置")
            QMessageBox.information(self, "下载完成", "远端配置已下载并恢复到本地。")

        self._run_task("正在从 WebDAV 下载配置...", task, on_result=on_success)

    def _reload_config_state(self, *, load_into_form: bool) -> None:
        self.state.config_data = load_config()
        if load_into_form:
            self._load_config_to_form()
        self._set_log_level_combo(str(self.state.config_data.get("log_level", "error")))
        self.logger = configure_app_logger(self.state.config_data.get("log_level", "error"))
        self._load_bucket_options_from_config()
        self._sync_config_section_summary()

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
            self._sync_config_section_summary()
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
            self._sync_config_section_summary()
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
        if self._upload_in_progress:
            QMessageBox.information(self, "上传进行中", "请等待当前上传完成，或先取消当前上传。")
            return
        local_path, _filter = QFileDialog.getOpenFileName(self, "选择要上传的文件")
        if not local_path:
            return
        self._upload_local_paths([local_path], status_text="正在上传文件...")

    def _upload_local_paths(self, local_paths: list[str], status_text: str) -> None:
        if self._upload_in_progress:
            QMessageBox.information(self, "上传进行中", "请等待当前上传完成，或先取消当前上传。")
            return
        manager = self._make_manager()
        if not manager:
            return

        bucket = self.bucket_combo.currentText().strip()
        if not bucket:
            QMessageBox.critical(self, "缺少 Bucket", "请先选择一个 bucket。")
            return

        upload_items: list[tuple[str, str, int]] = []
        for local_path in local_paths:
            path = Path(local_path)
            if not path.is_file():
                continue
            object_key = self._prompt_object_key(self._default_upload_key(path))
            if object_key is None:
                return
            try:
                file_size = max(0, path.stat().st_size)
            except OSError as exc:
                QMessageBox.warning(self, "无法读取文件", f"{path.name}：{exc}")
                continue
            upload_items.append((str(path), object_key, file_size))

        if not upload_items:
            QMessageBox.warning(self, "没有可上传的文件", "请选择或拖入本地文件。")
            return

        self._resume_upload_bucket = bucket
        self._resume_upload_items = list(upload_items)
        self._start_confirmed_upload(bucket, upload_items, status_text)

    def _start_confirmed_upload(
        self,
        bucket: str,
        upload_items: list[tuple[str, str, int]],
        status_text: str,
    ) -> None:
        if self._upload_in_progress:
            QMessageBox.information(self, "上传进行中", "请等待当前上传完成。")
            return
        manager = self._make_manager()
        if not manager:
            return

        upload_item_content_md5s: dict[tuple[str, str, int], str] = {}
        self.logger.info(
            "上传任务开始：bucket=%s, 文件数=%s, 总大小=%s, 文件=%s",
            bucket,
            len(upload_items),
            sum(item_size for _item_path, _item_key, item_size in upload_items),
            self._format_upload_items_for_log(upload_items),
        )
        self._start_upload_progress(upload_items)
        cancel_event = Event()
        self._upload_cancel_event = cancel_event
        self._upload_in_progress = True
        self._upload_stop_reason = None
        self._resume_upload_reason = None
        self._pending_close_after_upload_stop = False
        self.resume_upload_button.setEnabled(False)
        self.pause_upload_button.setEnabled(True)
        self.cancel_upload_button.setEnabled(True)

        def task(emit_progress) -> list[tuple[str, str, int]]:
            lock = Lock()
            total_bytes = sum(item_size for _item_path, _item_key, item_size in upload_items)
            uploaded_bytes = 0
            current_file_uploaded = 0
            current_file_start = 0
            current_file_is_resuming = False
            speed_window_bytes = 0
            speed_window_started_at = monotonic()
            last_emit_at = 0.0

            def emit_snapshot(
                item_path: str,
                item_key: str,
                item_index: int,
                item_size: int,
                speed_bps: float = 0.0,
                is_resuming: bool = False,
                is_hashing: bool = False,
            ) -> None:
                emit_progress(
                    {
                        "file_name": Path(item_path).name,
                        "object_key": item_key,
                        "current_index": item_index,
                        "total_files": len(upload_items),
                        "current_file_uploaded": current_file_uploaded,
                        "current_file_size": item_size,
                        "uploaded_bytes": uploaded_bytes,
                        "total_bytes": total_bytes,
                        "speed_bps": speed_bps,
                        "is_resuming": is_resuming,
                        "is_hashing": is_hashing,
                    }
                )

            for index, (item_path, item_key, item_size) in enumerate(upload_items, start=1):
                if cancel_event.is_set():
                    raise UploadCancelled(self._upload_stop_reason or "cancel")
                with lock:
                    current_file_start = uploaded_bytes
                    current_file_uploaded = 0
                    current_file_is_resuming = False
                    speed_window_bytes = 0
                    speed_window_started_at = monotonic()
                    last_emit_at = 0.0
                    emit_snapshot(item_path, item_key, index, item_size, is_hashing=True)

                def cancel_check() -> None:
                    if cancel_event.is_set():
                        raise UploadCancelled(self._upload_stop_reason or "cancel")

                content_md5 = calculate_file_md5(item_path, cancel_check=cancel_check)
                upload_item_content_md5s[(item_path, item_key, item_size)] = content_md5
                session_key, resume_session = find_upload_session_by_content(
                    manager.credentials.endpoint_url,
                    bucket,
                    item_key,
                    item_path,
                    item_size,
                    content_md5,
                )
                if not session_key:
                    session_key = make_upload_session_key(
                        manager.credentials.endpoint_url,
                        bucket,
                        item_key,
                        item_path,
                        content_md5=content_md5,
                        local_size=item_size,
                    )
                    legacy_session_key = make_upload_session_key(
                        manager.credentials.endpoint_url,
                        bucket,
                        item_key,
                        item_path,
                    )
                    resume_session = load_upload_session(legacy_session_key)

                effective_item_key = item_key
                if isinstance(resume_session, dict):
                    stored_item_key = str(resume_session.get("object_key", "")).strip()
                    if stored_item_key:
                        effective_item_key = stored_item_key
                if effective_item_key != item_key:
                    upload_items[index - 1] = (item_path, effective_item_key, item_size)
                    item_key = effective_item_key
                    session_key = make_upload_session_key(
                        manager.credentials.endpoint_url,
                        bucket,
                        item_key,
                        item_path,
                        content_md5=content_md5,
                        local_size=item_size,
                    )
                    if not isinstance(resume_session, dict):
                        resume_session = load_upload_session(session_key)
                upload_item_content_md5s[(item_path, item_key, item_size)] = content_md5
                with lock:
                    emit_snapshot(
                        item_path,
                        item_key,
                        index,
                        item_size,
                        is_resuming=isinstance(resume_session, dict),
                    )

                def session_callback(session: dict[str, object]) -> None:
                    save_upload_session(session_key, session)

                def resumed_callback(resumed_bytes: int) -> None:
                    nonlocal current_file_uploaded
                    nonlocal current_file_is_resuming
                    nonlocal uploaded_bytes

                    if resumed_bytes <= 0:
                        return
                    with lock:
                        restored = min(item_size, max(0, int(resumed_bytes)))
                        delta = max(0, restored - current_file_uploaded)
                        current_file_uploaded = restored
                        current_file_is_resuming = restored > 0
                        uploaded_bytes = min(total_bytes, uploaded_bytes + delta)
                        emit_snapshot(
                            item_path,
                            item_key,
                            index,
                            item_size,
                            is_resuming=True,
                        )

                def progress_callback(bytes_amount: int) -> None:
                    nonlocal current_file_uploaded
                    nonlocal current_file_is_resuming
                    nonlocal last_emit_at
                    nonlocal speed_window_bytes
                    nonlocal speed_window_started_at
                    nonlocal uploaded_bytes

                    if cancel_event.is_set():
                        raise UploadCancelled(self._upload_stop_reason or "cancel")

                    with lock:
                        if cancel_event.is_set():
                            raise UploadCancelled(self._upload_stop_reason or "cancel")
                        transferred = max(0, int(bytes_amount))
                        was_resuming = current_file_is_resuming
                        current_file_is_resuming = False
                        current_file_uploaded = min(item_size, current_file_uploaded + transferred)
                        uploaded_bytes = min(total_bytes, uploaded_bytes + transferred)
                        speed_window_bytes += transferred
                        now = monotonic()
                        should_emit = (
                            was_resuming
                            or now - last_emit_at >= 0.2
                            or uploaded_bytes >= total_bytes
                        )
                        if not should_emit:
                            return
                        elapsed = max(0.001, now - speed_window_started_at)
                        speed_bps = speed_window_bytes / elapsed
                        speed_window_bytes = 0
                        speed_window_started_at = now
                        last_emit_at = now
                        emit_snapshot(
                            item_path,
                            item_key,
                            index,
                            item_size,
                            speed_bps,
                            is_resuming=current_file_is_resuming,
                        )

                manager.upload_resumable_file(
                    bucket,
                    item_path,
                    item_key,
                    resume_session=resume_session,
                    session_callback=session_callback,
                    progress_callback=progress_callback,
                    resumed_callback=resumed_callback,
                    cancel_check=cancel_check,
                    content_md5=content_md5,
                )
                if cancel_event.is_set():
                    raise UploadCancelled(self._upload_stop_reason or "cancel")
                delete_upload_sessions_for_file(
                    manager.credentials.endpoint_url,
                    bucket,
                    item_key,
                    item_path,
                    content_md5=content_md5,
                    local_size=item_size,
                )

                with lock:
                    expected_uploaded = current_file_start + item_size
                    if uploaded_bytes < expected_uploaded:
                        uploaded_bytes = min(total_bytes, expected_uploaded)
                    current_file_uploaded = item_size
                    emit_snapshot(
                        item_path,
                        item_key,
                        index,
                        item_size,
                        is_resuming=current_file_is_resuming,
                    )
            return upload_items

        def on_success(uploaded_items: list[tuple[str, str, int]]) -> None:
            for item_path, item_key, _item_size in uploaded_items:
                self._apply_storage_upload_update(bucket, item_key, item_path)
            self._resume_upload_bucket = ""
            self._resume_upload_items = []
            self._resume_upload_reason = None
            self.resume_upload_button.setEnabled(False)
            self._mark_upload_complete(uploaded_items)
            if len(uploaded_items) == 1:
                self._set_status(f"文件已上传到 {bucket}/{uploaded_items[0][1]}")
            else:
                self._set_status(f"已上传 {len(uploaded_items)} 个文件到 {bucket}")
            self.logger.info(
                "上传任务完成：bucket=%s, 文件数=%s, 文件=%s",
                bucket,
                len(uploaded_items),
                self._format_upload_items_for_log(uploaded_items),
            )
            self.refresh_objects()

        def on_error(exc: Exception) -> None:
            if isinstance(exc, UploadCancelled):
                if exc.reason == "pause":
                    self._resume_upload_bucket = bucket
                    self._resume_upload_items = list(upload_items)
                    self._resume_upload_reason = "pause"
                    self._mark_upload_paused(upload_items)
                    self._set_status("上传已暂停，可继续上传")
                    self.logger.info(
                        "上传任务已暂停：bucket=%s, 文件=%s",
                        bucket,
                        self._format_upload_items_for_log(upload_items),
                    )
                else:
                    self._cleanup_upload_sessions(
                        manager,
                        bucket,
                        upload_items,
                        content_md5s=upload_item_content_md5s,
                    )
                    self._resume_upload_bucket = ""
                    self._resume_upload_items = []
                    self._resume_upload_reason = None
                    self.resume_upload_button.setEnabled(False)
                    self._mark_upload_cancelled()
                    self._set_status("上传已取消，下次会重新上传")
                    self.logger.info(
                        "上传任务已取消：bucket=%s, 文件=%s",
                        bucket,
                        self._format_upload_items_for_log(upload_items),
                    )
                return
            self._mark_upload_failed(exc)
            self._resume_upload_bucket = bucket
            self._resume_upload_items = list(upload_items)
            self._resume_upload_reason = "failure"
            self.resume_upload_button.setEnabled(True)
            self.logger.error(
                "上传任务失败：bucket=%s, 文件=%s",
                bucket,
                self._format_upload_items_for_log(upload_items),
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            QMessageBox.critical(self, "操作失败", str(exc))

        def on_finished() -> None:
            self._upload_in_progress = False
            self._upload_cancel_event = None
            self._upload_stop_reason = None
            self.pause_upload_button.setEnabled(False)
            if self._resume_upload_items and self._resume_upload_bucket:
                self.resume_upload_button.setEnabled(True)
                self.cancel_upload_button.setEnabled(True)
            else:
                self.cancel_upload_button.setEnabled(False)
            if self._pending_close_after_upload_stop:
                self._pending_close_after_upload_stop = False
                self.close()

        self._run_task(
            status_text,
            task,
            on_result=on_success,
            on_error=on_error,
            on_finished=on_finished,
            on_progress=self._update_upload_progress,
            task_accepts_progress=True,
        )

    def _start_upload_progress(self, upload_items: list[tuple[str, str, int]]) -> None:
        total_bytes = sum(item_size for _item_path, _item_key, item_size in upload_items)
        self._set_upload_progress_value(0 if total_bytes > 0 else 1000)
        self.upload_progress_title.setText("准备上传")
        self.upload_progress_detail.setText(
            f"共 {len(upload_items)} 个文件 · 总大小 {self._format_size(total_bytes)}"
        )

    def _update_upload_progress(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        if self._upload_stop_reason in {"pause", "cancel"}:
            return

        uploaded_bytes = self._coerce_object_size(payload.get("uploaded_bytes", 0))
        total_bytes = self._coerce_object_size(payload.get("total_bytes", 0))
        current_index = self._coerce_object_size(payload.get("current_index", 0))
        total_files = self._coerce_object_size(payload.get("total_files", 0))
        file_name = str(payload.get("file_name", "")).strip() or "当前文件"
        object_key = str(payload.get("object_key", "")).strip()
        speed_bps = self._coerce_float(payload.get("speed_bps", 0.0))
        is_resuming = bool(payload.get("is_resuming", False))
        is_hashing = bool(payload.get("is_hashing", False))

        progress = 1.0 if total_bytes <= 0 else min(1.0, uploaded_bytes / total_bytes)
        self._set_upload_progress_value(int(progress * 1000))
        if is_hashing:
            title_parts = [f"正在校验文件：{file_name}"]
            if total_files > 1 and current_index > 0:
                title_parts.append(f"第 {current_index}/{total_files} 个文件")
            self.upload_progress_title.setText(" · ".join(title_parts))
            detail_parts = [
                "正在计算 MD5",
                f"{self._format_size(uploaded_bytes)} / {self._format_size(total_bytes)}",
            ]
            if object_key:
                detail_parts.append(object_key)
            self.upload_progress_detail.setText(" · ".join(detail_parts))
            self._set_status("正在计算文件 MD5...")
            return

        title_prefix = "断点续传" if is_resuming else "正在上传"
        title_parts = [f"{title_prefix}：{file_name}"]
        if total_files > 1 and current_index > 0:
            title_parts.append(f"第 {current_index}/{total_files} 个文件")
        self.upload_progress_title.setText(" · ".join(title_parts))

        percent_text = f"{progress * 100:.1f}%"
        detail_parts = [
            percent_text,
            f"{self._format_size(uploaded_bytes)} / {self._format_size(total_bytes)}",
            self._format_speed(speed_bps),
        ]
        if object_key:
            detail_parts.append(object_key)
        self.upload_progress_detail.setText(" · ".join(detail_parts))
        self._set_status(f"正在上传 {percent_text} · {self._format_speed(speed_bps)}")

    def _mark_upload_complete(self, uploaded_items: list[tuple[str, str, int]]) -> None:
        total_bytes = sum(item_size for _item_path, _item_key, item_size in uploaded_items)
        self._set_upload_progress_value(1000)
        self.upload_progress_title.setText("上传完成")
        self.upload_progress_detail.setText(
            f"已上传 {len(uploaded_items)} 个文件 · {self._format_size(total_bytes)}"
        )

    def _mark_upload_failed(self, exc: Exception) -> None:
        self._restore_upload_progress_range()
        self.upload_progress_title.setText("上传失败")
        self.upload_progress_detail.setText(f"{exc}。可点击继续上传从断点重试。")

    def _mark_upload_paused(self, upload_items: list[tuple[str, str, int]]) -> None:
        total_bytes = sum(item_size for _item_path, _item_key, item_size in upload_items)
        self._restore_upload_progress_range()
        self.upload_progress_title.setText("上传已暂停")
        self.upload_progress_detail.setText(
            f"已保留断点 · 共 {len(upload_items)} 个文件 · {self._format_size(total_bytes)}"
        )
        self.resume_upload_button.setEnabled(True)
        self.cancel_upload_button.setEnabled(True)

    def _mark_upload_cancelled(self) -> None:
        self._set_upload_progress_value(0)
        self.upload_progress_title.setText("上传已取消")
        self.upload_progress_detail.setText("本次上传断点已清理，下次上传会重新开始。")

    def _set_upload_progress_busy(self) -> None:
        self.upload_progress_bar.setRange(0, 0)

    def _restore_upload_progress_range(self) -> None:
        if self.upload_progress_bar.minimum() != 0 or self.upload_progress_bar.maximum() != 1000:
            self.upload_progress_bar.setRange(0, 1000)
            self.upload_progress_bar.setValue(self._upload_progress_last_value)

    def _set_upload_progress_value(self, value: int) -> None:
        self._restore_upload_progress_range()
        self._upload_progress_last_value = max(0, min(1000, int(value)))
        self.upload_progress_bar.setValue(self._upload_progress_last_value)

    def _cleanup_upload_sessions(
        self,
        manager: R2Manager | None,
        bucket: str,
        upload_items: list[tuple[str, str, int]],
        ignore_abort_errors: bool = True,
        content_md5s: dict[tuple[str, str, int], str] | None = None,
    ) -> None:
        endpoint_url = manager.credentials.endpoint_url if manager else self.endpoint_edit.text().strip()
        for item_path, item_key, item_size in upload_items:
            content_md5 = (content_md5s or {}).get((item_path, item_key, item_size), "")
            matching_sessions = find_upload_sessions_for_file(
                endpoint_url,
                bucket,
                item_key,
                item_path,
                content_md5=content_md5,
                local_size=item_size,
            )
            for session in matching_sessions.values():
                upload_id = str(session.get("upload_id", "")).strip()
                session_object_key = str(session.get("object_key", "")).strip() or item_key
                if upload_id and manager is not None:
                    try:
                        manager.abort_multipart_upload(bucket, session_object_key, upload_id)
                    except Exception:
                        if not ignore_abort_errors:
                            raise
                delete_upload_sessions_for_file(
                    endpoint_url,
                    bucket,
                    session_object_key,
                    str(session.get("local_path", "")).strip() or item_path,
                    content_md5=str(session.get("content_md5", "")).strip(),
                    local_size=item_size,
                )
            if not matching_sessions:
                delete_upload_sessions_for_file(
                    endpoint_url,
                    bucket,
                    item_key,
                    item_path,
                    content_md5=content_md5,
                    local_size=item_size,
                )

    def _default_upload_key(self, local_path: Path) -> str:
        default_key = local_path.name
        prefix = self.prefix_edit.text().strip().strip("/")
        if prefix:
            default_key = f"{prefix}/{default_key}"
        return default_key

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
        self._sync_config_section_summary()

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
        self._sync_config_section_summary()

    def _sync_config_section_summary(self, status_override: str | None = None) -> None:
        bucket = self.bucket_combo.currentText().strip() or "未选择 bucket"
        has_required_values = self._can_auto_refresh_on_startup()
        status_text = status_override or ("连接信息已就绪" if has_required_values else "待补全连接信息")
        self.config_section.set_meta_texts(
            f"当前 bucket：{bucket}",
            status_text,
            status_accent=has_required_values,
        )

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

    def _coerce_float(self, value: object) -> float:
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0

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

    def _format_speed(self, bytes_per_second: float) -> str:
        return f"{self._format_size(max(0, int(bytes_per_second)))}/s"

    def _format_upload_items_for_log(self, upload_items: list[tuple[str, str, int]]) -> str:
        parts = [
            f"local_path={item_path}, object_key={item_key}, size={item_size}"
            for item_path, item_key, item_size in upload_items[:10]
        ]
        if len(upload_items) > 10:
            parts.append(f"... 其余 {len(upload_items) - 10} 个文件")
        return " | ".join(parts)

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
        row_count = layout.rowCount()
        column_count = layout.columnCount()
        while layout.count():
            layout.takeAt(0)
        for row in range(row_count):
            layout.setRowStretch(row, 0)
            layout.setRowMinimumHeight(row, 0)
        for column in range(column_count):
            layout.setColumnStretch(column, 0)
            layout.setColumnMinimumWidth(column, 0)

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
        margins = self.action_layout.contentsMargins()
        spacing = max(0, self.action_layout.horizontalSpacing())
        action_width = self.action_card.width() or width
        content_width = max(0, action_width - margins.left() - margins.right())
        column_unit = ACTION_BUTTON_TARGET_COLUMN_WIDTH + spacing
        columns = max(1, min(ACTION_BUTTON_MAX_COLUMNS, (content_width + spacing) // column_unit))
        for index, button in enumerate(self.object_action_buttons):
            row = index // columns
            column = index % columns
            self.action_layout.addWidget(button, row, column)
        progress_row = (len(self.object_action_buttons) + columns - 1) // columns
        self.action_layout.addWidget(self.upload_progress_panel, progress_row, 0, 1, columns)
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
