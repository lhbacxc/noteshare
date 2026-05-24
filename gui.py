from __future__ import annotations

import threading
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import END, StringVar, Tk, filedialog, messagebox, simpledialog, ttk

from config_manager import load_config, save_config
from r2_client import R2Credentials, R2Manager
from worker_client import WorkerClient, WorkerClientError


class R2GuiApp:
    COUNTDOWN_REFRESH_MS = 5000

    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("NoteShare R2 管理工具")
        self.root.geometry("1440x860")
        self.root.minsize(1180, 720)

        self.config_data = load_config()
        self.all_objects: list[dict[str, object]] = []
        self.filtered_objects: list[dict[str, object]] = []
        self.buttons: list[ttk.Button] = []

        self.account_id_var = StringVar(value=self.config_data.get("account_id", ""))
        self.access_key_var = StringVar(value=self.config_data.get("access_key_id", ""))
        self.secret_key_var = StringVar(value=self.config_data.get("secret_access_key", ""))
        self.endpoint_var = StringVar(value=self.config_data.get("endpoint_url", ""))
        self.worker_base_url_var = StringVar(
            value=self.config_data.get("worker_base_url", "")
        )
        self.worker_admin_token_var = StringVar(
            value=self.config_data.get("worker_admin_token", "")
        )
        self.bucket_var = StringVar(value=self.config_data.get("default_bucket", ""))
        self.expire_var = StringVar(
            value=str(self.config_data.get("url_expire_seconds", 3600))
        )
        self.prefix_var = StringVar()
        self.search_var = StringVar()
        self.url_var = StringVar()
        self.share_url_var = StringVar()
        self.status_var = StringVar(value="就绪")

        self._build_layout()
        self._load_bucket_options_from_config()
        self.search_var.trace_add("write", self._on_search_change)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_selection_change)
        self.root.after(200, self._auto_refresh_on_startup)
        self.root.after(self.COUNTDOWN_REFRESH_MS, self._refresh_countdown_timer)

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(2, weight=1)

        config_frame = ttk.LabelFrame(container, text="连接配置", padding=12)
        config_frame.grid(row=0, column=0, sticky="ew")
        for column in range(6):
            config_frame.columnconfigure(column, weight=1)

        self._add_labeled_entry(config_frame, "Account ID", self.account_id_var, 0, 0)
        self._add_labeled_entry(config_frame, "Access Key ID", self.access_key_var, 0, 1)
        self._add_labeled_entry(
            config_frame,
            "Secret Access Key",
            self.secret_key_var,
            0,
            2,
            show="*",
        )
        self._add_labeled_entry(config_frame, "Endpoint URL", self.endpoint_var, 1, 0)
        self._add_labeled_entry(config_frame, "默认过期秒数", self.expire_var, 1, 1)
        self._add_labeled_entry(
            config_frame,
            "Worker Base URL",
            self.worker_base_url_var,
            1,
            2,
        )
        self._add_labeled_entry(
            config_frame,
            "Worker Admin Token",
            self.worker_admin_token_var,
            2,
            0,
            show="*",
        )

        ttk.Label(config_frame, text="Bucket").grid(
            row=4, column=1, sticky="w", padx=6, pady=(0, 4)
        )
        self.bucket_combo = ttk.Combobox(config_frame, textvariable=self.bucket_var)
        self.bucket_combo.grid(row=5, column=1, sticky="ew", padx=6, pady=(0, 8))

        button_bar = ttk.Frame(config_frame)
        button_bar.grid(row=5, column=2, columnspan=4, sticky="e", padx=6, pady=(0, 8))

        self.save_button = self._make_button(button_bar, "保存配置", self.save_current_config)
        self.test_button = self._make_button(button_bar, "测试连接", self.test_connection)
        self.load_buckets_button = self._make_button(button_bar, "加载 Bucket", self.load_buckets)
        self.save_button.grid(row=0, column=0, padx=(0, 8))
        self.test_button.grid(row=0, column=1, padx=(0, 8))
        self.load_buckets_button.grid(row=0, column=2)

        filter_frame = ttk.LabelFrame(container, text="筛选与浏览", padding=12)
        filter_frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        filter_frame.columnconfigure(1, weight=1)
        filter_frame.columnconfigure(3, weight=1)

        ttk.Label(filter_frame, text="前缀").grid(row=0, column=0, sticky="w")
        ttk.Entry(filter_frame, textvariable=self.prefix_var).grid(
            row=0, column=1, sticky="ew", padx=(6, 16)
        )
        ttk.Label(filter_frame, text="搜索").grid(row=0, column=2, sticky="w")
        ttk.Entry(filter_frame, textvariable=self.search_var).grid(
            row=0, column=3, sticky="ew", padx=(6, 16)
        )
        self.refresh_button = self._make_button(filter_frame, "刷新列表", self.refresh_objects)
        self.refresh_button.grid(row=0, column=4, sticky="e")

        list_frame = ttk.LabelFrame(container, text="对象列表", padding=12)
        list_frame.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        columns = (
            "key",
            "size",
            "last_modified",
            "storage_class",
            "default_expire_seconds",
            "url_expiry_status",
        )
        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
        )
        self.tree.heading("key", text="Key")
        self.tree.heading("size", text="Size")
        self.tree.heading("last_modified", text="Last Modified")
        self.tree.heading("storage_class", text="Storage Class")
        self.tree.heading("default_expire_seconds", text="默认过期秒数")
        self.tree.heading("url_expiry_status", text="URL 到期 / 剩余时间")
        self.tree.column("key", width=430, anchor="w")
        self.tree.column("size", width=110, anchor="e")
        self.tree.column("last_modified", width=170, anchor="center")
        self.tree.column("storage_class", width=120, anchor="center")
        self.tree.column("default_expire_seconds", width=130, anchor="center")
        self.tree.column("url_expiry_status", width=260, anchor="w")

        scrollbar_y = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")

        action_frame = ttk.LabelFrame(container, text="操作与结果", padding=12)
        action_frame.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        action_frame.columnconfigure(0, weight=1)

        button_row = ttk.Frame(action_frame)
        button_row.grid(row=0, column=0, sticky="ew")

        self.upload_button = self._make_button(button_row, "上传文件", self.upload_file)
        self.download_button = self._make_button(
            button_row, "下载选中对象", self.download_selected
        )
        self.delete_button = self._make_button(button_row, "删除选中对象", self.delete_selected)
        self.set_expire_button = self._make_button(
            button_row,
            "设置选中文件过期秒数",
            self.set_selected_file_expire_seconds,
        )
        self.url_button = self._make_button(
            button_row, "生成预签名 URL", self.generate_presigned_url
        )
        self.copy_url_button = self._make_button(button_row, "复制 URL", self.copy_url)
        self.create_share_button = self._make_button(
            button_row,
            "创建可撤销分享",
            self.create_share,
        )
        self.revoke_share_button = self._make_button(
            button_row,
            "停止分享",
            self.revoke_share,
        )
        self.copy_share_button = self._make_button(
            button_row,
            "复制分享链接",
            self.copy_share_url,
        )

        self.upload_button.grid(row=0, column=0, padx=(0, 8), pady=(0, 8))
        self.download_button.grid(row=0, column=1, padx=(0, 8), pady=(0, 8))
        self.delete_button.grid(row=0, column=2, padx=(0, 8), pady=(0, 8))
        self.set_expire_button.grid(row=0, column=3, padx=(0, 8), pady=(0, 8))
        self.url_button.grid(row=0, column=4, padx=(0, 8), pady=(0, 8))
        self.copy_url_button.grid(row=0, column=5, padx=(0, 8), pady=(0, 8))
        self.create_share_button.grid(row=0, column=6, padx=(0, 8), pady=(0, 8))
        self.revoke_share_button.grid(row=0, column=7, padx=(0, 8), pady=(0, 8))
        self.copy_share_button.grid(row=0, column=8, pady=(0, 8))

        ttk.Label(action_frame, text="当前选中文件有效预签名 URL").grid(
            row=1, column=0, sticky="w", pady=(4, 4)
        )
        ttk.Entry(action_frame, textvariable=self.url_var).grid(
            row=2, column=0, sticky="ew", pady=(0, 8)
        )
        ttk.Label(action_frame, text="当前选中文件有效分享链接").grid(
            row=3, column=0, sticky="w", pady=(4, 4)
        )
        ttk.Entry(action_frame, textvariable=self.share_url_var).grid(
            row=4, column=0, sticky="ew", pady=(0, 8)
        )
        ttk.Label(action_frame, textvariable=self.status_var).grid(row=5, column=0, sticky="w")

    def _add_labeled_entry(
        self,
        parent: ttk.Frame,
        label: str,
        variable: StringVar,
        row: int,
        column: int,
        show: str | None = None,
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row * 2,
            column=column,
            sticky="w",
            padx=6,
            pady=(0, 4),
        )
        ttk.Entry(parent, textvariable=variable, show=show).grid(
            row=row * 2 + 1,
            column=column,
            sticky="ew",
            padx=6,
            pady=(0, 8),
        )

    def _make_button(self, parent: ttk.Frame, text: str, command) -> ttk.Button:
        button = ttk.Button(parent, text=text, command=command)
        self.buttons.append(button)
        return button

    def _load_bucket_options_from_config(self) -> None:
        buckets = self.config_data.get("recent_buckets", [])
        self.bucket_combo["values"] = buckets
        current_bucket = self.bucket_var.get()
        if current_bucket and current_bucket not in buckets:
            self.bucket_combo["values"] = [current_bucket, *buckets]

    def _collect_form_config(self) -> dict[str, object]:
        return {
            "account_id": self.account_id_var.get().strip(),
            "access_key_id": self.access_key_var.get().strip(),
            "secret_access_key": self.secret_key_var.get().strip(),
            "endpoint_url": self.endpoint_var.get().strip(),
            "worker_base_url": self.worker_base_url_var.get().strip(),
            "worker_admin_token": self.worker_admin_token_var.get().strip(),
            "default_bucket": self.bucket_var.get().strip(),
            "url_expire_seconds": self.expire_var.get().strip(),
            "recent_buckets": list(self.bucket_combo["values"]),
            "object_url_settings": self.config_data.get("object_url_settings", {}),
        }

    def _validate_connection_fields(self) -> dict[str, str] | None:
        config = self._collect_form_config()
        required_fields = {
            "account_id": "Account ID",
            "access_key_id": "Access Key ID",
            "secret_access_key": "Secret Access Key",
        }
        missing = [
            label for key, label in required_fields.items() if not str(config[key]).strip()
        ]
        if missing:
            messagebox.showerror("配置不完整", f"请先填写以下字段：{', '.join(missing)}")
            return None

        endpoint_url = str(config["endpoint_url"]).strip()
        if not endpoint_url:
            endpoint_url = (
                f'https://{str(config["account_id"]).strip()}.r2.cloudflarestorage.com'
            )
            self.endpoint_var.set(endpoint_url)
            config["endpoint_url"] = endpoint_url

        return {
            key: str(value)
            for key, value in config.items()
            if key != "object_url_settings"
        }

    def _get_selected_keys(self) -> list[str]:
        keys: list[str] = []
        for item_id in self.tree.selection():
            values = self.tree.item(item_id, "values")
            if values and values[0]:
                keys.append(str(values[0]))
        return keys

    def _get_selected_single_key(self) -> str | None:
        keys = self._get_selected_keys()
        if len(keys) == 1:
            return keys[0]
        return None

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
        worker_base_url = self.worker_base_url_var.get().strip()
        worker_admin_token = self.worker_admin_token_var.get().strip()

        if not worker_base_url:
            messagebox.showerror("缺少 Worker 配置", "请先填写 Worker Base URL。")
            return None
        if not worker_admin_token:
            messagebox.showerror("缺少 Worker 配置", "请先填写 Worker Admin Token。")
            return None

        try:
            return WorkerClient(worker_base_url, worker_admin_token)
        except WorkerClientError as exc:
            messagebox.showerror("Worker 配置错误", str(exc))
            return None

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _set_buttons_state(self, disabled: bool) -> None:
        state = "disabled" if disabled else "normal"
        for button in self.buttons:
            button.configure(state=state)

    def _run_in_thread(self, status_text: str, task, on_success=None, on_error=None) -> None:
        self._set_buttons_state(True)
        self._set_status(status_text)

        def worker() -> None:
            try:
                result = task()
            except Exception as exc:  # noqa: BLE001
                if on_error is None:
                    self.root.after(0, lambda: self._handle_task_error(exc))
                else:
                    self.root.after(0, lambda: on_error(exc))
                return

            if on_success is None:
                self.root.after(0, self._handle_task_success)
                return

            self.root.after(0, lambda: self._handle_task_success(on_success, result))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_task_error(self, exc: Exception) -> None:
        self._set_buttons_state(False)
        self._set_status("操作失败")
        messagebox.showerror("操作失败", str(exc))

    def _handle_task_success(self, callback=None, result=None) -> None:
        self._set_buttons_state(False)
        self._set_status("操作完成")
        if callback is not None:
            callback(result)

    def save_current_config(self) -> None:
        try:
            save_config(self._collect_form_config())
            self.config_data = load_config()
            self._load_bucket_options_from_config()
            self._set_status("配置已保存")
            messagebox.showinfo("保存成功", "配置已保存到本地 config.json。")
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc))

    def test_connection(self) -> None:
        manager = self._make_manager()
        if not manager:
            return

        def task() -> dict[str, object]:
            return manager.test_connection()

        def on_success(result: dict[str, object]) -> None:
            bucket_names = list(result.get("buckets", []))
            self.bucket_combo["values"] = bucket_names
            if bucket_names and not self.bucket_var.get():
                self.bucket_var.set(bucket_names[0])
            self._save_bucket_history(bucket_names)
            messagebox.showinfo(
                "连接成功",
                f"连接可用，共检测到 {result.get('bucket_count', 0)} 个 bucket。",
            )

        self._run_in_thread("正在测试连接...", task, on_success)

    def load_buckets(self) -> None:
        manager = self._make_manager()
        if not manager:
            return

        def task() -> list[str]:
            return manager.list_buckets()

        def on_success(bucket_names: list[str]) -> None:
            self.bucket_combo["values"] = bucket_names
            if bucket_names:
                current_bucket = self.bucket_var.get()
                if current_bucket not in bucket_names:
                    self.bucket_var.set(bucket_names[0])
            self._save_bucket_history(bucket_names)
            messagebox.showinfo("加载完成", f"已加载 {len(bucket_names)} 个 bucket。")

        self._run_in_thread("正在加载 bucket 列表...", task, on_success)

    def refresh_objects(self) -> None:
        self._refresh_objects(show_error=True, status_text="正在刷新对象列表...")

    def _refresh_objects(self, show_error: bool, status_text: str) -> None:
        manager = self._make_manager()
        if not manager:
            return

        bucket = self.bucket_var.get().strip()
        if not bucket:
            if show_error:
                messagebox.showerror("缺少 Bucket", "请先选择一个 bucket。")
            else:
                self._set_status("未找到可自动加载的 bucket")
            return

        prefix = self.prefix_var.get().strip()

        def task() -> list[dict[str, object]]:
            return manager.list_objects(bucket, prefix)

        def on_success(objects: list[dict[str, object]]) -> None:
            self.all_objects = objects
            self._apply_search_filter()
            self._set_status(f"已加载 {len(objects)} 个对象")

        def on_error(exc: Exception) -> None:
            self._set_buttons_state(False)
            if show_error:
                self._set_status("操作失败")
                messagebox.showerror("操作失败", str(exc))
            else:
                self._set_status(f"自动加载失败：{exc}")

        self._run_in_thread(status_text, task, on_success, on_error=on_error)

    def upload_file(self) -> None:
        manager = self._make_manager()
        if not manager:
            return

        bucket = self.bucket_var.get().strip()
        if not bucket:
            messagebox.showerror("缺少 Bucket", "请先选择一个 bucket。")
            return

        local_path = filedialog.askopenfilename(title="选择要上传的文件")
        if not local_path:
            return

        default_key = Path(local_path).name
        prefix = self.prefix_var.get().strip().strip("/")
        if prefix:
            default_key = f"{prefix}/{default_key}"

        object_key = simpledialog.askstring(
            "对象 Key",
            "请输入上传后的对象 Key：",
            initialvalue=default_key,
            parent=self.root,
        )
        if not object_key:
            return

        object_key = object_key.strip()

        def task() -> None:
            manager.upload_file(bucket, local_path, object_key)

        def on_success(_: None) -> None:
            messagebox.showinfo("上传成功", f"文件已上传到 {bucket}/{object_key}。")
            self.refresh_objects()

        self._run_in_thread("正在上传文件...", task, on_success)

    def download_selected(self) -> None:
        manager = self._make_manager()
        if not manager:
            return

        bucket = self.bucket_var.get().strip()
        selected_keys = self._get_selected_keys()
        if not bucket:
            messagebox.showerror("缺少 Bucket", "请先选择一个 bucket。")
            return
        if not selected_keys:
            messagebox.showwarning("未选择对象", "请先在列表中选择要下载的对象。")
            return

        if len(selected_keys) == 1:
            default_name = Path(selected_keys[0]).name or "downloaded_file"
            save_path = filedialog.asksaveasfilename(
                title="保存下载文件",
                initialfile=default_name,
            )
            if not save_path:
                return
            targets = [(selected_keys[0], save_path)]
        else:
            directory = filedialog.askdirectory(title="选择下载目录")
            if not directory:
                return
            targets = [(key, str(Path(directory) / Path(key).name)) for key in selected_keys]

        def task() -> int:
            for key, destination in targets:
                manager.download_file(bucket, key, destination)
            return len(targets)

        def on_success(count: int) -> None:
            messagebox.showinfo("下载成功", f"已下载 {count} 个对象。")

        self._run_in_thread("正在下载对象...", task, on_success)

    def delete_selected(self) -> None:
        manager = self._make_manager()
        if not manager:
            return

        bucket = self.bucket_var.get().strip()
        selected_keys = self._get_selected_keys()
        if not bucket:
            messagebox.showerror("缺少 Bucket", "请先选择一个 bucket。")
            return
        if not selected_keys:
            messagebox.showwarning("未选择对象", "请先在列表中选择要删除的对象。")
            return

        confirmed = messagebox.askyesno(
            "确认删除",
            f"确定要删除选中的 {len(selected_keys)} 个对象吗？此操作不可撤销。",
        )
        if not confirmed:
            return

        def task() -> dict[str, object]:
            return manager.delete_objects(bucket, selected_keys)

        def on_success(result: dict[str, object]) -> None:
            deleted_keys = list(result.get("deleted", []))
            deleted_count = len(deleted_keys)
            errors = list(result.get("errors", []))
            self._remove_object_records(bucket, deleted_keys)
            if errors:
                messagebox.showwarning(
                    "删除完成",
                    f"成功删除 {deleted_count} 个对象，失败 {len(errors)} 个：\n"
                    + "\n".join(errors[:10]),
                )
            else:
                messagebox.showinfo("删除成功", f"已删除 {deleted_count} 个对象。")
            self.refresh_objects()

        self._run_in_thread("正在删除对象...", task, on_success)

    def set_selected_file_expire_seconds(self) -> None:
        bucket = self.bucket_var.get().strip()
        object_key = self._get_selected_single_key()
        if not bucket:
            messagebox.showerror("缺少 Bucket", "请先选择一个 bucket。")
            return
        if object_key is None:
            messagebox.showwarning("选择数量不正确", "请只选择一个文件来设置过期秒数。")
            return

        current_seconds = self._get_file_expire_seconds(bucket, object_key)
        expire_seconds = simpledialog.askinteger(
            "设置过期秒数",
            "请输入该文件默认的过期秒数：",
            initialvalue=current_seconds,
            minvalue=1,
            parent=self.root,
        )
        if expire_seconds is None:
            return

        self._update_object_record(
            bucket,
            object_key,
            {"default_expire_seconds": expire_seconds},
        )
        self._apply_search_filter()
        self._set_status(f"已为 {object_key} 设置默认过期秒数：{expire_seconds}")

    def generate_presigned_url(self) -> None:
        manager = self._make_manager()
        if not manager:
            return

        bucket = self.bucket_var.get().strip()
        object_key = self._get_selected_single_key()
        if not bucket:
            messagebox.showerror("缺少 Bucket", "请先选择一个 bucket。")
            return
        if object_key is None:
            messagebox.showwarning("选择数量不正确", "请只选择一个对象来生成预签名 URL。")
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
            self.url_var.set(str(result["url"]))
            self.root.clipboard_clear()
            self.root.clipboard_append(str(result["url"]))
            self._apply_search_filter()
            self._sync_bottom_links_from_selection()
            messagebox.showinfo(
                "URL 已生成",
                "预签名 URL 已生成，并已复制到剪贴板。",
            )

        self._run_in_thread("正在生成预签名 URL...", task, on_success)

    def create_share(self) -> None:
        worker_client = self._make_worker_client()
        if not worker_client:
            return

        bucket = self.bucket_var.get().strip()
        object_key = self._get_selected_single_key()
        if not bucket:
            messagebox.showerror("缺少 Bucket", "请先选择一个 bucket。")
            return
        if object_key is None:
            messagebox.showwarning("选择数量不正确", "请只选择一个对象来创建分享。")
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
            self.share_url_var.set(share_url)
            if share_url:
                self.root.clipboard_clear()
                self.root.clipboard_append(share_url)
            self._apply_search_filter()
            self._sync_bottom_links_from_selection()
            messagebox.showinfo(
                "分享链接已创建",
                "可撤销分享链接已创建，并已复制到剪贴板。",
            )

        self._run_in_thread("正在创建可撤销分享...", task, on_success)

    def revoke_share(self) -> None:
        worker_client = self._make_worker_client()
        if not worker_client:
            return

        bucket = self.bucket_var.get().strip()
        object_key = self._get_selected_single_key()
        if not bucket:
            messagebox.showerror("缺少 Bucket", "请先选择一个 bucket。")
            return
        if object_key is None:
            messagebox.showwarning("选择数量不正确", "请只选择一个对象来停止分享。")
            return

        record = self._get_object_record(bucket, object_key)
        token = self._get_share_token_for_revoke(record)
        if not token:
            messagebox.showwarning("没有可停止的分享", "当前选中的文件没有有效分享记录。")
            return

        def task() -> dict[str, object]:
            return worker_client.revoke_share(token)

        def on_success(result: dict[str, object]) -> None:
            share_status = str(result.get("status", "revoked")).strip().lower() or "revoked"
            self._update_object_record(
                bucket,
                object_key,
                {"last_share_status": share_status},
            )
            self._apply_search_filter()
            self._sync_bottom_links_from_selection()
            messagebox.showinfo("分享已停止", "当前文件的可撤销分享已停止。")

        self._run_in_thread("正在停止分享...", task, on_success)

    def copy_url(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("没有可复制的 URL", "当前选中的文件没有有效的预签名 URL。")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        self._set_status("预签名 URL 已复制到剪贴板")

    def copy_share_url(self) -> None:
        share_url = self.share_url_var.get().strip()
        if not share_url:
            messagebox.showwarning("没有可复制的分享链接", "当前选中的文件没有有效分享链接。")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(share_url)
        self._set_status("分享链接已复制到剪贴板")

    def _on_search_change(self, *_args) -> None:
        self._apply_search_filter()

    def _on_tree_selection_change(self, *_args) -> None:
        self._sync_bottom_links_from_selection()

    def _apply_search_filter(self) -> None:
        keyword = self.search_var.get().strip().lower()
        if not keyword:
            self.filtered_objects = list(self.all_objects)
        else:
            self.filtered_objects = [
                item for item in self.all_objects if keyword in str(item["key"]).lower()
            ]
        self._refresh_tree()
        self._sync_bottom_links_from_selection()

    def _refresh_tree(self) -> None:
        bucket = self.bucket_var.get().strip()
        selected_keys = set(self._get_selected_keys())

        for item_id in self.tree.get_children():
            self.tree.delete(item_id)

        for item in self.filtered_objects:
            key = str(item["key"])
            self.tree.insert(
                "",
                END,
                iid=key,
                values=(
                    key,
                    self._format_size(int(item["size"])),
                    item["last_modified"],
                    item["storage_class"],
                    self._get_file_expire_seconds(bucket, key),
                    self._get_url_status_display(bucket, key),
                ),
            )

        for key in selected_keys:
            if self.tree.exists(key):
                self.tree.selection_add(key)

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

    def _save_bucket_history(self, buckets: list[str]) -> None:
        current = self._collect_form_config()
        current["recent_buckets"] = buckets
        save_config(current)
        self.config_data = load_config()

    def _get_file_expire_seconds(self, bucket: str, object_key: str) -> int:
        record = self._get_object_record(bucket, object_key)
        if record and isinstance(record.get("default_expire_seconds"), int):
            return int(record["default_expire_seconds"])
        return self._get_global_default_from_config()

    def _get_global_default_from_config(self) -> int:
        try:
            value = int(self.expire_var.get().strip())
        except ValueError:
            value = int(self.config_data.get("url_expire_seconds", 3600))
        return max(1, value)

    def _get_object_record(self, bucket: str, object_key: str) -> dict[str, object] | None:
        object_url_settings = self.config_data.get("object_url_settings", {})
        bucket_settings = object_url_settings.get(bucket, {})
        record = bucket_settings.get(object_key)
        if isinstance(record, dict):
            return record
        return None

    def _update_object_record(
        self,
        bucket: str,
        object_key: str,
        updates: dict[str, object],
    ) -> None:
        object_url_settings = dict(self.config_data.get("object_url_settings", {}))
        bucket_settings = dict(object_url_settings.get(bucket, {}))
        record = dict(bucket_settings.get(object_key, {}))
        record.update(updates)
        bucket_settings[object_key] = record
        object_url_settings[bucket] = bucket_settings
        self.config_data["object_url_settings"] = object_url_settings
        save_config(self._collect_form_config())
        self.config_data = load_config()

    def _remove_object_records(self, bucket: str, object_keys: list[str]) -> None:
        object_url_settings = dict(self.config_data.get("object_url_settings", {}))
        bucket_settings = dict(object_url_settings.get(bucket, {}))
        changed = False

        for object_key in object_keys:
            if object_key in bucket_settings:
                bucket_settings.pop(object_key, None)
                changed = True

        if not changed:
            return

        object_url_settings[bucket] = bucket_settings
        self.config_data["object_url_settings"] = object_url_settings
        save_config(self._collect_form_config())
        self.config_data = load_config()

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

        remaining = expires_at - now
        return f"{expires_text} | 剩余 {self._format_remaining(remaining)}"

    def _get_valid_historical_url(self, bucket: str, object_key: str) -> str:
        record = self._get_object_record(bucket, object_key)
        if not record:
            return ""

        url = str(record.get("last_presigned_url", "")).strip()
        if not url:
            return ""

        expires_at = self._parse_datetime(str(record.get("last_expires_at", "")))
        if expires_at is None:
            return ""

        if datetime.now().astimezone() >= expires_at:
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
        if expires_at is None:
            return False

        return datetime.now().astimezone() < expires_at

    def _get_share_token_for_revoke(self, record: dict[str, object] | None) -> str:
        if not self._has_active_share_record(record):
            return ""
        return str(record.get("last_share_token", "")).strip()

    def _sync_bottom_links_from_selection(self) -> None:
        bucket = self.bucket_var.get().strip()
        object_key = self._get_selected_single_key()
        if not bucket or object_key is None:
            self.url_var.set("")
            self.share_url_var.set("")
            return

        self.url_var.set(self._get_valid_historical_url(bucket, object_key))
        self.share_url_var.set(self._get_valid_share_url(bucket, object_key))

    def _parse_datetime(self, value: str) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.astimezone()
        return parsed

    def _format_remaining(self, delta) -> str:
        total_seconds = max(0, int(delta.total_seconds()))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}小时{minutes}分钟{seconds}秒"
        if minutes > 0:
            return f"{minutes}分钟{seconds}秒"
        return f"{seconds}秒"

    def _auto_refresh_on_startup(self) -> None:
        if not self._can_auto_refresh_on_startup():
            return
        self._refresh_objects(
            show_error=False,
            status_text="正在自动加载当前 bucket 的文件列表...",
        )

    def _can_auto_refresh_on_startup(self) -> bool:
        if not self.bucket_var.get().strip():
            return False
        required_values = [
            self.account_id_var.get().strip(),
            self.access_key_var.get().strip(),
            self.secret_key_var.get().strip(),
        ]
        return all(required_values)

    def _refresh_countdown_timer(self) -> None:
        if self.filtered_objects:
            self._refresh_tree()
            self._sync_bottom_links_from_selection()
        self.root.after(self.COUNTDOWN_REFRESH_MS, self._refresh_countdown_timer)
