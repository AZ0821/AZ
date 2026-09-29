"""中文 DSL 词法/语法解析。

脚本是按行组织的中文命令，例如：

    打开 https://www.baidu.com
    输入 "#kw" 为 "汉UI 自动化"
    点击 "#su"
    等待 2 秒
    读取 "#content_left" 到 结果
    打印 结果
    截图 "搜索.png"

注释以 # 或 // 开头；空行忽略。
"""

from __future__ import annotations

import re
from typing import Any

from .ast_nodes import Command, Condition, IfBlock, WhileBlock, RepeatBlock, Script, Node


class ParseError(Exception):
    def __init__(self, message: str, line: int = 0, raw: str = ""):
        self.line = line
        self.raw = raw
        super().__init__(f"第 {line} 行解析失败: {message}" + (f"  ({raw!r})" if raw else ""))


# ---------------------------------------------------------------------------
# 词法：把一行切成 token
# ---------------------------------------------------------------------------

# 引号字符串（支持 \" 转义）
_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?")
# 中英文标识符（变量名）
_IDENT_RE = re.compile(r"^[A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*")


def _unescape(s: str) -> str:
    return (
        s.replace(r"\"", '"')
        .replace(r"\'", "'")
        .replace(r"\n", "\n")
        .replace(r"\t", "\t")
        .replace(r"\\", "\\")
    )


def _is_comment_start(line: str, i: int) -> bool:
    """判断 i 处是否是行内注释起点。

    规则（避免误伤 CSS `#id` 和 URL 里的 `//`）：
      - `//` 仅在空白之后出现，且后面是空白或行尾，才视为注释；
      - `#` 仅在空白之后出现，且后面是空白或行尾，才视为注释；
        `#login`、`#kw` 这类选择器不满足「后面是空白」，因此保留。
    """
    if line.startswith("//", i):
        after = line[i + 2 : i + 3]
        return after == "" or after.isspace()
    if line[i] == "#":
        after = line[i + 1 : i + 2]
        return after == "" or after.isspace()
    return False


def tokenize(line: str) -> list[tuple[str, Any]]:
    """把一行切成 (kind, value) 列表，kind ∈ {str, num, word}。

    未加引号的连续非空白片段视为 word（命令关键字/介词/裸 URL/裸选择器）。
    """
    tokens: list[tuple[str, Any]] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch.isspace():
            i += 1
            continue

        # 行内注释：之后全部忽略
        if _is_comment_start(line, i):
            break

        m = _STRING_RE.match(line, i)
        if m:
            raw = m.group(0)
            tokens.append(("str", _unescape(raw[1:-1])))
            i = m.end()
            continue

        # 剩下的裸片段：读到空白或引号为止
        j = i
        while j < n and not line[j].isspace() and line[j] not in "\"'":
            j += 1
        word = line[i:j]
        if not word:
            i += 1
            continue

        mnum = _NUMBER_RE.match(word)
        if mnum and mnum.group(0) == word:
            tokens.append(("num", float(word) if "." in word else int(word)))
        else:
            tokens.append(("word", word))
        i = j
    return tokens


# ---------------------------------------------------------------------------
# 命令语法表
# ---------------------------------------------------------------------------
# 每条命令描述参数如何从 token 流中取。
# 占位符:
#   <target>  选择器/目标（str 或 word）
#   <text>    文本（str 或 word，直到介词/结尾）
#   <var>     变量名
#   <num>     数字
#   <file>    文件路径
#   介词/关键字: 固定字面量
#
# 简化做法：命令注册表里写 handler，由 handler 自己消费 tokens。

Var = str  # 变量名类型


def _expect(tokens: list, idx: int, line: int, raw: str, what: str) -> tuple[Any, int]:
    if idx >= len(tokens):
        raise ParseError(f"缺少{what}", line, raw)
    kind, val = tokens[idx]
    return val, idx + 1


def _take_until_keywords(tokens: list, idx: int, keywords: set[str]) -> tuple[str, int]:
    """收集 token 直到遇到指定关键字或流结束，拼成字符串。"""
    parts: list[str] = []
    while idx < len(tokens):
        kind, val = tokens[idx]
        if kind == "word" and val in keywords:
            break
        parts.append(str(val))
        idx += 1
    return " ".join(parts) if len(parts) != 1 else parts[0], idx


def _take_value(tokens: list, idx: int) -> tuple[Any, int]:
    """取一个值 token（str/num/word），不吞后续。"""
    if idx >= len(tokens):
        raise ParseError("缺少参数")
    kind, val = tokens[idx]
    return val, idx + 1


def _take_text(tokens: list, idx: int) -> tuple[str, int]:
    """取一段文本（可能含空格），直到行尾。"""
    if idx >= len(tokens):
        raise ParseError("缺少文本")
    parts: list[str] = []
    while idx < len(tokens):
        _k, val = tokens[idx]
        parts.append(str(val))
        idx += 1
    return " ".join(parts) if len(parts) != 1 else str(parts[0]), idx


# 命令名 -> (参数名列表, 构造函数)
# 为保持可读，下面用显式解析分支实现。


def _cmd_open(tokens, line, raw) -> Command:
    if not tokens:
        raise ParseError("「打开」需要一个网址", line, raw)
    url, _ = _take_text(tokens, 0)
    return Command("打开", {"url": url}, line, raw)


def _cmd_close(tokens, line, raw) -> Command:
    return Command("关闭", {}, line, raw)


def _cmd_refresh(tokens, line, raw) -> Command:
    return Command("刷新", {}, line, raw)


def _cmd_back(tokens, line, raw) -> Command:
    return Command("后退", {}, line, raw)


def _cmd_forward(tokens, line, raw) -> Command:
    return Command("前进", {}, line, raw)


def _cmd_click(tokens, line, raw) -> Command:
    target, _ = _take_text(tokens, 0)
    return Command("点击", {"target": target}, line, raw)


def _cmd_dblclick(tokens, line, raw) -> Command:
    target, _ = _take_text(tokens, 0)
    return Command("双击", {"target": target}, line, raw)


def _cmd_rclick(tokens, line, raw) -> Command:
    target, _ = _take_text(tokens, 0)
    return Command("右击", {"target": target}, line, raw)


def _cmd_hover(tokens, line, raw) -> Command:
    target, _ = _take_text(tokens, 0)
    return Command("悬停", {"target": target}, line, raw)


def _cmd_fill(tokens, line, raw) -> Command:
    # 输入 <target> 为 <text>
    if not tokens:
        raise ParseError("「输入」需要目标", line, raw)
    target, idx = _take_until_keywords(tokens, 0, {"为", "是"})
    if idx >= len(tokens):
        raise ParseError("「输入」缺少「为」", line, raw)
    idx += 1  # 跳过 为/是
    text, _ = _take_text(tokens, idx)
    return Command("输入", {"target": target, "text": text}, line, raw)


def _cmd_clear(tokens, line, raw) -> Command:
    target, _ = _take_text(tokens, 0)
    return Command("清空", {"target": target}, line, raw)


def _cmd_select(tokens, line, raw) -> Command:
    # 选择 <target> 选中 <value>
    if not tokens:
        raise ParseError("「选择」需要目标", line, raw)
    target, idx = _take_until_keywords(tokens, 0, {"选中", "选为"})
    if idx >= len(tokens):
        raise ParseError("「选择」缺少「选中」", line, raw)
    idx += 1
    value, _ = _take_text(tokens, idx)
    return Command("选择", {"target": target, "value": value}, line, raw)


def _cmd_read(tokens, line, raw) -> Command:
    # 读取 <target> 到 <var>
    if not tokens:
        raise ParseError("「读取」需要目标", line, raw)
    target, idx = _take_until_keywords(tokens, 0, {"到", "至"})
    if idx >= len(tokens):
        raise ParseError("「读取」缺少「到」", line, raw)
    idx += 1
    var, _ = _take_value(tokens, idx)
    return Command("读取", {"target": target, "var": str(var)}, line, raw)


def _cmd_read_attr(tokens, line, raw) -> Command:
    # 读取属性 <target> 的 <attr> 到 <var>
    if not tokens:
        raise ParseError("「读取属性」需要目标", line, raw)
    target, idx = _take_until_keywords(tokens, 0, {"的"})
    if idx >= len(tokens):
        raise ParseError("「读取属性」缺少「的」", line, raw)
    idx += 1
    attr, idx = _take_until_keywords(tokens, idx, {"到", "至"})
    if idx >= len(tokens):
        raise ParseError("「读取属性」缺少「到」", line, raw)
    idx += 1
    var, _ = _take_value(tokens, idx)
    return Command("读取属性", {"target": target, "attr": str(attr), "var": str(var)}, line, raw)


def _cmd_read_count(tokens, line, raw) -> Command:
    # 读取数量 <target> 到 <var>
    if not tokens:
        raise ParseError("「读取数量」需要目标", line, raw)
    target, idx = _take_until_keywords(tokens, 0, {"到", "至"})
    if idx >= len(tokens):
        raise ParseError("「读取数量」缺少「到」", line, raw)
    idx += 1
    var, _ = _take_value(tokens, idx)
    return Command("读取数量", {"target": target, "var": str(var)}, line, raw)


def _cmd_wait_element(tokens, line, raw) -> Command:
    target, _ = _take_text(tokens, 0)
    return Command("等待元素", {"target": target}, line, raw)


def _cmd_wait_text(tokens, line, raw) -> Command:
    text, _ = _take_text(tokens, 0)
    return Command("等待文本", {"text": text}, line, raw)


def _cmd_wait(tokens, line, raw) -> Command:
    # 等待 <n> 秒  |  等待 元素 <target>  |  等待 文本 <text>
    if not tokens:
        raise ParseError("「等待」需要参数（秒数 / 元素 / 文本）", line, raw)
    kind, first = tokens[0]
    if kind == "word" and first == "元素":
        target, _ = _take_text(tokens, 1)
        return Command("等待元素", {"target": target}, line, raw)
    if kind == "word" and first == "文本":
        text, _ = _take_text(tokens, 1)
        return Command("等待文本", {"text": text}, line, raw)
    # 等待 N 秒/毫秒
    num, idx = _take_value(tokens, 0)
    try:
        value = float(num)
    except (TypeError, ValueError):
        raise ParseError(f"「等待」的秒数无效: {num!r}", line, raw) from None
    unit = "秒"
    if idx < len(tokens):
        u = str(tokens[idx][1])
        if u in ("秒", "s", "second", "seconds"):
            unit = "秒"
        elif u in ("毫秒", "ms", "millisecond", "milliseconds"):
            unit = "毫秒"
        else:
            raise ParseError(f"「等待」单位无效: {u!r}", line, raw)
    return Command("等待", {"value": value, "unit": unit}, line, raw)


def _cmd_assert(tokens, line, raw) -> Command:
    # 断言 页面包含 <text>   （也接受「断言 页面 包含 ...」）
    # 断言 页面不包含 <text>
    # 断言 元素 <target> 存在 / 不存在   （也接受「断言 元素存在 <target>」）
    # 断言 标题为 <text> / 断言 标题包含 <text>
    # 断言 网址包含 <text>
    if not tokens:
        raise ParseError("「断言」需要条件", line, raw)
    _kind, first = tokens[0]
    first = str(first)

    # 合并形式：页面包含 / 页面不包含 / 标题为 / 标题包含 / 网址包含 / 元素存在 / 元素不存在
    if first in ("页面包含", "页面含"):
        text, _ = _take_text(tokens, 1)
        return Command("断言页面包含", {"text": text}, line, raw)
    if first in ("页面不包含", "页面不含"):
        text, _ = _take_text(tokens, 1)
        return Command("断言页面不包含", {"text": text}, line, raw)
    if first in ("标题为", "标题是"):
        text, _ = _take_text(tokens, 1)
        return Command("断言标题为", {"text": text}, line, raw)
    if first in ("标题包含", "标题含"):
        text, _ = _take_text(tokens, 1)
        return Command("断言标题包含", {"text": text}, line, raw)
    if first in ("网址包含", "网址含"):
        text, _ = _take_text(tokens, 1)
        return Command("断言网址包含", {"text": text}, line, raw)
    if first == "元素存在":
        target, _ = _take_text(tokens, 1)
        return Command("断言元素存在", {"target": target}, line, raw)
    if first == "元素不存在":
        target, _ = _take_text(tokens, 1)
        return Command("断言元素不存在", {"target": target}, line, raw)

    # 拆分形式
    if first == "页面":
        rest = tokens[1:]
        if not rest:
            raise ParseError("「断言 页面」缺少条件", line, raw)
        _k2, v2 = rest[0]
        if v2 in ("包含", "含"):
            text, _ = _take_text(rest, 1)
            return Command("断言页面包含", {"text": text}, line, raw)
        if v2 in ("不包含", "不含"):
            text, _ = _take_text(rest, 1)
            return Command("断言页面不包含", {"text": text}, line, raw)
        raise ParseError(f"未知的页面断言: {v2!r}", line, raw)
    if first == "元素":
        if len(tokens) < 2:
            raise ParseError("「断言 元素」缺少目标", line, raw)
        target, idx = _take_until_keywords(tokens, 1, {"存在", "不存在"})
        if idx >= len(tokens):
            raise ParseError("「断言 元素」缺少「存在/不存在」", line, raw)
        cond = str(tokens[idx][1])
        name = "断言元素存在" if cond == "存在" else "断言元素不存在"
        return Command(name, {"target": target}, line, raw)
    if first == "标题":
        rest = tokens[1:]
        if not rest:
            raise ParseError("「断言 标题」缺少条件", line, raw)
        _k2, v2 = rest[0]
        if v2 in ("为", "是"):
            text, _ = _take_text(rest, 1)
            return Command("断言标题为", {"text": text}, line, raw)
        if v2 in ("包含", "含"):
            text, _ = _take_text(rest, 1)
            return Command("断言标题包含", {"text": text}, line, raw)
        raise ParseError(f"未知的标题断言: {v2!r}", line, raw)
    if first == "网址":
        rest = tokens[1:]
        if not rest:
            raise ParseError("「断言 网址」缺少条件", line, raw)
        _k2, v2 = rest[0]
        if v2 in ("包含", "含"):
            text, _ = _take_text(rest, 1)
            return Command("断言网址包含", {"text": text}, line, raw)
        raise ParseError(f"未知的网址断言: {v2!r}", line, raw)
    raise ParseError(f"未知的断言条件: {first!r}", line, raw)


def _cmd_screenshot(tokens, line, raw) -> Command:
    if not tokens:
        return Command("截图", {"file": ""}, line, raw)
    file, _ = _take_text(tokens, 0)
    return Command("截图", {"file": file}, line, raw)


def _cmd_let(tokens, line, raw) -> Command:
    # 变量 <name> = <value>   或  变量 <name> 为 <value>
    if not tokens:
        raise ParseError("「变量」需要名字", line, raw)
    name, idx = _take_value(tokens, 0)
    if idx < len(tokens) and str(tokens[idx][1]) in ("=", "为", "是"):
        idx += 1
    if idx >= len(tokens):
        raise ParseError("「变量」缺少值", line, raw)
    value, _ = _take_text(tokens, idx)
    return Command("变量", {"name": str(name), "value": value}, line, raw)


def _cmd_print(tokens, line, raw) -> Command:
    if not tokens:
        raise ParseError("「打印」需要内容", line, raw)
    text, _ = _take_text(tokens, 0)
    return Command("打印", {"text": text}, line, raw)


def _cmd_js(tokens, line, raw) -> Command:
    # 执行脚本 <js>
    if not tokens:
        raise ParseError("「执行脚本」需要 JavaScript", line, raw)
    js, _ = _take_text(tokens, 0)
    return Command("执行脚本", {"js": js}, line, raw)


def _cmd_upload(tokens, line, raw) -> Command:
    # 上传 <target> 文件 <path>
    if not tokens:
        raise ParseError("「上传」需要目标", line, raw)
    target, idx = _take_until_keywords(tokens, 0, {"文件"})
    if idx >= len(tokens):
        raise ParseError("「上传」缺少「文件」", line, raw)
    idx += 1
    path, _ = _take_text(tokens, idx)
    return Command("上传", {"target": target, "path": path}, line, raw)


def _cmd_scroll(tokens, line, raw) -> Command:
    # 滚动到 <target>  |  向下滚动 <n>  |  向上滚动 <n>
    if not tokens:
        raise ParseError("「滚动」需要参数", line, raw)
    kind, first = tokens[0]
    if first == "到":
        target, _ = _take_text(tokens, 1)
        return Command("滚动到", {"target": target}, line, raw)
    if first in ("向下", "下"):
        n = tokens[1][1] if len(tokens) > 1 else 300
        return Command("向下滚动", {"px": n}, line, raw)
    if first in ("向上", "上"):
        n = tokens[1][1] if len(tokens) > 1 else 300
        return Command("向上滚动", {"px": n}, line, raw)
    # 默认：滚动到目标
    target, _ = _take_text(tokens, 0)
    return Command("滚动到", {"target": target}, line, raw)


def _cmd_sleep_only(tokens, line, raw) -> Command:
    return Command("等待", {"value": 1, "unit": "秒"}, line, raw)


# 主关键字 -> 解析函数（长关键字优先匹配）
COMMAND_PARSERS = {
    "读取属性": _cmd_read_attr,
    "读取数量": _cmd_read_count,
    "读取": _cmd_read,
    "等待元素": _cmd_wait_element,
    "等待文本": _cmd_wait_text,
    "等待": _cmd_wait,
    "打开": _cmd_open,
    "关闭": _cmd_close,
    "刷新": _cmd_refresh,
    "后退": _cmd_back,
    "前进": _cmd_forward,
    "点击": _cmd_click,
    "双击": _cmd_dblclick,
    "右击": _cmd_rclick,
    "悬停": _cmd_hover,
    "输入": _cmd_fill,
    "清空": _cmd_clear,
    "选择": _cmd_select,
    "断言": _cmd_assert,
    "截图": _cmd_screenshot,
    "变量": _cmd_let,
    "打印": _cmd_print,
    "执行脚本": _cmd_js,
    "上传": _cmd_upload,
    "滚动到": _cmd_scroll,
    "向下滚动": _cmd_scroll,
    "向上滚动": _cmd_scroll,
    "滚动": _cmd_scroll,
}

# 别名（打字更快）
ALIASES = {
    "打开网页": "打开",
    "访问": "打开",
    "跳转": "打开",
    "点": "点击",
    "单击": "点击",
    "填": "输入",
    "填写": "输入",
    "键入": "输入",
    "读": "读取",
    "取值": "读取",
    "输出": "打印",
    "打日志": "打印",
    "截图留证": "截图",
    "休眠": "等待",
    "延时": "等待",
}


def _lookup_parser(name: str):
    if name in COMMAND_PARSERS:
        return COMMAND_PARSERS[name]
    if name in ALIASES:
        return COMMAND_PARSERS[ALIASES[name]]
    return None


# 关键字按长度倒序，保证「读取属性」优先于「读取」
_KEYWORDS = sorted(COMMAND_PARSERS.keys(), key=len, reverse=True)


def _match_command(tokens: list[tuple[str, Any]], line: int, raw: str):
    """从 token 流匹配命令关键字（支持关键字被空格拆开的情况较少见，一般连写）。"""
    if not tokens:
        return None
    # 情形 1：第一个 token 就是完整命令关键字
    kind, val = tokens[0]
    if kind == "word":
        parser = _lookup_parser(str(val))
        if parser:
            return parser, tokens[1:]
    # 情形 2：命令关键字可能与后续 token 拼接（极少），也支持「等待 元素」这种
    # 已经在 _cmd_wait 里处理。
    return None


# ---------------------------------------------------------------------------
# 条件解析
# ---------------------------------------------------------------------------

def _parse_condition(tokens: list, line: int, raw: str) -> Condition:
    """解析 如果/当 后面的条件表达式。"""
    if not tokens:
        raise ParseError("缺少条件", line, raw)

    _k, first = tokens[0]
    first = str(first)

    # 真 / 假
    if first in ("真", "true", "True"):
        return Condition("always_true")
    if first in ("假", "false", "False"):
        return Condition("always_false")

    # 页面包含 / 页面不包含（合并或拆分）
    if first in ("页面包含", "页面含"):
        text, _ = _take_text(tokens, 1)
        return Condition("page_contains", {"text": text})
    if first in ("页面不包含", "页面不含"):
        text, _ = _take_text(tokens, 1)
        return Condition("page_not_contains", {"text": text})
    if first == "页面":
        _k2, v2 = tokens[1][1], tokens[1][1]
        rest = tokens[1:]
        _kk, v2 = rest[0]
        if v2 in ("包含", "含"):
            text, _ = _take_text(rest, 1)
            return Condition("page_contains", {"text": text})
        if v2 in ("不包含", "不含"):
            text, _ = _take_text(rest, 1)
            return Condition("page_not_contains", {"text": text})
        raise ParseError(f"未知的页面条件: {v2!r}", line, raw)

    # 元素存在 / 元素不存在（合并）
    if first == "元素存在":
        target, _ = _take_text(tokens, 1)
        return Condition("element_exists", {"target": target})
    if first == "元素不存在":
        target, _ = _take_text(tokens, 1)
        return Condition("element_not_exists", {"target": target})

    # 元素 <sel> 存在 / 不存在（拆分）
    if first == "元素":
        if len(tokens) < 2:
            raise ParseError("「元素」条件缺少目标", line, raw)
        target, idx = _take_until_keywords(tokens, 1, {"存在", "不存在"})
        if idx >= len(tokens):
            raise ParseError("「元素」条件缺少「存在/不存在」", line, raw)
        cond = str(tokens[idx][1])
        if cond == "存在":
            return Condition("element_exists", {"target": target})
        return Condition("element_not_exists", {"target": target})

    # 标题为 / 标题包含
    if first in ("标题为", "标题是"):
        text, _ = _take_text(tokens, 1)
        return Condition("title_is", {"text": text})
    if first in ("标题包含", "标题含"):
        text, _ = _take_text(tokens, 1)
        return Condition("title_contains", {"text": text})
    if first == "标题":
        rest = tokens[1:]
        _kk, v2 = rest[0]
        if v2 in ("为", "是"):
            text, _ = _take_text(rest, 1)
            return Condition("title_is", {"text": text})
        if v2 in ("包含", "含"):
            text, _ = _take_text(rest, 1)
            return Condition("title_contains", {"text": text})
        raise ParseError(f"未知的标题条件: {v2!r}", line, raw)

    # 网址包含
    if first in ("网址包含", "网址含"):
        text, _ = _take_text(tokens, 1)
        return Condition("url_contains", {"text": text})
    if first == "网址":
        rest = tokens[1:]
        _kk, v2 = rest[0]
        if v2 in ("包含", "含"):
            text, _ = _take_text(rest, 1)
            return Condition("url_contains", {"text": text})
        raise ParseError(f"未知的网址条件: {v2!r}", line, raw)

    # 变量 <name> = / != / 包含 <value>
    if first == "变量":
        if len(tokens) < 2:
            raise ParseError("「变量」条件缺少变量名", line, raw)
        var_name, idx = _take_value(tokens, 1)
        if idx >= len(tokens):
            raise ParseError("「变量」条件缺少运算符", line, raw)
        op = str(tokens[idx][1])
        idx += 1
        if idx >= len(tokens):
            raise ParseError("「变量」条件缺少比较值", line, raw)
        value, _ = _take_text(tokens, idx)
        if op in ("=", "==", "为", "是"):
            return Condition("var_eq", {"name": str(var_name), "value": value})
        if op in ("!=", "不为", "不是", "≠"):
            return Condition("var_neq", {"name": str(var_name), "value": value})
        if op in ("包含", "含"):
            return Condition("var_contains", {"name": str(var_name), "value": value})
        if op in ("不包含", "不含"):
            return Condition("var_not_contains", {"name": str(var_name), "value": value})
        raise ParseError(f"未知的变量运算符: {op!r}", line, raw)

    raise ParseError(f"未知的条件: {first!r}", line, raw)


# ---------------------------------------------------------------------------
# 块结构解析
# ---------------------------------------------------------------------------

_STRUCTURAL = {"如果", "当", "重复", "否则", "结束"}


class _Cursor:
    """按行扫描的游标。"""

    def __init__(self, source: str):
        self.lines = source.splitlines()
        self.pos = 0  # 0-based

    def eof(self) -> bool:
        return self.pos >= len(self.lines)

    def peek_raw(self) -> str:
        return self.lines[self.pos] if self.pos < len(self.lines) else ""

    def next_raw(self) -> str:
        line = self.lines[self.pos]
        self.pos += 1
        return line

    @property
    def lineno(self) -> int:
        return self.pos + 1


def _is_blank_or_comment(line: str) -> bool:
    s = line.strip()
    return not s or s.startswith("#") or s.startswith("//")


def _parse_block(cursor: _Cursor, stop: set[str]) -> tuple[list, str | None]:
    """解析到遇到 stop 中的结构关键字为止。

    返回 (节点列表, 遇到的关键字)。关键字为 '否则' / '结束' / None(EOF)。
    """
    nodes: list = []
    while not cursor.eof():
        raw_line = cursor.next_raw()
        if _is_blank_or_comment(raw_line):
            continue
        try:
            tokens = tokenize(raw_line)
            if not tokens:
                continue
            first = str(tokens[0][1])

            # 结构关键字
            if first in _STRUCTURAL:
                if first in stop:
                    return nodes, first
                # 嵌套：如果/当/重复
                if first == "如果":
                    node = _parse_if(cursor, tokens, cursor.lineno - 1, raw_line)
                    nodes.append(node)
                    continue
                if first == "当":
                    node = _parse_while(cursor, tokens, cursor.lineno - 1, raw_line)
                    nodes.append(node)
                    continue
                if first == "重复":
                    node = _parse_repeat(cursor, tokens, cursor.lineno - 1, raw_line)
                    nodes.append(node)
                    continue
                # 否则/结束 不属于当前块
                raise ParseError(f"意外的「{first}」", cursor.lineno - 1, raw_line)

            # 普通命令
            matched = _match_command(tokens, cursor.lineno - 1, raw_line)
            if matched is None:
                raise ParseError(f"未知命令 {tokens[0][1]!r}", cursor.lineno - 1, raw_line)
            parser, rest = matched
            cmd = parser(rest, cursor.lineno - 1, raw_line)
            nodes.append(cmd)
        except ParseError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ParseError(str(exc), cursor.lineno - 1, raw_line) from exc

    return nodes, None


def _parse_if(cursor: _Cursor, tokens: list, line: int, raw: str) -> IfBlock:
    """解析 如果 <条件> ... [否则 ...] 结束"""
    cond = _parse_condition(tokens[1:], line, raw)
    then_body, marker = _parse_block(cursor, {"否则", "结束"})
    else_body: list = []
    if marker == "否则":
        else_body, marker = _parse_block(cursor, {"结束"})
    if marker != "结束":
        raise ParseError("「如果」缺少配对的「结束」", line, raw)
    return IfBlock(condition=cond, then_body=then_body, else_body=else_body, line=line, raw=raw)


def _parse_while(cursor: _Cursor, tokens: list, line: int, raw: str) -> WhileBlock:
    """解析 当 <条件> ... 结束"""
    cond = _parse_condition(tokens[1:], line, raw)
    body, marker = _parse_block(cursor, {"结束"})
    if marker != "结束":
        raise ParseError("「当」缺少配对的「结束」", line, raw)
    return WhileBlock(condition=cond, body=body, line=line, raw=raw)


def _parse_repeat(cursor: _Cursor, tokens: list, line: int, raw: str) -> RepeatBlock:
    """解析 重复 <N> [次] ... 结束"""
    if len(tokens) < 2:
        raise ParseError("「重复」需要次数", line, raw)
    _k, val = tokens[1]
    try:
        count = int(val)
    except (TypeError, ValueError):
        raise ParseError(f"「重复」的次数无效: {val!r}", line, raw) from None
    if count < 0:
        raise ParseError("「重复」的次数不能为负数", line, raw)
    body, marker = _parse_block(cursor, {"结束"})
    if marker != "结束":
        raise ParseError("「重复」缺少配对的「结束」", line, raw)
    return RepeatBlock(count=count, body=body, line=line, raw=raw)


def parse(source: str, source_name: str = "<string>") -> Script:
    """解析整份脚本文本，返回 Script（支持 如果/当/重复 块）。"""
    if source.startswith("\ufeff"):
        source = source[1:]
    cursor = _Cursor(source)
    commands, marker = _parse_block(cursor, {"否则", "结束"})
    if marker is not None:
        raise ParseError(f"意外的「{marker}」", cursor.lineno)
    return Script(commands=commands, source_name=source_name)
