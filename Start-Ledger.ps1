$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$Python = Join-Path $Backend '.venv\Scripts\python.exe'
$Runtime = Join-Path $Root '.ledger-runtime'
$PidFile = Join-Path $Runtime 'processes.json'
$BackendOut = Join-Path $Runtime 'backend.out.log'
$BackendErr = Join-Path $Runtime 'backend.err.log'
$FrontendOut = Join-Path $Runtime 'frontend.out.log'
$FrontendErr = Join-Path $Runtime 'frontend.err.log'

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

function Wait-LedgerPort([int]$Port, [int]$TimeoutSeconds = 25) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $client.Connect('127.0.0.1', $Port)
            return $true
        } catch {
            Start-Sleep -Milliseconds 400
        } finally {
            $client.Dispose()
        }
    }
    return $false
}

if (-not (Test-Path $Python)) {
    Write-Host 'Ledger backend virtual environment was not found.' -ForegroundColor Yellow
    Write-Host 'From the backend folder run:'
    Write-Host '  py -3.11 -m venv .venv'
    Write-Host '  .venv\Scripts\python.exe -m pip install -r requirements.txt'
    exit 1
}

$Npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $Npm) {
    Write-Host 'npm was not found. Install a current Node.js LTS release first.' -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $Frontend 'node_modules'))) {
    Write-Host 'Installing frontend packages (first run only)...' -ForegroundColor Cyan
    Push-Location $Frontend
    try { npm.cmd ci } finally { Pop-Location }
}

New-Item -ItemType Directory -Force -Path $Runtime | Out-Null

# If Ledger is already running from this launcher, simply open it again.
if (Test-Path $PidFile) {
    try {
        $state = Get-Content $PidFile -Raw | ConvertFrom-Json
        $backendExisting = Get-LedgerProcess ([int]$state.backend_pid) 'uvicorn app.main:app'
        $frontendExisting = Get-LedgerProcess ([int]$state.frontend_pid) 'npm.cmd run dev'
        if ($backendExisting -and $frontendExisting) {
            Start-Process 'http://127.0.0.1:5173'
            Write-Host 'Ledger is already running in the background.' -ForegroundColor Green
            exit 0
        }
        # Clean up only processes that can still be positively identified as Ledger.
        if ($backendExisting) { Stop-LedgerTree ([int]$state.backend_pid) }
        if ($frontendExisting) { Stop-LedgerTree ([int]$state.frontend_pid) }
    } catch { }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

Write-Host 'Starting Ledger in the background...' -ForegroundColor Cyan

$backendProcess = Start-Process -FilePath $Python `
    -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') `
    -WorkingDirectory $Backend -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $BackendOut -RedirectStandardError $BackendErr

$frontendProcess = Start-Process -FilePath $env:ComSpec `
    -ArgumentList @('/d','/s','/c','npm.cmd run dev -- --host 127.0.0.1') `
    -WorkingDirectory $Frontend -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $FrontendOut -RedirectStandardError $FrontendErr

[pscustomobject]@{
    backend_pid = $backendProcess.Id
    frontend_pid = $frontendProcess.Id
    started_at = (Get-Date).ToString('o')
} | ConvertTo-Json | Set-Content -Path $PidFile -Encoding UTF8

$backendReady = Wait-LedgerPort 8000
$frontendReady = Wait-LedgerPort 5173
if (-not ($backendReady -and $frontendReady)) {
    Stop-LedgerTree $backendProcess.Id
    Stop-LedgerTree $frontendProcess.Id
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host 'Ledger did not start successfully. Check:' -ForegroundColor Red
    Write-Host "  $BackendErr"
    Write-Host "  $FrontendErr"
    exit 1
}

Start-Process 'http://127.0.0.1:5173'
Write-Host 'Ledger is running in the background.' -ForegroundColor Green
Write-Host 'Use Stop-Ledger.bat when you want to shut it down.'
Write-Host "Logs are stored in $Runtime"
