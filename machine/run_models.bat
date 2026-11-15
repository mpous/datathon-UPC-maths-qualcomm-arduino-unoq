@echo off
setlocal enabledelayedexpansion

:: Screen other GGUF models with the plain-letter prompt (full val) and short reasoning (100 problems).
:: usage: run_models.bat tag:file.gguf [tag:file.gguf ...] (files in board-prefetch/models)

set "PRE=..\"
set "SRV=%PRE%\llama.cpp\build\bin\Release\llama-server.exe"
set "HERE=%~dp0"
set "LOGS=..\lab\logs"
set "PORTS=18101,18102,18103"

if "%~1"=="" (
    echo Usage: run_models.bat tag:file.gguf [tag:file.gguf ...]
    exit /b 1
)

for %%S in (%*) do (
    set "SPEC=%%S"
    for /f "tokens=1* delims=:" %%A in ("!SPEC!") do (
        set "TAG=%%A"
        set "FILE=%%B"
    )

    echo Starting models for tag !TAG! on ports %PORTS%...
    for %%p in (%PORTS:,= %) do (
        start /b "" "%SRV%" -m "%PRE%\models\!FILE!" --host 127.0.0.1 --port %%p --threads 4 --ctx-size 4096 --parallel 1 --cache-ram 0 --ctx-checkpoints 2 --jinja --reasoning off --reasoning-budget 0 > "%LOGS%\llm-!TAG!-%%p.log" 2>&1
    )

    echo Waiting for servers to be healthy...
    for %%p in (%PORTS:,= %) do (
        :wait_port
        curl -sf localhost:%%p/health >nul 2>&1 || (timeout /t 1 /nobreak > nul & goto wait_port)
    )

    echo Running experiments for !TAG!...
    python -I "%HERE%lab.py" --variant letter --input val --ports %PORTS% --name !TAG!-letter
    python -I "%HERE%lab.py" --variant cot --input val --sample 100 --ports %PORTS% --name !TAG!-cot-s100

    echo Cleaning up servers for !TAG!...
    taskkill /F /IM "llama-server.exe" /T >nul 2>&1
    timeout /t 2 /nobreak > nul
)

echo MODELS DONE %date% %time%
pause
