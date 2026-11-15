@echo off
setlocal enabledelayedexpansion

:: Screen other GGUF models with the plain-letter prompt (full val) and short reasoning (100 problems).
:: usage: run_models.bat tag:file.gguf [tag:file.gguf ...]   (files in qualcomm\models)
::        a bare file.gguf is also accepted; the tag then defaults to the file name without .gguf

set "HERE=%~dp0"
pushd "%HERE%"
set "PRE=..\"
set "SRV=%PRE%\llama.cpp\build\bin\Release\llama-server.exe"
set "LOGS=..\lab\logs"
set "PORTS=18101,18102,18103"

if "%~1"=="" (
    echo Usage: run_models.bat tag:file.gguf [tag:file.gguf ...]
    popd
    exit /b 1
)
if not exist "%SRV%" (
    echo Missing llama-server: %SRV%
    popd
    exit /b 1
)
if not exist "%LOGS%" mkdir "%LOGS%"

for %%S in (%*) do (
    set "TAG="
    set "FILE="
    for /f "tokens=1* delims=:" %%A in ("%%~S") do (
        set "TAG=%%A"
        set "FILE=%%B"
    )
    if not defined FILE (
        set "FILE=!TAG!"
        set "TAG=!FILE:.gguf=!"
    )

    if not exist "%PRE%\models\!FILE!" (
        echo [!TAG!] missing model file: %PRE%\models\!FILE!
    ) else (
        echo Starting models for tag !TAG! on ports %PORTS%...
        for %%p in (%PORTS:,= %) do (
            start /b "" "%SRV%" -m "%PRE%\models\!FILE!" --host 127.0.0.1 --port %%p --threads 4 --ctx-size 4096 --parallel 1 --cache-ram 0 --ctx-checkpoints 2 --jinja --reasoning off --reasoning-budget 0 > "%LOGS%\llm-!TAG!-%%p.log" 2>&1
        )

        echo Waiting for servers to be healthy...
        call :wait_healthy
        if errorlevel 1 (
            echo [!TAG!] servers did not come up, skipping experiments
        ) else (
            echo Running experiments for !TAG!...
            python -I "%HERE%lab.py" --variant letter --input val --ports %PORTS% --name !TAG!-letter
            python -I "%HERE%lab.py" --variant cot --input val --sample 100 --ports %PORTS% --name !TAG!-cot-s100
        )

        echo Cleaning up servers for !TAG!...
        taskkill /F /IM "llama-server.exe" /T >nul 2>&1
        ping -n 3 127.0.0.1 >nul
    )
)

echo MODELS DONE %date% %time%
popd
pause
exit /b 0

:: wait for every port in PORTS to answer /health, give up after ~180s per port set
:wait_healthy
set /a WAITED=0
:wait_loop
set "READY=1"
for %%p in (%PORTS:,= %) do (
    curl -sf http://127.0.0.1:%%p/health >nul 2>&1 || set "READY=0"
)
if "!READY!"=="1" exit /b 0
set /a WAITED+=1
if !WAITED! geq 180 (
    echo Timed out after 180s; see "%LOGS%\llm-!TAG!-*.log"
    exit /b 1
)
ping -n 2 127.0.0.1 >nul
goto wait_loop
