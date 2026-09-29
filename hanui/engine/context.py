"""运行时上下文：变量表、日志回调、当前工作目录。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


_VAR_PATTERN = re.compile(r"\{([^{}]+)\}")


@dataclass
class RunContext:
    """脚本执行期间的共享状态。"""

    variables: dict[str, Any] = field(default_factory=dict)
    workdir: Path = field(default_factory=Path.cwd)
    on_log: Callable[[str, str], None] | None = None  # (level, message)
    headless: bool = True
    slow_mo: int = 0
    screenshot_dir: Path | None = None
    browser_channel: str | None = None  # "msedge" / "chrome" / None(自动)

    def log(self, message: str, level: str = "info") -> None:
        if self.on_log:
            self.on_log(level, message)

    def set_var(self, name: str, value: Any) -> None:
        self.variables[name] = value

    def get_var(self, name: str, default: Any = None) -> Any:
        return self.variables.get(name, default)

    def interpolate(self, text: str) -> str:
        """把 {变量名} 替换为变量值。"""

        def repl(m: re.Match) -> str:
            key = m.group(1).strip()
            if key in self.variables:
                return str(self.variables[key])
            return m.group(0)

        return _VAR_PATTERN.sub(repl, text)
