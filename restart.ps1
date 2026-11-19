param([switch]$NoOpen)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskPidFile = Join-Path $taskRoot 'artifacts\server.pid'
New-Item -ItemType Directory -Path (Join-Path $taskRoot 'artifacts') -Force | Out-Null
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Missing local environment. Follow README.md one-time setup instructions.'
}
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'app\.py.*--port\s+8766' } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 400
$taskProbe = New-Object System.Net.Sockets.Socket([System.Net.Sockets.AddressFamily]::InterNetwork, [System.Net.Sockets.SocketType]::Stream, [System.Net.Sockets.ProtocolType]::Tcp)
try {
    $taskProbe.ExclusiveAddressUse = $true
    $taskProbe.Bind((New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Loopback, 8766)))
} catch {
    throw 'Port 8766 is already in use. No unrelated process was stopped; choose another app.py --port explicitly.'
} finally {
    $taskProbe.Dispose()
}
$fetchScript = Join-Path $taskRoot 'tools\fetch_today_matches.py'
if (Test-Path -LiteralPath $fetchScript) {
    & $taskPython $fetchScript
}
$taskArguments = @('-u', 'app.py', '--port', '8766')
if (-not $NoOpen) { $taskArguments += '--open' }
$taskStarted = Start-Process -FilePath $taskPython -ArgumentList $taskArguments -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRoot 'artifacts\server-8766.log') -RedirectStandardError (Join-Path $taskRoot 'artifacts\server-8766-error.log') -PassThru
$taskStarted.Id | Set-Content -LiteralPath $taskPidFile
$taskHealthy = $false
for ($taskAttempt = 0; $taskAttempt -lt 10; $taskAttempt++) {
    try {
        $taskHealth = Invoke-RestMethod 'http://127.0.0.1:8766/api/health' -TimeoutSec 1
        if ($taskHealth.ok) { $taskHealthy = $true; break }
    } catch { Start-Sleep -Milliseconds 300 }
}
if (-not $taskHealthy -or $taskStarted.HasExited) {
    throw 'Dashboard did not start. Read artifacts/server-8766-error.log. If port 8766 belongs to another process, stop that process explicitly or use app.py --port with a different port.'
}
Write-Output 'MatchLab is running at http://127.0.0.1:8766 (local CPU inference; offline).'
