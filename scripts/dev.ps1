# Start OpenPokerLab on Windows 10/11.
# Requires Python 3.12+ (py launcher) and Node.js with npm.
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $Root

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' was not found. Install Python 3.12 from python.org and enable 'Add python.exe to PATH'."
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm was not found. Install the Node.js LTS from nodejs.org."
}

& py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.12 or newer is required. 'py -3' is older than that."
}

$VenvPython = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    & py -3 -m venv (Join-Path $Root "backend\.venv")
}

& $VenvPython -m pip install -e "$Root\backend[dev]"
if ($LASTEXITCODE -ne 0) {
    throw "Backend install failed."
}

$Frontend = Join-Path $Root "frontend"
Push-Location -LiteralPath $Frontend
npm install
if ($LASTEXITCODE -ne 0) {
    throw "npm install failed."
}
Pop-Location

$ApiCommand = "Set-Location -LiteralPath '$Root\backend'; & '$VenvPython' -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
$WebCommand = "Set-Location -LiteralPath '$Frontend'; npm run dev"
Start-Process -FilePath "powershell" -ArgumentList @("-NoExit", "-Command", $ApiCommand)
Start-Process -FilePath "powershell" -ArgumentList @("-NoExit", "-Command", $WebCommand)

Write-Host ""
Write-Host "API:  http://127.0.0.1:8000/health"
Write-Host "Play: http://localhost:3000/play"
Write-Host "Leave the two new windows open while you play."
Start-Sleep -Seconds 3
Start-Process "http://localhost:3000/play"
