# Instalador Windows

Este diretorio gera um instalador `.exe` do Open POS para cliente final.

## Requisitos na maquina de build

- Windows
- Python/venv do projeto ja criado
- Inno Setup 6 instalado

## Gerar instalador

No PowerShell, dentro da raiz do projeto:

```powershell
.\installer\build_installer.ps1
```

Saida esperada:

```text
installer\Output\OpenPOS_Setup.exe
```

## Comportamento no cliente

- Instala em `%LOCALAPPDATA%\Open POS`.
- Cria atalho no menu iniciar.
- Cria icone na Area de Trabalho.
- Ao abrir pela primeira vez, cria `data\openpos.db` automaticamente.
- O banco novo vem sem produtos cadastrados.
- Login inicial: `admin` / `admin123`.

## Observacoes

- Dados do cliente ficam em `data\` dentro da pasta instalada.
- Fotos de produtos ficam em `data\product_images`.
- Backups ficam em `data\backups`.
- Logs ficam em `data\logs`.
