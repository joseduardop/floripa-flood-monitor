# wsl-portproxy.ps1 - encaminha as portas do Windows (Acer) para o broker/dashboard no WSL2.
# rode no PowerShell como ADMINISTRADOR. rode de novo apos cada reboot do WSL/Acer
# (o IP do WSL2 muda a cada reinicio).

$wsl = (wsl hostname -I).Trim().Split(" ")[0]
Write-Host "IP atual do WSL: $wsl"

netsh interface portproxy reset
netsh interface portproxy add v4tov4 listenport=1883 listenaddress=0.0.0.0 connectport=1883 connectaddress=$wsl
netsh interface portproxy add v4tov4 listenport=8501 listenaddress=0.0.0.0 connectport=8501 connectaddress=$wsl

New-NetFirewallRule -DisplayName "MQTT 1883"     -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow -ErrorAction SilentlyContinue | Out-Null
New-NetFirewallRule -DisplayName "Streamlit 8501" -Direction Inbound -Protocol TCP -LocalPort 8501 -Action Allow -ErrorAction SilentlyContinue | Out-Null

netsh interface portproxy show v4tov4
Write-Host "pronto - broker (1883) e dashboard (8501) do WSL acessiveis pelo IP WireGuard do Acer."
