param(
  [ValidateSet("Install", "Show", "Run", "Disable", "Delete")]
  [string]$Action = "Show",
  [string]$BackupDirectory = "backups",
  [int]$Keep = 10,
  [string]$DailyAt = "02:00"
)
$ErrorActionPreference = "Stop"
$taskName = "YunxunDailyBackup"
$root = Split-Path -Parent $PSScriptRoot
$command = "Set-Location '$root'; python scripts/database_admin.py backup --dir '$BackupDirectory' --keep $Keep"
switch ($Action) {
  "Install" {
    $taskAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -NonInteractive -Command `"$command`""
    $trigger = New-ScheduledTaskTrigger -Daily -At $DailyAt
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $trigger -Settings $settings -Description "Yunxun SQLite verified backup" -Force | Out-Null
  }
  "Show" { Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue }
  "Run" { Start-ScheduledTask -TaskName $taskName }
  "Disable" { Disable-ScheduledTask -TaskName $taskName | Out-Null }
  "Delete" { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false }
}
