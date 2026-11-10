[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]$Python,
    [Parameter(Mandatory)][string]$Config,
    [Parameter(Mandatory)][PSCredential]$Credential,
    [string]$TaskName = 'ECPA-MCP-Gateway'
)
$ErrorActionPreference = 'Stop'
foreach ($file in @($Python,$Config)) {
    if (-not [IO.Path]::IsPathRooted($file) -or -not (Test-Path -LiteralPath $file -PathType Leaf) -or $file.Contains('"')) { throw 'Use valid absolute file paths.' }
}
$cfg = Get-Content -LiteralPath $Config -Raw | ConvertFrom-Json
$account = New-Object Security.Principal.NTAccount($Credential.UserName)
$sid = $account.Translate([Security.Principal.SecurityIdentifier]).Value
if ($cfg.runtime_identity -ne $sid) { throw 'Task account must match the Windows identity that initialized this runtime and its vault.' }
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { throw 'Task already exists. Review it explicitly before replacing a running service.' }
$action = New-ScheduledTaskAction -Execute $Python -Argument ('-m ecpa_gateway.cli --config "{0}" serve' -f $Config) -WorkingDirectory (Split-Path $Config -Parent)
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
if ($PSCmdlet.ShouldProcess($TaskName,'Register password-logon startup task; no interactive desktop required')) {
    # Task Scheduler needs the account password for a noninteractive logon with its vault.
    # Never log this value or use S4U/InteractiveToken as a silent fallback.
    $plain = $Credential.GetNetworkCredential().Password
    try {
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -User $Credential.UserName -Password $plain -RunLevel Limited | Out-Null
    } finally { $plain = $null }
    Write-Output 'Task registered, not started. Start it, run doctor --protocol, then perform the sign-out/reboot acceptance checks in HOST-READINESS.md.'
}
