# 双击入口的启动与错误提示；仅复用本项目环境，不下载或安装依赖。
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$entryPath = Join-Path $projectRoot 'note2lecture_gui.py'
$guidePath = Join-Path $projectRoot 'docs\quickstart-windows.md'

function Show-LauncherError {
    param([string]$Message)
    try {
        $popup = New-Object -ComObject WScript.Shell
        $null = $popup.Popup($Message, 0, 'Note2Lecture 启动提示', 16)
    }
    catch {
        Write-Error $Message
    }
}

try {
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        Show-LauncherError ("还没有可用的项目 Python 环境。`n`n" +
            "请先按首次使用指南创建 .venv，并安装 requirements-gui.txt。`n" +
            "配置一次后，以后双击即可启动。`n`n指南：" + $guidePath)
        exit 2
    }
    if (-not (Test-Path -LiteralPath $entryPath -PathType Leaf)) {
        Show-LauncherError ("缺少桌面入口 note2lecture_gui.py。`n请先完整解压项目文件。")
        exit 2
    }

    $logRoot = Join-Path $projectRoot '.cache\gui\launcher'
    $null = New-Item -ItemType Directory -Path $logRoot -Force
    $launchId = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N')
    $stdoutPath = Join-Path $logRoot ($launchId + '.stdout.log')
    $stderrPath = Join-Path $logRoot ($launchId + '.stderr.log')
    # 只影响此启动进程及子进程；不修改系统 PATH 或执行策略。
    $env:PYTHONIOENCODING = 'utf-8'
    $process = Start-Process -FilePath $pythonPath -ArgumentList @(
        '-X', 'utf8', ('"' + $entryPath + '"')
    ) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -Wait `
        -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath

    if ($process.ExitCode -ne 0) {
        $detail = Get-Content -LiteralPath $stderrPath -Encoding UTF8 |
            Where-Object { $_.Trim() } | Select-Object -Last 1
        if ($detail) {
            try {
                $report = $detail | ConvertFrom-Json
                if ($report.message) { $detail = $report.message }
            }
            catch { }
            if ($detail.Length -gt 600) { $detail = $detail.Substring(0, 600) }
        }
        Show-LauncherError ("窗口未能正常启动或异常退出。`n" + $detail + "`n`n" +
            "请检查 GUI 依赖、WebView2 与首次使用指南。`n" +
            "错误日志：" + $stderrPath + "`n指南：" + $guidePath)
        exit 2
    }
}
catch {
    Show-LauncherError ("无法准备启动环境。`n" + $_.Exception.Message + "`n`n指南：" + $guidePath)
    exit 2
}
exit 0
