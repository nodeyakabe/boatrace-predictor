# ================================================
# Phase 2.5 自動モニタリング タスクスケジューラ設定
# ================================================
#
# 使用方法（管理者権限で実行）:
#   .\setup_monitoring_task.ps1 -Action create
#   .\setup_monitoring_task.ps1 -Action remove
#   .\setup_monitoring_task.ps1 -Action status
#
# ================================================

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("create", "remove", "status")]
    [string]$Action
)

$TaskName = "BoatRace_AutoMonitoring"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
$PythonPath = "python"
$ScriptPath = Join-Path $ProjectRoot "scripts\automated_monitoring.py"

function Create-MonitoringTask {
    Write-Host "================================================"
    Write-Host "自動モニタリングタスクを作成中..."
    Write-Host "================================================"
    Write-Host ""

    # 既存タスクの削除
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Write-Host "既存タスクを削除中..."
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    # アクション定義
    $Action = New-ScheduledTaskAction `
        -Execute $PythonPath `
        -Argument """$ScriptPath""" `
        -WorkingDirectory $ProjectRoot

    # トリガー定義（毎日23:30に実行）
    $Trigger = New-ScheduledTaskTrigger -Daily -At "23:30"

    # 設定定義
    $Settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Hours 1)

    # タスク登録
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Description "BoatRace パターンシステム自動モニタリング（Phase 2.5）"

    Write-Host ""
    Write-Host "タスク作成完了: $TaskName"
    Write-Host "  実行時刻: 毎日 23:30"
    Write-Host "  スクリプト: $ScriptPath"
    Write-Host ""
}

function Remove-MonitoringTask {
    Write-Host "================================================"
    Write-Host "自動モニタリングタスクを削除中..."
    Write-Host "================================================"
    Write-Host ""

    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "タスク削除完了: $TaskName"
    } else {
        Write-Host "タスクが存在しません: $TaskName"
    }
    Write-Host ""
}

function Get-MonitoringTaskStatus {
    Write-Host "================================================"
    Write-Host "自動モニタリングタスクの状態"
    Write-Host "================================================"
    Write-Host ""

    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existingTask) {
        Write-Host "タスク名: $TaskName"
        Write-Host "状態: $($existingTask.State)"

        $taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName
        Write-Host "前回実行: $($taskInfo.LastRunTime)"
        Write-Host "次回実行: $($taskInfo.NextRunTime)"
        Write-Host "前回結果: $($taskInfo.LastTaskResult)"
    } else {
        Write-Host "タスクが登録されていません: $TaskName"
        Write-Host ""
        Write-Host "登録するには以下を実行:"
        Write-Host "  .\setup_monitoring_task.ps1 -Action create"
    }
    Write-Host ""
}

# メイン処理
switch ($Action) {
    "create" { Create-MonitoringTask }
    "remove" { Remove-MonitoringTask }
    "status" { Get-MonitoringTaskStatus }
}
