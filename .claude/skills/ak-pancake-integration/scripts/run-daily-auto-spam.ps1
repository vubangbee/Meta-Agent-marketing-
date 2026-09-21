# Wrapper for Windows Task Scheduler: runs pancake_auto_spam_tagged.py and appends
# timestamped output to logs/auto-spam-tagged.log, so a silent failure (e.g. the
# internal session token expiring ~2026-11-15) is visible without a terminal open.
$ErrorActionPreference = "Continue"
$logDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$logFile = Join-Path $logDir "auto-spam-tagged.log"

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"---- $timestamp ----" | Out-File -FilePath $logFile -Append -Encoding utf8

python "$PSScriptRoot\pancake_auto_spam_tagged.py" 2>&1 |
    Out-File -FilePath $logFile -Append -Encoding utf8
