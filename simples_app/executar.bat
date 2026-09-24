@echo off
title Calculadora Simples Nacional
cd /d "%~dp0"

echo ============================================
echo   Calculadora do Simples Nacional
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERRO] Python nao encontrado no PATH.
  echo Instale o Python em https://www.python.org/downloads/ e marque
  echo a opcao "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".venv" (
  echo Criando ambiente virtual...
  python -m venv .venv
)

echo Ativando ambiente virtual...
call .venv\Scripts\activate.bat

echo Instalando/verificando dependencias...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo.
echo Iniciando o servidor... Acesse http://127.0.0.1:5000
echo (Feche esta janela ou pressione CTRL+C para encerrar)
echo.
start "" http://127.0.0.1:5000
python app.py

pause
