# SSH setup — getting home

To use rover remotely you need a reliable SSH path back to your Mac. Three approaches, in order of recommendation: mesh VPN (Tailscale), self-hosted VPN on your router, or port forwarding with dynamic DNS. Most people should use Tailscale — it requires no router configuration and works through any NAT. Power users with capable routers can self-host WireGuard or OpenVPN for full control. Port forwarding is the fallback when neither is viable.

## Auto-launch rover on SSH

Add to your shell's startup file so every SSH login drops straight into rover.

**zsh** — `~/.zshrc`:

```bash
# Auto-launch rover on SSH login, but drop back to the shell on quit
# (no `exec` — otherwise quitting rover terminates the SSH session).
if [[ -n "$SSH_CONNECTION" ]] \
   && [[ -z "$TMUX" ]] \
   && [[ -z "$ROVER_LAUNCHED" ]] \
   && command -v rover >/dev/null 2>&1; then
  export ROVER_LAUNCHED=1
  rover
fi
```

**bash** — `~/.bash_profile` (macOS) or `~/.bashrc` (Linux):

```bash
# Auto-launch rover on SSH login, but drop back to the shell on quit
# (no `exec` — otherwise quitting rover terminates the SSH session).
if [[ -n "$SSH_CONNECTION" ]] \
   && [[ -z "$TMUX" ]] \
   && [[ -z "$ROVER_LAUNCHED" ]] \
   && command -v rover >/dev/null 2>&1; then
  export ROVER_LAUNCHED=1
  rover
fi
```

Guards: only fires over SSH, outside an existing tmux session, only when `rover` is on PATH, and only once per shell — the `ROVER_LAUNCHED` flag stops re-entry if rover spawns a subshell that re-sources your rc file. No `exec`, so quitting rover drops back to your shell instead of killing the SSH session.

Reload after editing:

```bash
source ~/.zshrc   # or source ~/.bash_profile
```

## Option A — Tailscale (recommended)

Tailscale is a zero-config mesh VPN built on WireGuard. It works through NAT, requires no port forwarding, and takes about five minutes to set up. The free tier supports up to 3 devices, which is enough for a Mac and a phone.

**Mac:**

```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

Then launch Tailscale from the menu bar and log in.

**Phone:** App Store or Google Play → search "Tailscale" → install → log in with the same account.

Once both devices are on the same tailnet, SSH from your phone's SSH client using the Tailscale IP shown in the Tailscale app or at `https://login.tailscale.com/admin/machines`:

```bash
ssh user@100.x.y.z
```

Tailscale assigns stable IPs (100.x.y.z range) that don't change between reconnects. You can also enable MagicDNS to use `mac-hostname.tailnet-name.ts.net` instead of an IP.

## Option B — Self-hosted VPN on your router

If you prefer to keep traffic off a third-party network, most capable routers have a built-in VPN server. Pick the protocol your router supports.

### WireGuard (recommended for router VPN)

Modern, fast, built into the Linux kernel. Lower overhead than OpenVPN; simpler key management than IPSec.

Routers with native WireGuard support:
- **GL.iNet** — all current models (MT-3000, MT-6000, MT-300N-V2, etc.) have a WireGuard GUI built in. Best option if you want a travel router. [vpn.gl-inet.com](https://vpn.gl-inet.com)
- **OpenWRT** — install the `luci-app-wireguard` package. Runs on hundreds of models. [openwrt.org/docs/guide-user/services/vpn/wireguard/start](https://openwrt.org/docs/guide-user/services/vpn/wireguard/start)
- **pfSense / OPNsense** — WireGuard plugin built in. [docs.opnsense.org/manual/vpnet.html](https://docs.opnsense.org/manual/vpnet.html)
- **Firewalla** — WireGuard server in the Firewalla app under VPN Server.
- **TP-Link** — Archer AX/AXE series: Advanced → VPN Server → WireGuard.
- **ASUS** — RT-AX series: Advanced Settings → VPN → VPN Server → WireGuard.

**Phone client:** official WireGuard app — App Store or Google Play.

### OpenVPN (most widely supported)

Available on nearly every consumer router that has VPN server capability. Slower than WireGuard but battle-tested and ubiquitous.

Routers with native OpenVPN server:
- **GL.iNet** — GUI built in alongside WireGuard.
- **TP-Link** — Archer AC/AX series: Advanced → VPN Server → OpenVPN.
- **ASUS** — RT-AX/RT-AC series: Advanced Settings → VPN → VPN Server → OpenVPN.
- **Netgear** — Nighthawk R7000, R8000, RS series: Advanced → Advanced Setup → VPN Service.
- **Linksys** — WRT3200ACM, WRT32X, WRT1900ACS: run OpenWRT-compatible firmware with OpenVPN.
- **D-Link** — DIR-3060, DIR-X5460, and most DIR-X series: Advanced → VPN Settings.
- **pfSense / OPNsense** — full enterprise-grade configuration. [docs.opnsense.org/manual/vpn.html](https://docs.opnsense.org/manual/vpn.html)
- **OpenWRT** — install the `openvpn` package. [openwrt.org/docs/guide-user/services/vpn/openvpn/basic](https://openwrt.org/docs/guide-user/services/vpn/openvpn/basic)

Check your router's admin panel under Advanced → VPN or a similar path; the exact label varies by firmware version.

**Phone client:** OpenVPN Connect (official app) — App Store or Google Play.

### IKEv2/IPSec (no phone app required)

IKEv2 is natively supported by iOS and Android — no third-party app to install on the phone.

Routers with IKEv2/IPSec support:
- **pfSense / OPNsense** — via StrongSwan. Most complete implementation.
- **Mikrotik** — built-in IKEv2 server.
- **ASUS** — select RT-AX models support IPSec VPN.

**iOS:** Settings → VPN → Add VPN Configuration → IKEv2

**Android:** Settings → Network & Internet → VPN → + → type: IKEv2/IPSec

## Option C — Port forwarding + Dynamic DNS (fallback)

Use this if you can't run a VPN. It works but exposes SSH directly to the internet, so harden accordingly (see caveat below).

**Enable Remote Login on your Mac:**

System Settings → General → Sharing → Remote Login → enable.

Find your Mac's LAN IP:

```bash
ipconfig getifaddr en0
```

**Forward port 22 (or a custom port) in your router** to that LAN IP. The exact path varies: look for Port Forwarding or NAT under Advanced in your router's admin panel.

Connect from your phone:

```bash
ssh -p 22 user@your-public-ip
```

**Dynamic DNS** — most home ISPs assign a dynamic public IP that changes on reconnect. A DDNS service gives you a stable hostname that tracks your current IP.

Popular options:
- **DuckDNS** — [duckdns.org](https://www.duckdns.org) — free, simple, no account required beyond OAuth. Update via a cron job.
- **No-IP** — [noip.com](https://www.noip.com) — free tier available; has a macOS Dynamic Update Client (DUC).
- **Cloudflare** — if you own a domain, update an A record via the Cloudflare API. More setup, but you keep your own domain.
- **Dynu** — [dynu.com](https://www.dynu.com) — free, supports custom hostnames.

DuckDNS update via cron (runs every 5 minutes):

```bash
*/5 * * * * curl -s "https://www.duckdns.org/update?domains=YOURDOMAIN&token=YOURTOKEN&ip=" > /dev/null 2>&1
```

Add with `crontab -e`. Replace `YOURDOMAIN` and `YOURTOKEN` with the values from your DuckDNS dashboard.

SSH using the DDNS hostname:

```bash
ssh user@yourhostname.duckdns.org
```

**Caveat:** port forwarding puts SSH on the public internet. Mitigate the exposure:
- Use a non-standard port (e.g. 2222) to reduce automated scan noise.
- Disable password authentication — key-only auth in `/etc/ssh/sshd_config`: `PasswordAuthentication no`.
- macOS's built-in SSH rate limiting is on by default; consider `fail2ban` if you see heavy scan traffic in `/var/log/auth.log`.

## SSH clients for your phone

**iOS:**
- **Blink Shell** — best-in-class; hardware keyboard support, Mosh, local shell. Paid.
- **Termius** — free tier works; syncs hosts and keys across devices. iOS and Android.
- **a-Shell** — free, full local shell environment with SSH.

**Android:**
- **Termius** — see above.
- **JuiceSSH** — free, clean UI.
- **ConnectBot** — open source, no frills.
