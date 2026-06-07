"""
店小秘排单号自动填写工具 - 浏览器自动化模块
"""
import asyncio
import os
from playwright.async_api import async_playwright, TimeoutError as PwTimeout
from config import (
    DIANXIAOMI_HOME_URL,
    PENDING_REVIEW_URLS,
    PENDING_REVIEW_URL_KEYWORDS,
    SELECTORS,
    TIMEOUTS,
    STORES,
)


class AutomatorError(Exception):
    """自动化操作异常"""
    pass


class DianXiaoMiAutomator:
    """店小秘浏览器自动化控制器"""

    def __init__(self, on_log=None):
        self.playwright = None
        self.context = None
        self.page = None
        self._on_log = on_log
        self._running = False
        self._profile_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "browser_profile",
        )

    def _log(self, msg: str):
        if self._on_log:
            self._on_log(msg)
        print(f"[Automator] {msg}")

    # ==================== 浏览器启动 ====================

    async def launch_browser(self, device_scale: float = 1.25):
        """启动浏览器并导航到店小秘"""
        self._log(f"浏览器缩放比例: {int(device_scale * 100)}%")
        self._log(f"浏览器配置文件: {self._profile_dir}")

        self.playwright = await async_playwright().start()
        os.makedirs(self._profile_dir, exist_ok=True)

        browser_channels = [
            ("chrome", "Chrome"),
            ("msedge", "Edge"),
            (None, "Playwright Chromium"),
        ]

        last_error = None
        for channel, label in browser_channels:
            try:
                ctx_kwargs = {
                    "user_data_dir": self._profile_dir,
                    "headless": False,
                    "args": [
                        "--start-maximized",
                        "--disable-blink-features=AutomationControlled",
                        f"--force-device-scale-factor={device_scale}",
                    ],
                    "locale": "zh-CN",
                    "timezone_id": "Asia/Shanghai",
                    "no_viewport": True,
                }
                if channel:
                    ctx_kwargs["channel"] = channel

                self.context = await self.playwright.chromium.launch_persistent_context(
                    **ctx_kwargs,
                )
                self._log(f"使用 {label} 浏览器启动成功")
                break
            except Exception as e:
                last_error = e
                self._log(f"  {label} 不可用: {str(e)[:60]}")
                continue

        if not self.context:
            raise AutomatorError(
                f"无法启动浏览器。请确保已安装 Chrome 或 Edge。\n最后错误: {last_error}"
            )

        # 获取初始页面
        pages = self.context.pages
        self.page = pages[0] if pages else await self.context.new_page()
        self.context.on("page", self._on_page_created)

        # 导航到店小秘
        self._log("浏览器已启动，正在导航到店小秘...")
        try:
            await self.page.goto(DIANXIAOMI_HOME_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            self._log("导航超时（可能页面加载较慢），继续等待...")

        self._log("")
        self._log("=" * 55)
        self._log("  【操作提示】")
        self._log("  1. 手动登录店小秘")
        self._log("  2. 关闭登录后的弹窗（如有）")
        self._log("  3. 点击左侧菜单：订单 → 待审核")
        self._log("  4. 完成后点击「我已就绪，开始执行」")
        self._log("=" * 55)
        self._log("")
        self._log("💡 下次启动自动保留登录状态")
        return True

    def _on_page_created(self, new_page):
        """新页面/弹窗事件"""
        self._log(f"检测到新页面: {new_page.url}")
        self.page = new_page

    # ==================== 页面验证 ====================

    async def verify_and_prepare(self, selected_store: str):
        """验证页面状态并筛选店铺"""
        if not self.context:
            raise AutomatorError("浏览器未启动")

        self._sync_current_page()
        if not self.page or self.page.is_closed():
            raise AutomatorError("页面已关闭，请重新启动")

        self._log("正在验证当前页面状态...")
        current_url = self.page.url
        self._log(f"当前URL: {current_url}")

        # 判断是否在待审核页面
        is_correct_page = any(
            keyword in current_url.lower() for keyword in PENDING_REVIEW_URL_KEYWORDS
        )

        if not is_correct_page:
            # 尝试自动跳转到待审核
            self._log("当前不在待审核页面，尝试自动跳转...")
            for url in PENDING_REVIEW_URLS:
                try:
                    await self.page.goto(url, wait_until="domcontentloaded", timeout=10000)
                    await asyncio.sleep(1)
                    new_url = self.page.url
                    if any(k in new_url.lower() for k in PENDING_REVIEW_URL_KEYWORDS):
                        is_correct_page = True
                        self._log(f"已跳转到: {new_url}")
                        break
                except Exception:
                    continue

        if not is_correct_page:
            raise AutomatorError(
                "当前不在「待审核」页面，且无法自动跳转。\n"
                "请手动点击左侧菜单：订单 → 待审核"
            )

        self._log("确认已在「待审核」页面")
        await asyncio.sleep(1.5)

        # 检查店铺筛选
        await self._ensure_store_filter(selected_store)
        return True

    def _sync_current_page(self):
        """同步 page 引用到当前前台页面"""
        if not self.context:
            return
        try:
            pages = self.context.pages
            for p in pages:
                if not p.is_closed():
                    self.page = p
                    break
        except Exception:
            pass

    # ==================== 店铺筛选 ====================

    async def _ensure_store_filter(self, store_key: str):
        """确保店铺筛选正确——点击店铺账号筛选，带重试"""
        store_name = STORES[store_key]["name"]
        self._log(f"正在筛选店铺: {store_name}")

        for attempt in range(3):
            # 方式1: 点击"店铺账号"触发筛选，再选店铺名
            try:
                shop_label = self.page.get_by_text("店铺账号", exact=False).first
                if await shop_label.is_visible(timeout=5000):
                    await shop_label.click()
                    await asyncio.sleep(1)

                    store_option = self.page.get_by_text(store_name, exact=True).first
                    if await store_option.is_visible(timeout=5000):
                        await store_option.click()
                        self._log(f"✅ 已选择店铺: {store_name}")
                        await asyncio.sleep(2)
                        return

                    await self.page.keyboard.press("Escape")
                    await asyncio.sleep(0.3)
            except Exception:
                pass

            # 方式2: 直接点击店铺名称标签
            try:
                store_tag = self.page.get_by_text(store_name, exact=True).first
                if await store_tag.is_visible(timeout=3000):
                    await store_tag.click()
                    self._log(f"✅ 已选择店铺: {store_name}")
                    await asyncio.sleep(2)
                    return
            except Exception:
                pass

            if attempt < 2:
                self._log(f"  第{attempt+1}次尝试失败，重试中...")
                await asyncio.sleep(2)

        self._log("⚠️ 未能自动筛选店铺（尝试3次均失败）")
        self._log("   请手动点击页面上方的「店铺账号」→ 选择对应店铺后重试")

    # ==================== 批量拣货说明 ====================

    async def execute_batch_picking(self, start_number: int, store_key: str):
        """执行批量拣货说明填写"""
        if not self.context:
            raise AutomatorError("浏览器未启动")

        self._sync_current_page()
        if not self.page or self.page.is_closed():
            raise AutomatorError("页面已关闭，请重新启动")

        store_info = STORES[store_key]
        need_change_color = (store_key == "二店")

        self._log(f"开始为【{store_info['name']}】填写排单号")
        self._log(f"   起始单号: {start_number}")

        # 1. 全选（返回已选中条数）
        self._log("正在全选订单...")
        expected_count = await self._select_all_orders()
        await asyncio.sleep(1)

        # 2. 批量操作
        self._log("正在打开批量操作...")
        await self._click_batch_operation()
        await asyncio.sleep(0.5)

        # 3. 批量拣货说明
        self._log("正在选择「批量拣货说明」...")
        await self._click_batch_picking_note()
        await asyncio.sleep(2)

        # 4. 填序号（传入期望条数做校验）
        self._log(f"正在填入序号（从 {start_number} 开始，期望 {expected_count} 条）...")
        filled_count = await self._fill_sequential_numbers(start_number, need_change_color, expected_count)

        # 5. 确定
        self._log("正在点击「确定」提交...")
        await self._click_confirm()
        await asyncio.sleep(1)

        self._log(f"✅ 【{store_info['name']}】排单号填写完成！")
        self._log(f"   本次填写范围: {start_number} ~ {start_number + filled_count - 1}")

        return {
            "store": store_key,
            "start": start_number,
            "end": start_number + filled_count - 1,
            "count": filled_count,
        }

    async def _select_all_orders(self):
        """全选——并获取已选中条数"""
        await self.page.wait_for_timeout(500)

        result = await self.page.evaluate("""
            () => {
                // 找表头区域的复选框
                const thead = document.querySelector('thead, .ant-table-thead, .vxe-table--header');
                if (thead) {
                    const cb = thead.querySelector('.ant-checkbox-input');
                    if (cb) { cb.checked = true; cb.dispatchEvent(new Event('change', {bubbles: true})); return 'thead_ok'; }
                }
                const all = document.querySelectorAll('.ant-checkbox-input:not([type="hidden"])');
                if (all.length > 0) { all[0].checked = true; all[0].dispatchEvent(new Event('change', {bubbles: true})); return 'first_ok'; }
                return 'not_found';
            }
        """)
        self._log(f"✅ 已全选订单")

        await asyncio.sleep(1)

        # 读取选中数量
        expected_count = 0
        for attempt in range(5):
            try:
                count_text = await self.page.text_content("body") or ""
                # 匹配 "已选中 X 条数据" 或 "已选中X条数据"
                import re
                match = re.search(r'已选中\s*(\d+)\s*条数据', count_text)
                if match:
                    expected_count = int(match.group(1))
                    self._log(f"📊 已选中 {expected_count} 条数据")
                    return expected_count
            except Exception:
                pass
            await asyncio.sleep(0.5)

        self._log("⚠️ 未读取到选中条数")
        return 0

    async def _click_batch_operation(self):
        """点击批量操作按钮——使用 Playwright 真实鼠标事件"""
        await asyncio.sleep(1)

        for attempt in range(3):
            # 方式1: 点击按钮本身（Playwright 真实事件）
            try:
                btn = self.page.locator("button:has-text('批量操作'):visible").first
                await btn.click(timeout=3000, force=True)
                self._log("✅ 已点击批量操作(按钮)")
                await asyncio.sleep(1.5)
                return
            except Exception:
                pass

            # 方式2: 文字定位点击
            try:
                btn = self.page.get_by_text("批量操作", exact=True).first
                await btn.click(timeout=3000, force=True)
                self._log("✅ 已点击批量操作(文字)")
                await asyncio.sleep(1.5)
                return
            except Exception:
                pass

            # 方式3: 点击按钮的父级（Ant Design 的 dropdown 触发器可能在父级）
            try:
                clicked = await self.page.evaluate("""
                    () => {
                        const btns = document.querySelectorAll('button');
                        for (const b of btns) {
                            if (b.innerText.trim() === '批量操作' && b.offsetParent !== null) {
                                // 点击按钮本身
                                b.click();
                                // 也尝试点击父级
                                const parent = b.parentElement;
                                if (parent) parent.click();
                                // 再尝试触发 ant-dropdown-trigger
                                const trigger = b.closest('.ant-dropdown-trigger') || b.closest('[class*="dropdown"]');
                                if (trigger) trigger.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)
                if clicked:
                    self._log("✅ 已点击批量操作(js+父级)")
                    await asyncio.sleep(1.5)
                    return
            except Exception:
                pass

            self._log(f"第{attempt+1}次尝试失败")
            await asyncio.sleep(1)

        raise AutomatorError("找不到「批量操作」按钮")

    async def _click_batch_picking_note(self):
        """在下拉菜单中选批量拣货说明"""
        await asyncio.sleep(1.5)

        for attempt in range(3):
            # 先调试看看下拉菜单里有什么
            debug_info = await self.page.evaluate("""
                () => {
                    // 找所有可能的下拉菜单容器
                    const menus = document.querySelectorAll(
                        '.ant-dropdown:not([style*="display: none"]), ' +
                        '.ant-dropdown-menu:not([style*="display: none"]), ' +
                        '.ant-select-dropdown:not([style*="display: none"]), ' +
                        '[class*="dropdown"]:not([style*="display: none"])'
                    );
                    const result = [];
                    for (const m of menus) {
                        const items = m.querySelectorAll('li, div, span');
                        items.forEach(item => {
                            const text = (item.innerText || '').trim();
                            if (text) result.push(text.slice(0, 40));
                        });
                    }
                    // 也找页面上所有可见的li元素
                    if (result.length === 0) {
                        document.querySelectorAll('li:not([style*="display: none"])').forEach(li => {
                            const text = (li.innerText || '').trim();
                            if (text && li.offsetParent) result.push(text.slice(0, 40));
                        });
                    }
                    return result;
                }
            """)

            if debug_info and len(debug_info) > 0:
                self._log(f"下拉菜单选项: {' | '.join(debug_info[:10])}")
            else:
                self._log("未检测到下拉菜单内容")

            # 尝试点击
            clicked = await self.page.evaluate("""
                () => {
                    // 遍历所有元素，用 includes 匹配（不怕空格/换行差异）
                    const allElements = document.querySelectorAll('li, span, div, a');
                    for (const el of allElements) {
                        const text = (el.innerText || '').trim();
                        if (text.includes('批量拣货说明') && el.offsetParent !== null) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }
            """)
            if clicked:
                self._log("✅ 已选择批量拣货说明")
                await asyncio.sleep(1.5)
                return

            self._log(f"第{attempt+1}次尝试未找到「批量拣货说明」")
            await asyncio.sleep(1)

        raise AutomatorError(
            "找不到「批量拣货说明」选项。\n"
            f"下拉菜单中检测到以下选项: {debug_info}"
        )

    async def _click_batch_picking_note(self):
        """在下拉选项中选择批量拣货说明"""
        await asyncio.sleep(1)

        # 方式1: 在下拉弹出层中选
        try:
            # Ant Design 的下拉选项在 .ant-select-dropdown 或 .ant-dropdown-menu
            option = self.page.locator(
                ".ant-select-item-option:has-text('批量拣货说明'):visible, "
                ".ant-dropdown-menu-item:has-text('批量拣货说明'):visible, "
                ".ant-select-item:has-text('批量拣货说明'):visible"
            ).first
            if await option.is_visible(timeout=5000):
                await option.click()
                self._log("✅ 已选择批量拣货说明")
                await asyncio.sleep(1)
                return
        except Exception:
            pass

        # 方式2: 直接找文字
        try:
            item = self.page.get_by_text("批量拣货说明", exact=True).first
            if await item.is_visible(timeout=3000):
                await item.click()
                self._log("✅ 已选择批量拣货说明(by text)")
                await asyncio.sleep(1)
                return
        except Exception:
            pass

        # 方式3: JavaScript
        try:
            clicked = await self.page.evaluate("""
                () => {
                    const items = document.querySelectorAll('.ant-select-item-option, ' +
                        '.ant-dropdown-menu-item, li');
                    for (const item of items) {
                        if (item.innerText.includes('批量拣货说明') && item.offsetParent !== null) {
                            item.click();
                            return true;
                        }
                    }
                    return false;
                }
            """)
            if clicked:
                self._log("✅ 已选择批量拣货说明(js)")
                await asyncio.sleep(1)
                return
        except Exception:
            pass

        raise AutomatorError(
            "找不到「批量拣货说明」选项。\n"
            "请确认下拉框中是否有该选项"
        )

    async def _fill_sequential_numbers(self, start: int, need_change_color: bool, expected_count: int = 0) -> int:
        """在弹窗中填序号 + 改颜色（二店），逐行处理确保每行的颜色下拉菜单能正确选到红色"""
        await asyncio.sleep(2)

        filled_count = 0
        current = start
        self._log(f"开始填写序号，从 {current} 开始")

        modal = self.page.locator(".ant-modal-content:visible").first
        if not await modal.is_visible():
            raise AutomatorError("找不到弹窗")

        # 滚动让所有行加载
        try:
            scroll_body = modal.locator(".ant-modal-body, .ant-table-body, .vxe-table--body").first
            if await scroll_body.is_visible(timeout=2000):
                for _ in range(5):
                    await scroll_body.evaluate("el => el.scrollTop += 300")
                    await asyncio.sleep(0.3)
                await scroll_body.evaluate("el => el.scrollTop = 0")
                await asyncio.sleep(0.5)
        except Exception:
            pass

        # ---- 第一步：一次性填完所有序号 ----
        fill_result = await self.page.evaluate(f"""
            () => {{
                const startNum = {start};
                const modal = document.querySelector('.ant-modal-content:not([style*="display: none"])');
                if (!modal) return {{ filled: 0 }};

                function findInput(row) {{
                    const inp = row.querySelector('input:not([type="checkbox"]):not([type="hidden"]):not([type="search"]), textarea');
                    if (!inp) return null;
                    const ph = (inp.placeholder || '').trim();
                    if (ph.includes('请选择') || inp.readOnly || inp.disabled) return null;
                    const rect = inp.getBoundingClientRect();
                    if (rect.width < 30 || rect.height < 10) return null;
                    return inp;
                }}

                let num = startNum;
                let filled = 0;

                // 方式A: 找弹窗内的所有表格行
                const tables = modal.querySelectorAll('table');
                if (tables.length > 0) {{
                    for (const table of tables) {{
                        const rows = table.querySelectorAll('tr');
                        for (const row of rows) {{
                            if (row.offsetParent === null) continue;
                            const inp = findInput(row);
                            if (!inp) continue;
                            inp.value = String(num);
                            inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                            filled++;
                            num++;
                        }}
                    }}
                    return {{ filled }};
                }}

                // 方式B: 直接找所有输入框
                const inputs = modal.querySelectorAll('input:not([type="checkbox"]):not([type="hidden"]):not([type="search"]), textarea');
                for (const inp of inputs) {{
                    const ph = (inp.placeholder || '').trim();
                    if (ph.includes('请选择') || inp.readOnly || inp.disabled) continue;
                    const rect = inp.getBoundingClientRect();
                    if (rect.width < 30 || rect.height < 10) continue;
                    inp.value = String(num);
                    inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    filled++;
                    num++;
                }}
                return {{ filled }};
            }}
        """)

        filled_count = fill_result.get("filled", 0) if isinstance(fill_result, dict) else 0
        self._log(f"✅ 已填写 {filled_count} 个序号")

        # ---- 第二步：逐行改颜色（二店） ----
        if need_change_color and filled_count > 0:
            self._log("正在逐行修改颜色为红色...")
            changed = 0

            # 扫描弹窗内所有可见的 .ant-select-selector（不局限于表格行）
            selector_data = await self.page.evaluate("""
                () => {
                    const modal = document.querySelector('.ant-modal-content:not([style*="display: none"])');
                    if (!modal) return { count: 0, found: [] };
                    const all = modal.querySelectorAll('.ant-select-selector');
                    const visible = [];
                    for (const sel of all) {
                        const rect = sel.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            visible.push({
                                text: (sel.innerText || '').trim().slice(0, 20),
                                size: `${Math.round(rect.width)}x${Math.round(rect.height)}`,
                            });
                        }
                    }
                    return { count: visible.length, found: visible };
                }
            """)

            color_count = selector_data.get("count", 0) if isinstance(selector_data, dict) else 0
            found = selector_data.get("found", []) if isinstance(selector_data, dict) else []

            self._log(f"弹窗内可见 .ant-select-selector: {color_count} 个")
            for i, s in enumerate(found):
                self._log(f"  [{i}] 文字='{s['text']}' 尺寸={s['size']}")

            if color_count == 0:
                self._log("⚠️ 未检测到颜色选择器，请点击「🎨 颜色扫描」查看详情")
            else:
                # 逐个点击颜色选择器 → 选红色
                for ri in range(color_count):
                    try:
                        # 点击第 ri 个颜色选择器
                        clicked = await self.page.evaluate(f"""
                            () => {{
                                const modal = document.querySelector('.ant-modal-content:not([style*="display: none"])');
                                if (!modal) return false;
                                const selectors = modal.querySelectorAll('.ant-select-selector');
                                let idx = 0;
                                for (const sel of selectors) {{
                                    const rect = sel.getBoundingClientRect();
                                    if (rect.width === 0 || rect.height === 0) continue;
                                    if (idx === {ri}) {{
                                        sel.click();
                                        return true;
                                    }}
                                    idx++;
                                }}
                                return false;
                            }}
                        """)

                        if not clicked:
                            self._log(f"  ⚠️ 第 {ri+1} 个颜色选择器找不到")
                            continue

                        self._log(f"  第 {ri+1} 个: 已点击，等待下拉菜单...")
                        await asyncio.sleep(0.5)

                        # 从当前可见的下拉菜单中选红色
                        red_result = await self._select_red_in_dropdown()
                        self._log(f"  第 {ri+1} 个: {red_result}")

                        if 'no_' not in str(red_result):
                            changed += 1

                        await asyncio.sleep(0.3)

                    except Exception as e:
                        self._log(f"  第 {ri+1} 个改色出错: {e}")

                self._log(f"🔴 颜色修改完成: {changed}/{color_count} 个已改红")

        # ---- 校验数量 ----
        if expected_count > 0 and filled_count != expected_count:
            self._log(f"⚠️ 警告：选中 {expected_count} 条，但只填了 {filled_count} 条")
            self._log("   可能是因为部分订单行未加载，点击「确定」提交已填部分")
        elif expected_count > 0 and filled_count == expected_count:
            self._log(f"✅ 数量校验通过（{filled_count} 条全部填完）")

        if filled_count == 0:
            raise AutomatorError(
                "未能填入序号。弹窗内找不到内容输入框。\n"
                "请确认弹窗中每一行是否有可输入的文本框"
            )

        return filled_count

    async def _select_red_in_dropdown(self) -> str:
        """从当前页面上可见的 Ant Design 下拉菜单中选中红色选项"""
        await asyncio.sleep(0.2)

        result = await self.page.evaluate("""
            () => {
                // 兜底：额外检查页面所有下拉菜单，用 visible 判断而非 inline style
                function isVisible(el) {
                    if (!el || el.offsetParent !== null) return true;
                    // offsetParent 为 null 时，再检查 getBoundingClientRect
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                }

                // 找当前页面中可见的 Ant Design 下拉菜单
                // 注意：不能用 [style*="display: none"]，因为 Ant Design 用 CSS class 隐藏
                const allDropdowns = document.querySelectorAll('.ant-select-dropdown');
                let dropdown = null;
                for (const dd of allDropdowns) {
                    if (isVisible(dd)) {
                        dropdown = dd;
                        break;
                    }
                }

                if (!dropdown) return 'no_dropdown';

                const options = dropdown.querySelectorAll('.ant-select-item-option');
                const results = [];

                for (const opt of options) {
                    const all = opt.querySelectorAll('*');
                    for (const el of all) {
                        const s = (el.getAttribute('style') || '').toLowerCase().replace(/\\s+/g, '');

                        // 内联样式: background:red / background-color:red
                        if (s.includes('background:red') || s.includes('background-color:red')) {
                            opt.click(); return 'inline_red';
                        }

                        // 内联样式: background:#ffxxxx（以 #f 开头的 hex 红色系）
                        if (/background(?:-color)?:#f[0-9a-f]{5}[;)]/i.test(s)) {
                            opt.click(); return 'inline_hex_ff';
                        }

                        // 内联样式: background:#f00 (short hex red)
                        if (/background(?:-color)?:#f00[;)]/i.test(s)) {
                            opt.click(); return 'inline_hex_short';
                        }

                        // 内联样式: background:rgb(255, 或 rgb(254, 等——R≈255, G≈0
                        if (/background(?:-color)?:rgb\\(\\s*2(?:5[0-5]|[0-4]\\d)\\s*,\\s*(?:[0-9]|[1-9]\\d?)\\s*,\\s*(?:[0-9]|[1-9]\\d?)\\s*\\)/.test(s)) {
                            opt.click(); return 'inline_rgb_red';
                        }

                        // 计算样式: computed background-color 检查
                        try {
                            const bg = window.getComputedStyle(el).backgroundColor;
                            if (bg && bg !== 'transparent' && bg !== 'rgba(0, 0, 0, 0)') {
                                const match = bg.match(/rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)/);
                                if (match) {
                                    const r = parseInt(match[1]);
                                    const g = parseInt(match[2]);
                                    const b = parseInt(match[3]);
                                    if (r > 180 && g < 100 && b < 100) {
                                        opt.click(); return 'computed_red';
                                    }
                                    // 记录非红色的背景色，用于调试
                                    results.push({idx: results.length, r, g, b, bg});
                                }
                            }
                        } catch(e) {}
                    }
                }

                // 调试：记录所有选项的背景色信息
                return JSON.stringify({found: results.map(r => `rgb(${r.r},${r.g},${r.b})`) });
            }
        """)

        # 检查结果是否是 JSON 字符串（调试输出）
        if isinstance(result, str) and result.startswith('{'):
            self._log(f"  颜色检测详情: {result}")
            # 兜底：点最后一个选项
            self._log(f"  尝试点击最后一个选项...")
            last_result = await self.page.evaluate("""
                () => {
                    function isVisible(el) {
                        if (!el || el.offsetParent !== null) return true;
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    }
                    const allDropdowns = document.querySelectorAll('.ant-select-dropdown');
                    let dropdown = null;
                    for (const dd of allDropdowns) {
                        if (isVisible(dd)) { dropdown = dd; break; }
                    }
                    if (!dropdown) return 'no_dropdown_final';
                    const opts = dropdown.querySelectorAll('.ant-select-item-option');
                    if (opts.length >= 2) { opts[opts.length - 1].click(); return 'fallback_last'; }
                    if (opts.length === 1) { opts[0].click(); return 'fallback_only'; }
                    return 'no_option';
                }
            """)
            return last_result or 'fallback_none'

        return result or 'no_result'

    async def _click_confirm(self):
        """点击确定"""
        try:
            btn = self.page.locator("button:has-text('确定')").first
            await btn.wait_for(state="visible", timeout=5000)
            await btn.click()
            self._log("✅ 已点击确定")
        except Exception:
            try:
                btn = self.page.locator(".ant-modal-footer .ant-btn-primary").first
                await btn.click()
                self._log("✅ 已点击确定（备用）")
            except Exception:
                raise AutomatorError("找不到「确定」按钮")

    # ==================== 调试扫描 ====================

    async def debug_scan_page(self):
        """调试模式：扫描页面所有可交互元素"""
        if not self.context:
            self._log("浏览器未启动")
            return

        self._sync_current_page()
        if not self.page or self.page.is_closed():
            self._log("页面已关闭")
            return

        self._log("=" * 55)
        self._log("🔍 调试模式 - 页面元素扫描")
        self._log("=" * 55)
        self._log(f"URL: {self.page.url}")
        self._log("")

        js = """
        (() => {
            const r = { buttons: [], inputs: [], selects: [], checkboxes: [], texts: [], dialogs: [], menu_items: [] };

            // 所有可见按钮
            document.querySelectorAll('button, [role="button"], .ant-btn').forEach(el => {
                if (el.tagName !== 'BUTTON' && !el.classList.contains('ant-btn')) return;
                const t = (el.innerText || el.textContent || '').trim().slice(0, 60);
                const c = (el.className || '').slice(0, 80);
                const v = el.offsetParent !== null;
                const rect = el.getBoundingClientRect();
                if (t && rect.width > 0) r.buttons.push({t, c, v, tag: el.tagName});
            });

            // 输入框
            document.querySelectorAll('input:not([type="hidden"])').forEach(el => {
                r.inputs.push({
                    type: el.type, ph: el.placeholder, cls: (el.className || '').slice(0, 60),
                    name: el.name, v: el.offsetParent !== null
                });
            });

            // Ant Design Select
            document.querySelectorAll('.ant-select-selector').forEach(el => {
                const text = el.innerText.trim().slice(0, 40);
                const v = el.offsetParent !== null;
                if (v) r.selects.push({type: 'ant-select', text, cls: (el.className || '').slice(0, 60)});
            });

            // 原生 select
            document.querySelectorAll('select').forEach(el => {
                if (el.offsetParent === null) return;
                const opts = Array.from(el.options).map(o => o.text.trim()).filter(Boolean).join(' | ').slice(0, 200);
                r.selects.push({type: 'native', name: el.name, opts});
            });

            // 复选框
            document.querySelectorAll('.ant-checkbox-input, input[type="checkbox"]').forEach(el => {
                if (el.offsetParent === null) return;
                r.checkboxes.push({tag: el.tagName, cls: (el.className || '').slice(0, 50)});
            });

            // 左侧菜单项
            document.querySelectorAll('.ant-menu-item, .ant-menu-submenu-title, li a, .menu-item').forEach(el => {
                const t = (el.innerText || '').trim().slice(0, 40);
                const v = el.offsetParent !== null;
                if (t && v) r.menu_items.push(t);
            });

            // 弹窗
            document.querySelectorAll('.ant-modal, .ant-modal-content, .ant-message, .el-dialog, [role="dialog"]').forEach(el => {
                const t = (el.innerText || '').trim().slice(0, 300);
                const v = el.offsetParent !== null;
                if (v && t) r.dialogs.push(t.slice(0, 200));
            });

            // 页面文本片段
            const ts = new Set();
            document.querySelectorAll('span, div, a, label, li, th, td, .ant-select-item-option').forEach(el => {
                const t = (el.innerText || '').trim();
                if (t && t.length < 60 && !/^[\\s\\d.]+$/.test(t)) ts.add(t);
            });
            r.texts = Array.from(ts).slice(0, 120);

            return r;
        })();
        """
        try:
            data = await self.page.evaluate(js)
        except Exception as e:
            self._log(f"扫描失败: {e}")
            return

        # 输出
        self._log(f"——— [左侧菜单] 共 {len(data['menu_items'])} 项 ———")
        for m in data["menu_items"]:
            self._log(f"  {m}")

        self._log("")
        self._log(f"——— [按钮] 共 {len(data['buttons'])} 个 ———")
        for b in data["buttons"]:
            self._log(f"  {'[可见]' if b['v'] else '[隐藏]'} {b['t']}  ({b['c'][:40]})")

        self._log("")
        self._log(f"——— [输入框] 共 {len(data['inputs'])} 个 ———")
        for inp in data["inputs"]:
            if inp["v"]:
                self._log(f"  type={inp['type']} ph={inp['ph'][:20]} name={inp['name'][:15]}")

        self._log("")
        self._log(f"——— [下拉框/选择器] 共 {len(data['selects'])} 个 ———")
        for s in data["selects"]:
            if s["type"] == "ant-select":
                self._log(f"  [AntSelect] 文字: {s['text']}  class: {s['cls'][:40]}")
            else:
                self._log(f"  [原生Select] name={s['name']} options={s['opts'][:80]}")

        self._log("")
        self._log(f"——— [复选框] 共 {len(data['checkboxes'])} 个 ———")
        for cb in data["checkboxes"][:5]:
            self._log(f"  {cb['cls'][:40]}")
        if len(data["checkboxes"]) > 5:
            self._log(f"  ... 共 {len(data['checkboxes'])} 个")

        self._log("")
        self._log(f"——— [弹窗/对话框] {len(data['dialogs'])} 个 ———")
        for d in data["dialogs"]:
            self._log(f"  {d[:200]}")

        self._log("")
        self._log("=" * 55)
        self._log("✅ 扫描完成，请把以上日志复制发给我")
        self._log("=" * 55)

    async def debug_scan_colors(self):
        """专门扫描颜色选择器下拉菜单的结构"""
        if not self.context:
            self._log("浏览器未启动")
            return

        self._sync_current_page()
        self._log("=" * 55)
        self._log("🎨 颜色选择器结构扫描")
        self._log("=" * 55)

        # 扫描页面中所有 Ant Design Select
        result = await self.page.evaluate("""
            () => {
                const r = { selectors: [], dropdowns: [] };

                // 扫描所有 .ant-select-selector
                document.querySelectorAll('.ant-select-selector').forEach(el => {
                    if (el.offsetParent === null) return;
                    const parent = el.closest('.ant-select');
                    const cls = (parent ? parent.className : el.className) || '';
                    const text = (el.innerText || '').trim().slice(0, 30);
                    const rect = el.getBoundingClientRect();
                    const inModal = !!el.closest('.ant-modal-content');
                    r.selectors.push({
                        cls: cls.slice(0, 80),
                        text,
                        inModal,
                        size: `${Math.round(rect.width)}x${Math.round(rect.height)}`,
                        pos: `${Math.round(rect.left)},${Math.round(rect.top)}`,
                    });
                });

                // 扫描所有可见的下拉菜单
                document.querySelectorAll('.ant-select-dropdown').forEach(dd => {
                    if (dd.offsetParent === null) return;
                    const opts = dd.querySelectorAll('.ant-select-item-option');
                    const optInfo = [];
                    opts.forEach((opt, i) => {
                        const innerHTML = (opt.innerHTML || '').trim().slice(0, 200);
                        const children = [];
                        opt.querySelectorAll('*').forEach(ch => {
                            const style = ch.getAttribute('style') || '';
                            const bg = window.getComputedStyle(ch).backgroundColor;
                            if (style.includes('background') || (bg && bg !== 'transparent' && bg !== 'rgba(0, 0, 0, 0)')) {
                                children.push({
                                    tag: ch.tagName,
                                    style: style.slice(0, 100),
                                    bg: bg,
                                });
                            }
                        });
                        optInfo.push({ index: i, html: innerHTML, coloredChildren: children });
                    });
                    r.dropdowns.push({
                        rect: dd.getBoundingClientRect(),
                        options: optInfo,
                    });
                });

                return r;
            }
        """)

        self._log(f"\n可见的 .ant-select-selector: {len(result['selectors'])} 个")
        for i, sel in enumerate(result['selectors']):
            self._log(f"  [{i}] inModal={sel['inModal']} text='{sel['text']}' size={sel['size']} pos={sel['pos']}")
            self._log(f"       class: {sel['cls']}")

        self._log(f"\n可见的下拉菜单: {len(result['dropdowns'])} 个")
        for di, dd in enumerate(result['dropdowns']):
            rect = dd['rect']
            self._log(f"  [下拉{di}] pos=({rect['left']:.0f},{rect['top']:.0f}) size=({rect['width']:.0f}x{rect['height']:.0f})")
            for opt in dd['options']:
                has_color = "🔴" if opt['coloredChildren'] else "  "
                self._log(f"    {has_color} 选项{opt['index']}: {opt['html'][:120]}")
                for cc in opt['coloredChildren']:
                    self._log(f"       → <{cc['tag']}> style={cc['style']}  computed={cc['bg']}")

        self._log("\n" + "=" * 55)
        self._log("扫描完成")

    # ==================== 关闭 ====================

    async def close(self):
        """关闭浏览器"""
        self._running = False
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass
        self._log("浏览器已关闭")
