"""录制器集成测试：启动真实浏览器，模拟操作，验证生成的中文脚本。

需要 `python -m playwright install chromium` 已执行。
"""

from __future__ import annotations

import pytest

from hanui.engine.recorder import Recorder

TEST_HTML = """<!DOCTYPE html>
<html>
<head><title>录制测试</title></head>
<body>
  <h1 id="title">Hello HanUI</h1>
  <input id="user" name="username" placeholder="用户名">
  <input id="pass" type="password" name="password">
  <select id="city">
    <option value="bj">北京</option>
    <option value="sh">上海</option>
  </select>
  <button id="go" type="button">提交</button>
  <a id="next" href="#done">下一步</a>
</body>
</html>
"""


@pytest.fixture
def test_page(tmp_path):
    p = tmp_path / "test.html"
    p.write_text(TEST_HTML, encoding="utf-8")
    return p.as_uri()


@pytest.fixture
def recorder():
    r = Recorder()
    yield r
    if r.is_running():
        r.stop()


def test_record_click_and_type(recorder, test_page):
    recorder.start()
    page = recorder._page
    page.goto(test_page)
    page.wait_for_timeout(80)

    page.click("#user")
    page.fill("#user", "张三")
    page.dispatch_event("#user", "input")
    page.wait_for_timeout(80)

    page.click("#go")
    page.wait_for_timeout(80)

    script = recorder.stop()
    assert "点击" in script
    assert "输入" in script
    assert "张三" in script
    assert "#user" in script or "用户名" in script
    assert "#go" in script or "提交" in script


def test_record_navigation_emits_open(recorder, test_page):
    recorder.start()
    page = recorder._page
    page.goto(test_page)
    page.wait_for_timeout(100)

    script = recorder.stop()
    assert "打开" in script


def test_record_select_and_click(recorder, test_page):
    recorder.start()
    page = recorder._page
    page.goto(test_page)
    page.wait_for_timeout(80)

    page.select_option("#city", value="sh")
    page.wait_for_timeout(80)
    page.click("#go")
    page.wait_for_timeout(80)

    script = recorder.stop()
    assert "选择" in script
    assert "上海" in script


def test_record_input_coalesced_in_real_browser(recorder, test_page):
    recorder.start()
    page = recorder._page
    page.goto(test_page)
    page.wait_for_timeout(80)

    page.click("#user")
    page.fill("#user", "a")
    page.dispatch_event("#user", "input")
    page.wait_for_timeout(50)
    page.fill("#user", "abc")
    page.dispatch_event("#user", "input")
    page.wait_for_timeout(50)
    page.fill("#user", "abcdef")
    page.dispatch_event("#user", "input")
    page.wait_for_timeout(80)

    script = recorder.stop()
    lines = [l for l in script.splitlines() if l.strip().startswith("输入")]
    # 同一选择器的多次输入应合并
    assert len(lines) <= 2, f"输入未合并: {lines}"
    assert "abcdef" in script


def test_record_selectors_use_id(recorder, test_page):
    recorder.start()
    page = recorder._page
    page.goto(test_page)
    page.wait_for_timeout(80)

    page.click("#user")
    page.wait_for_timeout(50)
    page.click("#go")
    page.wait_for_timeout(80)

    script = recorder.stop()
    # 选择器应包含 #user 而不是 body
    assert "#user" in script
    assert "#go" in script
    assert "点击 body" not in script
