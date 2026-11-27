param([ValidateSet('start', 'stop', 'status')][string]$Action = 'start')
$ErrorActionPreference = 'Stop'
$botRoot = $PSScriptRoot
$botScript = Join-Path $botRoot 'animeSuggest.py'
$botPython = Join-Path $botRoot '.venv\Scripts\python.exe'
$botPidFile = Join-Path $botRoot 'bot.pid'
# Check the full script path before touching a process; PID files can become stale.
$botProcesses = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -and $_.CommandLine.Contains($botScript)
})
if ($Action -eq 'status') {
    if ($botProcesses.Count) { Write-Output 'Anime bot is running.' }
    else { Write-Output 'Anime bot is stopped.' }
    exit 0
}
if ($Action -eq 'stop') {
    foreach ($botProcess in $botProcesses) { Stop-Process -Id $botProcess.ProcessId -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $botPidFile) { Remove-Item -LiteralPath $botPidFile }
    Write-Output 'Anime bot stopped.'
    exit 0
}
if ($botProcesses.Count) { Write-Output 'Anime bot is already running.'; exit 0 }
if (-not (Test-Path -LiteralPath $botPython)) { throw 'Create .venv and install requirements.txt first. See README.md.' }
if (-not (Test-Path -LiteralPath (Join-Path $botRoot '.env'))) { throw 'Save TELEGRAM_BOT_TOKEN in .env first.' }
$botProcess = Start-Process -FilePath $botPython -ArgumentList @('-u', ('"' + $botScript + '"')) `
    -WorkingDirectory $botRoot -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $botRoot 'bot.stdout.log') `
    -RedirectStandardError (Join-Path $botRoot 'bot.stderr.log') -PassThru
Set-Content -LiteralPath $botPidFile -Value $botProcess.Id
Start-Sleep -Seconds 2
if ($botProcess.HasExited) { throw 'Bot startup failed. Check bot.stderr.log.' }
Write-Output 'Anime bot started in the background. Logs: bot.stderr.log'
