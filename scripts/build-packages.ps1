param(
    [string]$OutputRoot = (Join-Path $PSScriptRoot "..\dist")
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$packageName = "SEELE-Maya-Transfer-0.2.0.zip"
$productionOrigin = "https://www.seeles.ai"
$testOrigin = "https://code4agent-feature-maya-dcc-server-web.seele.chat"

function New-SeelePackage {
    param(
        [string]$Channel,
        [string]$Origin
    )

    $channelRoot = Join-Path $OutputRoot $Channel
    $stageRoot = Join-Path $channelRoot "package"
    $archivePath = Join-Path $channelRoot $packageName

    if (Test-Path -LiteralPath $channelRoot) {
        Remove-Item -LiteralPath $channelRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $repositoryRoot "SeeleMaya.mod") -Destination $stageRoot
    $sourceRoot = Join-Path $repositoryRoot "SeeleMaya"
    Get-ChildItem -LiteralPath $sourceRoot -Recurse -File |
        Where-Object { $_.FullName -notmatch '[\\/]__pycache__[\\/]|\.py[co]$' } |
        ForEach-Object {
            $relative = $_.FullName.Substring($sourceRoot.Length).TrimStart('\')
            $destination = Join-Path (Join-Path $stageRoot "SeeleMaya") $relative
            New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
            Copy-Item -LiteralPath $_.FullName -Destination $destination
        }

    $configPath = Join-Path $stageRoot "SeeleMaya\scripts\seele_maya\config.py"
    if (-not (Test-Path -LiteralPath $configPath)) { throw "Package config.py was not copied" }
    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8
    $replacement = 'DEFAULT_ALLOWED_ORIGINS = (' + "`r`n" + '    "' + $Origin + '",' + "`r`n" + ')'
    $config = [regex]::Replace($config, 'DEFAULT_ALLOWED_ORIGINS\s*=\s*\([^)]*\)', $replacement)
    Set-Content -LiteralPath $configPath -Value $config -Encoding UTF8

    Compress-Archive -Path (Join-Path $stageRoot "SeeleMaya.mod"), (Join-Path $stageRoot "SeeleMaya") -DestinationPath $archivePath -CompressionLevel Optimal
    Remove-Item -LiteralPath $stageRoot -Recurse -Force

    [PSCustomObject]@{
        Channel = $Channel
        Origin = $Origin
        Archive = $archivePath
        Sha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
    }
}

$packages = @(
    New-SeelePackage -Channel "production" -Origin $productionOrigin
    New-SeelePackage -Channel "test" -Origin $testOrigin
)
$packages | Format-Table -AutoSize
