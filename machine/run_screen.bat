@echo off
setlocal enabledelayedexpansion

:: Quick 100-problem screens (same fixed subset): weight-edited model cot/pot, then thinking mode for both models.

set "PRE=..\"
set "SRV=%PRE%\llama.cpp\build\bin\Release\llama-server.exe"
set "HERE=%~dp0"
set "LOGS=..\lab\logs"

if not exist "%LOGS%" mkdir "%LOGS%"

echo Running CoT and PoT experiments...
python -I "%HERE%lab.py" --input val --sample 100 --ports 18091,18092,18093 --name wsp-cot-s100
python -I "%HERE%lab.py" --input val --sample 100 --ports 18091,18092,18093 --name wsp-pot-s100

echo Cleaning up background servers...
taskkill /F /IM "llama-server.exe" /T >nul 2>&1

echo Starting thinking mode experiments...

:: Define a function-like block for think
:: think $PRE/models/Qwen3.5-0.8B-WSP-Q8_0.gguf wsp 18094,18095,18096
set "MODEL1=%PRE%\models\Qwen3.5-0.8B-WSP-Q8_0.gguf"
set "TAG1=wsp"
set "PORTS1=18094,18095,18096"

echo Starting thinking mode for !TAG1!...
for %%p in (%PORTS1:,= %) do (
    start /b "" "%SRV%" -m "%MODEL1%" --host 127.0.0.1 --port %%p --threads 4 --ctx-size 4096 --parallel 1 --cache-ram 0 --ctx-checkpoints 2 --jinja --reasoning on --reasoning-budget 170 --alias qwen > "%LOGS%\think-!TAG1!-%%p.log" 2>&1
)

echo Waiting for servers to be healthy...
call :wait_healthy %PORTS1%
if errorlevel 1 echo [!TAG1!] servers did not come up

python -I "%HERE%lab.py" --variant think --max-tokens 200 --ports "%PORTS1%" --name %TAG1%-think-s100

taskkill /F /IM "llama-server.exe" /T >nul 2>&1

:: Second thinking mode batch
set "MODEL2=%PRE%\models\Qwen_Qwen3.5-0.8B-Q8_0.gguf"
set "TAG2=base"
set "PORTS2=18097,18098,18099"

echo Starting thinking mode for !TAG2!...
for %%p in (%PORTS2:,= %) do (
    start /b "" "%SRV%" -m "%MODEL2%" --host 127.0.0.1 --port %%p --threads 4 --ctx-size 4096 --parallel 1 --cache-ram 0 --ctx-checkpoints 2 --jinja --reasoning on --reasoning-budget 170 --alias qwen > "%LOGS%\think-!TAG2!-%%p.log" 2>&1
)

echo Waiting for servers to be healthy...
call :wait_healthy %PORTS2%
if errorlevel 1 echo [!TAG2!] servers did not come up

python -I "%HERE%lab.py" --variant think --max-tokens 200 --ports "%PORTS2%" --name %TAG2%-think-s100

taskkill /F /IM "llama-server.exe" /T >nul 2>&1

echo SCREEN DONE %date% %time%
pause
exit /b 0

:: wait for every port in %1 to answer /health, give up after ~180s
:wait_healthy
set "WANT=%~1"
set /a WAITED=0
:wait_loop
set "READY=1"
for %%p in (%WANT:,= %) do (
    curl -sf http://127.0.0.1:%%p/health >nul 2>&1 || set "READY=0"
)
if "!READY!"=="1" exit /b 0
set /a WAITED+=1
if !WAITED! geq 180 (
    echo Timed out after 180s; see "%LOGS%\*.log"
    exit /b 1
)
ping -n 2 127.0.0.1 >nul
goto wait_loop
