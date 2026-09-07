@echo off
cd /d "%~dp0"
echo ========================================
echo  Open POS - Iniciando
echo ========================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo Criando ambiente virtual e instalando dependencias...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ERRO: Python nao encontrado. Instale Python 3.10+ em https://python.org
        pause
        exit /b 1
    )
    venv\Scripts\python.exe -m pip install --upgrade pip >nul
    venv\Scripts\python.exe -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo ERRO: Falha ao instalar dependencias.
        pause
        exit /b 1
    )
    echo OK: Dependencias instaladas.
)

echo - Verificando dependencias...
venv\Scripts\python.exe -c "import PySide6, PIL, win32print" 2>nul
if %errorlevel% neq 0 (
    echo Instalando dependencias faltantes...
    venv\Scripts\python.exe -m pip install -r requirements.txt
)

echo - Abrindo Open POS...
start "" "venv\Scripts\pythonw.exe" main.py
echo OK: Aplicacao aberta.
echo.
echo Login padrao: admin / admin123
pause