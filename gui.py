"""
店小秘排单号自动填写工具 - 桌面GUI模块
"""
import threading
import asyncio
from functools import partial
import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
from config import STORES, STORE_LIST, WINDOW_CONFIG
from automator import DianXiaoMiAutomator, AutomatorError


# 配色方案
COLORS = {
    "bg": "#F5F7FA",
    "card_bg": "#FFFFFF",
    "primary": "#4A90D9",
    "primary_hover": "#3A7BD5",
    "primary_dark": "#2E6BB5",
    "success": "#4CAF50",
    "success_hover": "#43A047",
    "danger": "#F44336",
    "danger_hover": "#E53935",
    "text_primary": "#2C3E50",
    "text_secondary": "#7F8C8D",
    "border": "#E0E6ED",
    "green_dot": "#4CAF50",
    "red_dot": "#F44336",
    "log_bg": "#F8F9FA",
}

# 字体
FONTS = {
    "title": ("Microsoft YaHei", 16, "bold"),
    "heading": ("Microsoft YaHei", 13, "bold"),
    "body": ("Microsoft YaHei", 12),
    "small": ("Microsoft YaHei", 11),
    "log": ("Consolas", 11),
    "button": ("Microsoft YaHei", 13, "bold"),
}


class LogHandler:
    """将日志重定向到GUI文本控件"""

    def __init__(self, text_widget):
        self.text_widget = text_widget
        self._lock = threading.Lock()

    def write(self, message):
        if not message.strip():
            return
        with self._lock:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.text_widget.after(0, self._append_log, timestamp, message)

    def _append_log(self, timestamp, message):
        try:
            self.text_widget.configure(state="normal")
            self.text_widget.insert("end", f"[{timestamp}] {message}\n")
            self.text_widget.see("end")
            self.text_widget.configure(state="disabled")
        except Exception:
            pass


class App(ctk.CTk):
    """主应用窗口"""

    def __init__(self):
        super().__init__()

        # ---------- 窗口设置 ----------
        cfg = WINDOW_CONFIG
        self.title(cfg["title"])
        self.geometry(f"{cfg['width']}x{cfg['height']}")
        self.minsize(cfg["min_width"], cfg["min_height"])
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        # ---------- 持久化事件循环 ----------
        # 所有异步操作共享同一个事件循环，避免跨循环调用Playwright报错
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()

        # ---------- 状态变量 ----------
        self.selected_store = ctk.StringVar(value="")
        self.start_number = ctk.StringVar(value="")
        self.automator = None
        self._browser_launched = False
        self._current_store = None
        self._current_start = None

        # ---------- 构建界面 ----------
        self._build_ui()

        # ---------- 窗口关闭事件 ----------
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ==================== 事件循环管理 ====================

    def _run_loop(self):
        """后台线程：持久运行事件循环"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _async_call(self, coro, callback=None):
        """
        在持久事件循环上执行协程，不阻塞GUI线程
        callback会在主线程中执行（通过 self.after）
        """
        def _done_callback(future):
            exc = future.exception()
            if exc:
                self.after(0, callback, None, exc)
            else:
                self.after(0, callback, future.result(), None)

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        if callback:
            future.add_done_callback(_done_callback)

    # ==================== UI 构建 ====================

    def _build_ui(self):
        """构建完整界面"""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)

        self._build_title_bar()
        self._build_main_content()
        self._build_status_bar()

    def _build_title_bar(self):
        """顶部标题栏"""
        title_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=COLORS["primary"])
        title_frame.grid(row=0, column=0, sticky="ew")
        title_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            title_frame,
            text="  🏪  店小秘排单号自动填写工具",
            font=("Microsoft YaHei", 16, "bold"),
            text_color="#FFFFFF",
            anchor="w",
        ).grid(row=0, column=0, padx=20, pady=(12, 12), sticky="w")

    def _build_main_content(self):
        """主体内容"""
        main_frame = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        main_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(4, weight=0)
        main_frame.grid_rowconfigure(5, weight=1)

        self._build_store_card(main_frame)
        self._build_number_card(main_frame)
        self._build_info_card(main_frame)
        self._build_buttons(main_frame)
        self._build_log_area(main_frame)

    def _build_store_card(self, parent):
        """店铺选择卡片"""
        card = ctk.CTkFrame(parent, fg_color=COLORS["card_bg"], corner_radius=10)
        card.grid(row=0, column=0, padx=20, pady=(16, 0), sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="店铺选择", font=FONTS["heading"],
            text_color=COLORS["text_primary"], anchor="w",
        ).grid(row=0, column=0, padx=16, pady=(12, 4), sticky="w")

        ctk.CTkLabel(
            card, text="请选择要操作的店铺", font=FONTS["small"],
            text_color=COLORS["text_secondary"], anchor="w",
        ).grid(row=1, column=0, padx=16, pady=(0, 4), sticky="w")

        options_frame = ctk.CTkFrame(card, fg_color="transparent")
        options_frame.grid(row=2, column=0, padx=16, pady=(4, 12), sticky="ew")
        options_frame.grid_columnconfigure(0, weight=0)
        options_frame.grid_columnconfigure(1, weight=1)

        # 专营店（绿色指示点）
        ctk.CTkLabel(options_frame, text="●", font=("Microsoft YaHei", 18),
                      text_color=COLORS["green_dot"], width=20,
        ).grid(row=0, column=0, padx=(0, 4), pady=4, sticky="w")

        self.store1_radio = ctk.CTkRadioButton(
            options_frame,
            text=STORES["专营店"]["name"],
            variable=self.selected_store,
            value="专营店",
            font=FONTS["body"],
            text_color=COLORS["text_primary"],
            fg_color=COLORS["green_dot"],
            hover_color=COLORS["green_dot"],
            border_color=COLORS["green_dot"],
        )
        self.store1_radio.grid(row=0, column=1, padx=(0, 8), pady=4, sticky="w")

        # 二店（红色指示点）
        ctk.CTkLabel(options_frame, text="●", font=("Microsoft YaHei", 18),
                      text_color=COLORS["red_dot"], width=20,
        ).grid(row=1, column=0, padx=(0, 4), pady=4, sticky="w")

        self.store2_radio = ctk.CTkRadioButton(
            options_frame,
            text=STORES["二店"]["name"],
            variable=self.selected_store,
            value="二店",
            font=FONTS["body"],
            text_color=COLORS["text_primary"],
            fg_color=COLORS["red_dot"],
            hover_color=COLORS["red_dot"],
            border_color=COLORS["red_dot"],
        )
        self.store2_radio.grid(row=1, column=1, padx=(0, 8), pady=4, sticky="w")

    def _build_number_card(self, parent):
        """起始单号卡片"""
        card = ctk.CTkFrame(parent, fg_color=COLORS["card_bg"], corner_radius=10)
        card.grid(row=1, column=0, padx=20, pady=(10, 0), sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="起始单号", font=FONTS["heading"],
            text_color=COLORS["text_primary"], anchor="w",
        ).grid(row=0, column=0, padx=16, pady=(12, 4), sticky="w")

        ctk.CTkLabel(
            card, text="输入本次起始排单号（上一个单号 + 1）", font=FONTS["small"],
            text_color=COLORS["text_secondary"], anchor="w",
        ).grid(row=1, column=0, padx=16, pady=(0, 4), sticky="w")

        entry_frame = ctk.CTkFrame(card, fg_color="transparent")
        entry_frame.grid(row=2, column=0, padx=16, pady=(4, 12), sticky="ew")
        entry_frame.grid_columnconfigure(0, weight=1)

        self.number_entry = ctk.CTkEntry(
            entry_frame,
            placeholder_text="请输入起始单号（如: 23518）",
            font=FONTS["body"],
            text_color=COLORS["text_primary"],
            fg_color=COLORS["log_bg"],
            border_color=COLORS["border"],
            border_width=2,
            corner_radius=8,
            height=40,
        )
        self.number_entry.grid(row=0, column=0, sticky="ew")
        self.number_entry.bind("<KeyRelease>", self._on_number_input)

    def _on_number_input(self, event=None):
        """输入单号时实时校验"""
        val = self.number_entry.get()
        if val and not val.isdigit():
            filtered = "".join(c for c in val if c.isdigit())
            self.number_entry.delete(0, "end")
            self.number_entry.insert(0, filtered)
        self._update_info_panel()

    def _build_info_card(self, parent):
        """信息预览卡片"""
        card = ctk.CTkFrame(parent, fg_color=COLORS["card_bg"], corner_radius=10)
        card.grid(row=2, column=0, padx=20, pady=(10, 0), sticky="ew")

        ctk.CTkLabel(
            card, text="执行预览", font=FONTS["heading"],
            text_color=COLORS["text_primary"], anchor="w",
        ).grid(row=0, column=0, padx=16, pady=(12, 4), sticky="w")

        self.info_label = ctk.CTkLabel(
            card,
            text="选择店铺并输入起始单号后，此处显示预估信息",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="w",
            justify="left",
        )
        self.info_label.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="ew")

    def _update_info_panel(self):
        """更新信息预览面板"""
        store = self.selected_store.get()
        number = self.number_entry.get()

        if not store and not number:
            self.info_label.configure(text="选择店铺并输入起始单号后，此处显示预估信息")
            return

        lines = []
        if store:
            color_tag = {"专营店": "🟢 绿色", "二店": "🔴 红色"}
            lines.append(f"  店铺: {STORES[store]['name']}")
            lines.append(f"  备注颜色: {color_tag.get(store, '')}")
        if number and number.isdigit():
            lines.append(f"  起始单号: {number}")
            lines.append(f"  备注: 自动化执行时会筛选该店铺并填写递增序号")

        self.info_label.configure(text="\n".join(lines) if lines else "信息待完善")

    def _build_buttons(self, parent):
        """操作按钮区域"""
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.grid(row=3, column=0, padx=20, pady=(14, 4), sticky="ew")
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        self.launch_btn = ctk.CTkButton(
            btn_frame,
            text="🚀  启动浏览器",
            font=FONTS["button"],
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            text_color="#FFFFFF",
            corner_radius=8,
            height=42,
            command=self._on_launch_browser,
        )
        self.launch_btn.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.ready_btn = ctk.CTkButton(
            btn_frame,
            text="✓  我已就绪，开始执行",
            font=FONTS["button"],
            fg_color=COLORS["success"],
            hover_color=COLORS["success_hover"],
            text_color="#FFFFFF",
            corner_radius=8,
            height=42,
            state="disabled",
            command=self._on_ready,
        )
        self.ready_btn.grid(row=0, column=1, padx=(6, 0), sticky="ew")

    def _build_log_area(self, parent):
        """日志输出区域"""
        log_card = ctk.CTkFrame(parent, fg_color=COLORS["card_bg"], corner_radius=10)
        log_card.grid(row=4, column=0, padx=20, pady=(10, 0), sticky="nsew")
        log_card.grid_rowconfigure(1, weight=1)
        log_card.grid_columnconfigure(0, weight=1)

        header_frame = ctk.CTkFrame(log_card, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=16, pady=(10, 4), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header_frame, text="执行日志", font=FONTS["heading"],
            text_color=COLORS["text_primary"], anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.color_dbg_btn = ctk.CTkButton(
            header_frame,
            text="🎨 颜色扫描",
            font=FONTS["small"],
            fg_color="#E67E22",
            hover_color="#D35400",
            text_color="#FFFFFF",
            corner_radius=4,
            width=80,
            height=24,
            state="disabled",
            command=self._on_color_scan,
        )
        self.color_dbg_btn.grid(row=0, column=1, padx=(0, 4), sticky="e")

        self.debug_btn = ctk.CTkButton(
            header_frame,
            text="🔍 调试扫描",
            font=FONTS["small"],
            fg_color="#8E44AD",
            hover_color="#7D3C98",
            text_color="#FFFFFF",
            corner_radius=4,
            width=80,
            height=24,
            state="disabled",
            command=self._on_debug_scan,
        )
        self.debug_btn.grid(row=0, column=2, padx=(0, 4), sticky="e")

        self.clear_log_btn = ctk.CTkButton(
            header_frame,
            text="清空",
            font=FONTS["small"],
            fg_color="transparent",
            text_color=COLORS["text_secondary"],
            hover_color=COLORS["log_bg"],
            corner_radius=4,
            width=50,
            height=24,
            command=self._clear_log,
        )
        self.clear_log_btn.grid(row=0, column=1, sticky="e")

        self.log_text = ctk.CTkTextbox(
            log_card,
            font=FONTS["log"],
            fg_color=COLORS["log_bg"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=6,
            wrap="word",
            state="disabled",
        )
        self.log_text.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="nsew")

        self.log_handler = LogHandler(self.log_text)

    def _build_status_bar(self):
        """底部状态栏"""
        status_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=COLORS["card_bg"],
                                    height=32)
        status_frame.grid(row=2, column=0, sticky="ew")
        status_frame.grid_columnconfigure(0, weight=1)
        status_frame.grid_propagate(False)

        self.status_label = ctk.CTkLabel(
            status_frame,
            text="💤 等待操作...",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
            anchor="w",
        )
        self.status_label.grid(row=0, column=0, padx=16, pady=4, sticky="w")

    # ==================== 日志方法 ====================

    def log(self, message: str):
        """输出日志"""
        self.log_handler.write(message)

    def _clear_log(self):
        """清空日志"""
        self.log_text.configure(state="normal")
        self.log_text.delete("0.0", "end")
        self.log_text.configure(state="disabled")

    def set_status(self, text: str):
        """更新状态栏"""
        self.status_label.configure(text=text)

    # ==================== DPI检测 ====================

    def _detect_dpi_scale(self) -> float:
        """自动检测Windows DPI缩放比例"""
        try:
            import ctypes
            from ctypes import wintypes
            shcore = ctypes.windll.shcore
            monitor = shcore.MonitorFromWindow(0, 2)
            dpi_x = wintypes.UINT()
            dpi_y = wintypes.UINT()
            shcore.GetDpiForMonitor(monitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
            scale = dpi_x.value / 96.0
            scale = round(scale * 4) / 4
            scale = max(1.0, min(2.0, scale))
            self.log(f"检测到系统DPI缩放: {int(scale * 100)}%（{dpi_x.value} DPI）")
            return scale
        except Exception:
            self.log("未能自动检测DPI，使用默认缩放 125%")
            return 1.25

    # ==================== 按钮事件 ====================

    def _on_launch_browser(self):
        """点击「启动浏览器」按钮"""
        store = self.selected_store.get()
        number = self.number_entry.get()

        if not store:
            messagebox.showwarning("提示", "请先选择店铺")
            return
        if not number or not number.isdigit():
            messagebox.showwarning("提示", "请输入有效的起始单号（纯数字）")
            return

        start_num = int(number)
        dpi_scale = self._detect_dpi_scale()

        self._set_buttons_state(launch=False, ready=False)
        self.log("=" * 55)
        self.log(f"🚀 启动浏览器")
        self.log(f"   店铺: {STORES[store]['name']}")
        self.log(f"   起始单号: {start_num}")
        self.log(f"   缩放比例: {int(dpi_scale * 100)}%")
        self.set_status("🚀 正在启动浏览器...")

        # 如果已有浏览器，先关闭
        if self.automator:
            self.log("   已有浏览器进程，正在关闭旧浏览器...")
            # 异步关闭旧浏览器
            def _close_old():
                future = asyncio.run_coroutine_threadsafe(
                    self.automator.close(), self._loop
                )
                future.result(timeout=10)

            import threading
            close_thread = threading.Thread(target=_close_old, daemon=True)
            close_thread.start()
            close_thread.join(timeout=10)
            self.automator = None
            self._browser_launched = False

        # 创建自动化器，所有异步操作在同一个事件循环上执行
        self.automator = DianXiaoMiAutomator(on_log=lambda msg: self.log(msg))
        self._current_store = store
        self._current_start = start_num

        # 在持久事件循环上启动浏览器
        self._async_call(
            self.automator.launch_browser(device_scale=dpi_scale),
            callback=self._on_launch_result,
        )

    def _on_launch_result(self, result, exc):
        """浏览器启动结果回调"""
        if exc:
            self._on_error(f"启动浏览器失败: {exc}")
            return

        self._browser_launched = True
        self.ready_btn.configure(state="normal")
        self.debug_btn.configure(state="normal")
        self.color_dbg_btn.configure(state="normal")
        self.set_status("🌐 浏览器已启动，请登录店小秘并导航到「待审核」页面")
        self.log("")
        self.log("=" * 55)
        self.log("👉 【操作提示】")
        self.log("   1. 在浏览器中手动登录店小秘")
        self.log("   2. 关闭登录后的弹窗")
        self.log("   3. 点击左侧菜单：订单 → 待审核")
        self.log("   4. 完成后，点击「我已就绪，开始执行」")
        self.log("=" * 55)

    def _on_debug_scan(self):
        """点击「调试扫描」按钮"""
        if not self.automator or not self._browser_launched:
            return
        self._set_buttons_state(launch=False, ready=False)
        self.debug_btn.configure(state="disabled")
        self.log("")
        self.log("=" * 55)
        self.log("🔍 开始调试扫描...")
        self.set_status("🔍 正在扫描页面元素...")
        self._async_call(
            self.automator.debug_scan_page(),
            callback=self._on_debug_done,
        )

    def _on_color_scan(self):
        """点击「🎨 颜色扫描」按钮"""
        if not self.automator or not self._browser_launched:
            return
        self._set_buttons_state(launch=False, ready=False)
        self.color_dbg_btn.configure(state="disabled")
        self.log("")
        self.log("=" * 55)
        self.log("🎨 开始扫描颜色选择器结构...")
        self.set_status("🎨 正在扫描颜色选择器...")
        self._async_call(
            self.automator.debug_scan_colors(),
            callback=self._on_color_debug_done,
        )

    def _on_debug_done(self, result, exc):
        """调试扫描完成"""
        self._set_buttons_state(launch=True, ready=True)
        self.debug_btn.configure(state="normal")
        if exc:
            self.log(f"❌ 扫描出错: {exc}")
        self.set_status("🔍 扫描完成，请复制日志内容发给我")

    def _on_color_debug_done(self, result, exc):
        """颜色扫描完成"""
        self._enable_rerun()
        self.color_dbg_btn.configure(state="normal")
        if exc:
            self.log(f"❌ 颜色扫描出错: {exc}")
        self.set_status("🎨 颜色扫描完成")

    def _on_ready(self):
        """点击「我已就绪」按钮"""
        if not self.automator or not self._browser_launched:
            return

        store = self.selected_store.get()
        number = self.number_entry.get()

        if not store:
            messagebox.showwarning("提示", "请选择店铺")
            return
        if not number or not number.isdigit():
            messagebox.showwarning("提示", "请输入有效的起始单号（纯数字）")
            return

        start_num = int(number)
        self._current_store = store
        self._current_start = start_num

        self._set_buttons_state(launch=False, ready=False)
        self.log("")
        self.log("=" * 55)
        self.log("✓ 用户已就绪，开始自动化执行...")
        self.log(f"   店铺: {STORES[store]['name']}")
        self.log(f"   起始单号: {start_num}")
        self.set_status("⚙️ 正在执行自动填号...")

        # 在同一条事件循环上执行（与启动浏览器是同一条）
        self._async_call(
            self._run_full_automation(store, start_num),
            callback=self._on_automation_result,
        )

    async def _run_full_automation(self, store: str, start_num: int):
        """完整的自动化流程（在持久事件循环上运行）"""
        await self.automator.verify_and_prepare(store)
        result = await self.automator.execute_batch_picking(start_num, store)
        return result

    def _on_automation_result(self, result, exc):
        """自动化执行结果回调"""
        if exc:
            self._on_error(str(exc))
            return
        self._on_success(result)

    def _on_success(self, result: dict):
        """执行成功——保持浏览器不关闭，允许重新执行"""
        current_store = result["store"]
        self.log("")
        self.log(f"✅✅✅ 【{STORES[current_store]['name']}】执行完成！")
        self.log(f"   填写范围: {result['start']} ~ {result['end']}")
        self.log(f"   填写数量: {result['count']} 条")

        remaining = [s for s in STORE_LIST if s != current_store]

        if remaining:
            next_store = remaining[0]
            next_start = result["end"] + 1
            self.log("")
            self.log("=" * 55)
            self.log(f"👉 提示：浏览器保持打开状态")
            self.log(f"   如需继续处理「{STORES[next_store]['name']}」:")
            self.log(f"   ① 在浏览器中导航回「待审核」页面")
            self.log(f"   ② 选择店铺「{next_store}」，填入起始单号 {next_start}")
            self.log(f"   ③ 点击「我已就绪，开始执行」即可复用当前浏览器")
            self.log("=" * 55)
            self._prompt_next_store(next_store, next_start)
        else:
            self.log("")
            self.log("🎉🎉🎉 全部店铺处理完成！")
            self.log("   🔄 如需继续操作：更改店铺和单号后，点击「我已就绪」重新执行")
            self.set_status("✅ 全部完成，浏览器保持打开")
            self._enable_rerun()

    def _enable_rerun(self):
        """保持浏览器打开，允许用户修改参数后重新执行"""
        self._browser_launched = True
        self._set_buttons_state(launch=True, ready=True)
        self.debug_btn.configure(state="normal")
        self.color_dbg_btn.configure(state="normal")
        self.set_status("🔄 浏览器保持打开，可修改参数后点击「我已就绪」")

    def _prompt_next_store(self, next_store: str, next_start: int):
        """提示用户处理下一个店铺"""
        result = messagebox.askyesno(
            "继续处理下一个店铺",
            f"【{STORES[next_store]['name']}】\n\n"
            f"建议起始单号: {next_start}\n\n"
            f"浏览器保持打开，是否自动填入信息？\n"
            f"(点击「是」自动填入，点击「否」手动设置)",
        )
        if result:
            self.selected_store.set(next_store)
            self.number_entry.delete(0, "end")
            self.number_entry.insert(0, str(next_start))
            self._update_info_panel()
            self._enable_rerun()
            self._current_store = next_store
            self._current_start = next_start
            self.set_status(f"📋 已填入「{STORES[next_store]['name']}」信息，请导航到待审核页面后点击执行")
        else:
            self._enable_rerun()

    def _on_error(self, error_msg: str):
        """错误处理——保持浏览器打开以便调试或重试"""
        self.log(f"❌ 错误: {error_msg}")
        self.set_status("❌ 执行出错（浏览器保持打开）")
        # 保持浏览器打开，允许修改参数后重试或调试
        self._enable_rerun()
        messagebox.showerror("执行错误", error_msg)

    def _set_buttons_state(self, launch: bool = True, ready: bool = False):
        """设置按钮状态"""
        self.launch_btn.configure(state="normal" if launch else "disabled")
        self.ready_btn.configure(state="normal" if ready else "disabled")

    def _reset_ui(self):
        """重置UI到初始状态"""
        self._browser_launched = False
        self._set_buttons_state(launch=True, ready=False)
        self.set_status("💤 等待操作...")

    def _on_close(self):
        """窗口关闭事件"""
        if self.automator:
            # 在同一个事件循环上关闭浏览器
            future = asyncio.run_coroutine_threadsafe(
                self.automator.close(), self._loop
            )
            future.result(timeout=5)
        # 关闭事件循环
        self._loop.call_soon_threadsafe(self._loop.stop)
        self.destroy()
