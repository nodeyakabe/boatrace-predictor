$action = New-ScheduledTaskAction -Execute 'C:\Python313\python.exe' -Argument 'run_2025_all.py' -WorkingDirectory 'C:\Users\User\Desktop\BR\BoatRace_package_20251115_172032'
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 48)
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(5)
Register-ScheduledTask -TaskName 'BoatRace_2025_v2' -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName 'BoatRace_2025_v2'
Write-Host "Task started"
