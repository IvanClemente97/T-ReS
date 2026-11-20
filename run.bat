@echo off
set "PYTHONPATH=%~dp0src;%PYTHONPATH%"
python -m t_res %*
