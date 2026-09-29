"""运行时上下文测试。"""

from hanui.engine.context import RunContext


def test_interpolate():
    ctx = RunContext()
    ctx.set_var("姓名", "张三")
    ctx.set_var("age", 18)
    assert ctx.interpolate("你好 {姓名}") == "你好 张三"
    assert ctx.interpolate("{姓名} 今年 {age} 岁") == "张三 今年 18 岁"


def test_interpolate_missing_var_kept():
    ctx = RunContext()
    assert ctx.interpolate("值={不存在}") == "值={不存在}"
