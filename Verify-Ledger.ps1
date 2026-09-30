param([string]$OutputDirectory = '')
$ErrorActionPreference = 'Stop'
$repositoryRoot = $PSScriptRoot
$pythonExecutable = Join-Path $repositoryRoot 'backend/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) { throw 'Install backend/requirements-dev.txt in backend/.venv first.' }
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ('ledger-verification-' + [guid]::NewGuid())
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
$repositoryPrefix = [System.IO.Path]::GetFullPath($repositoryRoot).TrimEnd('\') + '\'
if ($OutputDirectory.StartsWith($repositoryPrefix, [System.StringComparison]::OrdinalIgnoreCase) -or $OutputDirectory -eq $repositoryRoot) {
    throw 'Verification output must be outside the repository, so live/generated files remain untouched.'
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$previousBytecode = $env:PYTHONDONTWRITEBYTECODE
$env:PYTHONDONTWRITEBYTECODE = '1'
try {
    Push-Location (Join-Path $repositoryRoot 'backend')
    try {
        & $pythonExecutable -m pytest tests -q -p no:cacheprovider --basetemp (Join-Path $OutputDirectory ('pytest-' + [guid]::NewGuid()))
        if ($LASTEXITCODE -ne 0) { throw 'Backend verification failed.' }
    } finally { Pop-Location }
    Push-Location (Join-Path $repositoryRoot 'frontend')
    try {
        & node --test tests/*.test.js
        if ($LASTEXITCODE -ne 0) { throw 'Frontend utility verification failed.' }
        & node verify-build.mjs (Join-Path $OutputDirectory 'frontend')
        if ($LASTEXITCODE -ne 0) { throw 'Frontend production build failed.' }
    } finally { Pop-Location }
    Write-Output "Verification passed. Isolated artifacts: $OutputDirectory"
} finally {
    $env:PYTHONDONTWRITEBYTECODE = $previousBytecode
}
