#!/usr/bin/env bash
# 汉UI 文件关联安装（macOS / Linux）
# 用法：  bash install-association.sh
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
EXE="$DIR/hanui"

echo "═══════════════════════════════════════"
echo "  汉UI 文件关联安装"
echo "═══════════════════════════════════════"

if [ ! -f "$EXE" ]; then
    echo "错误: 未找到 hanui 可执行文件"
    echo "请把此脚本放在 hanui 同一目录"
    exit 1
fi

chmod +x "$EXE"

echo ""
echo "将注册 .hrpa 文件关联 → $EXE"
echo "按 Enter 继续，Ctrl+C 取消..."
read -r

OS="$(uname -s)"

if [ "$OS" = "Darwin" ]; then
    # macOS: 用 duti 或者直接写 ~/Library/LaunchServices
    echo "检测到 macOS"
    # 创建简单的打开方式（通过 automator 不现实，改用 shell 脚本包装）
    cat > "$DIR/open-hrpa.command" <<EOF
#!/bin/bash
"$EXE" "\$1"
EOF
    chmod +x "$DIR/open-hrpa.command"
    echo ""
    echo "已创建 open-hrpa.command"
    echo "macOS 无法直接修改文件关联（需要 App 包或 duti）。"
    echo "替代方案：把 .hrpa 文件拖到 open-hrpa.command 上运行，"
    echo "或在终端执行: $EXE 脚本.hrpa"
elif [ "$OS" = "Linux" ]; then
    echo "检测到 Linux"
    DESKTOP_DIR="$HOME/.local/share/applications"
    mkdir -p "$DESKTOP_DIR"

    cat > "$DESKTOP_DIR/hanui.desktop" <<EOF
[Desktop Entry]
Name=汉UI
Comment=中文命令 RPA
Exec="$EXE" %f
Icon=application-x-executable
Terminal=false
Type=Application
MimeType=text/x-hrpa;
Categories=Utility;
EOF

    # 注册 MimeType
    mkdir -p "$HOME/.local/share/mime/packages"
    cat > "$HOME/.local/share/mime/packages/hanui.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="text/x-hrpa">
    <comment>汉UI 脚本</comment>
    <glob pattern="*.hrpa"/>
  </mime-type>
</mime-info>
EOF

    update-mime-database "$HOME/.local/share/mime" 2>/dev/null || true
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

    echo ""
    echo "已注册到 $DESKTOP_DIR/hanui.desktop"
    echo "现在双击 .hrpa 文件即可运行。"
fi

echo ""
echo "安装完成！"
