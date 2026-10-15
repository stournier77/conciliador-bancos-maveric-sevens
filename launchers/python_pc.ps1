# Captura stderr sin que PowerShell 5.1 lo convierta en una excepción prematura.
function Invoke-SevensProcess {
    param([string]$Executable, [string]$ArgumentLine, [int]$TimeoutSeconds = 600)
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $Executable
    $info.Arguments = $ArgumentLine
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $info
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill()
            throw "El proceso excedió el tiempo de espera: $Executable"
        }
        $process.WaitForExit()
        return [pscustomobject]@{Code=$process.ExitCode; Output=$stdout.Result.Trim(); Error=$stderr.Result.Trim()}
    } finally { $process.Dispose() }
}

function Get-SevensPython {
    param([string]$Uv, [string]$Runtime)
    $installed = Join-Path $Runtime '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $installed -PathType Leaf) {
        $probe = Invoke-SevensProcess $installed '-I -c "import sys; sys.exit(0 if sys.version_info[:2] == (3,12) else 1)"' 25
        if ($probe.Code -eq 0) { return $installed }
    }
    $found = Invoke-SevensProcess $Uv 'python find --managed-python 3.12' 30
    if ($found.Code -ne 0 -or -not $found.Output) {
        Write-Host 'Preparando Python 3.12 automáticamente...'
        $installedPython = Invoke-SevensProcess $Uv 'python install --no-bin --no-registry 3.12' 600
        if ($installedPython.Code -ne 0) { throw "No se pudo instalar Python 3.12: $($installedPython.Error)" }
        $found = Invoke-SevensProcess $Uv 'python find --managed-python 3.12' 30
    }
    if ($found.Code -ne 0 -or -not $found.Output -or -not (Test-Path -LiteralPath $found.Output -PathType Leaf)) {
        throw "No se encontró Python 3.12 después de preparar el entorno: $($found.Error)"
    }
    return $found.Output
}
