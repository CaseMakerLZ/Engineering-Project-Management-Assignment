# Windows PowerShell 5.1 / PowerShell 7. ASCII source also works without a BOM.
[CmdletBinding()]
param(
    [string]$OutputDir = "",
    [string]$MavenCommand = "mvn.cmd",
    [string]$JavaHome = $env:JAVA_HOME,
    [switch]$UseExistingNodeModules
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OutputDir) { $OutputDir = Join-Path $ProjectRoot ("outputs\release-" + (Get-Date -Format "yyyyMMdd-HHmmss")) }
$OutputDir = [IO.Path]::GetFullPath($OutputDir)
# Never delete an existing destination, even if the caller passes the project root.
if (Test-Path -LiteralPath $OutputDir) { throw "Output directory already exists: $OutputDir" }
foreach ($Tool in @("git", "node", "npm.cmd", "tar.exe", $MavenCommand)) {
    if (-not (Get-Command $Tool -ErrorAction SilentlyContinue)) { throw "Command not found: $Tool" }
}
$OldPath = $env:Path
$OldJavaHome = $env:JAVA_HOME
$OldMode = $env:VITE_APP_MODE
$OldApi = $env:VITE_API_BASE_URL
try {
    if ($JavaHome) {
        if (-not (Test-Path -LiteralPath (Join-Path $JavaHome "bin\javac.exe"))) { throw "JDK not found: $JavaHome" }
        $env:JAVA_HOME = $JavaHome
        $env:Path = (Join-Path $JavaHome "bin") + ";" + $env:Path
    }
    & $MavenCommand -v
    if ($LASTEXITCODE -ne 0) { throw "Maven/JDK check failed" }
    Push-Location (Join-Path $ProjectRoot "frontend")
    try {
        if (-not $UseExistingNodeModules) {
            & npm.cmd ci
            if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
        }
        # Override local-only frontend settings; production needs cloud login.
        $env:VITE_APP_MODE = "cloud"
        $env:VITE_API_BASE_URL = "/"
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
    } finally { Pop-Location }
    Push-Location (Join-Path $ProjectRoot "JavaBackend")
    try {
        & $MavenCommand "-Dmaven.test.skip=true" clean package
        if ($LASTEXITCODE -ne 0) { throw "Java build failed" }
    } finally { Pop-Location }
    $Jars = @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot "JavaBackend\target") -Filter "*.jar")
    if ($Jars.Count -ne 1) { throw "Expected exactly one executable jar" }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $Zip = [IO.Compression.ZipFile]::OpenRead($Jars[0].FullName)
    try {
        if (@($Zip.Entries | Where-Object { $_.FullName -match "application-private|(^|/)\.env" }).Count -gt 0) {
            throw "Private configuration found in Java jar"
        }
    } finally { $Zip.Dispose() }
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
    foreach ($Name in @("web", "python", "db", "deploy")) {
        New-Item -ItemType Directory -Path (Join-Path $OutputDir $Name) | Out-Null
    }
    Copy-Item -LiteralPath $Jars[0].FullName -Destination (Join-Path $OutputDir "javabackend.jar")
    Get-ChildItem -LiteralPath (Join-Path $ProjectRoot "frontend\dist") -Force |
        Copy-Item -Destination (Join-Path $OutputDir "web") -Recurse
    # Copy tracked runtime files only. Never copy secrets and then try to remove them.
    $Tracked = @(& git -C $ProjectRoot -c core.quotepath=false ls-files)
    if ($LASTEXITCODE -ne 0) { throw "git ls-files failed" }
    foreach ($Relative in $Tracked) {
        if ($Relative -notmatch "^(agent/|agent_service/|llm/|tools/|requirements\.txt$)") { continue }
        if ($Relative -match "(?i)(^|/)(tests?|__pycache__)(/|$)|(^|/)(test_|.*_test\.)|\.pyc$") { continue }
        if ($Relative -notmatch "\.py$|^requirements\.txt$|^tools/terminal/(Dockerfile|\.dockerignore)$") { continue }
        $Target = Join-Path $OutputDir ("python/" + $Relative)
        New-Item -ItemType Directory -Path (Split-Path $Target) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $ProjectRoot $Relative) -Destination $Target
    }
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "JavaBackend/src/main/resources/schema.sql") -Destination (Join-Path $OutputDir "db/schema.sql")
    $Utf8 = [Text.UTF8Encoding]::new($false)
    foreach ($File in Get-ChildItem -LiteralPath $PSScriptRoot -File) {
        if ($File.Name -eq "deploy-ubuntu.sh" -or $File.Name -eq "build-release.ps1") { continue }
        if ($File.Extension -notin @(".sh", ".py", ".md")) { continue }
        $Content = [IO.File]::ReadAllText($File.FullName).Replace("`r`n", "`n")
        [IO.File]::WriteAllText((Join-Path $OutputDir ("deploy/" + $File.Name)), $Content, $Utf8)
    }
    [ordered]@{
        built_at = (Get-Date).ToUniversalTime().ToString("o")
        git_commit = (& git -C $ProjectRoot rev-parse HEAD).Trim()
        uncommitted = [bool](& git -C $ProjectRoot status --porcelain)
        mode = "cloud"
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $OutputDir "release-manifest.json") -Encoding UTF8
    $Hashes = foreach ($File in Get-ChildItem -LiteralPath $OutputDir -Recurse -File) {
        $Relative = $File.FullName.Substring($OutputDir.Length + 1).Replace("\", "/")
        (Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash.ToLower() + "  " + $Relative
    }
    [IO.File]::WriteAllText((Join-Path $OutputDir "SHA256SUMS"), ($Hashes -join "`n") + "`n", $Utf8)
    $Archive = $OutputDir + ".tar.gz"
    if (Test-Path -LiteralPath $Archive) { throw "Archive already exists: $Archive" }
    & tar.exe -czf $Archive -C $OutputDir .
    if ($LASTEXITCODE -ne 0) { throw "Archive creation failed" }
    Write-Host "Release: $OutputDir"
    Write-Host "Upload:  $Archive"
} finally {
    $env:Path = $OldPath
    $env:JAVA_HOME = $OldJavaHome
    $env:VITE_APP_MODE = $OldMode
    $env:VITE_API_BASE_URL = $OldApi
}
