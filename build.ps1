# 汉UI 打包脚本（Windows PowerShell）
# 用法：  .\build.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "═══════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  汉UI 打包工具  " -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════" -ForegroundColor Cyan

# 1. 检查 PyInstaller
Write-Host "`n[1/5] 检查 PyInstaller..." -ForegroundColor Yellow
$pyi = Get-Command pyinstaller -ErrorAction SilentlyContinue
if (-not $pyi) {
    Write-Host "  安装 PyInstaller..."
    pip install pyinstaller
} else {
    Write-Host "  已安装" -ForegroundColor Green
}

# 2. 打包
Write-Host "`n[2/5] 开始打包（约 1-3 分钟）..." -ForegroundColor Yellow
python -m PyInstaller hanui.spec --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ 打包失败" -ForegroundColor Red
    exit 1
}

# 3. 复制安装脚本和文档
Write-Host "`n[3/5] 复制安装脚本和文档..." -ForegroundColor Yellow
Copy-Item "scripts\安装文件关联.bat" -Destination "dist\hanui\"
Copy-Item "docs\使用说明.md" -Destination "dist\hanui\" -ErrorAction SilentlyContinue
Write-Host "  已复制" -ForegroundColor Green

# 4. 打 zip + 生成 SHA256
Write-Host "`n[4/5] 打包 zip + SHA256..." -ForegroundColor Yellow
$version = "v0.1.2"
$zipName = "hanui-$version-win64.zip"
$zipPath = "dist\$zipName"
Compress-Archive -Path "dist\hanui" -DestinationPath $zipPath -Force

$hash = (Get-FileHash $zipPath -Algorithm SHA256).Hash
$shaPath = "$zipPath.sha256"
"$hash  $zipName" | Out-File -FilePath $shaPath -Encoding ascii
Write-Host "  zip  →  $zipPath" -ForegroundColor Green
Write-Host "  sha  →  $shaPath" -ForegroundColor Green

# 完成
Write-Host "`n═══════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  打包完成！" -ForegroundColor Green
Write-Host "═══════════════════════════════════════" -ForegroundColor Cyan
Write-Host @"

产物:
  dist\$zipName              —— 分发 zip
  dist\$zipName.sha256       —— 校验文件
  dist\hanui\                —— 解压后目录

SHA256:
  $hash

分发方式:
  1. 发送 $zipName 和 .sha256 两个文件
  2. 对方校验:  Get-FileHash $zipName -Algorithm SHA256
  3. 解压后双击 安装文件关联.bat（仅需一次）
  4. 之后双击任意 .hrpa 文件即可运行

"@
