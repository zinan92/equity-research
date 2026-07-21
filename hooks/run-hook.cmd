: <<'BATCH_SCRIPT'
@echo off
REM Polyglot wrapper: runs as .cmd on Windows, as bash on Unix
REM Usage: run-hook.cmd session-start

setlocal
set "SCRIPT_DIR=%~dp0"
set "HOOK_NAME=%~1"

if "%HOOK_NAME%"=="" (
    echo Usage: run-hook.cmd ^<hook-name^>
    exit /b 1
)

if exist "%SCRIPT_DIR%%HOOK_NAME%.cmd" (
    call "%SCRIPT_DIR%%HOOK_NAME%.cmd"
) else if exist "%SCRIPT_DIR%%HOOK_NAME%" (
    bash "%SCRIPT_DIR%%HOOK_NAME%"
) else (
    echo Hook not found: %HOOK_NAME%
    exit /b 1
)
exit /b 0
BATCH_SCRIPT

#!/usr/bin/env bash
# Polyglot: Windows sees the BATCH above, Unix runs bash below
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK_NAME="${1:?Usage: run-hook.cmd <hook-name>}"

if [ -x "$SCRIPT_DIR/$HOOK_NAME" ]; then
    exec "$SCRIPT_DIR/$HOOK_NAME"
elif [ -f "$SCRIPT_DIR/$HOOK_NAME" ]; then
    exec bash "$SCRIPT_DIR/$HOOK_NAME"
else
    echo "Hook not found: $HOOK_NAME" >&2
    exit 1
fi
