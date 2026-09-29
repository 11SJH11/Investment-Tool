$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runtime = Join-Path $Root '.ledger-runtime'
$PidFile = Join-Path $Runtime 'processes.json'

function Get-LedgerProcess([int]$ProcessId, [string]$Marker) {
    if (-not $ProcessId) { return $null }
    try {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
        if ($process -and [string]$process.CommandLine -like "*$Marker*") { return $process }
    } catch { }
    return $null
}

function Stop-LedgerTree([int]$ProcessId) {
    if (-not $ProcessId) { return }
    try { & taskkill.exe /PID $ProcessId /T /F *> $null } catch { }
}

if (-not (Test-Path $PidFile)) {
    Write-Host 'Ledger is not recorded as running.' -ForegroundColor Yellow
    exit 0
}

try {
    $state = Get-Content $PidFile -Raw | ConvertFrom-Json
    $backend = Get-LedgerProcess ([int]$state.backend_pid) 'uvicorn app.main:app'
    $frontend = Get-LedgerProcess ([int]$state.frontend_pid) 'npm.cmd run dev'
    if ($backend) { Stop-LedgerTree ([int]$state.backend_pid) }
    if ($frontend) { Stop-LedgerTree ([int]$state.frontend_pid) }
} finally {
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

Write-Host 'Ledger background processes stopped.' -ForegroundColor Green
