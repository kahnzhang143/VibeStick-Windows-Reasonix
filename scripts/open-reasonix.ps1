[CmdletBinding()]
param(
    [switch]$NoLaunch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ReasonixDir = Join-Path $HOME ".vibestick\reasonix"
$PortPath = Join-Path $ReasonixDir "port"
$TokenPath = Join-Path $ReasonixDir "token"

try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8765/state" -TimeoutSec 12 | Out-Null
} catch {
    throw "The VibeStick Bridge is not running. Run .\scripts\install.ps1 or .\scripts\dev.ps1 first."
}

$deadline = [DateTime]::UtcNow.AddSeconds(12)
while ([DateTime]::UtcNow -lt $deadline) {
    if ((Test-Path -LiteralPath $PortPath) -and (Test-Path -LiteralPath $TokenPath)) {
        $rawPort = [System.IO.File]::ReadAllText($PortPath).Trim()
        $port = $rawPort.Split(":")[-1]
        $token = [System.IO.File]::ReadAllText($TokenPath).Trim()
        if ($port -match '^\d+$' -and $token) {
            $url = "http://127.0.0.1:$port/#token=$token"
            if ($NoLaunch) {
                Write-Output $url
            } else {
                Start-Process $url
            }
            exit 0
        }
    }
    Start-Sleep -Milliseconds 200
}

throw "Reasonix Serve did not publish its port and token files. Check $HOME\.vibestick\reasonix\serve.log."
