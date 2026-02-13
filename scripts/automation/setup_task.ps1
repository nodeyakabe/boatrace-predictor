# Windowsタスクスケジューラー登録スクリプト (PowerShell版)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "ボートレース自動化システム - Windowsタスク登録" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# プロジェクトルートのパス
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Write-Host "INFO: プロジェクトルート: $ProjectRoot" -ForegroundColor Green

# Pythonのパスを取得
$PythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source

if (-not $PythonPath) {
    Write-Host "ERROR: Pythonが見つかりません" -ForegroundColor Red
    Write-Host "Pythonをインストールしてください" -ForegroundColor Red
    Read-Host "Enterキーを押して終了"
    exit 1
}

Write-Host "INFO: Python: $PythonPath" -ForegroundColor Green
Write-Host ""

# daily_scheduler.pyのパス
$ScriptPath = Join-Path $ProjectRoot "scripts\automation\daily_scheduler.py"

if (-not (Test-Path $ScriptPath)) {
    Write-Host "ERROR: daily_scheduler.pyが見つかりません" -ForegroundColor Red
    Write-Host "パス: $ScriptPath" -ForegroundColor Red
    Read-Host "Enterキーを押して終了"
    exit 1
}

Write-Host "INFO: スクリプト: $ScriptPath" -ForegroundColor Green
Write-Host ""

# 既存のタスクを削除（エラーは無視）
Write-Host "既存のタスクを削除中..." -ForegroundColor Yellow
try {
    Unregister-ScheduledTask -TaskName "BoatRace_AutomationSystem" -Confirm:$false -ErrorAction SilentlyContinue
} catch {
    # エラーは無視
}
Write-Host ""

# アクション: Pythonでdaily_scheduler.pyを実行
$Action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument "`"$ScriptPath`"" `
    -WorkingDirectory $ProjectRoot

# トリガー: システム起動時
$Trigger = New-ScheduledTaskTrigger -AtStartup

# プリンシパル: 最高権限で実行
$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

# 設定
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

# タスクを登録
Write-Host "タスクを登録中..." -ForegroundColor Yellow
try {
    Register-ScheduledTask `
        -TaskName "BoatRace_AutomationSystem" `
        -Action $Action `
        -Trigger $Trigger `
        -Principal $Principal `
        -Settings $Settings `
        -Description "ボートレース自動収集・予想生成システム" `
        -Force

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "OK: タスク登録完了" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "タスク名: BoatRace_AutomationSystem" -ForegroundColor White
    Write-Host "実行タイミング: システム起動時" -ForegroundColor White
    Write-Host ""
    Write-Host "確認方法:" -ForegroundColor Cyan
    Write-Host "  1. タスクスケジューラーを開く" -ForegroundColor White
    Write-Host "  2. 'BoatRace_AutomationSystem'を検索" -ForegroundColor White
    Write-Host ""
    Write-Host "手動実行方法:" -ForegroundColor Cyan
    Write-Host "  Start-ScheduledTask -TaskName 'BoatRace_AutomationSystem'" -ForegroundColor White
    Write-Host ""
    Write-Host "削除方法:" -ForegroundColor Cyan
    Write-Host "  Unregister-ScheduledTask -TaskName 'BoatRace_AutomationSystem'" -ForegroundColor White
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green

} catch {
    Write-Host ""
    Write-Host "ERROR: タスク登録失敗" -ForegroundColor Red
    Write-Host "エラー: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "管理者権限でPowerShellを起動してください" -ForegroundColor Yellow
}

Write-Host ""
Read-Host "Enterキーを押して終了"
