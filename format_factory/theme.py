# format_factory/theme.py
"""
统一样式表。
  • 亮/暗两套基础色盘
  • 有背景图时动态替换主色（互补色方案）
  • GPU 厂商按钮：四种颜色（NVIDIA 绿 / AMD 红 / Intel 蓝 / 不使用灰）
  • 所有控件尺寸、间距、圆角统一收口
"""

BLUR_LEVELS = {"无": 0, "一点点": 1, "中度": 2, "重度": 3}

# ─── Light ─────────────────────────────────────────────────────────
LIGHT_THEME = {
    "name":           "light",
    "window_bg":      "#EDEEF4",
    "card_no_img":    "rgba(255,255,255,0.92)",
    "card_img":       "rgba(255,255,255,0.18)",
    "tp":             "#0D0D1A",
    "ts":             "#454560",
    "tm":             "#7070A0",
    "accent":         "#F97316",
    "accent_h":       "#EA580C",
    "accent_p":       "#C2410C",
    "tab_act_bg":     "#F97316",
    "tab_act_txt":    "#FFFFFF",
    "tab_inact":      "#6B7280",
    "toggle_light_bg":  "#F97316",
    "toggle_light_txt": "#FFFFFF",
    "toggle_dark_bg":   "transparent",
    "toggle_dark_txt":  "#6B7280",
    "toggle_dark_border": "rgba(0,0,0,0.18)",
    "cb":             "rgba(0,0,0,0.14)",
    "cf":             "#F97316",
    "hb":             "#F97316",
    "btn_subtle":     "rgba(249,115,22,0.05)",
    "btn_hover":      "rgba(249,115,22,0.09)",
    "btn_pressed":    "rgba(249,115,22,0.17)",
    "list_h":         "rgba(0,0,0,0.04)",
    "list_sel":       "rgba(249,115,22,0.13)",
    "divider":        "rgba(0,0,0,0.08)",
    "prog_bg":        "rgba(0,0,0,0.07)",
    "error":          "#DC2626",
    "scroll":         "rgba(0,0,0,0.13)",
    "scroll_h":       "rgba(0,0,0,0.26)",
    "status_bg":      "rgba(237,238,244,0.88)",
    "pop_bg":         "#FFFFFF",
    "pop_txt":        "#1A1A2E",
    "pop_sel":        "rgba(249,115,22,0.13)",
}

# ─── Dark ──────────────────────────────────────────────────────────
DARK_THEME = {
    "name":           "dark",
    "window_bg":      "#0E0E1C",
    "card_no_img":    "rgba(255,255,255,0.055)",
    "card_img":       "rgba(0,0,0,0.28)",
    "tp":             "#E6E6F5",
    "ts":             "#9898BC",
    "tm":             "#7070A0",
    "accent":         "#06B6D4",
    "accent_h":       "#0891B2",
    "accent_p":       "#0E7490",
    "tab_act_bg":     "#06B6D4",
    "tab_act_txt":    "#FFFFFF",
    "tab_inact":      "#9CA3AF",
    "toggle_light_bg":   "transparent",
    "toggle_light_txt":  "#9CA3AF",
    "toggle_dark_bg":    "#06B6D4",
    "toggle_dark_txt":   "#FFFFFF",
    "toggle_dark_border":"rgba(255,255,255,0.14)",
    "cb":             "rgba(255,255,255,0.12)",
    "cf":             "#06B6D4",
    "hb":             "#06B6D4",
    "btn_subtle":     "rgba(6,182,212,0.06)",
    "btn_hover":      "rgba(6,182,212,0.13)",
    "btn_pressed":    "rgba(6,182,212,0.22)",
    "list_h":         "rgba(255,255,255,0.055)",
    "list_sel":       "rgba(6,182,212,0.20)",
    "divider":        "rgba(255,255,255,0.07)",
    "prog_bg":        "rgba(255,255,255,0.08)",
    "error":          "#F87171",
    "scroll":         "rgba(255,255,255,0.11)",
    "scroll_h":       "rgba(255,255,255,0.26)",
    "status_bg":      "rgba(14,14,28,0.88)",
    "pop_bg":         "#18182C",
    "pop_txt":        "#DDDDF2",
    "pop_sel":        "rgba(6,182,212,0.20)",
}


def _hex_rgb(h: str):
    h = h.lstrip("#")
    return int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)

def _rgba(r, g, b, a):
    return f"rgba({r},{g},{b},{a})"

def _rgb_to_hsv(r, g, b):
    """RGB (0-255) → HSV (0-1, 0-1, 0-1)"""
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    v = mx
    s = 0.0 if mx == 0 else (mx - mn) / mx
    if mx == mn:
        h = 0.0
    elif mx == r:
        h = (g - b) / (mx - mn) % 6
    elif mx == g:
        h = (b - r) / (mx - mn) + 2
    else:
        h = (r - g) / (mx - mn) + 4
    return h / 6.0, s, v

def _hsv_to_rgb(h, s, v):
    """HSV (0-1) → RGB (0-255)"""
    import math
    h = h % 1.0
    if s == 0:
        c = int(v * 255)
        return c, c, c
    i = int(h * 6)
    f = h * 6 - i
    p, q, t_ = v*(1-s), v*(1-s*f), v*(1-s*(1-f))
    seg = i % 6
    if seg == 0: r, g, b = v, t_, p
    elif seg == 1: r, g, b = q, v, p
    elif seg == 2: r, g, b = p, v, t_
    elif seg == 3: r, g, b = p, q, v
    elif seg == 4: r, g, b = t_, p, v
    else:          r, g, b = v, p, q
    return int(r*255), int(g*255), int(b*255)

def _vivid_text_color(avg_hue: float, theme_name: str) -> tuple:
    """
    根据背景平均色调的色相（0-1），生成高对比度的字色，避免与主题色相撞或看不清。

    亮色模式：
      色相偏移 +30° 避免与背景色直接相撞，同时降低饱和度，亮度不至于刺眼
      S=0.85, V=0.45

    暗色模式：
      色相偏移 +30°，提高亮度和可见度。
      S=0.55，V=0.95
    """
    if theme_name == "dark":
        shifted_hue = (avg_hue + 0.083) % 1.0
        r, g, b = _hsv_to_rgb(shifted_hue, 0.55, 0.95)
        luma = (r * 299 + g * 587 + b * 114) // 1000
        if luma < 120:
            r, g, b = _hsv_to_rgb(shifted_hue, 0.35, 1.0)
    else:
        shifted_hue = (avg_hue + 0.083) % 1.0
        r, g, b = _hsv_to_rgb(shifted_hue, 0.85, 0.45)
    return r, g, b, f"#{r:02X}{g:02X}{b:02X}"


def _apply_bg(t: dict, theme_name: str, bg: dict) -> dict:
    if not bg: return t
    o  = dict(t)
    ac = bg.get("accent_hex", "")
    dk = bg.get("is_dark",    False)

    # ── 从背景平均色调生成鲜艳字色 ────────────────────────────────────
    avg_hue = bg.get("avg_hue", -1.0)   # analyze_image_colors 返回的平均色相 0-1，无色时 -1

    if avg_hue >= 0:
        # 有明显颜色：用色相直接生成高饱和字色
        r2, g2, b2, tp_hex = _vivid_text_color(avg_hue, theme_name)
    else:
        # 无色（纯黑白灰图）：退回到互补色压暗/提亮方案
        c = bg.get("complement_hex", "")
        if c:
            r2, g2, b2 = _hex_rgb(c)
            bright = (r2*299 + g2*587 + b2*114) / 1000
            if theme_name == "dark":
                if bright < 160:
                    factor = min(2.2, 210 / max(bright, 1))
                    r2 = min(255, int(r2 * factor))
                    g2 = min(255, int(g2 * factor))
                    b2 = min(255, int(b2 * factor))
            else:
                if bright > 130:
                    factor = max(0.45, 110 / max(bright, 1))
                    r2 = max(0, int(r2 * factor))
                    g2 = max(0, int(g2 * factor))
                    b2 = max(0, int(b2 * factor))
            tp_hex = f"#{r2:02X}{g2:02X}{b2:02X}"
        else:
            # 完全没有颜色信息，不改变主题色
            o["card"] = o["card_img"]
            return o

    # ── 应用字色 ─────────────────────────────────────────────────────
    o["tp"]         = tp_hex
    o["ts"]         = _rgba(r2, g2, b2, 0.72)
    o["tm"]         = _rgba(r2, g2, b2, 0.50)
    o["tab_inact"]  = _rgba(r2, g2, b2, 0.65)
    o["cb"]         = _rgba(r2, g2, b2, 0.22)
    o["hb"]         = tp_hex
    o["divider"]    = _rgba(r2, g2, b2, 0.14)
    o["scroll"]     = _rgba(r2, g2, b2, 0.18)
    o["scroll_h"]   = _rgba(r2, g2, b2, 0.38)
    o["btn_subtle"] = _rgba(r2, g2, b2, 0.07)
    o["btn_hover"]  = _rgba(r2, g2, b2, 0.15)
    o["btn_pressed"]= _rgba(r2, g2, b2, 0.24)
    o["pop_bg"]     = "#0A0A18" if dk else "#FFFFFF"
    o["pop_txt"]    = tp_hex

    # ── accent 色：与字色保持足够色相差 ─────────────────────────────
    if ac:
        ar, ag, ab_ = _hex_rgb(ac)
    elif avg_hue >= 0:
        # 暗色：字色已偏移+30°，accent 用互补色（+180°），确保三者（背景/字/accent）各异
        # 亮色：字色未偏移，accent 用互补色
        if theme_name == "dark":
            acc_hue = (avg_hue + 0.5) % 1.0   # 与字色相差 ~150°，视觉区分强
            ar, ag, ab_ = _hsv_to_rgb(acc_hue, 0.80, 1.0)
        else:
            acc_hue = (avg_hue + 0.5) % 1.0
            ar, ag, ab_ = _hsv_to_rgb(acc_hue, 0.85, 0.80)
        ac = f"#{ar:02X}{ag:02X}{ab_:02X}"
    else:
        ar, ag, ab_ = _hex_rgb(t["accent"])

    o["accent"]     = ac
    o["accent_h"]   = ac
    o["tab_act_bg"] = ac
    o["cf"]         = ac
    o["list_sel"]   = _rgba(ar, ag, ab_, 0.20)
    o["pop_sel"]    = _rgba(ar, ag, ab_, 0.20)

    if theme_name == "light":
        o["toggle_light_bg"]    = ac
        o["toggle_light_txt"]   = "#FFFFFF"
        o["toggle_dark_bg"]     = "transparent"
        o["toggle_dark_txt"]    = o["ts"]
        o["toggle_dark_border"] = o["cb"]
    else:
        o["toggle_light_bg"]    = "transparent"
        o["toggle_light_txt"]   = o["ts"]
        o["toggle_dark_bg"]     = ac
        o["toggle_dark_txt"]    = "#FFFFFF"
        o["toggle_dark_border"] = o["cb"]

    o["card"] = o["card_img"]
    return o


def build_stylesheet(theme: dict,
                     theme_name: str = "light",
                     has_bg: bool = False,
                     bg_colors: dict = None) -> str:
    if bg_colors is None:
        bg_colors = {}

    t       = _apply_bg(theme, theme_name, bg_colors) if has_bg else theme
    card_bg = t.get("card", t["card_img"]) if has_bg else t["card_no_img"]

    a   = t["accent"];   ah  = t["accent_h"];  ap  = t["accent_p"]
    tp  = t["tp"];       ts  = t["ts"];         tm  = t["tm"]
    cb  = t["cb"];       cf  = t["cf"];         hb  = t["hb"]
    bs  = t["btn_subtle"]; bh = t["btn_hover"]; bp  = t["btn_pressed"]
    tl_bg  = t["toggle_light_bg"];  tl_txt = t["toggle_light_txt"]
    td_bg  = t["toggle_dark_bg"];   td_txt = t["toggle_dark_txt"]
    t_bdr  = t.get("toggle_dark_border", cb)

    return f"""
/* ══ Window ══════════════════════════════════════════════════════ */
QMainWindow {{ background-color: {t["window_bg"]}; }}
QMainWindow > QWidget {{ background-color: {t["window_bg"]}; }}
QWidget {{ color:{tp}; font-family:"Microsoft YaHei UI","Microsoft YaHei",
           "PingFang SC","Segoe UI",sans-serif;
           font-size:13px; font-weight:500; background:transparent; }}

/* ══ Tab bar ══════════════════════════════════════════════════════ */
QTabWidget       {{ background:transparent; }}
QTabWidget::pane {{ border:none; background:transparent; padding-top:4px; }}
QTabBar          {{ background:transparent; qproperty-drawBase:0; }}
QTabBar::tab {{
    background:transparent; color:{t["tab_inact"]};
    padding:8px 20px; margin:4px 2px;
    border-radius:8px; font-weight:500; font-size:13px;
    min-width:68px; min-height:22px; border:1px solid transparent;
}}
QTabBar::tab:selected {{
    background:{t["tab_act_bg"]}; color:{t["tab_act_txt"]};
    font-weight:600; border:none;
}}
QTabBar::tab:hover:!selected {{ border:1px solid {hb}; color:{tp}; }}

/* ══ Cards ════════════════════════════════════════════════════════ */
QFrame#card {{
    background:{card_bg}; border:1px solid {cb}; border-radius:12px;
}}

/* ══ Scroll Area ══════════════════════════════════════════════════ */
QScrollArea {{ background:transparent; border:none; }}
QScrollArea > QWidget > QWidget {{ background:transparent; }}

/* ══ Buttons ══════════════════════════════════════════════════════ */
QPushButton {{
    background:{bs}; color:{tp}; border:1px solid {cb};
    border-radius:7px; padding:4px 14px;
    font-size:13px; font-weight:500;
    min-height:32px; min-width:72px;
}}
QPushButton:hover   {{ background:{bh}; border:1.5px solid {hb}; color:{a}; }}
QPushButton:pressed {{ background:{bp}; border:1.5px solid {a};  color:{a}; }}
QPushButton:disabled {{ background:transparent; color:{tm}; border:1px solid {cb}; }}

/* Primary */
QPushButton#primary {{
    background:{a}; color:#FFFFFF; border:none;
    font-weight:600; min-height:34px; min-width:110px; padding:6px 18px;
}}
QPushButton#primary:hover   {{ background:{ah}; }}
QPushButton#primary:pressed {{ background:{ap}; }}
QPushButton#primary:disabled {{ background:{t["prog_bg"]}; color:{tm}; border:none; }}

/* Danger */
QPushButton#danger {{
    background:transparent; color:{t["error"]};
    border:1px solid {t["error"]}; min-width:60px; min-height:32px;
}}
QPushButton#danger:hover    {{ background:{t["error"]}; color:#FFFFFF; }}
QPushButton#danger:disabled {{ color:{tm}; border-color:{cb}; }}

/* ── 主题切换 ── */
QPushButton#toggle_light {{
    background:{tl_bg}; color:{tl_txt}; border:1px solid {t_bdr};
    border-radius:7px; font-weight:{"600" if tl_bg!="transparent" else "500"};
    min-width:96px; min-height:32px;
}}
QPushButton#toggle_light:hover {{ border-color:{hb}; color:{a if tl_bg=="transparent" else tl_txt}; }}
QPushButton#toggle_dark {{
    background:{td_bg}; color:{td_txt}; border:1px solid {t_bdr};
    border-radius:7px; font-weight:{"600" if td_bg!="transparent" else "500"};
    min-width:96px; min-height:32px;
}}
QPushButton#toggle_dark:hover  {{ border-color:{hb}; color:{a if td_bg=="transparent" else td_txt}; }}

/* ── GPU 厂商按钮（4 态 × 4 厂商）────────────────────────────── */
/* NVIDIA  inactive */
QPushButton[objectName="vendor_btn_nvidia"] {{
    background:transparent; color:{ts}; border:1px solid {cb};
    border-radius:8px; min-height:36px; font-weight:500;
}}
QPushButton[objectName="vendor_btn_nvidia"]:hover {{
    border-color:#76b900; color:#76b900;
}}
/* NVIDIA  active */
QPushButton[objectName="vendor_btn_nvidia_active"] {{
    background:#76b900; color:#FFFFFF; border:none;
    border-radius:8px; min-height:36px; font-weight:700;
}}
QPushButton[objectName="vendor_btn_nvidia_active"]:hover {{ background:#68a300; }}

/* AMD  inactive */
QPushButton[objectName="vendor_btn_amd"] {{
    background:transparent; color:{ts}; border:1px solid {cb};
    border-radius:8px; min-height:36px; font-weight:500;
}}
QPushButton[objectName="vendor_btn_amd"]:hover {{ border-color:#ed1c24; color:#ed1c24; }}
/* AMD  active */
QPushButton[objectName="vendor_btn_amd_active"] {{
    background:#ed1c24; color:#FFFFFF; border:none;
    border-radius:8px; min-height:36px; font-weight:700;
}}
QPushButton[objectName="vendor_btn_amd_active"]:hover {{ background:#d01820; }}

/* Intel  inactive */
QPushButton[objectName="vendor_btn_intel"] {{
    background:transparent; color:{ts}; border:1px solid {cb};
    border-radius:8px; min-height:36px; font-weight:500;
}}
QPushButton[objectName="vendor_btn_intel"]:hover {{ border-color:#0071c5; color:#0071c5; }}
/* Intel  active */
QPushButton[objectName="vendor_btn_intel_active"] {{
    background:#0071c5; color:#FFFFFF; border:none;
    border-radius:8px; min-height:36px; font-weight:700;
}}
QPushButton[objectName="vendor_btn_intel_active"]:hover {{ background:#005fa3; }}

/* None  inactive */
QPushButton[objectName="vendor_btn_none"] {{
    background:transparent; color:{ts}; border:1px solid {cb};
    border-radius:8px; min-height:36px; font-weight:500;
}}
QPushButton[objectName="vendor_btn_none"]:hover {{ border-color:{hb}; color:{a}; }}
/* None  active */
QPushButton[objectName="vendor_btn_none_active"] {{
    background:{t["prog_bg"]}; color:{tp}; border:1px solid {cb};
    border-radius:8px; min-height:36px; font-weight:700;
}}
QPushButton[objectName="vendor_btn_none_active"]:hover {{ border-color:{hb}; }}

/* ══ Inputs ═══════════════════════════════════════════════════════ */
QLineEdit {{
    background:transparent; color:{tp}; border:1.5px solid {cb};
    border-radius:7px; padding:5px 10px;
    font-size:13px; font-weight:500; min-height:32px;
    selection-background-color:{a}; selection-color:#FFFFFF;
}}
QLineEdit:focus     {{ border-color:{cf}; }}
QLineEdit:read-only {{ color:{ts}; }}
QLineEdit:disabled  {{ color:{tm}; border-color:{cb}; }}

QTextEdit {{
    background:transparent; color:{tp}; border:1px solid {cb};
    border-radius:8px; padding:6px 8px;
    font-size:12px; font-weight:500;
    font-family:"Consolas","Cascadia Code","Courier New",monospace;
    min-height:60px;
    selection-background-color:{a}; selection-color:#FFFFFF;
}}
QTextEdit:focus   {{ border-color:{cf}; }}
QTextEdit:disabled {{ color:{tm}; }}

QComboBox {{
    background:{bs}; color:{tp}; border:1.5px solid {cb};
    border-radius:7px; padding:5px 10px;
    font-size:13px; font-weight:500; min-height:32px; min-width:110px;
}}
QComboBox:focus, QComboBox:on {{ border-color:{cf}; }}
QComboBox:disabled {{ color:{tm}; }}
QComboBox::drop-down {{ border:none; width:26px; }}
QComboBox::down-arrow {{
    width:0; height:0;
    border-left:4px solid transparent; border-right:4px solid transparent;
    border-top:5px solid {ts}; margin-right:8px;
}}
QComboBox QAbstractItemView {{
    background:{t["pop_bg"]}; color:{t["pop_txt"]};
    border:1px solid {cb}; border-radius:8px; padding:4px;
    outline:none; selection-background-color:{t["pop_sel"]}; selection-color:{a};
}}

/* ══ List ═════════════════════════════════════════════════════════ */
QListWidget {{
    background:transparent; color:{tp}; border:1.5px solid {cb};
    border-radius:10px; padding:4px; outline:none;
    font-size:12px; font-weight:500; min-height:60px;
}}
QListWidget::item {{
    padding:6px 10px; border-radius:6px; margin:1px 2px;
    background:transparent; min-height:20px;
}}
QListWidget::item:hover    {{ background:{t["list_h"]}; }}
QListWidget::item:selected {{ background:{t["list_sel"]}; color:{a}; }}

/* ══ Progress ═════════════════════════════════════════════════════ */
QProgressBar {{
    background:{t["prog_bg"]}; border:none; border-radius:6px;
    min-height:10px; max-height:12px;
    text-align:center; font-size:11px; font-weight:600; color:transparent;
}}
QProgressBar::chunk {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {a}, stop:0.5 {ah}, stop:1 {a});
    border-radius:6px;
}}

/* ══ Labels ═══════════════════════════════════════════════════════ */
QLabel                 {{ color:{tp}; background:transparent; font-weight:500; }}
QLabel#section_title   {{ font-size:11px; font-weight:600; color:{ts};
                          letter-spacing:0.4px; background:transparent; }}
QLabel#row_label       {{ font-size:12px; font-weight:600; color:{ts};
                          background:transparent; }}
QLabel#card_title      {{ font-size:14px; font-weight:700; color:{tp};
                          background:transparent; }}

/* ══ Scroll bars ══════════════════════════════════════════════════ */
QScrollBar:vertical   {{ background:transparent; width:7px; margin:2px 0; }}
QScrollBar::handle:vertical {{
    background:{t["scroll"]}; border-radius:3px; min-height:24px;
}}
QScrollBar::handle:vertical:hover {{ background:{t["scroll_h"]}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QScrollBar::add-page:vertical,  QScrollBar::sub-page:vertical {{ background:transparent; }}
QScrollBar:horizontal {{ background:transparent; height:7px; margin:0 2px; }}
QScrollBar::handle:horizontal {{
    background:{t["scroll"]}; border-radius:3px; min-width:24px;
}}
QScrollBar::handle:horizontal:hover {{ background:{t["scroll_h"]}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background:transparent; }}

/* ══ Status bar ═══════════════════════════════════════════════════ */
QStatusBar {{
    background:{t["status_bg"]}; color:{ts};
    border-top:1px solid {t["divider"]};
    font-size:12px; font-weight:500; padding:3px 14px;
}}

/* ══ Dividers ═════════════════════════════════════════════════════ */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color:{t["divider"]}; background:{t["divider"]};
    border:none; max-height:1px;
}}

/* ══ Tooltip / MessageBox ════════════════════════════════════════ */
QToolTip {{
    background:{t["pop_bg"]}; color:{t["pop_txt"]};
    border:1px solid {cb}; border-radius:6px;
    padding:5px 9px; font-size:12px;
}}
QMessageBox        {{ background:{t["pop_bg"]}; }}
QMessageBox QLabel {{ color:{t["pop_txt"]}; }}
"""