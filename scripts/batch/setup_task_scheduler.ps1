# タスクスケジューラ自動設定スクリプト
# 管理者権限で実行してください

# 設定値
$TaskName = "BoatRace_Daily_Tenji_Collection"
$Description = "ボートレースオリジナル展示データの日次自動収集"
$ScriptPath = Join-Path $PSScriptRoot "run_daily_tenji_collection.bat"
$WorkingDirectory = $PSScriptRoot

# 既存のタスクを削除（存在する場合）
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "既存のタスク '$TaskName' を削除します..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# トリガー設定: 毎日20:00
$trigger = New-ScheduledTaskTrigger -Daily -At "20:00"

# アクション設定: バッチファイルを実行
$action = New-ScheduledTaskAction -Execute $ScriptPath -WorkingDirectory $WorkingDirectory

# プリンシパル設定: ユーザーがログオンしているときのみ実行
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

# 設定: 実行時間制限なし、電源投入時に実行
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)

# タスクを登録
Write-Host "タスク '$TaskName' を登録します..."
Register-ScheduledTask -TaskName $TaskName -Description $Description -Trigger $trigger -Action $action -Principal $principal -Settings $settings

Write-Host ""
Write-Host "タスクスケジューラの設定が完了しました！" -ForegroundColor Green
Write-Host ""
Write-Host "設定内容:" -ForegroundColor Cyan
Write-Host "  タスク名: $TaskName"
Write-Host "  実行時刻: 毎日 20:00"
Write-Host "  スクリプト: $ScriptPath"
Write-Host ""
Write-Host "確認方法: タスクスケジューラアプリを開いて確認してください"
Write-Host "  コマンド: taskschd.msc"
Write-Host ""
Write-Host "手動実行テスト:" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
