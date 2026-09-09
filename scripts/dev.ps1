[CmdletBinding()]
param(
    [string]$HostAddress = "0.0.0.0",
    [int]$Port = 8765
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "windows-common.ps1")

$EnvPath = Join-Path $RootDir ".env"
Import-DotEnv -Path $EnvPath

if ($HostAddress -ne "127.0.0.1" -and (Test-PlaceholderToken $env:VIBE_STICK_BRIDGE_TOKEN)) {
    throw "VIBE_STICK_BRIDGE_TOKEN is required when the bridge listens outside loopback. Run .\scripts\setup.ps1."
}

$env:PYTHONPATH = Join-Path $RootDir "bridge\src"
$python = Get-PythonCommand
Set-Location (Join-Path $RootDir "bridge")
& $python -m vibe_stick --host $HostAddress --port $Port
exit $LASTEXITCODE
