$ErrorActionPreference = 'Stop'
$appName = ([char]0x54F2).ToString() + ([char]0x5E97) + ([char]0x957F) + ([char]0x5DE5) + ([char]0x4F5C) + ([char]0x53F0)
$installation = Join-Path $PSScriptRoot ('desktop\' + $appName)
$application = Join-Path $installation ($appName + '.exe')
if (-not (Test-Path -LiteralPath $application)) { throw 'Extract the full Windows release ZIP before restoring.' }
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'tasks.db'))) { throw 'The task database is missing.' }
$location = @{project_root = $PSScriptRoot} | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $installation 'project-location.json'), $location, (New-Object Text.UTF8Encoding($false)))
& (Join-Path $PSScriptRoot 'install_desktop_shortcut.ps1')
Write-Output 'Desktop shortcut restored. Double-click it to open the workbench.'
