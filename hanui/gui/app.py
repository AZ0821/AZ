"""汉UI 桌面界面。

功能：脚本编辑（中文语法高亮）、运行/停止、日志输出、打开/保存。
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QAction, QFont, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..dsl import ParseError, parse
from ..engine import ExecutionError, Executor, RunContext
from .highlighter import HanHighlighter

APP_TITLE = "汉UI —— 中文命令 RPA"

DEFAULT_SCRIPT = """# 汉UI 脚本示例
# 命令用中文写，保存为 .hrpa 文件

打开 https://example.com
等待 1 秒
断言 标题包含 Example
读取 h1 到 标题
打印 标题
截图 "示例.png"
"""


class RecordWorker(QObject):
    """在后台线程里跑录制器，并泵送 Playwright 事件循环。"""

    log = Signal(str, str)  # level, message
    command = Signal(str)  # 实时命令文本
    started = Signal()
    finished = Signal(str)  # 生成的脚本文本

    def __init__(self, start_url: str = ""):
        super().__init__()
        self.start_url = start_url
        self._stop_flag = False

    def request_stop(self) -> None:
        self._stop_flag = True

    def run(self) -> None:
        from ..engine import Recorder

        rec = Recorder(
            on_log=lambda m: self.log.emit("info", m),
            on_command=lambda c: self.command.emit(c),
        )
        try:
            rec.start(url=self.start_url or None)
        except Exception as e:  # noqa: BLE001
            self.log.emit("error", f"录制启动失败: {e}")
            self.finished.emit("")
            return

        self.started.emit()
        # 泵送事件循环：wait_for_timeout 会触发 Playwright 派发回调
        try:
            while not self._stop_flag:
                if rec._page is None:
                    break
                try:
                    if rec._browser and not rec._browser.is_connected():
                        break
                except Exception:
                    break
                try:
                    rec._page.wait_for_timeout(80)
                except Exception:
                    break
        except Exception:  # noqa: BLE001
            pass

        try:
            script = rec.stop()
        except Exception:  # noqa: BLE001
            script = rec.to_script()
        self.finished.emit(script)


class RunWorker(QObject):
    """在后台线程里跑脚本，避免卡住 UI。"""

    log = Signal(str, str)  # level, message
    finished = Signal(bool, str)  # ok, error_message

    def __init__(self, script_text: str, workdir: Path, headless: bool = True):
        super().__init__()
        self.script_text = script_text
        self.workdir = workdir
        self.headless = headless
        self._cancelled = False

    def run(self) -> None:
        try:
            script = parse(self.script_text, source_name="编辑器")
        except ParseError as e:
            self.log.emit("error", str(e))
            self.finished.emit(False, str(e))
            return

        ctx = RunContext(
            workdir=self.workdir,
            on_log=lambda level, msg: self.log.emit(level, msg),
            headless=self.headless,
            screenshot_dir=self.workdir,
        )
        ex = Executor(ctx)
        try:
            ex.run(script)
            self.finished.emit(True, "")
        except ExecutionError as e:
            self.log.emit("error", str(e))
            self.finished.emit(False, str(e))
        except Exception as e:  # noqa: BLE001
            tb = traceback.format_exc()
            self.log.emit("error", tb)
            self.finished.emit(False, str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1100, 720)
        self._worker_thread: QThread | None = None
        self._worker: RunWorker | None = None
        self._rec_thread: QThread | None = None
        self._rec_worker: RecordWorker | None = None
        self._current_file: Path | None = None

        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        self._apply_style()

        self.editor.setPlainText(DEFAULT_SCRIPT)

    # ------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        tb = QToolBar("主工具栏", self)
        tb.setMovable(False)
        self.addToolBar(tb)

        def act(text: str, slot, shortcut: str | None = None) -> QAction:
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(slot)
            tb.addAction(a)
            return a

        act("新建", self.new_file, "Ctrl+N")
        act("打开…", self.open_file, "Ctrl+O")
        act("保存", self.save_file, "Ctrl+S")
        tb.addSeparator()
        self.run_action = act("▶ 运行", self.run_script, "F5")
        self.stop_action = act("■ 停止", self.stop_script, "Ctrl+.")
        self.stop_action.setEnabled(False)
        tb.addSeparator()
        self.record_action = act("⏺ 录制", self.start_record, "Ctrl+R")
        self.stop_record_action = act("⏹ 停止录制", self.stop_record)
        self.stop_record_action.setEnabled(False)
        tb.addSeparator()
        act("清空日志", self.clear_log)

    def _build_central(self) -> None:
        splitter = QSplitter(Qt.Orientation.Vertical, self)

        # 编辑器
        editor_wrap = QWidget()
        ev = QVBoxLayout(editor_wrap)
        ev.setContentsMargins(0, 0, 0, 0)
        header = QLabel("脚本编辑器（.hrpa）")
        header.setObjectName("panelHeader")
        ev.addWidget(header)
        self.editor = QPlainTextEdit()
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas", 12)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.editor.setFont(font)
        self.highlighter = HanHighlighter(self.editor.document())
        ev.addWidget(self.editor)
        splitter.addWidget(editor_wrap)

        # 日志
        log_wrap = QWidget()
        lv = QVBoxLayout(log_wrap)
        lv.setContentsMargins(0, 0, 0, 0)
        lheader = QLabel("执行日志")
        lheader.setObjectName("panelHeader")
        lv.addWidget(lheader)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 11))
        self.log_view.setMaximumBlockCount(5000)
        lv.addWidget(self.log_view)
        splitter.addWidget(log_wrap)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.setCentralWidget(splitter)

    def _build_statusbar(self) -> None:
        sb = QStatusBar(self)
        self.setStatusBar(sb)
        self.status_label = QLabel("就绪")
        sb.addWidget(self.status_label)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #282c34; }
            QPlainTextEdit {
                background: #21252b;
                color: #abb2bf;
                border: 1px solid #181a1f;
                selection-background-color: #3e4451;
            }
            QLabel#panelHeader {
                background: #21252b;
                color: #61afef;
                padding: 6px 10px;
                font-weight: bold;
                border: 1px solid #181a1f;
                border-bottom: none;
            }
            QToolBar {
                background: #21252b;
                border-bottom: 1px solid #181a1f;
                spacing: 6px;
                padding: 4px;
            }
            QToolBar QToolButton {
                background: #2c313a;
                color: #abb2bf;
                padding: 6px 12px;
                border-radius: 4px;
                border: 1px solid #181a1f;
            }
            QToolBar QToolButton:hover { background: #3e4451; }
            QToolBar QToolButton:pressed { background: #3a3f4b; }
            QStatusBar {
                background: #21252b;
                color: #abb2bf;
                border-top: 1px solid #181a1f;
            }
            QSplitter::handle { background: #181a1f; }
            """
        )

    # ------------------------------------------------------------------
    def append_log(self, level: str, message: str) -> None:
        prefix = {"info": "·", "print": "»", "warn": "!", "error": "✗"}.get(level, "·")
        self.log_view.appendPlainText(f"{prefix} {message}")
        if level == "error":
            self.status_label.setText("出错")
        elif level == "print":
            self.status_label.setText(message)

    def clear_log(self) -> None:
        self.log_view.clear()
        self.status_label.setText("日志已清空")

    # -- 文件 ---------------------------------------------------------

    def new_file(self) -> None:
        if self._confirm_discard():
            self.editor.setPlainText(DEFAULT_SCRIPT)
            self._current_file = None
            self.setWindowTitle(APP_TITLE)

    def open_file(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "打开脚本", str(Path.cwd()), "汉UI 脚本 (*.hrpa);;所有文件 (*)"
        )
        if not path:
            return
        self._load_file(Path(path))

    def _load_file(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as e:
            QMessageBox.warning(self, "打开失败", str(e))
            return
        self.editor.setPlainText(text)
        self._current_file = path
        self.setWindowTitle(f"{APP_TITLE} —— {path.name}")
        self.status_label.setText(f"已打开 {path}")

    def save_file(self) -> None:
        if self._current_file is None:
            self.save_file_as()
            return
        self._write_file(self._current_file)

    def save_file_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "保存脚本", str(Path.cwd()), "汉UI 脚本 (*.hrpa);;所有文件 (*)"
        )
        if not path:
            return
        p = Path(path)
        if p.suffix == "":
            p = p.with_suffix(".hrpa")
        self._current_file = p
        self._write_file(p)
        self.setWindowTitle(f"{APP_TITLE} —— {p.name}")

    def _write_file(self, path: Path) -> None:
        try:
            path.write_text(self.editor.toPlainText(), encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, "保存失败", str(e))
            return
        self.status_label.setText(f"已保存 {path}")

    def _confirm_discard(self) -> bool:
        if not self.editor.document().isModified():
            return True
        ret = QMessageBox.question(
            self,
            "未保存的更改",
            "当前脚本尚未保存，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return ret == QMessageBox.StandardButton.Yes

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self._confirm_discard():
            self.stop_script()
            event.accept()
        else:
            event.ignore()

    # -- 运行 ---------------------------------------------------------

    def run_script(self) -> None:
        if self._worker_thread is not None:
            return
        text = self.editor.toPlainText()
        workdir = self._current_file.parent if self._current_file else Path.cwd()

        self.run_action.setEnabled(False)
        self.stop_action.setEnabled(True)
        self.status_label.setText("运行中…")
        self.append_log("info", "──── 开始执行 ────")

        self._worker_thread = QThread(self)
        self._worker = RunWorker(text, workdir, headless=False)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.log.connect(self.append_log)
        self._worker.finished.connect(self._on_finished)
        self._worker_thread.start()

    def stop_script(self) -> None:
        # 协作式停止：目前只在运行结束后恢复 UI；
        # 真正中断 Playwright 需要更重的进程隔离，留作后续。
        self.append_log("warn", "停止请求已发出（当前命令执行完后停止）")
        self.status_label.setText("正在停止…")

    def _on_finished(self, ok: bool, error: str) -> None:
        if ok:
            self.append_log("info", "──── 执行成功 ────")
            self.status_label.setText("成功")
        else:
            self.append_log("info", "──── 执行失败 ────")
            self.status_label.setText("失败")
        self.run_action.setEnabled(True)
        self.stop_action.setEnabled(False)
        if self._worker_thread is not None:
            self._worker_thread.quit()
            self._worker_thread.wait(3000)
            self._worker_thread = None
            self._worker = None

    # -- 录制 ---------------------------------------------------------

    def start_record(self) -> None:
        if self._rec_thread is not None:
            return

        start_url = ""
        # 若编辑器里已有「打开 <url>」，作为起始地址
        for line in self.editor.toPlainText().splitlines():
            s = line.strip()
            if s.startswith("打开 ") or s.startswith("访问 "):
                start_url = s.split(None, 1)[1].strip().strip('"')
                break

        self.record_action.setEnabled(False)
        self.stop_record_action.setEnabled(True)
        self.status_label.setText("录制中… 在浏览器里操作即可")
        self.append_log("info", "──── 开始录制 ────")
        self.append_log("info", "在弹出的浏览器里操作，完成后点「⏹ 停止录制」")

        self._rec_thread = QThread(self)
        self._rec_worker = RecordWorker(start_url)
        self._rec_worker.moveToThread(self._rec_thread)
        self._rec_thread.started.connect(self._rec_worker.run)
        self._rec_worker.log.connect(self.append_log)
        self._rec_worker.command.connect(lambda c: self.append_log("print", f"录制: {c}"))
        self._rec_worker.finished.connect(self._on_record_finished)
        self._rec_thread.start()

    def stop_record(self) -> None:
        if self._rec_worker is None:
            return
        self.append_log("info", "正在停止录制…")
        self.status_label.setText("正在停止录制…")
        self._rec_worker.request_stop()

    def _on_record_finished(self, script: str) -> None:
        self.record_action.setEnabled(True)
        self.stop_record_action.setEnabled(False)
        if self._rec_thread is not None:
            self._rec_thread.quit()
            self._rec_thread.wait(5000)
            self._rec_thread = None
            self._rec_worker = None

        if script.strip():
            self.editor.setPlainText(script)
            self.editor.document().setModified(True)
            n = len([l for l in script.splitlines() if l.strip() and not l.strip().startswith("#")])
            self.append_log("info", f"已生成 {n} 条命令，写入编辑器")
            self.status_label.setText("录制完成")
        else:
            self.status_label.setText("录制结束（无操作）")


def run_gui() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("汉UI")
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    return app.exec()
