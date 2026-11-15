@echo off
setlocal enabledelayedexpansion

:: One prediction for one problem: starts a llama-server for the model, answers one
:: line of data/val.jsonl, then stops the server again.
:: usage: run_predict.bat [model.gguf] [predict_one.py options]
::   run_predict.bat --list                       show the entries of val.jsonl
::   run_predict.bat --index 3                    predict entry 3 with the base model
::   run_predict.bat --id lvl-0_2015_17 --variant cot
::   run_predict.bat --index 3 --variant cot --max-tokens 1000
::   run_predict.bat --index 3 --variant cot --max-tokens 8000 --ctx-size 16384
::   run_predict.bat --index 3 --variant cot --max-tokens 30000 --ctx-size 0
::   run_predict.bat Qwen3.5-0.8B-WSP-Q8_0.gguf --index 2 --out ..\lab\predictions.jsonl

set "HERE=%~dp0"
pushd "%HERE%"
set "ARGS=%*"
set "MODEL=Qwen_Qwen3.5-0.8B-Q8_0.gguf"

:: an argument ending in .gguf is the model; everything else is passed on to predict_one.py
set "REST="
:parse
if "%~1"=="" goto parsed
if /i "%~x1"==".gguf" (
    set "MODEL=%~nx1"
    shift
    goto parse
)
set "REST=%REST% %1"
shift
goto parse
:parsed

if "%ARGS%"=="" (
    echo Usage: run_predict.bat [model.gguf] [options]
    echo Options:
    echo   --list
    echo   --index [index]
    echo   --id [level-year-number] --variant [cot or official]
    echo   --max-tokens [tokens] --ctx-size [tokens, 0 = model maximum]
    echo   --out [path]
    popd
    pause
    exit /b 1
)

python -I "%HERE%predict_one.py" --serve "%MODEL%" %REST%
set "RC=%ERRORLEVEL%"
popd
pause
exit /b %RC%
