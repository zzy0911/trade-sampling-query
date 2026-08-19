param(
    [string]$Version = "v0.1.3",
    [string]$Python = "python",
    [ValidateSet("x64", "x86")]
    [string]$Architecture = "x64"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$WorkRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot ".codex-work\packaging-$Architecture"))
$ReleaseRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot "release"))
$ProductName = "TradeQuery"
$CleanVersion = $Version.TrimStart("v")
$ArchiveName = "trade-query-v$CleanVersion-windows-$Architecture.zip"

$RuntimeInfo = & $Python -c "import platform, struct, sys; print('%d.%d|%s|%d' % (sys.version_info[0], sys.version_info[1], platform.python_implementation(), struct.calcsize('P') * 8))"
if ($LASTEXITCODE -ne 0) { throw "Cannot inspect the build runtime" }
$RuntimeParts = $RuntimeInfo.Trim().Split("|")
$ExpectedBits = if ($Architecture -eq "x64") { "64" } else { "32" }
if ($RuntimeParts[0] -ne "3.8" -or $RuntimeParts[1] -ne "CPython" -or $RuntimeParts[2] -ne $ExpectedBits) {
    throw "Windows 7 packages must use CPython 3.8 with matching architecture. Found: $RuntimeInfo"
}

function Reset-ProjectDirectory([string]$Path) {
    $fullPath = [IO.Path]::GetFullPath($Path)
    if (-not $fullPath.StartsWith($ProjectRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝清理项目目录之外的路径：$fullPath"
    }
    if (Test-Path -LiteralPath $fullPath) {
        Remove-Item -LiteralPath $fullPath -Recurse -Force
    }
    New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
}

Reset-ProjectDirectory $WorkRoot
New-Item -ItemType Directory -Path $ReleaseRoot -Force | Out-Null
$BuildHome = Join-Path $WorkRoot "home"
New-Item -ItemType Directory -Path $BuildHome -Force | Out-Null
$env:USERPROFILE = $BuildHome
$env:PYINSTALLER_CONFIG_DIR = $BuildHome

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --console `
    --name $ProductName `
    --add-data "$ProjectRoot\static;static" `
    --distpath "$WorkRoot\dist" `
    --workpath "$WorkRoot\build" `
    --specpath "$WorkRoot\spec" `
    "$ProjectRoot\run.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败" }

$AppDirectory = Join-Path $WorkRoot "dist\$ProductName"
Copy-Item -LiteralPath "$ProjectRoot\packaging\README-zh-CN.txt" -Destination $AppDirectory
Copy-Item -LiteralPath "$ProjectRoot\packaging\change-admin-password.cmd" -Destination $AppDirectory

& $Python "$ProjectRoot\scripts\verify_windows_compatibility.py" $AppDirectory --architecture $Architecture
if ($LASTEXITCODE -ne 0) { throw "Windows compatibility audit failed" }

$ArchivePath = Join-Path $ReleaseRoot $ArchiveName
$ChecksumPath = "$ArchivePath.sha256"
Remove-Item -LiteralPath $ArchivePath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $ChecksumPath -Force -ErrorAction SilentlyContinue
Compress-Archive -Path $AppDirectory -DestinationPath $ArchivePath -CompressionLevel Optimal
$Hash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath $ChecksumPath -Value "$Hash  $ArchiveName" -Encoding ascii

Write-Host "发行包：$ArchivePath"
Write-Host "校验值：$ChecksumPath"
