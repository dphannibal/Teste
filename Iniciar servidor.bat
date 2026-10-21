@echo off
chcp 65001 >nul
title Agenda de Licitações - servidor
cd /d "%~dp0"

rem Dados (banco, chave das sessões, brasão) e ambiente Python ficam FORA da pasta
rem compartilhada, para os usuários da rede não terem acesso direto a eles.
set "DADOS=%ProgramData%\AgendaLicitacoes"
set "PY=%DADOS%\venv\Scripts\python.exe"

where python >nul 2>nul
if errorlevel 1 if not exist "%PY%" (
  echo Python não encontrado neste computador.
  echo Instale o Python 3.10 ou mais novo em https://www.python.org/downloads/
  echo e marque a opção "Add python.exe to PATH" durante a instalação.
  pause
  exit /b 1
)

if not exist "%PY%" (
  echo Primeira execução: preparando o ambiente em "%DADOS%"...
  python -m venv "%DADOS%\venv"
  if errorlevel 1 ( pause & exit /b 1 )
)

rem Instala as dependências só quando o requirements.txt mudar.
fc /b requirements.txt "%DADOS%\requirements.instalado" >nul 2>nul
if errorlevel 1 (
  echo Instalando as dependências...
  "%PY%" -m pip install --quiet --disable-pip-version-check -r requirements.txt
  if errorlevel 1 ( echo Falha ao instalar as dependências. & pause & exit /b 1 )
  copy /y requirements.txt "%DADOS%\requirements.instalado" >nul
)

"%PY%" servidor.py --dados "%DADOS%" %*
pause
