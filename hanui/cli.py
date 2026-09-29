"""hanui 命令行入口。

用法：
    hanui run 脚本.hrpa [--show] [--slow 100] [--workdir DIR]
    hanui parse 脚本.hrpa
    hanui record [-o 输出.hrpa] [--start URL] [--slow 100]
    hanui gui
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .dsl import ParseError, parse
from .engine import ExecutionError, Executor, RunContext


def _make_log_fn(verbose: bool = True):
    def _log(level: str, message: str) -> None:
        prefix = {
            "info": "·",
            "print": "»",
            "warn": "!",
            "error": "✗",
        }.get(level, "·")
        print(f"{prefix} {message}", flush=True)

    return _log


def cmd_run(args: argparse.Namespace) -> int:
    path = Path(args.script)
    if not path.exists():
        print(f"✗ 找不到脚本: {path}", file=sys.stderr)
        return 2

    source = path.read_text(encoding="utf-8-sig")
    try:
        script = parse(source, source_name=str(path))
    except ParseError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1

    ctx = RunContext(
        workdir=path.parent,
        on_log=_make_log_fn(),
        headless=not args.show,
        slow_mo=args.slow,
        screenshot_dir=path.parent,
        browser_channel=getattr(args, "browser", None),
    )
    ex = Executor(ctx)
    try:
        ex.run(script)
    except ExecutionError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    path = Path(args.script)
    source = path.read_text(encoding="utf-8-sig") if path.exists() else args.script
    try:
        script = parse(source, source_name=str(path) if path.exists() else "<string>")
    except ParseError as e:
        print(f"✗ {e}", file=sys.stderr)
        return 1
    print(f"✓ 解析成功，共 {len(script)} 条顶层节点：")
    _print_nodes(script.commands, indent=2)
    return 0


def _print_nodes(nodes, indent: int = 2) -> None:
    from .dsl import IfBlock, RepeatBlock, WhileBlock

    for i, n in enumerate(nodes, 1):
        pad = " " * indent
        if isinstance(n, IfBlock):
            cond = n.condition
            print(f"{pad}{i:3d}. 如果 {cond.kind} {cond.args}")
            if n.then_body:
                _print_nodes(n.then_body, indent + 4)
            if n.else_body:
                print(f"{pad}     否则")
                _print_nodes(n.else_body, indent + 4)
            print(f"{pad}     结束")
        elif isinstance(n, WhileBlock):
            cond = n.condition
            print(f"{pad}{i:3d}. 当 {cond.kind} {cond.args}")
            _print_nodes(n.body, indent + 4)
            print(f"{pad}     结束")
        elif isinstance(n, RepeatBlock):
            print(f"{pad}{i:3d}. 重复 {n.count} 次")
            _print_nodes(n.body, indent + 4)
            print(f"{pad}     结束")
        else:
            print(f"{pad}{i:3d}. {n.name:10s} {n.args}")


def cmd_gui(_args: argparse.Namespace) -> int:
    from .gui.app import run_gui

    return run_gui()


def cmd_record(args: argparse.Namespace) -> int:
    """启动可见浏览器录制操作，Ctrl+C 或关闭浏览器结束。"""
    from .engine import Recorder

    out_path = Path(args.output) if args.output else None
    recorder = Recorder(
        on_log=lambda m: print(f"· {m}", flush=True),
        on_command=lambda c: print(f"» {c}", flush=True),
    )
    print("⏺ 开始录制（关闭浏览器窗口或按 Ctrl+C 结束）", flush=True)
    recorder.start(url=args.start, slow_mo=args.slow)
    try:
        # 泵送 Playwright 事件循环（wait_for_timeout 会派发回调）
        while recorder.is_running():
            page = recorder._page
            browser = recorder._browser
            if page is None:
                break
            try:
                if browser and not browser.is_connected():
                    break
                page.wait_for_timeout(100)
            except Exception:
                break
    except KeyboardInterrupt:
        print()
    finally:
        script = recorder.stop()

    print()
    print("═" * 50)
    print(script)
    print("═" * 50)

    if out_path:
        out_path.write_text(script, encoding="utf-8")
        print(f"✓ 已保存 → {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hanui", description="汉UI —— 中文命令 RPA")
    sub = p.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="运行脚本")
    run_p.add_argument("script", help="脚本路径")
    run_p.add_argument("--show", action="store_true", help="显示浏览器窗口")
    run_p.add_argument("--slow", type=int, default=0, help="慢速模式（毫秒延迟）")
    run_p.add_argument("--browser", choices=["msedge", "chrome", "chromium"],
                       default=None, help="指定浏览器（默认自动探测 Edge/Chrome）")
    run_p.set_defaults(func=cmd_run)

    parse_p = sub.add_parser("parse", help="仅解析脚本，打印命令列表")
    parse_p.add_argument("script", help="脚本路径或脚本文本")
    parse_p.set_defaults(func=cmd_parse)

    gui_p = sub.add_parser("gui", help="打开图形界面")
    gui_p.set_defaults(func=cmd_gui)

    rec_p = sub.add_parser("record", help="录制浏览器操作，生成中文脚本")
    rec_p.add_argument("-o", "--output", help="保存到文件（.hrpa）")
    rec_p.add_argument("--start", help="起始网址")
    rec_p.add_argument("--slow", type=int, default=0, help="慢速模式（毫秒延迟）")
    rec_p.set_defaults(func=cmd_record)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
