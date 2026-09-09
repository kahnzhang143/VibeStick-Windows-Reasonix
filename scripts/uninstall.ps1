[CmdletBinding()]
param(
    [switch]$RemoveData
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "windows-common.ps1")

$TaskName = "VibeStick Bridge"
$ConfigDir = Join-Path $HOME ".vibestick"
$ReasonixPidPath = Join-Path $ConfigDir "reasonix\pid"
$ReasonixTokenPath = Join-Path $ConfigDir "reasonix\token"

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed the VibeStick Bridge scheduled task."
} else {
    Write-Host "The VibeStick Bridge scheduled task was not installed."
}

Stop-VibeStickBridgeListener

Stop-ManagedReasonixProcess -PidPath $ReasonixPidPath -TokenPath $ReasonixTokenPath
Write-Host "Stopped the managed Reasonix Serve process when its identity matched."

if ($RemoveData -and (Test-Path -LiteralPath $ConfigDir)) {
    Remove-Item -LiteralPath $ConfigDir -Recurse -Force
    Write-Host "Removed VibeStick runtime data from $ConfigDir."
} else {
    Write-Host "Kept VibeStick configuration and recordings in $ConfigDir."
}
