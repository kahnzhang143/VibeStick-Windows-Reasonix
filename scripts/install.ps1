[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "windows-common.ps1")
& (Join-Path $PSScriptRoot "setup.ps1")

$EnvPath = Join-Path $RootDir ".env"
$SecretsPath = Join-Path $RootDir "firmware\sticks3\include\vibe_stick_secrets.h"
$envToken = Get-DotEnvValue -Path $EnvPath -Key "VIBE_STICK_BRIDGE_TOKEN"
$secretToken = Get-HeaderDefine -Path $SecretsPath -Key "VIBE_STICK_BRIDGE_TOKEN"
if (Test-PlaceholderToken $envToken) {
    throw "VIBE_STICK_BRIDGE_TOKEN is missing from .env."
}
if ($envToken -ne $secretToken) {
    throw "The bridge token differs between .env and firmware secrets."
}

$ConfigDir = Join-Path $HOME ".vibestick"
$RuntimeDir = Join-Path $ConfigDir "runtime"
$RuntimeBridge = Join-Path $RuntimeDir "bridge"
$RunnerPath = Join-Path $ConfigDir "run-bridge.ps1"
$InstalledEnvPath = Join-Path $ConfigDir ".env"
$LogPath = Join-Path $ConfigDir "bridge.log"
$TaskName = "VibeStick Bridge"
$python = Get-PythonCommand
$reasonix = Get-Command reasonix.cmd -ErrorAction SilentlyContinue
if (-not $reasonix) {
    $reasonix = Get-Command reasonix -ErrorAction SilentlyContinue
}
if (-not $reasonix) {
    throw "Reasonix is not on PATH. Install it with: npm install -g reasonix"
}

Set-DotEnvValue -Path $EnvPath -Key "VIBE_STICK_PROJECT_ROOT" -Value $RootDir
Set-DotEnvValue -Path $EnvPath -Key "VIBE_STICK_REASONIX_COMMAND" -Value $reasonix.Source
Set-DotEnvValue -Path $EnvPath -Key "VIBE_STICK_DATA_DIR" -Value $ConfigDir
Set-DotEnvValue -Path $EnvPath -Key "VIBE_STICK_LOG_FILE" -Value $LogPath

$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 200
        $state = (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue).State
    } while ($state -eq "Running" -and [DateTime]::UtcNow -lt $deadline)
    if ($state -eq "Running") {
        throw "The existing VibeStick Bridge task did not stop within 10 seconds."
    }
}

Stop-VibeStickBridgeListener

$ReasonixDir = Join-Path $ConfigDir "reasonix"
$ReasonixPidPath = Join-Path $ReasonixDir "pid"
$ReasonixTokenPath = Join-Path $ReasonixDir "token"
if (Test-Path -LiteralPath $ReasonixPidPath) {
    $reasonixPid = [System.IO.File]::ReadAllText($ReasonixPidPath).Trim()
    $isManagedReasonix = (
        $reasonixPid -match '^\d+$' -and
        (Test-ManagedReasonixProcess -ProcessId ([int]$reasonixPid) -TokenPath $ReasonixTokenPath)
    )
    if (-not $isManagedReasonix) {
        foreach ($name in @("pid", "port", "token")) {
            Remove-Item -LiteralPath (Join-Path $ReasonixDir $name) -Force -ErrorAction SilentlyContinue
        }
    }
}

New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
if (Test-Path -LiteralPath $RuntimeBridge) {
    Remove-Item -LiteralPath $RuntimeBridge -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $RootDir "bridge") -Destination $RuntimeBridge -Recurse
Copy-Item -LiteralPath $EnvPath -Destination $InstalledEnvPath -Force

$runner = @"
Set-StrictMode -Version Latest
`$ErrorActionPreference = "Stop"
`$envPath = "$($InstalledEnvPath.Replace('"', '""'))"
if (Test-Path -LiteralPath `$envPath) {
    foreach (`$line in [System.IO.File]::ReadAllLines(`$envPath)) {
        `$trimmed = `$line.Trim()
        if (-not `$trimmed -or `$trimmed.StartsWith("#") -or -not `$trimmed.Contains("=")) {
            continue
        }
        `$parts = `$trimmed.Split("=", 2)
        `$name = `$parts[0].Trim()
        `$value = `$parts[1].Trim().Trim('"').Trim("'")
        if (`$name) {
            [Environment]::SetEnvironmentVariable(`$name, `$value, "Process")
        }
    }
}
`$env:PYTHONPATH = "$($RuntimeBridge.Replace('"', '""'))\src"
Set-Location "$($ConfigDir.Replace('"', '""'))"
& "$($python.Replace('"', '""'))" -m vibe_stick --host 0.0.0.0 --port 8765
"@
Write-Utf8BomFile -Path $RunnerPath -Content $runner

$powerShell = (Get-Command powershell.exe).Source
$action = New-ScheduledTaskAction `
    -Execute $powerShell `
    -Argument "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$RunnerPath`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "VibeStick Windows bridge for Reasonix" `
    -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Installed and started the VibeStick Bridge scheduled task."
Write-Host "Runtime: $RuntimeDir"
Write-Host "Log: $LogPath"
Write-Host "Windows Firewall may ask for permission. Allow access on private networks only."
