"""流程控制解析与执行测试。"""

import pytest

from hanui.dsl import (
    Condition,
    IfBlock,
    ParseError,
    RepeatBlock,
    WhileBlock,
    parse,
)
from hanui.dsl.ast_nodes import Command


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------

def test_parse_if_then_else():
    s = parse("""
如果 页面包含 欢迎
  打印 你好
否则
  打印 再见
结束
""")
    assert len(s) == 1
    node = s.commands[0]
    assert isinstance(node, IfBlock)
    assert node.condition.kind == "page_contains"
    assert node.condition.args["text"] == "欢迎"
    assert len(node.then_body) == 1
    assert len(node.else_body) == 1


def test_parse_if_without_else():
    s = parse("""
如果 元素 "#ok" 存在
  点击 "#ok"
结束
""")
    node = s.commands[0]
    assert isinstance(node, IfBlock)
    assert node.else_body == []


def test_parse_if_nested():
    s = parse("""
如果 页面包含 A
  如果 页面包含 B
    打印 AB
  结束
结束
""")
    outer = s.commands[0]
    assert isinstance(outer, IfBlock)
    inner = outer.then_body[0]
    assert isinstance(inner, IfBlock)
    assert inner.condition.args["text"] == "B"


def test_parse_while():
    s = parse("""
当 元素存在 "#loading"
  等待 1 秒
结束
""")
    node = s.commands[0]
    assert isinstance(node, WhileBlock)
    assert node.condition.kind == "element_exists"
    assert len(node.body) == 1


def test_parse_repeat():
    s = parse("""
重复 5 次
  截图 "s.png"
结束
""")
    node = s.commands[0]
    assert isinstance(node, RepeatBlock)
    assert node.count == 5
    assert len(node.body) == 1


def test_parse_repeat_zero():
    s = parse("重复 0 次\n  打印 空\n结束")
    assert s.commands[0].count == 0


def test_parse_condition_var_eq():
    s = parse("""
如果 变量 姓名 = 张三
  打印 对
结束
""")
    cond = s.commands[0].condition
    assert cond.kind == "var_eq"
    assert cond.args["name"] == "姓名"
    assert cond.args["value"] == "张三"


def test_parse_condition_var_neq():
    s = parse("""
如果 变量 状态 != 失败
  打印 好
结束
""")
    assert s.commands[0].condition.kind == "var_neq"


def test_parse_condition_var_contains():
    s = parse("""
如果 变量 标题 包含 欢迎
  打印 是
结束
""")
    assert s.commands[0].condition.kind == "var_contains"


def test_parse_condition_title():
    s = parse("""
如果 标题包含 首页
  打印 对
结束
""")
    assert s.commands[0].condition.kind == "title_contains"


def test_parse_condition_element_not_exists():
    s = parse("""
如果 元素不存在 ".error"
  打印 好
结束
""")
    assert s.commands[0].condition.kind == "element_not_exists"


def test_parse_condition_true_false():
    s = parse("""
如果 真
  打印 恒真
结束
""")
    assert s.commands[0].condition.kind == "always_true"

    s = parse("""
如果 假
  打印 不会执行
结束
""")
    assert s.commands[0].condition.kind == "always_false"


def test_parse_if_missing_end():
    with pytest.raises(ParseError) as e:
        parse("如果 真\n  打印 没结束")
    assert "结束" in str(e.value)


def test_parse_unexpected_else():
    with pytest.raises(ParseError):
        parse("否则\n  打印 不该有")


def test_parse_unexpected_end():
    with pytest.raises(ParseError):
        parse("结束")


def test_parse_repeat_invalid_count():
    with pytest.raises(ParseError):
        parse("重复 abc 次\n  打印 x\n结束")


def test_parse_mixed_blocks():
    s = parse("""
打开 https://example.com
如果 页面包含 欢迎
  重复 2 次
    点击 "#btn"
  结束
否则
  当 元素存在 "#retry"
    点击 "#retry"
  结束
结束
打印 完成
""")
    assert len(s) == 3  # 打开, 如果, 打印
    if_node = s.commands[1]
    assert isinstance(if_node, IfBlock)
    assert isinstance(if_node.then_body[0], RepeatBlock)
    assert isinstance(if_node.else_body[0], WhileBlock)


# ---------------------------------------------------------------------------
# 执行（条件求值，不需要浏览器）
# ---------------------------------------------------------------------------

def _make_ctx():
    from hanui.engine.context import RunContext

    return RunContext(on_log=lambda l, m: None)


def _make_ex(ctx):
    from hanui.engine.executor import Executor

    return Executor(ctx)


def test_eval_var_eq():
    ctx = _make_ctx()
    ex = _make_ex(ctx)
    ctx.set_var("姓名", "张三")
    assert ex._eval_condition(Condition("var_eq", {"name": "姓名", "value": "张三"}))
    assert not ex._eval_condition(Condition("var_eq", {"name": "姓名", "value": "李四"}))


def test_eval_var_neq():
    ctx = _make_ctx()
    ex = _make_ex(ctx)
    ctx.set_var("状态", "成功")
    assert ex._eval_condition(Condition("var_neq", {"name": "状态", "value": "失败"}))
    assert not ex._eval_condition(Condition("var_neq", {"name": "状态", "value": "成功"}))


def test_eval_var_contains():
    ctx = _make_ctx()
    ex = _make_ex(ctx)
    ctx.set_var("标题", "欢迎来到首页")
    assert ex._eval_condition(Condition("var_contains", {"name": "标题", "value": "欢迎"}))
    assert not ex._eval_condition(Condition("var_contains", {"name": "标题", "value": "再见"}))


def test_eval_always():
    ctx = _make_ctx()
    ex = _make_ex(ctx)
    assert ex._eval_condition(Condition("always_true"))
    assert not ex._eval_condition(Condition("always_false"))


def test_eval_var_interpolation():
    ctx = _make_ctx()
    ex = _make_ex(ctx)
    ctx.set_var("期望值", "OK")
    ctx.set_var("实际值", "OK")
    assert ex._eval_condition(Condition("var_eq", {"name": "实际值", "value": "{期望值}"}))


# ---------------------------------------------------------------------------
# 执行（重复 / 如果 块级逻辑，mock 页面）
# ---------------------------------------------------------------------------

def test_repeat_sets_counter():
    ctx = _make_ctx()
    ex = _make_ex(ctx)
    from hanui.dsl.ast_nodes import RepeatBlock

    seen = []
    node = RepeatBlock(count=3, body=[], line=1)
    # 手动调用，body 为空所以不会触发浏览器
    ex._exec_repeat(node)
    assert ctx.get_var("循环次数") == 3
    assert ctx.get_var("i") == 3


def test_repeat_body_runs():
    ctx = _make_ctx()
    ex = _make_ex(ctx)
    # 用 变量 命令做 body
    body = [
        Command("变量", {"name": "计数", "value": "{循环次数}"}),
    ]
    node = RepeatBlock(count=3, body=body, line=1)
    ex._exec_repeat(node)
    assert ctx.get_var("计数") == "3"
