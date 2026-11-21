$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Write-Host 'HandwriteFont -- Windows local install'
if (-not (Test-Path '.venv\Scripts\python.exe')) { py -3.12 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
if (Get-Command npm -ErrorAction SilentlyContinue) {
    Push-Location frontend
    try {
        npm install
        if ($LASTEXITCODE -eq 0) {
            npm run build
            if ($LASTEXITCODE -ne 0) { Write-Warning 'React build failed; bundled HTML interface will be used.' }
        } else {
            Write-Warning 'NPM packages unavailable; bundled HTML interface will be used.'
        }
    } finally { Pop-Location }
} else {
    Write-Host 'Node.js was not found. Bundled HTML interface enabled.'
}
Write-Host 'Installation completed. Double-click start-windows.bat.'
