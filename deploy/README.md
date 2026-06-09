# Deploy no servidor

Execute no servidor Windows, dentro da pasta do projeto:

```powershell
cd C:\Bilhetagem
.\deploy\install-server.ps1 -Rebuild
```

Depois acesse:

- Frontend: `http://26.119.90.177:3000`
- API: `http://26.119.90.177:8000/docs`

O arquivo `.env` controla senhas, segredo JWT e URLs publicas.
