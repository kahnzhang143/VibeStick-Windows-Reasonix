[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

$RootDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "windows-common.ps1")

$EnvPath = Join-Path $RootDir ".env"
$SecretsPath = Join-Path $RootDir "firmware\sticks3\include\vibe_stick_secrets.h"
$script:PassCount = 0
$script:WarnCount = 0
$script:FailCount = 0

function Write-Pass([string]$Message) {
    $script:PassCount++
    Write-Host "PASS $Message" -ForegroundColor Green
}

function Write-Warn([string]$Message) {
    $script:WarnCount++
    Write-Host "WARN $Message" -ForegroundColor Yellow
}

function Write-Fail([string]$Message) {
    $script:FailCount++
    Write-Host "FAIL $Message" -ForegroundColor Red
}

try {
    $python = Get-PythonCommand
    $versionText = & $python -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    $supported = & $python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    if ($LASTEXITCODE -eq 0) {
        Write-Pass "Python $versionText is available."
    } else {
        Write-Fail "Python 3.11 or newer is required; found $versionText."
    }
} catch {
    Write-Fail $_.Exception.Message
}

if (Get-Command reasonix -ErrorAction SilentlyContinue) {
    Write-Pass "Reasonix is available on PATH."
} else {
    Write-Fail "Reasonix is not on PATH. Install it with: npm install -g reasonix"
}

if (Test-Path -LiteralPath $EnvPath) {
    Write-Pass ".env exists."
} else {
    Write-Fail ".env is missing; run .\scripts\setup.ps1."
}

if (Test-Path -LiteralPath $SecretsPath) {
    Write-Pass "Firmware secrets exist."
} else {
    Write-Fail "Firmware secrets are missing; run .\scripts\setup.ps1."
}

if ((Test-Path -LiteralPath $EnvPath) -and (Test-Path -LiteralPath $SecretsPath)) {
    $envToken = Get-DotEnvValue -Path $EnvPath -Key "VIBE_STICK_BRIDGE_TOKEN"
    $secretToken = Get-HeaderDefine -Path $SecretsPath -Key "VIBE_STICK_BRIDGE_TOKEN"
    if (Test-PlaceholderToken $envToken) {
        Write-Fail "The bridge token is empty or a placeholder."
    } elseif ($envToken -ne $secretToken) {
        Write-Fail "The bridge token differs between .env and firmware secrets."
    } else {
        Write-Pass "The bridge token is configured and synchronized."
    }

    $bridgeHost = Get-HeaderDefine -Path $SecretsPath -Key "VIBE_STICK_BRIDGE_HOST"
    if (Test-PlaceholderHost $bridgeHost) {
        Write-Fail "The firmware bridge host is empty, loopback, or a placeholder."
    } else {
        Write-Pass "Firmware bridge host is $bridgeHost."
    }

    $provider = Get-DotEnvValue -Path $EnvPath -Key "VIBE_STICK_PROVIDER"
    if ($provider -eq "reasonix") {
        Write-Pass "Reasonix is the selected provider."
    } else {
        Write-Warn "VIBE_STICK_PROVIDER is '$provider'; expected 'reasonix'."
    }

    $asrKey = Get-DotEnvValue -Path $EnvPath -Key "VIBE_STICK_ASR_API_KEY"
    $transcribeCommand = Get-DotEnvValue -Path $EnvPath -Key "VIBE_STICK_TRANSCRIBE_CMD"
    if ($asrKey -or $transcribeCommand) {
        Write-Pass "An ASR provider or local transcription command is configured."
    } else {
        Write-Fail "Configure VIBE_STICK_ASR_API_KEY or VIBE_STICK_TRANSCRIBE_CMD."
    }
}

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8765/health" -TimeoutSec 2
    if ($health.ok) {
        Write-Pass "Bridge health endpoint responded."
    } else {
        Write-Warn "Bridge health endpoint returned an unexpected response."
    }
} catch {
    Write-Warn "Bridge is not responding on 127.0.0.1:8765."
}

Write-Host ""
Write-Host "Summary: PASS=$script:PassCount WARN=$script:WarnCount FAIL=$script:FailCount"
if ($script:FailCount -gt 0) {
    exit 1
}
