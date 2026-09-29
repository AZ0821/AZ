"""AST 执行器：把中文命令翻译为浏览器动作。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..dsl.ast_nodes import Command, Condition, IfBlock, WhileBlock, RepeatBlock, Script, Node
from .browser import BrowserSession
from .context import RunContext


class ExecutionError(Exception):
    def __init__(self, message: str, command: Command | None = None):
        self.command = command
        loc = f"第 {command.line} 行" if command else ""
        super().__init__(f"{loc}执行失败: {message}" if loc else message)


class Executor:
    def __init__(self, ctx: RunContext | None = None):
        self.ctx = ctx or RunContext()
        self.session: BrowserSession | None = None

    def run(self, script: Script) -> None:
        self.ctx.log(f"开始执行 {script.source_name}（{len(script)} 条命令）", "info")
        self.session = BrowserSession(self.ctx)
        try:
            self.session.start()
            self._exec_nodes(script.commands)
        finally:
            if self.session:
                self.session.stop()
            self.ctx.log("执行结束", "info")

    # ------------------------------------------------------------------

    def _exec_nodes(self, nodes: list[Node]) -> None:
        """按顺序执行一组节点（命令或块）。"""
        for node in nodes:
            self._exec_one(node)

    def _exec_one(self, node: Node) -> None:
        if isinstance(node, IfBlock):
            self._exec_if(node)
            return
        if isinstance(node, WhileBlock):
            self._exec_while(node)
            return
        if isinstance(node, RepeatBlock):
            self._exec_repeat(node)
            return
        # 普通命令
        cmd: Command = node
        handler = getattr(self, f"_do_{cmd.name}", None)
        if handler is None:
            raise ExecutionError(f"未实现的命令「{cmd.name}」", cmd)
        try:
            handler(cmd)
        except ExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ExecutionError(str(exc), cmd) from exc

    # -- 流程控制 -----------------------------------------------------

    def _exec_if(self, node: IfBlock) -> None:
        result = self._eval_condition(node.condition)
        self.ctx.log(f"如果 {node.condition.kind} → {'真' if result else '假'}", "info")
        if result:
            self._exec_nodes(node.then_body)
        else:
            self._exec_nodes(node.else_body)

    def _exec_while(self, node: WhileBlock) -> None:
        n = 0
        while self._eval_condition(node.condition):
            n += 1
            if n > node.max_iterations:
                raise ExecutionError(
                    f"「当」循环超过最大次数 {node.max_iterations}，已自动终止",
                    Command("当", line=node.line, raw=node.raw),
                )
            self.ctx.log(f"当 循环第 {n} 轮", "info")
            self._exec_nodes(node.body)
        self.ctx.log(f"当 循环结束（共 {n} 轮）", "info")

    def _exec_repeat(self, node: RepeatBlock) -> None:
        for i in range(1, node.count + 1):
            self.ctx.set_var(node.counter_var, i)
            self.ctx.set_var("i", i)
            self.ctx.log(f"重复 第 {i}/{node.count} 次", "info")
            self._exec_nodes(node.body)
        self.ctx.log(f"重复 结束（共 {node.count} 次）", "info")

    def _eval_condition(self, cond: Condition) -> bool:
        kind = cond.kind
        args = cond.args

        if kind == "always_true":
            return True
        if kind == "always_false":
            return False

        if kind == "page_contains":
            text = self.ctx.interpolate(str(args.get("text", "")))
            return text in self._need_page().content()
        if kind == "page_not_contains":
            text = self.ctx.interpolate(str(args.get("text", "")))
            return text not in self._need_page().content()

        if kind == "element_exists":
            target = self.ctx.interpolate(str(args.get("target", "")))
            return self.session.resolve_locator(target).count() > 0
        if kind == "element_not_exists":
            target = self.ctx.interpolate(str(args.get("target", "")))
            return self.session.resolve_locator(target).count() == 0

        if kind == "title_is":
            text = self.ctx.interpolate(str(args.get("text", "")))
            return self._need_page().title() == text
        if kind == "title_contains":
            text = self.ctx.interpolate(str(args.get("text", "")))
            return text in self._need_page().title()

        if kind == "url_contains":
            text = self.ctx.interpolate(str(args.get("text", "")))
            return text in self._need_page().url

        if kind in ("var_eq", "var_neq", "var_contains", "var_not_contains"):
            name = str(args.get("name", ""))
            expected = self.ctx.interpolate(str(args.get("value", "")))
            actual = str(self.ctx.get_var(name, ""))
            if kind == "var_eq":
                return actual == expected
            if kind == "var_neq":
                return actual != expected
            if kind == "var_contains":
                return expected in actual
            return expected not in actual

        raise ExecutionError(f"未实现的条件类型「{kind}」")

    def _need_page(self):
        if self.session is None:
            raise RuntimeError("浏览器未启动")
        return self.session.page

    def _t(self, key: str, cmd: Command) -> str:
        val = cmd.args.get(key, "")
        return self.ctx.interpolate(str(val))

    # -- 导航 ---------------------------------------------------------

    def _do_打开(self, cmd: Command) -> None:
        url = self._t("url", cmd)
        if not url.startswith(("http://", "https://", "file://", "about:")):
            url = "https://" + url
        self.ctx.log(f"打开 {url}", "info")
        self._need_page().goto(url, wait_until="domcontentloaded")

    def _do_关闭(self, cmd: Command) -> None:
        self.ctx.log("关闭浏览器", "info")
        if self.session:
            self.session.stop()
            self.session = None

    def _do_刷新(self, cmd: Command) -> None:
        self._need_page().reload(wait_until="domcontentloaded")

    def _do_后退(self, cmd: Command) -> None:
        self._need_page().go_back(wait_until="domcontentloaded")

    def _do_前进(self, cmd: Command) -> None:
        self._need_page().go_forward(wait_until="domcontentloaded")

    # -- 元素操作 -----------------------------------------------------

    def _do_点击(self, cmd: Command) -> None:
        target = self._t("target", cmd)
        self.ctx.log(f"点击 {target}", "info")
        self.session.resolve_locator(target).first.click()

    def _do_双击(self, cmd: Command) -> None:
        target = self._t("target", cmd)
        self.session.resolve_locator(target).first.dblclick()

    def _do_右击(self, cmd: Command) -> None:
        target = self._t("target", cmd)
        self.session.resolve_locator(target).first.click(button="right")

    def _do_悬停(self, cmd: Command) -> None:
        target = self._t("target", cmd)
        self.session.resolve_locator(target).first.hover()

    def _do_输入(self, cmd: Command) -> None:
        target = self._t("target", cmd)
        text = self._t("text", cmd)
        self.ctx.log(f"输入 {target} ← {text!r}", "info")
        self.session.resolve_locator(target).first.fill(text)

    def _do_清空(self, cmd: Command) -> None:
        target = self._t("target", cmd)
        self.session.resolve_locator(target).first.fill("")

    def _do_选择(self, cmd: Command) -> None:
        target = self._t("target", cmd)
        value = self._t("value", cmd)
        self.session.resolve_locator(target).first.select_option(value)

    def _do_上传(self, cmd: Command) -> None:
        target = self._t("target", cmd)
        path = self._t("path", cmd)
        p = Path(path)
        if not p.is_absolute():
            p = self.ctx.workdir / p
        self.session.resolve_locator(target).first.set_input_files(str(p))

    def _do_滚动到(self, cmd: Command) -> None:
        target = self._t("target", cmd)
        self.session.resolve_locator(target).first.scroll_into_view_if_needed()

    def _do_向下滚动(self, cmd: Command) -> None:
        px = cmd.args.get("px", 300)
        self._need_page().mouse.wheel(0, float(px))

    def _do_向上滚动(self, cmd: Command) -> None:
        px = cmd.args.get("px", 300)
        self._need_page().mouse.wheel(0, -float(px))

    # -- 读取 ---------------------------------------------------------

    def _do_读取(self, cmd: Command) -> None:
        target = self._t("target", cmd)
        var = cmd.args["var"]
        value = self.session.resolve_locator(target).first.inner_text()
        self.ctx.set_var(var, value)
        self.ctx.log(f"读取 {target} → {{{var}}} = {value!r}", "info")

    def _do_读取属性(self, cmd: Command) -> None:
        target = self._t("target", cmd)
        attr = self._t("attr", cmd)
        var = cmd.args["var"]
        value = self.session.resolve_locator(target).first.get_attribute(attr)
        self.ctx.set_var(var, value)
        self.ctx.log(f"读取属性 {target}.{attr} → {{{var}}} = {value!r}", "info")

    def _do_读取数量(self, cmd: Command) -> None:
        target = self._t("target", cmd)
        var = cmd.args["var"]
        count = self.session.resolve_locator(target).count()
        self.ctx.set_var(var, count)
        self.ctx.log(f"读取数量 {target} → {{{var}}} = {count}", "info")

    # -- 等待 ---------------------------------------------------------

    def _do_等待(self, cmd: Command) -> None:
        value = float(cmd.args.get("value", 1))
        unit = cmd.args.get("unit", "秒")
        ms = int(value if unit == "毫秒" else value * 1000)
        self.ctx.log(f"等待 {value} {unit}", "info")
        self.session.wait_for_timeout(ms)

    def _do_等待元素(self, cmd: Command) -> None:
        target = self._t("target", cmd)
        self.ctx.log(f"等待元素 {target}", "info")
        self.session.resolve_locator(target).first.wait_for(state="visible", timeout=30_000)

    def _do_等待文本(self, cmd: Command) -> None:
        text = self._t("text", cmd)
        self.ctx.log(f"等待文本 {text!r}", "info")
        self._need_page().get_by_text(text, exact=False).first.wait_for(state="visible", timeout=30_000)

    # -- 断言 ---------------------------------------------------------

    def _assert_fail(self, cmd: Command, msg: str):
        raise ExecutionError(msg, cmd)

    def _do_断言页面包含(self, cmd: Command) -> None:
        text = self._t("text", cmd)
        content = self._need_page().content()
        if text not in content:
            self._assert_fail(cmd, f"页面不包含 {text!r}")
        self.ctx.log(f"断言通过：页面包含 {text!r}", "info")

    def _do_断言页面不包含(self, cmd: Command) -> None:
        text = self._t("text", cmd)
        content = self._need_page().content()
        if text in content:
            self._assert_fail(cmd, f"页面不应包含 {text!r}")
        self.ctx.log(f"断言通过：页面不包含 {text!r}", "info")

    def _do_断言元素存在(self, cmd: Command) -> None:
        target = self._t("target", cmd)
        n = self.session.resolve_locator(target).count()
        if n == 0:
            self._assert_fail(cmd, f"元素不存在: {target}")
        self.ctx.log(f"断言通过：元素存在 {target}", "info")

    def _do_断言元素不存在(self, cmd: Command) -> None:
        target = self._t("target", cmd)
        n = self.session.resolve_locator(target).count()
        if n != 0:
            self._assert_fail(cmd, f"元素不应存在: {target}（找到 {n} 个）")
        self.ctx.log(f"断言通过：元素不存在 {target}", "info")

    def _do_断言标题为(self, cmd: Command) -> None:
        text = self._t("text", cmd)
        title = self._need_page().title()
        if title != text:
            self._assert_fail(cmd, f"标题应为 {text!r}，实际 {title!r}")
        self.ctx.log(f"断言通过：标题为 {text!r}", "info")

    def _do_断言标题包含(self, cmd: Command) -> None:
        text = self._t("text", cmd)
        title = self._need_page().title()
        if text not in title:
            self._assert_fail(cmd, f"标题 {title!r} 不包含 {text!r}")
        self.ctx.log(f"断言通过：标题包含 {text!r}", "info")

    def _do_断言网址包含(self, cmd: Command) -> None:
        text = self._t("text", cmd)
        url = self._need_page().url
        if text not in url:
            self._assert_fail(cmd, f"网址 {url!r} 不包含 {text!r}")
        self.ctx.log(f"断言通过：网址包含 {text!r}", "info")

    # -- 输出 / 变量 --------------------------------------------------

    def _do_截图(self, cmd: Command) -> None:
        filename = self._t("file", cmd) or f"截图.png"
        path = self.session.screenshot(filename)
        self.ctx.log(f"截图已保存 → {path}", "info")

    def _do_变量(self, cmd: Command) -> None:
        name = cmd.args["name"]
        value = self._t("value", cmd)
        self.ctx.set_var(name, value)
        self.ctx.log(f"变量 {name} = {value!r}", "info")

    def _do_打印(self, cmd: Command) -> None:
        raw = str(cmd.args.get("text", ""))
        # 整体是变量名 → 打印变量值；否则按文本插值（支持 {变量} 语法）
        if raw in self.ctx.variables:
            text = str(self.ctx.variables[raw])
        else:
            text = self.ctx.interpolate(raw)
        self.ctx.log(f"打印: {text}", "print")

    def _do_执行脚本(self, cmd: Command) -> None:
        js = self._t("js", cmd)
        result = self._need_page().evaluate(js)
        self.ctx.log(f"执行脚本 → {result!r}", "info")
