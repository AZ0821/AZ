"""操作录制器：捕获浏览器操作并生成中文脚本。

原理：
  1. 启动可见 Chromium，注入事件钩子脚本
  2. 用户操作时，DOM 事件回调 `window.__hanui_describe` 生成选择器
  3. 通过 Playwright binding 把事件推到 Python
  4. Python 把事件翻译成中文命令（去重/合并）
  5. 停止后输出完整 .hrpa 脚本文本
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from .selectors import SELECTOR_SCRIPT

# 录制事件回调：注入页面的 JS 通过它把动作推给 Python
_RECORDER_HOOK = r"""
(() => {
  if (window.__hanui_recorder_installed) return;
  window.__hanui_recorder_installed = true;

  function describe(el) {
    return (window.__hanui_describe && window.__hanui_describe(el)) || { kind: 'css', sel: 'body', tag: 'body', text: '' };
  }

  function val(el) {
    if (!el) return '';
    if (el.tagName === 'SELECT') {
      const opt = el.options[el.selectedIndex];
      return opt ? (opt.text || opt.value).trim() : '';
    }
    return (el.value != null ? String(el.value) : (el.textContent || '')).trim();
  }

  function fire(type, payload) {
    try {
      window.__hanui_record(type, payload);
    } catch (e) { /* binding 尚未就绪 */ }
  }

  // ---- 点击 ----
  document.addEventListener('click', (e) => {
    const el = e.target instanceof Element ? e.target.closest('a,button,input[type=submit],input[type=button],[role=button],label,select,option,summary,details') || e.target : e.target;
    fire('click', Object.assign(describe(el), { value: val(el) }));
  }, true);

  document.addEventListener('dblclick', (e) => {
    const el = e.target instanceof Element ? e.target : e.target;
    fire('dblclick', Object.assign(describe(el), {}));
  }, true);

  document.addEventListener('contextmenu', (e) => {
    const el = e.target instanceof Element ? e.target : e.target;
    fire('contextmenu', Object.assign(describe(el), {}));
  }, true);

  // ---- 输入（合并为一条「输入」） ----
  document.addEventListener('input', (e) => {
    const el = e.target;
    if (!el || !(el instanceof Element)) return;
    const tag = el.tagName.toLowerCase();
    if (tag !== 'input' && tag !== 'textarea') return;
    const type = (el.type || '').toLowerCase();
    if (type === 'checkbox' || type === 'radio' || type === 'file') return;
    fire('input', Object.assign(describe(el), { value: val(el) }));
  }, true);

  // ---- 下拉框 ----
  document.addEventListener('change', (e) => {
    const el = e.target;
    if (!el || !(el instanceof Element)) return;
    const tag = el.tagName.toLowerCase();
    if (tag === 'select') {
      fire('select', Object.assign(describe(el), { value: val(el) }));
    }
    if (tag === 'input') {
      const type = (el.type || '').toLowerCase();
      if (type === 'checkbox' || type === 'radio') {
        fire('check', Object.assign(describe(el), { value: String(!!el.checked) }));
      }
      if (type === 'file') {
        const files = el.files ? el.files.length : 0;
        fire('file', Object.assign(describe(el), { value: String(files) }));
      }
    }
  }, true);

  // ---- 表单提交 ----
  document.addEventListener('submit', (e) => {
    fire('submit', { value: '' });
  }, true);
})();
"""


@dataclass
class RecordedCommand:
    """一条录制出来的中文命令。"""

    text: str
    kind: str = ""
    selector: str = ""
    line_hint: int = 0


@dataclass
class Recorder:
    """浏览器操作录制器。"""

    on_command: Callable[[str], None] | None = None
    on_log: Callable[[str], None] | None = None

    commands: list[RecordedCommand] = field(default_factory=list)
    _playwright: Playwright | None = field(default=None, repr=False)
    _browser: Browser | None = field(default=None, repr=False)
    _context: BrowserContext | None = field(default=None, repr=False)
    _page: Page | None = field(default=None, repr=False)
    _running: bool = field(default=False, repr=False)
    _last_input_sel: str = field(default="", repr=False)
    _last_open_url: str = field(default="", repr=False)
    _last_was_click: bool = field(default=False, repr=False)
    _pending_nav: str = field(default="", repr=False)

    # ------------------------------------------------------------------
    def start(self, url: str | None = None, slow_mo: int = 0) -> None:
        """启动浏览器并开始录制。"""
        if self._running:
            raise RuntimeError("录制已在进行中")
        self._playwright = sync_playwright().start()
        # 优先系统 Edge/Chrome，回退内置 Chromium
        self._browser = None
        for ch in ("msedge", "chrome", None):
            try:
                kw = dict(headless=False, slow_mo=slow_mo)
                if ch:
                    kw["channel"] = ch
                self._browser = self._playwright.chromium.launch(**kw)
                break
            except Exception:
                continue
        if self._browser is None:
            raise RuntimeError("无法启动浏览器（已尝试 Edge/Chrome/Chromium）")
        self._context = self._browser.new_context(ignore_https_errors=True)
        self._context.add_init_script(SELECTOR_SCRIPT)
        self._context.add_init_script(_RECORDER_HOOK)
        self._running = True

        # 新标签页（popup）也要挂钩
        self._context.on("page", self._attach_page)

        self._page = self._context.new_page()
        self._attach_page(self._page)

        if url:
            full = url if "://" in url else "https://" + url
            self._log(f"打开起始页 {full}")
            # 先标记再导航，避免 _on_navigate 重复记录
            self._last_open_url = full.rstrip("/")
            self._emit(f'打开 {full}', kind="open", selector="")
            self._page.goto(full, wait_until="domcontentloaded")

    def _attach_page(self, page: Page) -> None:
        """给每个页面绑定录制回调与导航监听。"""
        try:
            page.expose_binding("__hanui_record", self._on_dom_event)
        except Exception:
            pass  # 同一 page 重复绑定时忽略
        page.on("framenavigated", self._on_navigate)

    def stop(self) -> str:
        """停止录制，返回生成的中文脚本文本。"""
        self._running = False
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        finally:
            if self._playwright:
                self._playwright.stop()
            self._playwright = self._browser = self._context = self._page = None

        script = self.to_script()
        self._log(f"录制结束，共 {len(self.commands)} 条命令")
        return script

    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    def _log(self, msg: str) -> None:
        if self.on_log:
            self.on_log(msg)

    def _emit(self, text: str, kind: str = "", selector: str = "") -> None:
        """追加一条命令并去抖。"""
        text = text.strip()
        if not text:
            return
        # 合并连续「输入」到同一选择器
        if kind == "input" and selector and self.commands:
            last = self.commands[-1]
            if last.kind == "input" and last.selector == selector:
                last.text = text
                if self.on_command:
                    self.on_command(f"↑更新 {text}")
                return
        cmd = RecordedCommand(text=text, kind=kind, selector=selector)
        self.commands.append(cmd)
        if self.on_command:
            self.on_command(text)

    def _fmt_selector(self, desc: dict[str, Any]) -> str:
        """把 describe 结果转成脚本里的目标字符串。"""
        kind = desc.get("kind", "css")
        value = str(desc.get("sel", "")).strip()
        if not value:
            return "body"
        if kind == "text":
            # 用 文本= 前缀，脚本更可读
            return f"文本={value}"
        # CSS：加引号
        return f'"{value}"'

    # ------------------------------------------------------------------
    # DOM 事件入口（由页面里的 __hanui_record 调用）
    def _on_dom_event(self, source: Any, event_type: str, payload: dict[str, Any]) -> None:
        if not self._running:
            return
        # 只录制主框架（忽略 iframe 里的，避免重复）
        try:
            frame = source.get("frame") if isinstance(source, dict) else None
            if frame is not None and frame != frame.page.main_frame:
                return
        except Exception:
            pass

        sel = self._fmt_selector(payload)
        value = str(payload.get("value", "") or "")
        tag = str(payload.get("tag", ""))

        self._last_was_click = False

        if event_type == "click":
            # 复选框 / 单选框
            if tag == "input" and value in ("true", "false"):
                self._emit(f"点击 {sel}", kind="click", selector=sel)
            else:
                self._emit(f"点击 {sel}", kind="click", selector=sel)
            self._last_was_click = True

        elif event_type == "dblclick":
            self._emit(f"双击 {sel}", kind="dblclick", selector=sel)
            self._last_was_click = True

        elif event_type == "contextmenu":
            self._emit(f"右击 {sel}", kind="rclick", selector=sel)
            self._last_was_click = True

        elif event_type == "input":
            # 输入框：值为空则清空
            if value == "":
                self._emit(f"清空 {sel}", kind="input", selector=sel)
            else:
                self._emit(f'输入 {sel} 为 "{value}"', kind="input", selector=sel)
            self._last_input_sel = sel

        elif event_type == "select":
            self._emit(f'选择 {sel} 选中 "{value}"', kind="select", selector=sel)

        elif event_type == "check":
            state = "选中" if value == "true" else "取消选中"
            self._emit(f"点击 {sel}  # {state}", kind="click", selector=sel)

        elif event_type == "file":
            self._emit(f"上传 {sel} 文件 \"<请选择文件>\"", kind="upload", selector=sel)

        elif event_type == "submit":
            # 表单提交：若前一步已经是点击提交按钮，则跳过
            if self._last_was_click:
                return
            self._emit("执行脚本 \"document.forms[0].submit()\"", kind="submit")

    # ------------------------------------------------------------------
    def _on_navigate(self, frame: Any) -> None:
        """主导航事件 → 记录「打开」（点击引发的导航不重复记录）。"""
        if not self._running:
            return
        try:
            if frame.parent_frame is not None:
                return  # 忽略 iframe
            url = frame.url
        except Exception:
            return
        if not url or url == "about:blank":
            return
        # 点击/输入引发的导航不再插一条「打开」
        if self._last_was_click:
            self._last_was_click = False
            return
        # 同一 URL 不重复（忽略末尾斜杠差异）
        norm = url.rstrip("/")
        if getattr(self, "_last_open_url", "") == norm:
            return
        self._emit(f"打开 {url}", kind="open", selector="")
        self._last_open_url = norm

    # ------------------------------------------------------------------
    def to_script(self, header: bool = True) -> str:
        """把录制结果渲染为 .hrpa 脚本文本。"""
        lines: list[str] = []
        if header:
            lines.append("# 由汉UI 录制器自动生成")
            lines.append("# 检查目标选择器后可手动调整")
            lines.append("")
        for cmd in self.commands:
            lines.append(cmd.text)
        return "\n".join(lines).rstrip() + "\n"
