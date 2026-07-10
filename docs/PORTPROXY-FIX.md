# PortProxy Fix — WSL2 Network Troubleshooting

> **Date:** 2026-07-10, **Affects:** AI-CLAW (Windows + WSL2 Kali, Docker host network mode)

## Symptom

External agents (e.g., Pawly via Tailscale IP `100.70.166.21:18880`) get `Connection timed out` or `Connection reset` while:
- `curl http://127.0.0.1:18880/health` on the WSL2 host works fine
- CORE container is running and healthy
- portproxy rule appears to exist (`netsh interface portproxy show v4tov4`)

## Root Cause

Two-part failure:

### 1. wslrelay loopback-only

`wslrelay.exe` (WSL2's Windows-side network relay) only binds to `127.0.0.1`. This means:
- `0.0.0.0:18880 → 127.0.0.1:18880` routes through wslrelay, which only listens on loopback
- External traffic (Tailscale, LAN) never reaches the WSL2 side

### 2. WSL2 IP drift

WSL2 IP addresses (e.g., `172.19.227.99` on the `vEthernet (WSL)` adapter) change after:
- Windows sleep/wake
- WSL2 restart (`wsl --shutdown`)
- Docker Desktop restart

When WSL2 IP changes, the portproxy rule still points to the old IP → silent packet drop.

## Fix

### Step 1: Point portproxy at WSL2 eth0, not 127.0.0.1

```batch
@echo off
REM Get WSL2 eth0 IP (first token from hostname -I)
for /f "tokens=1" %%a in ('wsl -d kali-linux hostname -I') do set WSL_IP=%%a
REM Delete old rule
netsh interface portproxy delete v4tov4 listenport=18880 listenaddress=0.0.0.0 >nul 2>&1
REM Add new rule pointing directly to WSL2 eth0
netsh interface portproxy add v4tov4 listenport=18880 listenaddress=0.0.0.0 connectport=18880 connectaddress=%WSL_IP%
echo PortProxy updated: 0.0.0.0:18880 to %WSL_IP%:18880
```

Script location: `C:\agentwire\update_portproxy.bat`

### Step 2: Periodic self-healing health check

PowerShell script at `C:\agentwire\healthcheck_portproxy.ps1`:
- Checks local CORE health (`127.0.0.1:18880/health`)
- If local OK but Tailscale path fails → runs `update_portproxy.bat`
- Runs every 1 minute via `schtasks`

## Diagnostic Commands

```powershell
# Check portproxy rules
netsh interface portproxy show v4tov4

# Check WSL2 IP
wsl -d kali-linux hostname -I

# Test local CORE
curl http://127.0.0.1:18880/health

# Test Tailscale path
curl http://100.70.166.21:18880/health

# Check scheduled tasks
schtasks /Query /TN "AgentWire-PortProxyHealthCheck"
schtasks /Query /TN "AgentWire-UpdatePortProxy"

# View health check log
Get-Content C:\agentwire\portproxy_healthcheck.log -Tail 10 -Wait
```

## Long-Term Solution

**Tailscale serve** (planned for v2.2.0):
- CORE registers directly with Tailscale network
- No portproxy needed — Tailscale handles L3 routing natively
- Eliminates both wslrelay and IP drift problems

Until Tailscale serve is available, the 1-minute health check keeps the path alive.

## Registry Key Note

`netsh interface portproxy` requires administrator privileges. The health check scheduled task runs as `SYSTEM` to ensure it can modify portproxy rules.
