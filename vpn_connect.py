# -*- coding: utf-8 -*-
"""
GitHub Actions VPN Tunnel Connector (VPNGate Thailand)
============================================================
"""

import sys
import io
import urllib.request
import csv
import base64
import subprocess
import time
import json
import os

# Prevent console encoding issues on Windows/Linux
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

VPNGATE_API = "http://www.vpngate.net/api/iphone/"
CONFIG_FILE = "vpn_config.ovpn"

def check_ip():
    """Checks the current public IP and returns the country code."""
    urls = [
        "https://ipinfo.io/json",
        "http://ip-api.com/json/"
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode('utf-8', errors='ignore'))
                country = data.get('country') or data.get('countryCode')
                ip = data.get('ip') or data.get('query')
                if country:
                    return ip, country.upper()
        except Exception:
            continue
    return None, None

def get_thai_vpn_servers():
    """Fetches the list of active Thailand VPN servers from VPNGate."""
    print("🌐 Fetching VPN server list from VPNGate...")
    try:
        req = urllib.request.Request(VPNGATE_API, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            content = r.read().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"❌ Failed to fetch VPNGate list: {e}")
        return []

    lines = content.split('\n')
    data_lines = []
    for line in lines:
        if line.startswith('*') or line.startswith('#'):
            continue
        if line.strip():
            data_lines.append(line)

    reader = csv.reader(data_lines)
    servers = []
    for row in reader:
        if len(row) >= 15:
            country_long = row[5].strip()
            country_short = row[6].strip()
            if country_long.lower() == "thailand" or country_short.lower() == "th":
                try:
                    score = int(row[2])
                    speed = int(row[4])
                    ping = int(row[3])
                except ValueError:
                    score = speed = ping = 0
                servers.append({
                    'ip': row[1],
                    'score': score,
                    'ping': ping,
                    'speed': speed,
                    'config_base64': row[14]
                })
    # Sort by score descending (best first)
    servers.sort(key=lambda s: s['score'], reverse=True)
    return servers

def connect_vpn(server):
    print(f"\n⚡ Trying to connect to Thailand VPN server: {server['ip']} (Ping: {server['ping']}ms, Speed: {server['speed']/10**6:.2f} Mbps)...")
    
    # Write OpenVPN config file
    try:
        config_bytes = base64.b64decode(server['config_base64'])
        config_text = config_bytes.decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"❌ Failed to decode config: {e}")
        return False

    # Force configurations for non-interactive runners
    # Add auth-nocache, route-delay to prevent credential prompts or route issues
    extra_configs = "\nauth-nocache\nroute-delay 3\n"
    full_config = config_text + extra_configs

    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        f.write(full_config)

    # Terminate any existing openvpn process
    subprocess.run(["sudo", "killall", "openvpn"], capture_output=True)
    time.sleep(2)

    # Start openvpn daemon
    try:
        # In GitHub Actions (Ubuntu), openvpn is run via sudo
        cmd = ["sudo", "openvpn", "--config", CONFIG_FILE, "--daemon"]
        print(f"Executing: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
    except Exception as e:
        print(f"❌ Failed to start openvpn process: {e}")
        return False

    # Wait and poll IP address to check if we are on Thailand IP
    print("⏳ Waiting for VPN connection to establish (up to 20 seconds)...")
    for i in range(1, 11):
        time.sleep(2)
        ip, country = check_ip()
        print(f"  [Attempt {i}/10] Current Public IP: {ip} | Country: {country}")
        if country == "TH":
            print(f"🎉 SUCCESS! Connected to Thailand VPN tunnel via {server['ip']}.")
            return True
            
    # If connection failed, kill the openvpn process
    print("❌ Connection timeout or IP did not switch to TH. Terminating this VPN connection.")
    subprocess.run(["sudo", "killall", "openvpn"], capture_output=True)
    if os.path.exists(CONFIG_FILE):
        try: os.remove(CONFIG_FILE)
        except Exception: pass
    return False

def main():
    initial_ip, initial_country = check_ip()
    print(f"Initial Public IP: {initial_ip} | Country: {initial_country}")
    if initial_country == "TH":
        print("✅ Runner is already on Thailand IP. Skipping VPN setup.")
        sys.exit(0)

    servers = get_thai_vpn_servers()
    print(f"Found {len(servers)} active Thailand VPN servers.")
    if not servers:
        print("❌ No Thailand VPN servers available at the moment.")
        sys.exit(1)

    # Try up to 5 servers
    max_attempts = min(5, len(servers))
    for i in range(max_attempts):
        success = connect_vpn(servers[i])
        if success:
            sys.exit(0)
            
    print("\n❌ Failed to establish a working Thailand VPN connection with all attempts.")
    sys.exit(1)

if __name__ == "__main__":
    main()
