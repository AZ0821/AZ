"""录制器单元测试（不启动真实浏览器）。"""

from hanui.engine.recorder import Recorder, RecordedCommand


def test_to_script_empty():
    r = Recorder()
    assert "由汉UI 录制器自动生成" in r.to_script()
    assert r.commands == []


def test_to_script_with_commands():
    r = Recorder()
    r._emit("打开 https://example.com", kind="open", selector="")
    r._emit('点击 "文本=登录"', kind="click", selector="文本=登录")
    script = r.to_script(header=False)
    assert script.strip().splitlines() == [
        "打开 https://example.com",
        '点击 "文本=登录"',
    ]


def test_input_coalescing():
    r = Recorder()
    r._emit('输入 "#u" 为 "a"', kind="input", selector="#u")
    r._emit('输入 "#u" 为 "ab"', kind="input", selector="#u")
    r._emit('输入 "#u" 为 "abc"', kind="input", selector="#u")
    assert len(r.commands) == 1
    assert r.commands[0].text == '输入 "#u" 为 "abc"'


def test_input_different_selector_not_merged():
    r = Recorder()
    r._emit('输入 "#u" 为 "a"', kind="input", selector="#u")
    r._emit('输入 "#p" 为 "b"', kind="input", selector="#p")
    assert len(r.commands) == 2


def test_click_after_input_not_merged():
    r = Recorder()
    r._emit('输入 "#u" 为 "a"', kind="input", selector="#u")
    r._emit('点击 "#btn"', kind="click", selector="#btn")
    assert len(r.commands) == 2


def test_fmt_selector_text():
    r = Recorder()
    assert r._fmt_selector({"kind": "text", "sel": "登录"}) == "文本=登录"


def test_fmt_selector_css():
    r = Recorder()
    assert r._fmt_selector({"kind": "css", "sel": "#kw"}) == '"#kw"'


def test_fmt_selector_empty():
    r = Recorder()
    assert r._fmt_selector({"kind": "css", "sel": ""}) == "body"


def test_emit_empty_ignored():
    r = Recorder()
    r._emit("", kind="click", selector="x")
    assert r.commands == []


def test_header_included():
    r = Recorder()
    r._emit("刷新", kind="refresh", selector="")
    s = r.to_script()
    assert s.startswith("# 由汉UI 录制器自动生成")
    assert "刷新" in s
