# MVP Lite sem Docker

Este modo roda o sistema em uma unica maquina Windows usando:

- Python para o backend.
- SQLite como banco local.
- Node.js para servir o frontend.

Nao requer Docker nem PostgreSQL.

## Instalar

1. Instale Python 3.12 e marque `Add python.exe to PATH`.
2. Instale Node.js LTS.
3. Copie o projeto para `C:\Bilhetagem`.
4. Execute PowerShell como Administrador:

```powershell
cd C:\Bilhetagem
.\deploy\lite-install.ps1
.\deploy\lite-start.ps1
```

## Acessar

- Frontend: `http://localhost:3000`
- API: `http://localhost:8000/docs`

Usuario inicial:

- `admin`
- `admin12345`

## Banco

O arquivo do banco fica em:

```text
C:\Bilhetagem\data\printbilling.db
```
