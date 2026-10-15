param([Parameter(Mandatory=$true)][string]$Python)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '..\launchers\python_pc.ps1')
# Un error escrito en stderr debe devolver su código, sin abortar PowerShell.
$result=Invoke-SevensProcess $Python '-I -c "import sys; print(123, file=sys.stderr); sys.exit(3)"' 25
if ($result.Code -ne 3 -or $result.Error -ne '123') { throw 'La captura nativa de stderr falló' }
$temporary=Join-Path ([IO.Path]::GetTempPath()) ([Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $script:basePython=Join-Path $temporary 'python.exe'
    [IO.File]::WriteAllText($script:basePython,'fixture')
    $script:calls=New-Object System.Collections.Generic.List[string]
    function Invoke-SevensProcess {
        param($Executable,$ArgumentLine,$TimeoutSeconds)
        $script:calls.Add($ArgumentLine)
        if ($ArgumentLine -like 'python find*' -and $script:calls.Count -eq 1) {
            return [pscustomobject]@{Code=2;Output='';Error='No interpreter found for Python 3.12'}
        }
        if ($ArgumentLine -like 'python install*') {
            return [pscustomobject]@{Code=0;Output='';Error=''}
        }
        return [pscustomobject]@{Code=0;Output=$script:basePython;Error=''}
    }
    $result=Get-SevensPython -Uv 'fake-uv.exe' -Runtime $temporary
    if ($result -ne $script:basePython -or $script:calls.Count -ne 3 -or $script:calls[1] -notlike 'python install*') {
        throw 'No reparó el intérprete ausente'
    }
    $venv=Join-Path $temporary '.venv\Scripts'
    New-Item -ItemType Directory -Force -Path $venv | Out-Null
    [IO.File]::WriteAllText((Join-Path $venv 'python.exe'),'fixture')
    $script:calls.Clear()
    $result=Get-SevensPython -Uv 'fake-uv.exe' -Runtime $temporary
    if ($result -ne (Join-Path $venv 'python.exe') -or $script:calls.Count -ne 1 -or $script:calls[0] -notlike '-I -c*') {
        throw 'No reutilizó el entorno instalado'
    }
    Write-Host 'PC: stderr nativo, reparación y reutilización del entorno OK'
} finally { Remove-Item -LiteralPath $temporary -Recurse -Force }
