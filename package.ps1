$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$dist = Join-Path $PSScriptRoot 'dist'
New-Item -ItemType Directory -Path $dist -Force | Out-Null
$target = Join-Path $dist ('WHS-Asistent-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.zip')
$zip = [IO.Compression.ZipFile]::Open($target, [IO.Compression.ZipArchiveMode]::Create)
try {
    $files = @(Get-Item -LiteralPath (Join-Path $PSScriptRoot 'WHS-Asistent.bat'))
    $files += Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'app') -File |
        Where-Object { $_.Extension -in @('.py', '.ps1', '.txt') }
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($PSScriptRoot.Length + 1).Replace('\', '/')
        [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file.FullName, 'WHS-Asistent/' + $relative) | Out-Null
    }
} finally { $zip.Dispose() }
Write-Host $target
