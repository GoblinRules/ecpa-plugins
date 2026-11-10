[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$Destination,
    [Parameter(Mandatory)][string]$Helper,
    [Parameter(Mandatory)][string]$Bws,
    [Parameter(Mandatory)][ValidatePattern('^[a-z][a-z0-9-]{0,39}$')][string]$HostId,
    [string]$DataDirectory,
    [int]$Port = 8769
)
$ErrorActionPreference = 'Stop'
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Choose an unprivileged port.' }
foreach ($file in @($Python,$Helper,$Bws)) {
    if (-not [IO.Path]::IsPathRooted($file) -or -not (Test-Path -LiteralPath $file -PathType Leaf)) { throw 'Executable paths must be absolute existing files.' }
}
$target = [IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $target) { throw 'Use a new version directory. Existing runtime files and credentials will not be overwritten.' }
$source = Split-Path $PSScriptRoot -Parent
if (-not $DataDirectory) { $DataDirectory = Join-Path $target 'data' }
if (-not [IO.Path]::IsPathRooted($DataDirectory)) { throw 'DataDirectory must be absolute.' }
$config = Join-Path $DataDirectory 'gateway-runtime.json'
if (Test-Path -LiteralPath $config) { throw 'Runtime already configured; existing identities were preserved.' }
New-Item -ItemType Directory -Path $target | Out-Null
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
# Runtime config/backups may contain client configuration; restrict the entire tree.
& icacls.exe $target /inheritance:r /grant:r "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not restrict runtime directory ACL.' }
& $Python -m venv (Join-Path $target 'venv')
if ($LASTEXITCODE -ne 0) { throw 'Python venv creation failed.' }
$runtimePython = Join-Path $target 'venv\Scripts\python.exe'
& $runtimePython -m pip install --only-binary=:all: -r (Join-Path $source 'requirements-windows.lock')
if ($LASTEXITCODE -ne 0) { throw 'Locked dependency installation failed.' }
& $runtimePython -m pip install --no-deps --no-build-isolation $source
if ($LASTEXITCODE -ne 0) { throw 'Gateway package installation failed.' }
Copy-Item -LiteralPath $Helper -Destination (Join-Path $target 'ecpa-connect.exe')
& $runtimePython -m ecpa_gateway.cli --config $config init --helper (Join-Path $target 'ecpa-connect.exe') --bws $Bws --host-id $HostId --port $Port
if ($LASTEXITCODE -ne 0) { throw 'Runtime initialization failed.' }
Write-Output "Installed under $target. Credentials belong to Windows SID $sid. No task, firewall rule or remote deployment was created."
Write-Output 'Next: bootstrap Bitwarden under this identity, run doctor, test the worker, then register unattended startup.'
