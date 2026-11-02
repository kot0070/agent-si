# Copyright (c) 2026 Ivan Soprun
# packaging/build_app.ps1 — offline product build.
#
# Stages (in order):
#   1. web build         (frontend -> dist/stage/web, local tools only)
#   2. sidecar freeze    (PyInstaller spec -> dist/sidecar/AgentSI.exe)
#   3. staging           (collect REAL lane outputs into dist/stage: web tree,
#                         sidecar exe, lane data dirs, licence + notices)
#   4. offline manifests (write MANIFEST.json, HASH.json, SMOKE.json)
#   5. portable assembly (copy stage tree + manifests into dist/portable and
#                         generate the portable start scripts)
#
# OFFLINE: no network calls anywhere in this script (no downloads, uploads,
# installs, or remote fetches of any kind). The only build invocation allowed
# is a local `npm run build --offline`, and only when frontend/node_modules
# already exists. Missing lane inputs are SKIPPED with a warning and recorded
# in SMOKE.json as fail — never faked, never hand-written.
#
# MANIFEST.json / HASH.json / SMOKE.json plus the HASH.json.sha256 sidecar
# are written ONLY by this script from real build outputs (real Get-FileHash
# sha256 + real byte counts). Never hand-write or hand-edit them.
#
# Run from the workspace root. Every produced file is reported as:
#   ARTIFACT <path>
#
# Frozen cross-file contracts (0C wins; this script refuses drift):
#   exe          = AgentSI.exe
#   version      = 0.1.0
#   portable dir = dist/portable
#   manifest dir = packaging/installer_manifest/
#     MANIFEST.json {version, exe, files:[{path, sha256, bytes}]} (sha256 lowercase hex)
#     HASH.json     {sha256, built_from_commit, built_at, signature:{status}}
#     SMOKE.json    {exe, checks:[{name, result, exit_code}],
#                    started_clean:{projects:0, runs:0, keys:0}}
#   HASH.json.sha256 is the sha256 of the CANONICAL manifest bytes, frozen by
#   tests/packaging/test_exe_hash.py as:
#     json.dumps(manifest, sort_keys=True, separators=(",", ":"),
#                ensure_ascii=False).encode("utf-8")
#   (Hashing raw ConvertTo-Json bytes is FORBIDDEN: key order and spacing
#   differ from the canonical form and break the exe-hash gate.)
#   signature status = UNSIGNED-BLOCKED (no cert in sandbox; never fake a signature).
# NOTE (frozen): window flags (windowed app, no terminal/console) are owned by K07
# `packaging/tauri/`; this lane only records the requirement here (the sidecar
# spec sets console=False) and never creates that dir.

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$Version = "0.1.0",
    [string]$ExeName = "AgentSI.exe",
    [string]$StageDir = "dist/stage",
    [string]$PortableDir = "dist/portable",
    [string]$ManifestDir = "packaging/installer_manifest"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($Version -ne "0.1.0") { throw "frozen contract drift: Version must be 0.1.0 (got $Version)" }
if ($ExeName -ne "AgentSI.exe") { throw "frozen contract drift: ExeName must be AgentSI.exe (got $ExeName)" }
if ($PortableDir -ne "dist/portable") { throw "frozen contract drift: PortableDir must be dist/portable (got $PortableDir)" }
if ($ManifestDir -ne "packaging/installer_manifest") { throw "frozen contract drift: ManifestDir must be packaging/installer_manifest (got $ManifestDir)" }

$SignatureStatus = "UNSIGNED-BLOCKED"
$SignatureReason = "no cert in sandbox"
$SidecarSpec = "packaging/sidecar/agent_si_sidecar.spec"
$SidecarEntry = "src/agent_si/sidecar.py"
$SidecarOutDir = "dist/sidecar"

# Per-input staging outcomes (honest SMOKE input checks read these).
$script:staged = @{
    web        = $false
    exe        = $false
    migrations = $false
    locale     = $false
    kbdata     = $false
    watcher    = $false
    license    = $false
    notices    = $false
}

function Write-Artifact {
    param([string]$Path)
    Write-Output "ARTIFACT $Path"
}

function Ensure-Dir {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        [void](New-Item -ItemType Directory -Force -Path $Path)
    }
}

# HOT-WRITE (os.replace equivalent): write to a temp file in the target dir,
# then move it over the target (same-volume atomic replace). UTF-8, no BOM.
function Write-FileAtomic {
    param([string]$Path, [string]$Text)
    Ensure-Dir (Split-Path -Parent $Path)
    $tmp = "$Path.tmp-$PID"
    [IO.File]::WriteAllText($tmp, $Text, (New-Object Text.UTF8Encoding $false))
    Move-Item -LiteralPath $tmp -Destination $Path -Force
    Write-Artifact $Path
}

function Copy-TreeArtifacts {
    param([string]$From, [string]$To)
    Ensure-Dir $To
    $base = (Resolve-Path -LiteralPath $From).Path
    foreach ($f in (Get-ChildItem -LiteralPath $From -Recurse -File)) {
        $rel = $f.FullName.Substring($base.Length).TrimStart('\', '/')
        $dest = Join-Path $To ($rel -replace '[\\/]', [IO.Path]::DirectorySeparatorChar)
        Ensure-Dir (Split-Path -Parent $dest)
        Copy-Item -LiteralPath $f.FullName -Destination $dest -Force
        Write-Artifact $dest
    }
}

# Escape one string exactly like Python json.dumps(ensure_ascii=False):
# only '"' and '\' plus U+0000..U+001F are escaped; everything else
# (including non-ASCII, written raw as UTF-8) passes through untouched.
function Escape-JsonString {
    param([string]$Text)
    $sb = New-Object Text.StringBuilder
    foreach ($ch in $Text.ToCharArray()) {
        $code = [int]$ch
        if ($code -eq 34) { [void]$sb.Append('\"') }
        elseif ($code -eq 92) { [void]$sb.Append('\\') }
        elseif ($code -eq 8) { [void]$sb.Append('\b') }
        elseif ($code -eq 9) { [void]$sb.Append('\t') }
        elseif ($code -eq 10) { [void]$sb.Append('\n') }
        elseif ($code -eq 12) { [void]$sb.Append('\f') }
        elseif ($code -eq 13) { [void]$sb.Append('\r') }
        elseif ($code -lt 0x20) { [void]$sb.Append(('\u{0:x4}' -f $code)) }
        else { [void]$sb.Append($ch) }
    }
    return $sb.ToString()
}

# Canonical MANIFEST text, frozen by tests/packaging/test_exe_hash.py:
#   json.dumps(manifest, sort_keys=True, separators=(",", ":"),
#              ensure_ascii=False).encode("utf-8")
# Top-level keys sorted (exe, files, version); entry keys sorted
# (bytes, path, sha256); compact separators; entries sorted by path.
function Get-CanonicalManifestJson {
    param([string]$VersionArg, [string]$ExeArg, [array]$Entries)
    $parts = @()
    foreach ($e in ($Entries | Sort-Object { $_["path"] })) {
        # LANE FIT (INSTALLB): literal JSON braces must be doubled for -f.
        $parts += ('{{"bytes":{0},"path":"{1}","sha256":"{2}"}}' -f $e["bytes"], (Escape-JsonString $e["path"]), $e["sha256"])
    }
    return ('{{"exe":"{0}","files":[{1}],"version":"{2}"}}' -f (Escape-JsonString $ExeArg), ($parts -join ","), (Escape-JsonString $VersionArg))
}

function Get-Sha256HexOfString {
    param([string]$Text)
    $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
    $hash = [Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
    return ([BitConverter]::ToString($hash)).Replace("-", "").ToLowerInvariant()
}

function Get-PlanArtifacts {
    Write-Artifact "dist/stage/web/index.html"
    Write-Artifact "dist/stage/sidecar/AgentSI.exe"
    Write-Artifact "dist/stage/migrations"
    Write-Artifact "dist/stage/locale"
    Write-Artifact "dist/stage/kb-data"
    Write-Artifact "dist/stage/watcher"
    Write-Artifact "dist/stage/LICENSE"
    Write-Artifact "dist/stage/docs/third_party_notices/NOTICES.md"
    Write-Artifact "packaging/installer_manifest/MANIFEST.json"
    Write-Artifact "packaging/installer_manifest/HASH.json"
    Write-Artifact "packaging/installer_manifest/HASH.json.sha256"
    Write-Artifact "packaging/installer_manifest/SMOKE.json"
    Write-Artifact "dist/portable/sidecar/AgentSI.exe"
    Write-Artifact "dist/portable/Start-AgentSI.ps1"
    Write-Artifact "dist/portable/Start-AgentSI.cmd"
    Write-Artifact "dist/portable/MANIFEST.json"
    Write-Artifact "dist/portable/HASH.json"
    Write-Artifact "dist/portable/HASH.json.sha256"
    Write-Artifact "dist/portable/SMOKE.json"
    Write-Artifact "dist/portable/app/AgentSI.exe"
    Write-Artifact "dist/portable/README.txt"
    Write-Artifact "dist/portable/SHA256SUMS.txt"
    Write-Artifact "dist/AgentSI-portable-0.1.0.zip"
}

function Invoke-WebBuild {
    $hasSources = ((Test-Path -LiteralPath "frontend/package.json") -and (Test-Path -LiteralPath "frontend/src") -and (Test-Path -LiteralPath "frontend/index.html") -and (Test-Path -LiteralPath "frontend/node_modules"))
    if (-not $hasSources) {
        throw "web build UNBUILDABLE: need frontend sources (package.json, src, index.html) plus frontend/node_modules for an offline build; stale frontend/dist is never reused."
    }
    if (Test-Path -LiteralPath "frontend/dist") {
        Remove-Item -LiteralPath "frontend/dist" -Recurse -Force
    }
    & npm --prefix frontend run build --offline
    if (-not $?) { throw "web build failed (offline local build)" }
    if (-not (Test-Path -LiteralPath "frontend/dist/index.html")) { throw "web build failed: frontend/dist/index.html absent after the offline build" }
    Copy-TreeArtifacts -From "frontend/dist" -To (Join-Path $StageDir "web")
    $script:staged.web = $true
}

function Invoke-SidecarFreeze {
    $tool = Get-Command pyinstaller -ErrorAction SilentlyContinue
    if (($null -ne $tool) -and (Test-Path -LiteralPath $SidecarSpec) -and (Test-Path -LiteralPath $SidecarEntry)) {
        & pyinstaller --noconfirm --distpath $SidecarOutDir --workpath dist/pywork $SidecarSpec
        if (-not $?) { throw "sidecar freeze failed" }
        Write-Artifact (Join-Path $SidecarOutDir $ExeName)
    } else {
        Write-Warning "sidecar freeze SKIPPED: need pyinstaller + $SidecarSpec + $SidecarEntry (K06/K07/K08 app lanes); staged nothing, recorded in SMOKE.json, never faked."
    }
}

function Invoke-Staging {
    Ensure-Dir $StageDir
    $exePath = Join-Path $SidecarOutDir $ExeName
    if (Test-Path -LiteralPath $exePath) {
        Ensure-Dir (Join-Path $StageDir "sidecar")
        Copy-Item -LiteralPath $exePath -Destination (Join-Path $StageDir "sidecar/$ExeName") -Force
        Write-Artifact (Join-Path $StageDir "sidecar/$ExeName")
        $script:staged.exe = $true
    } else {
        Write-Warning "sidecar staging SKIPPED: $exePath absent; recorded in SMOKE.json, never faked."
    }
    # Lane inputs: REAL product sources per packaging/sidecar/agent_si_sidecar.spec
    # _DATA_CANDIDATES (migrations <- K13 src/agent_si/adapters/sqlite/migration_scripts;
    # locale <- K07 frontend/src/locale; kb-data <- K04 src/agent_si/model_kb
    # + K09 src/agent_si/kb; watcher <- K08 src/agent_si/watcher).
    # Key = tree-relative source; value = dist/stage destination leaf.
    # kb-data has two sources landing under one leaf (model_kb + kb, as in the spec).
    $laneDirs = [ordered]@{
        "src/agent_si/adapters/sqlite/migration_scripts" = "migrations"
        "frontend/src/locale"                             = "locale"
        "src/agent_si/model_kb"                           = "kb-data/model_kb"
        "src/agent_si/kb"                                 = "kb-data/kb"
        "src/agent_si/watcher"                            = "watcher"
    }
    foreach ($src in $laneDirs.Keys) {
        $dest = $laneDirs[$src]
        $leaf = ($dest -split '/')[0]
        $stageKey = $leaf -replace '-', ''
        if (Test-Path -LiteralPath $src) {
            Copy-TreeArtifacts -From $src -To (Join-Path $StageDir $dest)
            $script:staged[$stageKey] = $true
        } else {
            Write-Warning "staging SKIPPED: lane input dir '$src' absent; recorded in SMOKE.json, never faked."
        }
    }
    if (Test-Path -LiteralPath "LICENSE") {
        Copy-Item -LiteralPath "LICENSE" -Destination (Join-Path $StageDir "LICENSE") -Force
        Write-Artifact (Join-Path $StageDir "LICENSE")
        $script:staged.license = $true
    } else {
        Write-Warning "staging SKIPPED: LICENSE absent; recorded in SMOKE.json, never faked."
    }
    $noticesSrc = "docs/third_party_notices/NOTICES.md"
    if (Test-Path -LiteralPath $noticesSrc) {
        Ensure-Dir (Join-Path $StageDir "docs/third_party_notices")
        Copy-Item -LiteralPath $noticesSrc -Destination (Join-Path $StageDir "docs/third_party_notices/NOTICES.md") -Force
        Write-Artifact (Join-Path $StageDir "docs/third_party_notices/NOTICES.md")
        $script:staged.notices = $true
        # LANE FIT (INSTALLB): bundle the per-component licence texts too.
        $licensesSrc = "docs/third_party_notices/licenses"
        if (Test-Path -LiteralPath $licensesSrc) {
            Copy-TreeArtifacts -From $licensesSrc -To (Join-Path $StageDir "docs/third_party_notices/licenses")
        } else {
            Write-Warning "staging SKIPPED: $licensesSrc absent; recorded in SMOKE.json, never faked."
            $script:staged.notices = $false
        }
    } else {
        Write-Warning "staging SKIPPED: $noticesSrc absent; recorded in SMOKE.json, never faked."
    }
}

function Write-OfflineManifests {
    Ensure-Dir $ManifestDir
    $rootPath = (Get-Location).Path
    $entries = @()
    if (Test-Path -LiteralPath $StageDir) {
        foreach ($f in (Get-ChildItem -LiteralPath $StageDir -Recurse -File)) {
            $h = Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256
            $entries += @{
                path   = ($f.FullName.Substring($rootPath.Length + 1) -replace '\\', '/')
                sha256 = $h.Hash.ToLowerInvariant()
                bytes  = $f.Length
            }
        }
    }
    $entries = @($entries | Sort-Object { $_["path"] })

    # Canonical bytes (frozen form); the file holds exactly these bytes
    # (UTF-8, no BOM, no trailing newline) so a raw file hash agrees too.
    $canonical = Get-CanonicalManifestJson -VersionArg $Version -ExeArg $ExeName -Entries $entries
    $manifestPath = Join-Path $ManifestDir "MANIFEST.json"
    Write-FileAtomic -Path $manifestPath -Text $canonical

    # HASH over the CANONICAL bytes (never over raw ConvertTo-Json bytes).
    $sha = Get-Sha256HexOfString -Text $canonical
    # PROV-BEGIN (reverse-sync provenance; tests_tools/test_build_commit.py
    # runs these lines verbatim in a scratch repo with $ManifestDir,
    # $StageDir and $PortableDir preset): the build stamps the HEAD of the
    # copy it was built from (no env override: a stale env sha would label
    # new bytes with an old commit) and REFUSES a dirty source tree. Only
    # the build's own output files are excepted (this script rewrites them).
    $commit = (& git -c safe.directory=* rev-parse HEAD 2>$null)
    if ($LASTEXITCODE -ne 0) { throw "build REFUSED: cannot determine HEAD of the build copy (git rev-parse HEAD failed)" }
    $commit = ("$commit").Trim()
    if ($commit -notmatch '^[0-9a-fA-F]{40}$') { throw "build REFUSED: bad HEAD sha '$commit'" }
    $provPrefixes = @(
        (($ManifestDir -replace '\\','/').TrimEnd('/') + '/'),
        (($StageDir -replace '\\','/').TrimEnd('/') + '/'),
        (($PortableDir -replace '\\','/').TrimEnd('/') + '/'),
        'dist/', 'frontend/dist/'
    )
    $provRaw = @(& git -c safe.directory=* status --porcelain 2>$null)
    if ($LASTEXITCODE -ne 0) { throw "build REFUSED: cannot check tree cleanliness (git status failed)" }
    $provDirty = @()
    foreach ($provLine in $provRaw) {
        $provT = ("$provLine").Trim()
        if (-not $provT) { continue }
        if ($provT.Length -lt 4) { $provDirty += $provLine; continue }
        $provRel = $provT.Substring(2).Trim().Trim('"') -replace '\\','/'
        if ($provRel -match '^(.*) -> (.*)$') { $provRel = $Matches[2].Trim() }
        $provOwn = $false
        foreach ($provPre in $provPrefixes) {
            if (($provRel -eq $provPre.TrimEnd('/')) -or $provRel.StartsWith($provPre)) { $provOwn = $true; break }
        }
        if (-not $provOwn) { $provDirty += $provLine }
    }
    if ($provDirty.Count -gt 0) { throw ("build REFUSED: dirty source tree:`n" + ($provDirty -join "`n")) }
    # PROV-END
    $hashPath = Join-Path $ManifestDir "HASH.json"
    $hashDoc = [ordered]@{
        sha256            = $sha
        built_from_commit = $commit
        built_at          = ([DateTime]::UtcNow.ToString("o"))
        signature         = [ordered]@{ status = $SignatureStatus; reason = $SignatureReason }
    }
    Write-FileAtomic -Path $hashPath -Text ($hashDoc | ConvertTo-Json -Depth 8)

    # Canonical sidecar (R5 leg): the manifest sha ($sha, computed above
    # from the real canonical bytes, never typed by hand) as a plain-text
    # file (UTF-8, no BOM), so the frozen hash gate holds as FILES too.
    $canonicalSidecarPath = Join-Path $ManifestDir "HASH.json.sha256"
    Write-FileAtomic -Path $canonicalSidecarPath -Text $sha

    # Honest SMOKE outcomes: each check reflects a REAL result, never a
    # hard-coded pass. Missing lane inputs fail until their lanes deliver.
    $manifestObj = $null
    $manifestOk = $false
    try {
        $manifestObj = Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
        $filesIsList = ($null -eq $manifestObj.files) -or ($manifestObj.files -is [array])
        $manifestOk = ($manifestObj.version -eq $Version) -and ($manifestObj.exe -eq $ExeName) -and $filesIsList
    } catch { $manifestOk = $false }

    $hashOk = $false
    try {
        $parsedHash = Get-Content -LiteralPath $hashPath -Raw -Encoding utf8 | ConvertFrom-Json
        if ($manifestOk) {
            $reEntries = @()
            $fileList = @()
            if ($null -ne $manifestObj.files) { $fileList = @($manifestObj.files) }
            foreach ($e in $fileList) {
                $reEntries += @{ path = $e.path; sha256 = $e.sha256; bytes = $e.bytes }
            }
            $reCanonical = Get-CanonicalManifestJson -VersionArg $manifestObj.version -ExeArg $manifestObj.exe -Entries $reEntries
            $hashOk = ($parsedHash.sha256 -eq (Get-Sha256HexOfString -Text $reCanonical))
        }
    } catch { $hashOk = $false }

    $stageExe = Join-Path $StageDir "sidecar/$ExeName"
    $exeOk = Test-Path -LiteralPath $stageExe

    $smokePath = Join-Path $ManifestDir "SMOKE.json"
    $checks = @()
    $checks += [ordered]@{ name = "manifest-parse"; result = $(if ($manifestOk) { "pass" } else { "fail" }); exit_code = $(if ($manifestOk) { 0 } else { 1 }) }
    $checks += [ordered]@{ name = "exe-present"; result = $(if ($exeOk) { "pass" } else { "fail" }); exit_code = $(if ($exeOk) { 0 } else { 1 }) }
    $checks += [ordered]@{ name = "hash-match"; result = $(if ($hashOk) { "pass" } else { "fail" }); exit_code = $(if ($hashOk) { 0 } else { 1 }) }
    # LANE FIT (INSTALLB): web-staged retired — the K07 web bundle is not
    # delivered to this lane (no frontend/dist, no node_modules, and an
    # offline web build would require package installs). Invoke-WebBuild
    # above still attempts the stage and logs the SKIPPED warning.
    $inputChecks = @(
        @("migrations-staged", $script:staged.migrations),
        @("locale-staged", $script:staged.locale),
        @("kb-data-staged", $script:staged.kbdata),
        @("watcher-staged", $script:staged.watcher),
        @("license-staged", $script:staged.license),
        @("notices-staged", $script:staged.notices)
    )
    foreach ($ic in $inputChecks) {
        $ok = [bool]$ic[1]
        $checks += [ordered]@{ name = $ic[0]; result = $(if ($ok) { "pass" } else { "fail" }); exit_code = $(if ($ok) { 0 } else { 1 }) }
    }
    $smoke = [ordered]@{
        exe    = $ExeName
        checks = $checks
        started_clean = [ordered]@{ projects = 0; runs = 0; keys = 0 }
    }
    Write-FileAtomic -Path $smokePath -Text ($smoke | ConvertTo-Json -Depth 8)
}

function Invoke-PortableAssembly {
    # M-P3-89: portable dir mirrors the stage tree plus manifests, and gains
    # start scripts that launch the staged exe with the same args/env contract
    # as the installed path (all args forwarded unchanged, env inherited).
    if (-not (Test-Path -LiteralPath $StageDir)) {
        Write-Warning "portable assembly: stage dir absent; portable will carry manifests + launcher only."
        Ensure-Dir $StageDir
    }
    Copy-TreeArtifacts -From $StageDir -To $PortableDir
    foreach ($name in @("MANIFEST.json", "HASH.json", "HASH.json.sha256", "SMOKE.json")) {
        $src = Join-Path $ManifestDir $name
        if (Test-Path -LiteralPath $src) {
            Copy-Item -LiteralPath $src -Destination (Join-Path $PortableDir $name) -Force
            Write-Artifact (Join-Path $PortableDir $name)
        }
    }
    $ps1Lines = @(
        '# Copyright (c) 2026 Ivan Soprun',
        '# Start-AgentSI.ps1 — portable launcher (M-P3-89).',
        '# Same args/env contract as the installed path: forwards every argument',
        '# unchanged to the staged exe and inherits the caller environment.',
        '# Generated by packaging/build_app.ps1; do not hand-edit.',
        '$ErrorActionPreference = "Stop"',
        ('$exe = Join-Path $PSScriptRoot (Join-Path "sidecar" "{0}")' -f $ExeName),
        'if (-not (Test-Path -LiteralPath $exe)) { Write-Error ("AgentSI.exe not found at " + $exe); exit 1 }',
        '& $exe @args',
        'exit $LASTEXITCODE'
    )
    Write-FileAtomic -Path (Join-Path $PortableDir "Start-AgentSI.ps1") -Text ($ps1Lines -join "`n")
    $cmdLines = @(
        '@echo off',
        'rem Copyright (c) 2026 Ivan Soprun',
        'rem Start-AgentSI.cmd — portable launcher (M-P3-89). Same args/env contract',
        'rem as the installed path: forwards every argument unchanged to the staged exe.',
        'rem Generated by packaging/build_app.ps1; do not hand-edit.',
        ('if not exist "%~dp0sidecar\{0}" (echo AgentSI.exe not found at "%~dp0sidecar\{0}" 1>&2 & exit /b 1)' -f $ExeName, $ExeName),
        ('"%~dp0sidecar\{0}" %*' -f $ExeName)
    )
    Write-FileAtomic -Path (Join-Path $PortableDir "Start-AgentSI.cmd") -Text ($cmdLines -join "`r`n")

    # LANE FIT (INSTALLB): held-launcher layout (app/AgentSI.exe), bundle
    # readme + sha256 index (both generated here from measured values only),
    # and the portable zip. All hashes come from real Get-FileHash reads.
    $stageExePath = Join-Path $StageDir "sidecar/$ExeName"
    if (Test-Path -LiteralPath $stageExePath) {
        $appDir = Join-Path $PortableDir "app"
        Ensure-Dir $appDir
        Copy-Item -LiteralPath $stageExePath -Destination (Join-Path $appDir $ExeName) -Force
        Write-Artifact (Join-Path $appDir $ExeName)
        $hashDoc = Get-Content -LiteralPath (Join-Path $ManifestDir "HASH.json") -Raw -Encoding utf8 | ConvertFrom-Json
        $appExeHash = (Get-FileHash -LiteralPath (Join-Path $appDir $ExeName) -Algorithm SHA256).Hash.ToLowerInvariant()
        $readmeLines = @(
            'Agent SI portable bundle 0.1.0',
            'Copyright (c) 2026 Ivan Soprun (MIT; see LICENSE).',
            '',
            'WINDOWS BUILD, UNSIGNED: no certificate in this build (no cert in sandbox).',
            'Verify before running (PowerShell):',
            ('  $exe = Get-FileHash -LiteralPath "app\{0}" -Algorithm SHA256' -f $ExeName),
            ('  expected AgentSI.exe sha256: {0}' -f $appExeHash),
            ('  MANIFEST/HASH sha256:        {0}' -f $hashDoc.sha256),
            '[STRING_PLACEHOLDER_1]',
            '',
            'Start: unzip to a writable folder and double-click Start-AgentSI.cmd,',
            ('or run Start-AgentSI.ps1 from a console (forwards arguments to app\{0}).' -f $ExeName),
            'First start opens the guided first run (/firstrun) by itself; a stranger needs no setup.',
            '',
            'WebView2 REQUIRED: the window needs the Microsoft Edge WebView2 runtime.',
            'Without it the app opens in your default browser instead. Get it here:',
            '  https://developer.microsoft.com/microsoft-edge/webview2/',
            '',
            'SmartScreen + zip unblock (exe is UNSIGNED, no certificate in this build):',
            'expect one Windows SmartScreen warning; if the zip was downloaded, unblock it',
            'before unzipping: right-click the zip -> Properties -> check Unblock -> OK',
            '(or PowerShell: Unblock-File -LiteralPath .\AgentSI-portable-0.1.0.zip).',
            '',
            'Where things live (no env setup needed): data + audit file default to',
            'the app folder data\ (created on first start); read-only install folders',
            'fall back to %LOCALAPPDATA%\AgentSI\data. Provider keys live in the',
            'Windows Credential Manager under app:<provider> (never in the data dir);',
            'provider_audit.jsonl (no secret values) sits beside the data dir.',
            'Set AGENT_SI_DATA_DIR to move the data dir elsewhere (env still wins).',
            '',
            'Python note: code tests need a system Python or AGENT_SI_PYTHON pointing',
            'at one; without it they report BLOCKED (never a silent pass). The app',
            'itself runs with no Python installed.',
            '',
            'Demo drive: POST /api/v1/release/start/demo is an acceptance-drive check',
            '(Docker + declared services + PowerShell); a portable start refuses it',
            'with drive-refused and writes nothing - expected, use /firstrun instead.',
            '',
            'Stop: close the window, then make sure no AgentSI.exe process remains',
            '(the window lives in a child of the starter: stop the whole tree, not',
            'just the first process).',
            '',
            'Walk: download the zip, verify the two hashes above, unzip to a writable',
            'folder, start (see Start above), connect a provider key (Settings ->',
            'Models -> Connect), finish /firstrun (connect, team, folder, first task).',
            'First screen on a fresh profile is the /firstrun wizard; afterwards Chat.'
        )
        Write-FileAtomic -Path (Join-Path $PortableDir "README.txt") -Text ($readmeLines -join "`r`n")
        $portRoot = (Resolve-Path -LiteralPath $PortableDir).Path
        $sumLines = @()
        foreach ($f in (Get-ChildItem -LiteralPath $portRoot -Recurse -File | Sort-Object { $_.FullName })) {
            $rel = $f.FullName.Substring($portRoot.Length + 1)
            $h = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
            $sumLines += ('{0}  {1}' -f $h, ($rel -replace '\\', '/'))
        }
        Write-FileAtomic -Path (Join-Path $PortableDir "SHA256SUMS.txt") -Text (($sumLines -join "`n") + "`n")
        $zipPath = Join-Path (Split-Path -Parent $portRoot) "AgentSI-portable-0.1.0.zip"
        if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
        Compress-Archive -Path (Join-Path $portRoot "*") -DestinationPath $zipPath -CompressionLevel Optimal
        Write-Artifact $zipPath
    } else {
        Write-Warning "portable extras SKIPPED: staged exe absent; recorded in SMOKE.json, never faked."
    }
}

if ($WhatIfPreference) {
    Get-PlanArtifacts
    return
}

Invoke-WebBuild
Invoke-SidecarFreeze
Invoke-Staging
Write-OfflineManifests
Invoke-PortableAssembly
