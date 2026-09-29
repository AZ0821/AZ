"""Playwright 浏览器封装。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from .context import RunContext

# 常见 HTML 标签名：裸写时按 CSS 标签选择器处理
_HTML_TAGS = {
    "html", "head", "body", "div", "span", "p", "a", "img", "ul", "ol", "li",
    "table", "tr", "td", "th", "thead", "tbody", "form", "input", "button",
    "select", "option", "textarea", "label", "h1", "h2", "h3", "h4", "h5", "h6",
    "header", "footer", "nav", "main", "section", "article", "aside", "iframe",
    "video", "audio", "canvas", "svg", "br", "hr", "strong", "em", "code",
    "pre", "blockquote", "dl", "dt", "dd", "figure", "figcaption", "details",
    "summary", "dialog", "menu", "menuitem", "object", "embed", "source",
    "track", "map", "area", "picture", "caption", "col", "colgroup", "fieldset",
    "legend", "meter", "output", "progress", "datalist", "optgroup", "template",
    "slot", "shadow", "time", "mark", "small", "sub", "sup", "b", "i", "u",
    "s", "strike", "font", "center", "big", "tt", "abbr", "address", "cite",
    "dfn", "kbd", "samp", "var", "wbr", "noscript",
}


class BrowserSession:
    """管理一次脚本执行期间的浏览器生命周期。"""

    def __init__(self, ctx: RunContext):
        self.ctx = ctx
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> Page:
        self._pw = sync_playwright().start()
        self._browser = self._launch_browser()
        self._context = self._browser.new_context(ignore_https_errors=True)
        self._page = self._context.new_page()
        self._page.set_default_timeout(30_000)
        return self._page

    def _launch_browser(self):
        """优先用系统 Edge/Chrome，回退 Playwright 内置 Chromium。

        这样打包后的 exe 不必内置浏览器内核（省 ~150MB）。
        """
        launch_kw = dict(
            headless=self.ctx.headless,
            slow_mo=self.ctx.slow_mo or 0,
        )
        # 已指定 channel 时直接用
        channel = getattr(self.ctx, "browser_channel", None)
        if channel:
            try:
                return self._pw.chromium.launch(channel=channel, **launch_kw)
            except Exception:
                pass
        # 自动探测系统浏览器
        for ch in ("msedge", "chrome"):
            try:
                return self._pw.chromium.launch(channel=ch, **launch_kw)
            except Exception:
                continue
        # 回退：Playwright 内置 Chromium
        return self._pw.chromium.launch(**launch_kw)

    def stop(self) -> None:
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()
            self._page = None
            self._context = None
            self._browser = None
            self._pw = None

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("浏览器尚未启动")
        return self._page

    # -- helpers -----------------------------------------------------------

    def resolve_locator(self, target: str):
        """把中文脚本里的目标解析为 Playwright Locator。

        支持：
          - 显式前缀：css=... / text=... / xpath=... / 文本=... / id=... / name=...
          - XPath：以 / 或 (// 开头
          - CSS 选择器：含 CSS 元字符（#.[]:()"'@=~）或 HTML 标签名（div/h1/input…）
          - 文本定位：含中文字符，或不含 CSS 元字符的普通短语（登录 / Submit）
        """
        target = self.ctx.interpolate(target)
        t = target.strip()

        # 显式前缀
        for prefix, kind in (
            ("文本=", "text"),
            ("text=", "text"),
            ("css=", "css"),
            ("xpath=", "xpath"),
            ("id=", "id"),
            ("name=", "name"),
        ):
            if t.startswith(prefix):
                val = t[len(prefix) :]
                if kind == "text":
                    return self.page.get_by_text(val, exact=False)
                if kind == "xpath":
                    return self.page.locator(f"xpath={val}")
                if kind == "id":
                    return self.page.locator(f"#{val}")
                if kind == "name":
                    return self.page.locator(f"[name={val!r}]")
                return self.page.locator(val)

        # XPath
        if t.startswith("/") or t.startswith("(//"):
            return self.page.locator(f"xpath={t}")

        # 含 CSS 元字符 → CSS
        css_chars = set("#.[]:()\"'@=~+>")
        if any(ch in css_chars for ch in t):
            return self.page.locator(t)

        # 纯英文 HTML 标签名 → CSS（h1 / div / input / button …）
        if t.lower() in _HTML_TAGS:
            return self.page.locator(t)

        # 含中文字符或普通短语 → 文本定位
        return self.page.get_by_text(t, exact=False)

    def screenshot(self, filename: str) -> Path:
        path = Path(filename)
        if not path.is_absolute():
            base = self.ctx.screenshot_dir or self.ctx.workdir
            path = base / path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(path), full_page=True)
        return path

    def wait_for_timeout(self, ms: int) -> None:
        self.page.wait_for_timeout(ms)
