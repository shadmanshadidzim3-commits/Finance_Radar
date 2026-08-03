<#
    Registers Finance Radar as a Windows scheduled task so it runs by itself
    every day. Run this once, from this folder:

        powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1

    To remove it later:

        powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1 -Remove
#>

param(
    [switch]$Remove,
    [string]$Time,
    [string]$TaskName = "FinanceRadar Daily"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition

if ($Remove) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed scheduled task '$TaskName'." -ForegroundColor Yellow
    } else {
        Write-Host "No scheduled task named '$TaskName' was found." -ForegroundColor Yellow
    }
    return
}

# Read the run time from config.yaml unless one was passed in.
if (-not $Time) {
    $configPath = Join-Path $root "config.yaml"
    $Time = "19:30"
    if (Test-Path $configPath) {
        $match = Select-String -Path $configPath -Pattern 'daily_time:\s*"?(\d{1,2}:\d{2})"?'
        if ($match) { $Time = $match.Matches[0].Groups[1].Value }
    }
}

$python = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $python)) { $python = Join-Path $root ".venv\Scripts\python.exe" }
if (-not (Test-Path $python)) {
    throw "No virtual environment found. Run setup.ps1 first."
}

$script = Join-Path $root "run_daily.py"
if (-not (Test-Path $script)) { throw "run_daily.py not found in $root" }

$action    = New-ScheduledTaskAction -Execute $python -Argument "`"$script`"" -WorkingDirectory $root
$trigger   = New-ScheduledTaskTrigger -Daily -At $Time
# -WakeToRun pulls the machine out of sleep or hibernation at the scheduled
# time. It cannot help if the laptop is fully shut down — nothing on the
# machine is running then, so nothing can wake it. Sleep, don't shut down.
$settings  = New-ScheduledTaskSettingsSet `
                -StartWhenAvailable `
                -WakeToRun `
                -DontStopIfGoingOnBatteries `
                -AllowStartIfOnBatteries `
                -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
                -RestartCount 2 `
                -RestartInterval (New-TimeSpan -Minutes 15)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Finance Radar: collects financial news and market data, analyses it, and writes the daily brief." | Out-Null

Write-Host ""
Write-Host "Finance Radar is scheduled." -ForegroundColor Green
Write-Host "  Task     : $TaskName"
Write-Host "  Runs     : every day at $Time"
Write-Host "  Python   : $python"
Write-Host ""
Write-Host "'StartWhenAvailable' is on, so if your PC is off at $Time the run happens"
Write-Host "when you next switch it on."
Write-Host ""
Write-Host "Run it right now to test:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Remove it later:           .\install_schedule.ps1 -Remove"
