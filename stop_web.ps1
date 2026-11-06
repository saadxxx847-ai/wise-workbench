$ErrorActionPreference = 'Stop'
$pidFile = Join-Path $PSScriptRoot '.web.pid'
if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Host 'The workbench is not running (no PID file).'
    exit 0
}
$webProcessId = [int](Get-Content -LiteralPath $pidFile -Raw)
$webProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $webProcessId"
if ($null -eq $webProcess) {
    Remove-Item -LiteralPath $pidFile
    Write-Host 'The workbench has already stopped.'
    exit 0
}
$expectedPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$baseHomeLine = Get-Content -LiteralPath (Join-Path $PSScriptRoot '.venv\pyvenv.cfg') | Where-Object { $_ -match '^home\s*=' } | Select-Object -First 1
$basePython = Join-Path (($baseHomeLine -split '=',2)[1].Trim()) 'python.exe'
$expectedScript = Join-Path $PSScriptRoot 'run_web.py'
if ((($webProcess.ExecutablePath -ine $expectedPython) -and ($webProcess.ExecutablePath -ine $basePython)) -or
    ($webProcess.CommandLine -notmatch [regex]::Escape($expectedScript))) {
    throw 'Process identity did not match this workbench; no process was stopped.'
}
Stop-Process -Id $webProcessId
Remove-Item -LiteralPath $pidFile
Write-Host 'Workbench stopped. Successful operations are already saved.'
