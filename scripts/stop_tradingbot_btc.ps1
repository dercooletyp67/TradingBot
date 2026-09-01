# Stops whatever start_tradingbot_btc.ps1 started, using the PID file it wrote.

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pidFile = Join-Path $root "scripts\tradingbot_btc.pids"

if (-not (Test-Path $pidFile)) {
    Write-Host "No PID file found -- nothing to stop (or it wasn't started via the script)."
    exit
}

Get-Content $pidFile | ForEach-Object {
    $procId = $_.Trim()
    if (-not $procId) { return }
    try {
        Stop-Process -Id $procId -Force -ErrorAction Stop
        Write-Host "Stopped PID $procId"
    } catch {
        Write-Host "PID $procId was not running."
    }
}
Remove-Item $pidFile
