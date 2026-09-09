[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "windows-common.ps1")

$EnvPath = Join-Path $RootDir ".env"
$EnvExamplePath = Join-Path $RootDir ".env.example"
$SecretsPath = Join-Path $RootDir "firmware\sticks3\include\vibe_stick_secrets.h"
$SecretsExamplePath = Join-Path $RootDir "firmware\sticks3\include\vibe_stick_secrets.example.h"

if (-not (Test-Path -LiteralPath $EnvPath)) {
    Copy-Item -LiteralPath $EnvExamplePath -Destination $EnvPath
    Write-Host "Created .env from .env.example."
} else {
    Write-Host "Kept existing .env."
}

if (-not (Test-Path -LiteralPath $SecretsPath)) {
    Copy-Item -LiteralPath $SecretsExamplePath -Destination $SecretsPath
    Write-Host "Created firmware secrets from the example."
} else {
    Write-Host "Kept existing firmware secrets."
}

$envToken = Get-DotEnvValue -Path $EnvPath -Key "VIBE_STICK_BRIDGE_TOKEN"
$secretToken = Get-HeaderDefine -Path $SecretsPath -Key "VIBE_STICK_BRIDGE_TOKEN"

if (-not (Test-PlaceholderToken $envToken) -and -not (Test-PlaceholderToken $secretToken)) {
    if ($envToken -eq $secretToken) {
        Write-Host "Bridge token is already synchronized."
    } else {
        Write-Warning "Bridge tokens differ; existing non-placeholder values were preserved."
    }
} elseif (-not (Test-PlaceholderToken $envToken)) {
    Set-HeaderDefine -Path $SecretsPath -Key "VIBE_STICK_BRIDGE_TOKEN" -Value $envToken
    Write-Host "Copied the .env bridge token into firmware secrets."
} elseif (-not (Test-PlaceholderToken $secretToken)) {
    Set-DotEnvValue -Path $EnvPath -Key "VIBE_STICK_BRIDGE_TOKEN" -Value $secretToken
    Write-Host "Copied the firmware bridge token into .env."
} else {
    $token = New-BridgeToken
    Set-DotEnvValue -Path $EnvPath -Key "VIBE_STICK_BRIDGE_TOKEN" -Value $token
    Set-HeaderDefine -Path $SecretsPath -Key "VIBE_STICK_BRIDGE_TOKEN" -Value $token
    Write-Host "Generated and synchronized a bridge token."
}

Set-DotEnvValue -Path $EnvPath -Key "VIBE_STICK_PROVIDER" -Value "reasonix"
Set-DotEnvValue -Path $EnvPath -Key "VIBE_STICK_REASONIX_MANAGE_SERVE" -Value "1"
Set-DotEnvValue -Path $EnvPath -Key "VIBE_STICK_RECORDING_USE_MAC_MIC" -Value "0"

$lanIp = Get-PreferredLanIPv4
$bridgeHost = Get-HeaderDefine -Path $SecretsPath -Key "VIBE_STICK_BRIDGE_HOST"
if ($lanIp) {
    Write-Host "Detected Windows LAN IPv4: $lanIp"
    if (Test-PlaceholderHost $bridgeHost) {
        Set-HeaderDefine -Path $SecretsPath -Key "VIBE_STICK_BRIDGE_HOST" -Value $lanIp
        Write-Host "Updated the firmware bridge host."
    } elseif ($bridgeHost -ne $lanIp) {
        Write-Warning "Firmware bridge host is $bridgeHost, but the detected address is $lanIp."
    }
} else {
    Write-Warning "Could not detect a LAN IPv4 address. Configure VIBE_STICK_BRIDGE_HOST manually."
}

Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Edit firmware\sticks3\include\vibe_stick_secrets.h and set the 2.4 GHz Wi-Fi credentials."
Write-Host "2. Edit .env and configure the ASR provider and API key."
Write-Host "3. Run .\scripts\doctor.ps1."
