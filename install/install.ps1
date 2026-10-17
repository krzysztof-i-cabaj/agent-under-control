# ==============================================================================
# Tytul:        install.ps1
# Opis:         Instaluje hooki i agenta agent-under-control do katalogu Claude Code:
#               kopia zapasowa, kopiowanie plikow, scalenie settings.json (bez nadpisywania)
# Description [EN]: Installs the agent-under-control hooks and agent into the Claude Code
#               directory: backup, file copy, settings.json merge (never overwrite)
#
# Autor:        KCB Kris
# Data:         2026-10-17
# Wersja:       1.1 (decision_log.py + zdarzenia PermissionRequest/PermissionDenied/PostToolUse(Failure) / log-only hook events)
# Konwencje:    README.md (sekcja Install - scripted)
#
# Wymagania [PL]:    - PowerShell 7+, Python 3.10+, Windows 10/11
# Requirements [EN]: - PowerShell 7+, Python 3.10+, Windows 10/11
#
# Uzycie [PL]:       pwsh install/install.ps1 -DryRun      (podglad, nic nie zmienia)
#                    pwsh install/install.ps1              (instalacja)
# Usage [EN]:        pwsh install/install.ps1 -DryRun      (preview, changes nothing)
#                    pwsh install/install.ps1              (install)
# ==============================================================================
#Requires -Version 7.0
[CmdletBinding()]
param(
    [switch]$DryRun,
    [string]$ClaudeDir = (Join-Path $HOME '.claude'),
    [string]$Python = ''
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Backup = Join-Path $ClaudeDir "backups/agent-under-control-$Stamp"
$HooksDir = Join-Path $ClaudeDir 'hooks'

function Step($text) { Write-Host ("{0} {1}" -f ($(if ($DryRun) { '[DRY-RUN]' } else { '[RUN]    ' })), $text) }

# --- 1. Python: pelna sciezka (hook z golym "python" moze po cichu zniknac) / full path ---
if (-not $Python) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd -or $cmd.Source -like '*WindowsApps*') { throw 'Python not found (or only the Microsoft Store alias). Pass -Python "C:/path/to/python.exe".' }
    $Python = $cmd.Source
}
$ver = & $Python -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$ver -lt [version]'3.10') { throw "Python $ver found, 3.10+ required: $Python" }
$PyFwd = $Python -replace '\\', '/'
$HooksFwd = $HooksDir -replace '\\', '/'
Write-Host "Python:     $Python ($ver)"
Write-Host "Claude dir: $ClaudeDir"
Write-Host "Backup:     $Backup`n"

# --- 2. Kopia zapasowa istniejacych plikow / backup of existing files ---
$targets = @(
    (Join-Path $HooksDir 'path_guard.py'),
    (Join-Path $HooksDir 'readonly_bash_guard.py'),
    (Join-Path $HooksDir 'decision_log.py'),
    (Join-Path $ClaudeDir 'agents/docs-auditor.md'),
    (Join-Path $ClaudeDir 'settings.json'),
    (Join-Path $ClaudeDir 'path_guard.config.json')
)
foreach ($t in $targets | Where-Object { Test-Path $_ }) {
    Step "backup  $t"
    if (-not $DryRun) {
        New-Item -ItemType Directory -Force $Backup | Out-Null
        Copy-Item $t (Join-Path $Backup (Split-Path $t -Leaf))
    }
}

# --- 3. Hooki i agent / hooks and agent ---
foreach ($f in 'path_guard.py', 'readonly_bash_guard.py', 'decision_log.py') {
    Step "copy    hooks/$f -> $HooksDir"
    if (-not $DryRun) {
        New-Item -ItemType Directory -Force $HooksDir | Out-Null
        Copy-Item (Join-Path $Root "hooks/$f") (Join-Path $HooksDir $f) -Force
    }
}
$agentDst = Join-Path $ClaudeDir 'agents/docs-auditor.md'
Step "write   agents/docs-auditor.md (python and hooks path filled in)"
if (-not $DryRun) {
    New-Item -ItemType Directory -Force (Split-Path $agentDst) | Out-Null
    $agent = (Get-Content -Raw (Join-Path $Root 'agents/docs-auditor.md')).Replace('__PYTHON__', $PyFwd).Replace('__HOOKS_DIR__', $HooksFwd)
    $agent | Set-Content -Encoding utf8NoBOM -NoNewline $agentDst
}

# --- 4. Konfiguracja path_guard (tylko gdy jej nie ma) / config only if missing ---
$cfg = Join-Path $ClaudeDir 'path_guard.config.json'
if (Test-Path $cfg) { Step "keep    $cfg (exists, not touched)" }
else {
    Step "create  $cfg from example - EDIT 'workspaces' afterwards"
    if (-not $DryRun) { Copy-Item (Join-Path $Root 'hooks/path_guard.config.example.json') $cfg }
}

# --- 5. Scalenie settings.json / settings.json merge ---
$settingsPath = Join-Path $ClaudeDir 'settings.json'
$settings = if (Test-Path $settingsPath) { Get-Content -Raw $settingsPath | ConvertFrom-Json -AsHashtable } else { @{} }
$example = Get-Content -Raw (Join-Path $Root 'settings/settings.example.json') | ConvertFrom-Json -AsHashtable
if (-not $settings.ContainsKey('permissions')) { $settings.permissions = @{} }
foreach ($kind in 'deny', 'ask') {
    $have = @($settings.permissions[$kind] | Where-Object { $_ })
    foreach ($rule in $example.permissions[$kind]) {
        if ($have -notcontains $rule) { Step "add     permissions.$kind  $rule"; $have += $rule }
    }
    $settings.permissions[$kind] = $have
}
if (-not $settings.ContainsKey('hooks')) { $settings.hooks = @{} }
# Kazde zdarzenie z szablonu: dodaj, jesli ten skrypt nie jest jeszcze podpiety / add per event if script not wired
foreach ($hookEvent in $example.hooks.Keys) {
    $have = @($settings.hooks[$hookEvent] | Where-Object { $_ })
    foreach ($entry in $example.hooks[$hookEvent]) {
        $script = ([regex]::Match($entry.hooks[0].command, '[\w-]+\.py')).Value
        $entry.hooks[0].command = $entry.hooks[0].command.Replace('__PYTHON__', $PyFwd).Replace('__HOOKS_DIR__', $HooksFwd)
        $already = $have | Where-Object { $_.hooks | Where-Object { $_.command -like "*$script*" } }
        if ($already) { Step "keep    hooks.$hookEvent $script (already wired - check the python path by hand)" }
        else { Step "add     hooks.$hookEvent -> $($entry.hooks[0].command)"; $have += $entry }
    }
    $settings.hooks[$hookEvent] = $have
}
if (-not $DryRun) {
    $settings | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8NoBOM $settingsPath
    $null = Get-Content -Raw $settingsPath | ConvertFrom-Json   # weryfikacja: poprawny JSON / verify valid JSON
}

# --- 6. Weryfikacja / verification ---
Write-Host ''
if ($DryRun) { Write-Host 'Dry run finished - nothing was changed. Run again without -DryRun to install.' }
else {
    Step 'test    python tests/run_tests.py'
    & $Python (Join-Path $Root 'tests/run_tests.py')
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed - see above. Restore from backup if needed.' }
    Write-Host "`nDone. Next: edit 'workspaces' in $cfg, then start a NEW Claude Code session."
}
