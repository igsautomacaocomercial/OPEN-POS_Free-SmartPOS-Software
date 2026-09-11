param(
    [string]$InnoSetupCompiler = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root "venv\Scripts\python.exe"
$distExe = Join-Path $root "dist\OpenPOS\OpenPOS.exe"
$iconPath = Join-Path $PSScriptRoot "openpos.ico"
$issPath = Join-Path $PSScriptRoot "openpos.iss"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Ambiente virtual nao encontrado: $venvPython. Rode rodar.bat uma vez antes de gerar o instalador."
}

& $venvPython -m pip install -r (Join-Path $root "requirements.txt")
& $venvPython -m pip install pyinstaller
& $venvPython (Join-Path $PSScriptRoot "create_icon.py") $iconPath

& $venvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "OpenPOS" `
    --icon $iconPath `
    --add-data "web;web" `
    --hidden-import "qrcode.image.svg" `
    (Join-Path $root "main.py")

if (-not (Test-Path -LiteralPath $distExe)) {
    throw "Executavel nao gerado: $distExe"
}

if (-not (Test-Path -LiteralPath $InnoSetupCompiler)) {
    throw "Inno Setup nao encontrado em $InnoSetupCompiler. Instale o Inno Setup 6 ou informe o caminho com -InnoSetupCompiler."
}

& $InnoSetupCompiler $issPath
"Instalador gerado em: $(Join-Path $PSScriptRoot 'Output')"
