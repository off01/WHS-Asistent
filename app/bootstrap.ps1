$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $root '.runtime'
$python = Join-Path $runtime 'venv\Scripts\python.exe'
$requirements = Join-Path $PSScriptRoot 'requirements.txt'
$stamp = Join-Path $runtime 'requirements.sha256'
try {
    $hash = (Get-FileHash -LiteralPath $requirements -Algorithm SHA256).Hash
    if ((Test-Path -LiteralPath $python) -and (Test-Path -LiteralPath $stamp) -and
        ((Get-Content -LiteralPath $stamp -Raw).Trim() -eq $hash)) {
        & $python -B -c 'import selenium, prompt_toolkit' 2>$null
        if ($LASTEXITCODE -eq 0) { exit 0 }
    }
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null
    $uv = Join-Path $runtime 'uv.exe'
    if (-not (Test-Path -LiteralPath $uv)) {
        Write-Host 'Stahuji lokalni spousteci nastroj...'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $archive = Join-Path $runtime 'uv.zip'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' -OutFile $archive
        Expand-Archive -LiteralPath $archive -DestinationPath $runtime -Force
        Remove-Item -LiteralPath $archive
        if (-not (Test-Path -LiteralPath $uv)) { throw 'Archiv neobsahuje uv.exe.' }
    }
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $runtime 'python'
    $env:UV_CACHE_DIR = Join-Path $runtime 'cache'
    $env:UV_PYTHON_PREFERENCE = 'only-managed'
    $env:UV_NO_PROGRESS = '1'
    if (-not (Test-Path -LiteralPath $python)) {
        Write-Host 'Pripravuji lokalni Python. Systemova instalace neni potreba...'
        & $uv --no-config venv --python 3.13 (Join-Path $runtime 'venv')
        if ($LASTEXITCODE -ne 0) { throw 'Priprava Pythonu selhala.' }
    }
    Write-Host 'Pripravuji zavislosti...'
    & $uv --no-config pip install --python $python --requirements $requirements
    if ($LASTEXITCODE -ne 0) { throw 'Stazeni zavislosti selhalo.' }
    & $python -B -c 'import selenium, prompt_toolkit'
    if ($LASTEXITCODE -ne 0) { throw 'Kontrola Pythonu selhala.' }
    Set-Content -LiteralPath $stamp -Value $hash -Encoding ascii
} catch {
    Write-Host ('Priprava selhala: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
