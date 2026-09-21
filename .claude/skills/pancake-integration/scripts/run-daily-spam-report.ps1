# Wrapper for Windows Task Scheduler: runs pancake_spam_report.py (today 00:00-16:59:59)
# and appends timestamped output to logs/spam-report.log.
$ErrorActionPreference = "Continue"
$logDir = Join-Path $PSScriptRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$logFile = Join-Path $logDir "spam-report.log"

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"---- $timestamp ----" | Out-File -FilePath $logFile -Append -Encoding utf8

python "$PSScriptRoot\pancake_spam_report.py" 2>&1 |
    Out-File -FilePath $logFile -Append -Encoding utf8
