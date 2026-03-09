$action = New-ScheduledTaskAction -Execute 'C:\Python313\python.exe' -Argument 'run_odds_exhibition_補完.py' -WorkingDirectory 'C:\Users\User\Desktop\BR\BoatRace_package_20251115_172032'
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 72)
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(5)
Register-ScheduledTask -TaskName 'BoatRace_OddsExhibition' -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName 'BoatRace_OddsExhibition'
Write-Host "Task started"
