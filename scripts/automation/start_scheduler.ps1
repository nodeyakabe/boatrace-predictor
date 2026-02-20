$proj = "C:\Users\User\Desktop\BR\BoatRace_package_20251115_172032"
$logFile = "$proj\logs\scheduler_startup.log"
$errFile = "$proj\logs\scheduler_startup_err.log"

# 古いロックファイルを削除
Remove-Item "$proj\data\daily_scheduler.lock" -ErrorAction SilentlyContinue

# python.exe + Start-Process でターミナル独立プロセスとして起動
Start-Process -FilePath "C:\Python313\python.exe" -ArgumentList "$proj\scripts\automation\daily_scheduler.py" -WorkingDirectory $proj -WindowStyle Hidden -RedirectStandardOutput $logFile -RedirectStandardError $errFile

Start-Sleep -Seconds 6

$lockContent = Get-Content "$proj\data\daily_scheduler.lock" -ErrorAction SilentlyContinue
Write-Host "ロックファイルPID: $lockContent"

if ($lockContent) {
    $proc = Get-Process -Id ([int]$lockContent) -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "OK: PID=$($proc.Id) 起動=$($proc.StartTime) 名前=$($proc.ProcessName)"
    } else {
        Write-Host "NG: PID $lockContent は停止済み"
        Write-Host "--- エラーログ ---"
        Get-Content $errFile -Tail 20 -ErrorAction SilentlyContinue
    }
}
