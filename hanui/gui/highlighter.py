"""中文 DSL 语法高亮。"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


# 命令关键字（高亮为关键字色）
KEYWORDS = {
    "打开", "关闭", "刷新", "后退", "前进",
    "点击", "双击", "右击", "悬停",
    "输入", "清空", "选择", "上传",
    "读取", "读取属性", "读取数量",
    "等待", "等待元素", "等待文本",
    "断言", "截图", "变量", "打印", "执行脚本",
    "滚动到", "向下滚动", "向上滚动", "滚动",
    # 流程控制
    "如果", "否则", "结束", "当", "重复", "次", "跳出", "继续",
    # 别名
    "打开网页", "访问", "跳转", "点", "单击", "填", "填写", "键入",
    "读", "取值", "输出", "打日志", "截图留证", "休眠", "延时",
}

# 流程控制关键字（加粗高亮）
FLOW_KEYWORDS = {"如果", "否则", "结束", "当", "重复", "跳出", "继续"}

# 介词 / 连接词
PREPOSITIONS = {"为", "是", "到", "至", "的", "秒", "毫秒", "存在", "不存在", "包含", "含", "不包含", "不含", "选中", "选为", "文件", "元素", "文本"}

# 断言子命令
ASSERT_SUBS = {"页面包含", "页面不包含", "页面含", "页面不含", "标题为", "标题是", "标题包含", "标题含", "网址包含", "网址含", "元素存在", "元素不存在"}


class HanHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._kw_fmt = QTextCharFormat()
        self._kw_fmt.setForeground(QColor("#c678dd"))  # 紫色关键字
        self._kw_fmt.setFontWeight(QFont.Weight.Bold)

        self._prep_fmt = QTextCharFormat()
        self._prep_fmt.setForeground(QColor("#e5c07b"))  # 黄色介词

        self._str_fmt = QTextCharFormat()
        self._str_fmt.setForeground(QColor("#98c379"))  # 绿色字符串

        self._comment_fmt = QTextCharFormat()
        self._comment_fmt.setForeground(QColor("#5c6370"))  # 灰色注释
        self._comment_fmt.setFontItalic(True)

        self._num_fmt = QTextCharFormat()
        self._num_fmt.setForeground(QColor("#d19a66"))  # 橙色数字

        self._var_fmt = QTextCharFormat()
        self._var_fmt.setForeground(QColor("#61afef"))  # 蓝色变量

        self._flow_fmt = QTextCharFormat()
        self._flow_fmt.setForeground(QColor("#56b6c2"))  # 青色流程控制
        self._flow_fmt.setFontWeight(QFont.Weight.Bold)

    def highlightBlock(self, text: str) -> None:  # noqa: N802 (Qt API)
        stripped = text.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            self.setFormat(0, len(text), self._comment_fmt)
            return

        # 行内注释
        comment_idx = -1
        for marker in (" # ", " // ", "\t# ", "\t// "):
            idx = text.find(marker)
            if idx != -1 and (comment_idx == -1 or idx < comment_idx):
                comment_idx = idx
        code_part = text if comment_idx == -1 else text[:comment_idx]
        if comment_idx != -1:
            self.setFormat(comment_idx, len(text) - comment_idx, self._comment_fmt)

        # 简易分词高亮
        i = 0
        n = len(code_part)
        while i < n:
            ch = code_part[i]
            if ch.isspace():
                i += 1
                continue

            # 字符串
            if ch in "\"'":
                j = i + 1
                while j < n and code_part[j] != ch:
                    if code_part[j] == "\\":
                        j += 1
                    j += 1
                j = min(j + 1, n)
                self.setFormat(i, j - i, self._str_fmt)
                i = j
                continue

            # 词
            j = i
            while j < n and not code_part[j].isspace() and code_part[j] not in "\"'":
                j += 1
            word = code_part[i:j]

            if word in FLOW_KEYWORDS:
                self.setFormat(i, j - i, self._flow_fmt)
            elif word in KEYWORDS or word in ASSERT_SUBS:
                self.setFormat(i, j - i, self._kw_fmt)
            elif word in PREPOSITIONS:
                self.setFormat(i, j - i, self._prep_fmt)
            else:
                try:
                    float(word)
                except ValueError:
                    pass
                else:
                    self.setFormat(i, j - i, self._num_fmt)
            i = j
