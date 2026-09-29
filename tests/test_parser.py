"""解析器单元测试。"""

import pytest

from hanui.dsl import ParseError, parse


def test_parse_open():
    s = parse("打开 https://www.baidu.com")
    assert len(s) == 1
    assert s.commands[0].name == "打开"
    assert s.commands[0].args["url"] == "https://www.baidu.com"


def test_parse_fill():
    s = parse('输入 "#kw" 为 "汉UI 自动化"')
    assert s.commands[0].name == "输入"
    assert s.commands[0].args["target"] == "#kw"
    assert s.commands[0].args["text"] == "汉UI 自动化"


def test_parse_fill_unquoted():
    s = parse("输入 #kw 为 你好世界")
    assert s.commands[0].args["target"] == "#kw"
    assert s.commands[0].args["text"] == "你好世界"


def test_parse_read():
    s = parse('读取 "#content" 到 结果')
    assert s.commands[0].name == "读取"
    assert s.commands[0].args["target"] == "#content"
    assert s.commands[0].args["var"] == "结果"


def test_parse_wait_seconds():
    s = parse("等待 2 秒")
    assert s.commands[0].args["value"] == 2
    assert s.commands[0].args["unit"] == "秒"


def test_parse_wait_ms():
    s = parse("等待 500 毫秒")
    assert s.commands[0].args["value"] == 500
    assert s.commands[0].args["unit"] == "毫秒"


def test_parse_assert_contains():
    s = parse("断言 页面包含 欢迎")
    assert s.commands[0].name == "断言页面包含"
    assert s.commands[0].args["text"] == "欢迎"


def test_parse_assert_element_exists():
    s = parse('断言 元素 "#login" 存在')
    assert s.commands[0].name == "断言元素存在"
    assert s.commands[0].args["target"] == "#login"


def test_parse_comments_and_blank():
    src = """
    # 注释
    打开 https://example.com

    // 另一种注释
    打印 你好
    """
    s = parse(src)
    assert len(s) == 2


def test_parse_unknown_command():
    with pytest.raises(ParseError) as e:
        parse("飞天 无所不能")
    assert "未知命令" in str(e.value)


def test_parse_missing_arg():
    with pytest.raises(ParseError):
        parse("点击")


def test_parse_variable():
    s = parse("变量 姓名 = 张三")
    assert s.commands[0].args["name"] == "姓名"
    assert s.commands[0].args["value"] == "张三"


def test_parse_alias():
    s = parse("访问 https://example.com")
    assert s.commands[0].name == "打开"


def test_parse_multiple():
    src = """
    打开 https://www.baidu.com
    输入 "#kw" 为 "测试"
    点击 "#su"
    等待 2 秒
    截图 "result.png"
    """
    s = parse(src)
    assert len(s) == 5
    assert [c.name for c in s] == ["打开", "输入", "点击", "等待", "截图"]


def test_parse_select():
    s = parse("选择 #city 选中 北京")
    assert s.commands[0].name == "选择"
    assert s.commands[0].args["target"] == "#city"
    assert s.commands[0].args["value"] == "北京"


def test_parse_read_attr():
    s = parse("读取属性 #link 的 href 到 网址")
    assert s.commands[0].name == "读取属性"
    assert s.commands[0].args["attr"] == "href"
    assert s.commands[0].args["var"] == "网址"


def test_parse_wait_element():
    s = parse("等待元素 #done")
    assert s.commands[0].name == "等待元素"
    assert s.commands[0].args["target"] == "#done"
