#!/usr/bin/env bash
# 汉UI 打包脚本（macOS / Linux）
# 用法：  bash build.sh
set -euo pipefail

cd "$(dirname "$0")"
VERSION="v0.1.0"
PLATFORM="$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
if [ "$PLATFORM" = "darwin-arm64" ]; then PLATFORM="macos-arm64"; fi
if [ "$PLATFORM" = "darwin-x86_64" ]; then PLATFORM="macos-x64"; fi

echo "═══════════════════════════════════════"
echo "  汉UI 打包工具 ($PLATFORM)"
echo "═══════════════════════════════════════"

# 1. 依赖
echo -e "\n[1/5] 检查依赖..."
if ! command -v pyinstaller &>/dev/null; then
    pip install pyinstaller
fi
echo "  已就绪"

# 2. 测试
echo -e "\n[2/5] 运行测试..."
python -m pytest tests/ -q --ignore=tests/test_recorder_integration.py

# 3. 打包
echo -e "\n[3/5] 开始打包..."
python -m PyInstaller hanui.spec --noconfirm

# 4. 安装脚本 + 文档
echo -e "\n[4/5] 复制安装脚本和文档..."
cp scripts/install-association.sh dist/hanui/
cp "scripts/安装文件关联.bat" dist/hanui/ 2>/dev/null || true
cp docs/使用说明.md dist/hanui/ 2>/dev/null || true
chmod +x dist/hanui/install-association.sh

# 5. zip + SHA256
echo -e "\n[5/5] 打包 zip + SHA256..."
cd dist
ZIPNAME="hanui-${VERSION}-${PLATFORM}.zip"
zip -r "$ZIPNAME" hanui/
HASH=$(shasum -a 256 "$ZIPNAME" | awk '{print $1}')
echo "$HASH  $ZIPNAME" > "$ZIPNAME.sha256"

echo ""
echo "═══════════════════════════════════════"
echo "  打包完成！"
echo "═══════════════════════════════════════"
echo ""
echo "产物:"
echo "  dist/$ZIPNAME              —— 分发 zip"
echo "  dist/$ZIPNAME.sha256       —— 校验文件"
echo ""
echo "SHA256:"
echo "  $HASH"
echo ""
echo "分发方式:"
echo "  1. 发送 $ZIPNAME 和 .sha256 两个文件"
echo "  2. 对方校验: shasum -a 256 $ZIPNAME"
echo "  3. 解压后运行 ./install-association.sh（仅需一次）"
echo "  4. 之后双击任意 .hrpa 文件即可运行"
echo ""
