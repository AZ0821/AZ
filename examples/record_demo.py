# 模拟用户操作的录制演示脚本
import time
from hanui.engine import Recorder

r = Recorder(
    on_log=lambda m: print(f"[LOG] {m}"),
    on_command=lambda c: print(f"[CMD] {c}"),
)
r.start(url="https://example.com")
page = r._page
page.wait_for_timeout(500)

# 模拟用户点击
page.click("h1")
page.wait_for_timeout(200)

script = r.stop()
print("=" * 50)
print(script)
print("=" * 50)
