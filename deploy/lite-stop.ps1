Get-Process -Name python,node -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "*\Bilhetagem\*" -or $_.CommandLine -like "*Bilhetagem*"
} | Stop-Process -Force
