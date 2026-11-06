$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$script = Join-Path $PSScriptRoot 'run_web.py'
$process = Start-Process -FilePath $python -ArgumentList @('-X', 'utf8', ('"{0}"' -f $script)) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'web.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'web.stderr.log') -PassThru
Write-Host "Started workbench process $($process.Id). Open http://127.0.0.1:5000"
