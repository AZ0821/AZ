"""双击 .hrpa 文件时的进度运行窗口。

不需要用户懂命令行——点开就跑，有进度、日志、成功/失败提示。
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..dsl import ParseError, parse
from ..engine import ExecutionError, Executor, RunContext

APP_TITLE = "汉UI 脚本运行器"


class RunWorker(QObject):
    log = Signal(str, str)  # level, message
    finished = Signal(bool, str)  # ok, error

    def __init__(self, script_path: Path):
        super().__init__()
        self.script_path = script_path

    def run(self) -> None:
        path = self.script_path
        try:
            source = path.read_text(encoding="utf-8-sig")
        except OSError as e:
            self.log.emit("error", f"无法读取脚本: {e}")
            self.finished.emit(False, str(e))
            return

        try:
            script = parse(source, source_name=str(path))
        except ParseError as e:
            self.log.emit("error", str(e))
            self.finished.emit(False, str(e))
            return

        ctx = RunContext(
            workdir=path.parent,
            on_log=lambda level, msg: self.log.emit(level, msg),
            headless=False,  # 双击运行时让用户看到浏览器
            screenshot_dir=path.parent,
        )
        ex = Executor(ctx)
        try:
            ex.run(script)
            self.finished.emit(True, "")
        except ExecutionError as e:
            self.log.emit("error", str(e))
            self.finished.emit(False, str(e))
        except Exception as e:  # noqa: BLE001
            self.log.emit("error", traceback.format_exc())
            self.finished.emit(False, str(e))


class RunnerWindow(QMainWindow):
    def __init__(self, script_path: Path):
        super().__init__()
        self.script_path = script_path
        self.setWindowTitle(f"{APP_TITLE} —— {script_path.name}")
        self.resize(640, 480)
        self._thread: QThread | None = None

        self._build()
        self._apply_style()
        self._start()

    def _build(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # 标题
        self.title = QLabel(f"▶ 正在运行  {self.script_path.name}")
        self.title.setObjectName("title")
        font = self.title.font()
        font.setPointSize(12)
        font.setBold(True)
        self.title.setFont(font)
        layout.addWidget(self.title)

        # 进度条（不确定模式）
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # busy indicator
        layout.addWidget(self.progress)

        # 日志
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 10))
        self.log.setMaximumBlockCount(3000)
        layout.addWidget(self.log, stretch=1)

        # 按钮栏
        btn_bar = QHBoxLayout()
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setEnabled(False)
        btn_bar.addStretch()
        btn_bar.addWidget(self.close_btn)
        layout.addLayout(btn_bar)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #282c34; }
            QLabel#title { color: #61afef; padding: 8px; }
            QPlainTextEdit {
                background: #21252b; color: #abb2bf;
                border: 1px solid #181a1f;
            }
            QProgressBar {
                background: #21252b; border: 1px solid #181a1f;
                height: 16px; text-align: center; color: #abb2bf;
            }
            QProgressBar::chunk { background: #61afef; }
            QPushButton {
                background: #2c313a; color: #abb2bf;
                padding: 8px 24px; border-radius: 4px;
                border: 1px solid #181a1f;
            }
            QPushButton:hover { background: #3e4451; }
            QPushButton:disabled { color: #5c6370; }
            """
        )

    def _append_log(self, level: str, message: str) -> None:
        prefix = {"info": "·", "print": "»", "warn": "!", "error": "✗"}.get(level, "·")
        self.log.appendPlainText(f"{prefix} {message}")

    def _start(self) -> None:
        self._thread = QThread(self)
        worker = RunWorker(self.script_path)
        worker.moveToThread(self._thread)
        self._thread.started.connect(worker.run)
        worker.log.connect(self._append_log)
        worker.finished.connect(self._on_finished)
        self._thread.start()
        self._worker = worker

    def _on_finished(self, ok: bool, error: str) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.close_btn.setEnabled(True)
        if ok:
            self.title.setText(f"✓ 运行成功  {self.script_path.name}")
            self.title.setStyleSheet("color: #98c379;")
        else:
            self.title.setText(f"✗ 运行失败  {self.script_path.name}")
            self.title.setStyleSheet("color: #e06c75;")
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
            self._thread = None

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(1000)
        event.accept()


def run_script_window(script_path: Path) -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("汉UI")
    app.setStyle("Fusion")
    win = RunnerWindow(script_path)
    win.show()
    return app.exec()
