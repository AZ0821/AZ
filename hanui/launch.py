"""hanui 桌面启动入口。

设计目标：
  - 双击 `脚本.hrpa` → 弹出进度窗口直接运行
  - 双击 `hanui.exe`（无参数）→ 打开 GUI 编辑器
  - 命令行用法保持不变（hanui run / parse / record / gui）
"""

from __future__ import annotations

import sys
from pathlib import Path


def _is_hrpa_file(arg: str) -> bool:
    return arg.lower().endswith(".hrpa") and Path(arg).exists()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    # 模式 1：双击 .hrpa 文件 → 用进度窗口运行
    if len(args) >= 1 and _is_hrpa_file(args[0]):
        from hanui.gui.runner import run_script_window

        return run_script_window(Path(args[0]))

    # 模式 2：无参数 → 打开 GUI
    if not args:
        from hanui.gui.app import run_gui

        return run_gui()

    # 模式 3：标准命令行
    from hanui.cli import main as cli_main

    return cli_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
