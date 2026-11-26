param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    throw "未找到 .venv 虚拟环境，请先按 README 完成依赖安装。"
}

if (-not (Test-Path ".\frontend\dist\index.html")) {
    Write-Host "未检测到前端构建产物，正在构建..." -ForegroundColor Yellow
    Push-Location ".\frontend"
    try {
        npm install
        npm run build
    }
    finally {
        Pop-Location
    }
}

$env:OA_PORT = "$Port"
Write-Host "绵绵聚道已启动：http://127.0.0.1:$Port" -ForegroundColor Green
& ".\.venv\Scripts\python.exe" ".\main.py"
