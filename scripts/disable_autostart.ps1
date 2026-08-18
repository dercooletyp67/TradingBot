# Removes the Startup-folder shortcut that launches TradingBot at login.
# Does not stop an already-running bot -- run stop_tradingbot.ps1 for that.

$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "TradingBotAutoStart.lnk"

if (Test-Path $shortcutPath) {
    Remove-Item $shortcutPath
    Write-Host "Removed auto-start shortcut. The bot will no longer launch automatically at login."
} else {
    Write-Host "No auto-start shortcut found -- it's already disabled."
}
