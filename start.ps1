Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Write-Host "MatchLab: Checking today's sports matches online..." -ForegroundColor Cyan
& $python (Join-Path $PSScriptRoot 'tools\fetch_today_matches.py')
Write-Host "`nStarting MatchLab local sports dashboard..." -ForegroundColor Green
& $python (Join-Path $PSScriptRoot 'app.py') --port 8766 --open
