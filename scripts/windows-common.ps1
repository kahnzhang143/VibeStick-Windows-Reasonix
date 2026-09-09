Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Utf8BomFile {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string]$Content
    )

    $encoding = [System.Text.UTF8Encoding]::new($true)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [string]$Key
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }
        $parts = $trimmed.Split("=", 2)
        if ($parts[0].Trim() -eq $Key) {
            return $parts[1].Trim().Trim('"').Trim("'")
        }
    }
    return ""
}

function Set-DotEnvValue {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [string]$Key,
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string]$Value
    )

    $lines = [System.Collections.Generic.List[string]]::new()
    $updated = $false
    if (Test-Path -LiteralPath $Path) {
        foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
            $trimmed = $line.Trim()
            if (-not $trimmed.StartsWith("#") -and $trimmed.Contains("=")) {
                $parts = $trimmed.Split("=", 2)
                if ($parts[0].Trim() -eq $Key) {
                    $lines.Add("$Key=$Value")
                    $updated = $true
                    continue
                }
            }
            $lines.Add($line)
        }
    }
    if (-not $updated) {
        $lines.Add("$Key=$Value")
    }
    Write-Utf8BomFile -Path $Path -Content (($lines -join [Environment]::NewLine) + [Environment]::NewLine)
}

function Get-HeaderDefine {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [string]$Key
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }
    $pattern = '^\s*#define\s+' + [regex]::Escape($Key) + '\s+"([^"]*)"'
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        if ($line -match $pattern) {
            return $Matches[1]
        }
    }
    return ""
}

function Set-HeaderDefine {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [string]$Key,
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string]$Value
    )

    $pattern = '^\s*#define\s+' + [regex]::Escape($Key) + '\s+'
    $lines = [System.Collections.Generic.List[string]]::new()
    $updated = $false
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        if ($line -match $pattern) {
            $lines.Add("#define $Key `"$Value`"")
            $updated = $true
        } else {
            $lines.Add($line)
        }
    }
    if (-not $updated) {
        $lines.Add("#define $Key `"$Value`"")
    }
    Write-Utf8BomFile -Path $Path -Content (($lines -join [Environment]::NewLine) + [Environment]::NewLine)
}

function Import-DotEnv {
    param(
        [Parameter(Mandatory)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }
        $parts = $trimmed.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        if ($name) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

function Test-PlaceholderToken {
    param([AllowEmptyString()][string]$Value)
    return [string]::IsNullOrWhiteSpace($Value) -or $Value.ToLowerInvariant() -in @(
        "change-this-shared-token",
        "paste-generated-token-here",
        "changeme",
        "change-me",
        "your-token"
    )
}

function Test-PlaceholderHost {
    param([AllowEmptyString()][string]$Value)
    return [string]::IsNullOrWhiteSpace($Value) -or $Value.ToLowerInvariant() -in @(
        "127.0.0.1",
        "0.0.0.0",
        "192.168.1.10",
        "192.168.0.10",
        "10.0.0.10",
        "your_mac_ip",
        "your-mac-ip",
        "your_windows_ip",
        "your-windows-ip"
    )
}

function New-BridgeToken {
    $bytes = [byte[]]::new(32)
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    } finally {
        $generator.Dispose()
    }
    return -join ($bytes | ForEach-Object { $_.ToString("x2") })
}

function Get-PreferredLanIPv4 {
    try {
        $configuration = Get-NetIPConfiguration |
            Where-Object {
                $_.IPv4DefaultGateway -and
                $_.NetAdapter.Status -eq "Up" -and
                $_.IPv4Address
            } |
            Select-Object -First 1
        if ($configuration) {
            $address = $configuration.IPv4Address |
                Where-Object { $_.IPAddress -notlike "169.254.*" } |
                Select-Object -ExpandProperty IPAddress -First 1
            if ($address) {
                return $address
            }
        }
    } catch {
    }

    $udp = [System.Net.Sockets.UdpClient]::new()
    try {
        $udp.Connect("8.8.8.8", 53)
        return ([System.Net.IPEndPoint]$udp.Client.LocalEndPoint).Address.IPAddressToString
    } finally {
        $udp.Dispose()
    }
}

function Get-PythonCommand {
    foreach ($candidate in @("python", "py")) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }
    throw "Python 3.11 or newer was not found on PATH."
}

function Stop-VibeStickBridgeListener {
    $listeners = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
        $commandLine = [string]$process.CommandLine
        if ($process -and $commandLine -match '(?i)-m\s+vibe_stick\b' -and $commandLine -match '(?i)--port\s+8765\b') {
            Stop-Process -Id $listener.OwningProcess -ErrorAction Stop
            continue
        }
        throw "Port 8765 is occupied by a process that was not identified as VibeStick (PID $($listener.OwningProcess))."
    }
}

function Test-ManagedReasonixProcess {
    param(
        [Parameter(Mandatory)]
        [int]$ProcessId,
        [Parameter(Mandatory)]
        [string]$TokenPath
    )

    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if (-not $process) {
        return $false
    }
    $commandLine = [string]$process.CommandLine
    return (
        $commandLine -match '(?i)\breasonix(?:\.js|\.cmd|\.exe)?\b' -and
        $commandLine -match '(?i)\bserve\b' -and
        $commandLine.IndexOf($TokenPath, [StringComparison]::OrdinalIgnoreCase) -ge 0
    )
}

function Stop-ManagedReasonixProcess {
    param(
        [Parameter(Mandatory)]
        [string]$PidPath,
        [Parameter(Mandatory)]
        [string]$TokenPath
    )

    if (-not (Test-Path -LiteralPath $PidPath)) {
        return
    }
    $rawPid = [System.IO.File]::ReadAllText($PidPath).Trim()
    if ($rawPid -notmatch '^\d+$') {
        Write-Warning "Ignored an invalid managed Reasonix PID file."
        return
    }
    $processId = [int]$rawPid
    if (Test-ManagedReasonixProcess -ProcessId $processId -TokenPath $TokenPath) {
        Stop-Process -Id $processId -ErrorAction Stop
        Wait-Process -Id $processId -Timeout 10 -ErrorAction SilentlyContinue
        return
    }
    Write-Warning "Ignored stale Reasonix PID $processId because its process identity did not match."
}
