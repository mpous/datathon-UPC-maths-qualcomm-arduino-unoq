@echo off
setlocal enabledelayedexpansion

:: Laptop experiment batch: starts 3 LLM servers + 1 embedding server
:: Usage: run_lab_.bat <model.gguf> <tag> [ports]

:: Relative paths based on the location of this script (qualcomm_lab/)
set "STARTER=..\"

set "HERE=%~dp0"
set "LOGS=%~dp0logs"

:: Determine model and tag
set "MODEL=%~1"
if "%MODEL%"=="" set "MODEL=%STARTER%\models\Qwen_Qwen3.5-0.8B-Q8_0.gguf"
set "TAG=%~2"
if "%TAG%"=="" set "TAG=base"
set "PORTS=%~3"
if "%PORTS%"=="" set "PORTS=18081,18084,18085"

:: Paths to executable and logs
set "SRV=%STARTER%\llama.cpp\build\bin\Release\llama-server.exe"

if not exist "%LOGS%" mkdir "%LOGS%"

echo Waiting for starter data at %STARTER%\data\val.jsonl ...
:wait_data
if not exist "%STARTER%\data\val.jsonl" (
    timeout /t 10 /nobreak > nul
    goto wait_data
)

echo Starting LLM servers on ports: %PORTS%
for %%p in (%PORTS:,= %) do (
    echo Starting server on port %%p...
    start /b "" "%SRV%" -m "%MODEL%" --host 127.0.0.1 --port %%p --threads 4 --ctx-size 4096 --parallel 1 --cache-ram 0 --ctx-checkpoints 2 --jinja --reasoning off --reasoning-budget 0 --alias qwen > "%LOGS%\llm-%TAG%-%%p.log" 2>&1
)

echo Starting Embedding server on port 18090...
start /b "" "%SRV%" -m "%STARTER%\models\bge-small-en-v1.5-q8_0.gguf" --embedding --host 127.0.0.1 --port 18090 --threads 4 --ctx-size 512 --parallel 1 --cache-ram 0 --batch-size 512 --ubatch-size 512 > "%LOGS%\embed.log" 2>&1

echo Waiting for servers to be healthy...
for %%p in (%PORTS:,= %) do (
    :wait_port
    curl -sf localhost:%%p/health >nul 2>&1 || (timeout /t 1 /nobreak > nul & goto wait_port)
)
:wait_embed
curl -sf localhost:18090/health >nul 2>&1 || (timeout /t 1 /nobreak > nul & goto wait_embed)

set "EMBED_PORT=18090"

if not exist "%STARTER%\data\index.db" (
  echo Building index...
  cd /d "%STARTER%"
  python build_index.py --languages eng
  echo.
)

echo Running experiments...
python -I "%HERE%lab.py" --ports "%PORTS%" --variant letter --input val --name %TAG%-letter
python -I "%HERE%lab.py" --ports "%PORTS%" --variant letter --input train --limit 450 --name %TAG%-letter-train
python -I "%HERE%lab.py" --ports "%PORTS%" --variant rag --k 1 --input val --name %TAG%-rag1
python -I "%HERE%lab.py" --ports "%PORTS%" --variant rag --k 2 --input val --name %TAG%-rag2
python -I "%HERE%lab.py" --ports "%PORTS%" --variant cot --input val --name %TAG%-cot
python -I "%HERE%lab.py" --ports "%PORTS%" --variant pot --input val --name %TAG%-pot

echo ALL DONE %TAG% %date% %time%
pause
