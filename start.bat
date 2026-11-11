@echo off
cd /d %~dp0
title Sistema de Biblioteca

if not exist "venv\Scripts\activate.bat" (
    echo [1/3] Creando entorno virtual...
    py -m venv venv
    echo [2/3] Instalando dependencias...
    call venv\Scripts\activate.bat && pip install -r requirements.txt
) else (
    echo [1/2] Entorno virtual encontrado.
)

echo [3/3] Iniciando servidor...
echo.
echo Abra http://127.0.0.1:5000
echo Desarrollo: admin@escuela.local / admin123
echo.
call venv\Scripts\activate.bat && python run.py
pause
