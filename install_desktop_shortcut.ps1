$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$appName = ([char]0x54F2).ToString() + ([char]0x5E97) + ([char]0x957F) + ([char]0x5DE5) + ([char]0x4F5C) + ([char]0x53F0)
$application = Join-Path $root ("desktop\{0}\{0}.exe" -f $appName)
if (-not (Test-Path -LiteralPath $application)) { throw 'Build the desktop application first.' }
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$shortcutPath = Join-Path $desktop ($appName + '.lnk')
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $application
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = $application + ',0'
$shortcut.Description = 'Random Play personal workbench'
$shortcut.WindowStyle = 1
$shortcut.Save()
$verified = $shell.CreateShortcut($shortcutPath)
if ($verified.TargetPath -ine $application) { throw 'Shortcut target verification failed.' }
Write-Output $shortcutPath
