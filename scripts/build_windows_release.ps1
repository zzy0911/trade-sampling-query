param(
    [string]$Version = "v0.1.0",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$WorkRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot ".codex-work\packaging"))
$ReleaseRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot "release"))
$ProductName = "TradeQuery"
$CleanVersion = $Version.TrimStart("v")
$ArchiveName = "trade-query-v$CleanVersion-windows-x64.zip"

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

$ArchivePath = Join-Path $ReleaseRoot $ArchiveName
$ChecksumPath = "$ArchivePath.sha256"
Remove-Item -LiteralPath $ArchivePath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $ChecksumPath -Force -ErrorAction SilentlyContinue
Compress-Archive -Path $AppDirectory -DestinationPath $ArchivePath -CompressionLevel Optimal
$Hash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath $ChecksumPath -Value "$Hash  $ArchiveName" -Encoding ascii

Write-Host "发行包：$ArchivePath"
Write-Host "校验值：$ChecksumPath"
