"""DSL 抽象语法树节点。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union


@dataclass(frozen=True)
class Condition:
    """条件表达式。

    kind 取值：
      page_contains / page_not_contains
      element_exists / element_not_exists
      title_is / title_contains
      url_contains
      var_eq / var_neq / var_contains
      always_true / always_false
    """

    kind: str
    args: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Cond {self.kind} {self.args}>"


@dataclass(frozen=True)
class Command:
    """一条中文命令（叶子节点）。"""

    name: str
    args: dict[str, Any] = field(default_factory=dict)
    line: int = 0
    raw: str = ""

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.name} {self.args} @{self.line}>"


@dataclass
class IfBlock:
    """如果 <条件> ... 否则 ... 结束"""

    condition: Condition
    then_body: list["Node"] = field(default_factory=list)
    else_body: list["Node"] = field(default_factory=list)
    line: int = 0
    raw: str = ""


@dataclass
class WhileBlock:
    """当 <条件> ... 结束"""

    condition: Condition
    body: list["Node"] = field(default_factory=list)
    line: int = 0
    raw: str = ""
    max_iterations: int = 10000  # 防死循环


@dataclass
class RepeatBlock:
    """重复 <N> 次 ... 结束"""

    count: int = 1
    body: list["Node"] = field(default_factory=list)
    line: int = 0
    raw: str = ""
    counter_var: str = "循环次数"


Node = Union[Command, "IfBlock", "WhileBlock", "RepeatBlock"]


@dataclass
class Script:
    """解析后的脚本。"""

    commands: list[Node]
    source_name: str = "<string>"

    def __len__(self) -> int:
        return len(self.commands)

    def __iter__(self):
        return iter(self.commands)
