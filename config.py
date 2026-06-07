"""
店小秘排单号自动填写工具 - 配置文件
"""

# ==================== 店铺配置 ====================
STORES = {
    "专营店": {
        "name": "Partsmost Professional Store 专营店(速卖通)",
        "short": "专营店",
        "note_color": "green",
        "color_label": "绿色",
    },
    "二店": {
        "name": "速卖通二店Partsmost auto parts store(速卖通)",
        "short": "二店",
        "note_color": "red",
        "color_label": "红色",
    },
}

STORE_LIST = list(STORES.keys())

# ==================== 页面URL配置 ====================
DIANXIAOMI_HOME_URL = "https://www.dianxiaomi.com/index.htm"

# 待审核页面可能的URL
# 注意：实际扫描显示 待审核页面 URL 可能是 /web/order/paid?go=m100
PENDING_REVIEW_URLS = [
    "https://www.dianxiaomi.com/web/order/paid",
    "https://www.dianxiaomi.com/web/order/audit",
    "https://www.dianxiaomi.com/web/order/auditList",
    "https://www.dianxiaomi.com/web/order/review",
    "https://www.dianxiaomi.com/order/auditList.htm",
]

# URL关键字（用于判断是否已在待审核页面）
PENDING_REVIEW_URL_KEYWORDS = [
    "paid", "audit", "review", "pending", "待审核",
    "verify", "approve",
]

# ==================== Ant Design 元素选择器 ====================
# 根据用户实际扫描结果，店小秘使用 Ant Design + vxe-table 组件库
SELECTORS = {
    # 左侧菜单：订单
    "menu_order": ".ant-menu-item:has-text('订单'), span:has-text('订单')",

    # 左侧菜单：待审核
    "menu_pending_review": "span:has-text('待审核'), .ant-menu-item:has-text('待审核')",

    # 店铺筛选——Ant Design Select组件
    # 店小秘筛选栏：先点筛选区域，再选店铺
    "store_filter_trigger": ".ant-select-selector, .ant-select, [class*='shop-filter']",

    # 全选 —— Ant Design 复选框（表格表头的那个）
    "select_all_checkbox": ".ant-checkbox-input",

    # 批量操作按钮（可见）
    "batch_button": "button:has-text('批量操作')",

    # 批量标记菜单项（在批量操作的下拉菜单里）
    "batch_picking_note": "批量标记",

    # 批量拣货说明弹窗中的输入框
    "picking_note_input": ".vxe-input--inner, .ant-input, .el-input__inner",

    # 颜色下拉框
    "color_select": ".ant-select-selector",

    # 确定按钮（在弹窗底部）
    "confirm_button": "button:has-text('确定'), .ant-btn-primary:has-text('确定')",
}

# ==================== 超时配置（毫秒） ====================
TIMEOUTS = {
    "page_load": 30000,
    "element_visible": 15000,
    "operation": 5000,
}

# ==================== 窗口配置 ====================
WINDOW_CONFIG = {
    "title": "店小秘排单号自动填写工具",
    "width": 520,
    "height": 680,
    "min_width": 480,
    "min_height": 620,
}
