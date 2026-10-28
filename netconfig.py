# Network interface configurator
"""
			NETWORK CONFIG TOOL
			===================
This utility manages network interface configurations, allowing users to
seamlessly toggle between DHCP and Static IP modes. It maintains a local 
database of manual configurations for quick switching.

FEATURES:
	- Supported platforms: Windows (netsh) and Linux with NetworkManager
	  (nmcli). There is no macOS backend: any other OS exits non-zero.
	- A missing platform tool (nmcli, ip, ethtool, iw) is reported as an error;
	  it is never reported as a successful change.
	- Persistent storage for Static IP profiles (networks.json).
	- Quick-restart functionality for network adapters.
	- Real-time network configuration inspection (Verbose).
	- Automatic admin/root privilege elevation.

USAGE:
	python netconfig.py

RENDERING:
	- Each page is one `tui.panel` holding the title, subtitle and menu rows,
	  and the menus and prompts come from `tui.chrome`/`tui.prompts`, so the
	  theme, colour level and ASCII fallback are the library's, not this
	  script's. Answers are still plain numbers.

INTERMEDIATE OPTIONS:
	- Switch Mode: Toggle between dynamic and manual addressing.
	- Set DNS: Configure DNS servers (Auto/Manual).
	- Restart: Cycles the adapter (Disable -> Enable).
	- Show Info: Displays Verbose IP, MAC, MTU, and Power info.
"""

import os
import sys
import json
import shutil
import subprocess
import platform
import time

import tui

# Configuration file for storing manual profiles
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "networks.json")

# Masthead of the tool: the shared page width, so every page lines up.
PAGE_WIDTH = 64


def menu(items, cap=None, width=PAGE_WIDTH):
	"""Numbered menu rows from the shared chrome.

	`selected=None`: these menus are answered by number, so nothing is
	highlighted until the operator picks a row. A caller that does select a row
	gets the accent-on-surface bar from `chrome.menu`.
	"""
	return tui.chrome.menu(items, selected=None, width=width, cap=cap)


def page(title, subtitle, items, cap=None):
	"""One tool page: the title, subtitle and menu rows inside the page frame.

	The frame spans PAGE_WIDTH; the menu is narrowed by the frame's two edge
	cells and its two gutters, so its bars land inside the box instead of being
	truncated by it. Piped, `panel` drops the frame and the page is the old
	title/subtitle/menu lines, one per row.
	"""
	if cap is None:
		cap = tui.detect()
	body = []
	if subtitle:
		body.append(tui.style(subtitle, fg="fg-muted", cap=cap))
	body.extend(menu(items, cap=cap, width=PAGE_WIDTH - 4).splitlines())
	return tui.panel(title, body, width=PAGE_WIDTH, cap=cap)


def get_platform():
	return platform.system().lower()

def run_cmd(cmd):
	"""Executes a shell command and returns output/error."""
	try:
		result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
		return result.stdout.strip(), None
	except subprocess.CalledProcessError as e:
		return None, e.stderr.strip()
	except OSError as e:
		# A tool or shell that cannot even be launched is a failure, not success.
		return None, str(e)

def require_tool(name, cap=None):
	"""Checks that an external tool exists; prints an error and returns False if not."""
	if cap is None:
		cap = tui.detect()
	if shutil.which(name) is None:
		print(tui.style(f"Error: required tool '{name}' is not installed or not on PATH.",
						fg="fg-error", cap=cap), file=sys.stderr)
		return False
	return True

def run_step(cmd, cap=None):
	"""Runs one command for a write operation; returns False and reports the failure."""
	if cap is None:
		cap = tui.detect()
	_, err = run_cmd(cmd)
	if err:
		print(tui.style(f"Error: command failed: {cmd}", fg="fg-error", cap=cap),
			  file=sys.stderr)
		for line in err.splitlines():
			print(tui.style(f"  {line}", fg="fg-error", cap=cap), file=sys.stderr)
		return False
	return True

def mask_to_prefix(mask):
	"""Converts a dotted netmask (255.255.255.0) or a prefix length (24) to an int.

	Returns None when the value is not a valid contiguous IPv4 netmask.
	"""
	text_mask = str(mask).strip()
	if text_mask.isdigit():
		value = int(text_mask)
		return value if 0 <= value <= 32 else None
	parts = text_mask.split(".")
	if len(parts) != 4 or not all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
		return None
	bits = "".join(format(int(part), "08b") for part in parts)
	if "01" in bits:  # a gap between ones is not a netmask
		return None
	return bits.count("1")

def elevate_privileges(cap=None):
	"""Attempts to relaunch the script with administrative privileges."""
	if cap is None:
		cap = tui.detect()
	system = get_platform()
	
	# Check if already admin
	if system == "windows":
		import ctypes
		is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
	elif system == "linux":
		is_admin = os.getuid() == 0
	else:
		print(tui.style(f"Error: elevation is not supported on {system}.", fg="fg-error",
						cap=cap), file=sys.stderr)
		return False

	if is_admin:
		return True

	print(tui.style("Requesting administrative privileges...", fg="fg-warn", cap=cap))
	
	try:
		if system == "windows":
			import ctypes
			# Re-run the script with admin rights
			ctypes.windll.shell32.ShellExecuteW(
				None, "runas", sys.executable, " ".join(sys.argv), None, 1
			)
		elif system == "linux":
			# Re-run with sudo on Linux
			args = ['sudo', sys.executable] + sys.argv
			os.execvp('sudo', args)
		else:
			print(tui.style(f"Error: elevation is not supported on {system}.", fg="fg-error",
							cap=cap), file=sys.stderr)
			return False
			
		sys.exit(0) # Exit the non-privileged instance
	except Exception as e:
		print(tui.style(f"Elevation failed: {e}", fg="fg-error", cap=cap))
		return False

def load_configs():
	if os.path.exists(CONFIG_FILE):
		try:
			with open(CONFIG_FILE, 'r', encoding="utf-8") as f:
				return json.load(f)
		except:
			return {}
	return {}

def save_configs(configs):
	with open(CONFIG_FILE, 'w', encoding="utf-8") as f:
		json.dump(configs, f, indent=4)

def get_interfaces(cap=None):
	"""Lists available network interfaces."""
	if cap is None:
		cap = tui.detect()
	interfaces = []
	system = get_platform()
	
	if system == "windows":
		out, _ = run_cmd("netsh interface ipv4 show interfaces")
		if out:
			lines = out.splitlines()
			start_parsing = False
			for line in lines:
				if "---" in line:
					start_parsing = True
					continue
				if start_parsing and line.strip():
					parts = line.split()
					if len(parts) >= 5:
						name = " ".join(parts[4:])
						if "Loopback" not in name:
							interfaces.append(name)
	elif system == "linux":
		if not require_tool("ip", cap):
			return []
		out, _ = run_cmd("ip -o link show | awk -F': ' '{print $2}'")
		if out:
			interfaces = [iface for iface in out.splitlines() if iface != "lo"]
			
	return sorted(list(set(interfaces)))

def show_network_info(iface, cap=None):
	"""Displays detailed configuration including MAC, Power, and MTU."""
	if cap is None:
		cap = tui.detect()
	system = get_platform()
	print()
	print(tui.section(f"--- Verbose Info: {iface} ---", cap=cap))
	
	if system == "windows":
		# 1. IP Configuration
		print()
		print(tui.section("[ IP Configuration ]", cap=cap))
		ip_out, _ = run_cmd(f'netsh interface ipv4 show config name="{iface}"')
		if ip_out:
			print(ip_out.replace("IP Address:",
								 tui.style("IP Address:", fg="fg-success", cap=cap)))
		
		# 2. Hardware and Performance via PowerShell
		print()
		print(tui.section("[ Hardware Details ]", cap=cap))
		ps_cmd = (
			f"Get-NetAdapter -Name '{iface}' | "
			"Select-Object -Property MACAddress, Status, LinkSpeed, MTU, MediaType, PhysicalMediaType | "
			"Format-List"
		)
		hw_out, _ = run_cmd(f'powershell -Command "{ps_cmd}"')
		if hw_out: print(hw_out)
		
		# 3. Power Management
		print(tui.section("[ Power Management ]", cap=cap))
		pwr_cmd = (
			f"Get-NetAdapterPowerManagement -Name '{iface}' | "
			"Select-Object -Property AllowComputerToTurnOffDevice, WakeOnMagicPacket, WakeOnPattern | "
			"Format-List"
		)
		pwr_out, _ = run_cmd(f'powershell -Command "{pwr_cmd}"')
		if pwr_out: print(pwr_out)
		else: print("Power management info unavailable for this adapter.")

	elif system == "linux":
		# Linux implementation: `ip` is required, ethtool/iw are optional.
		# 1. IP and MAC
		if not require_tool("ip", cap):
			tui.ask_text("\nPress Enter to return...")
			return
		print()
		print(tui.section("[ IP & Hardware Details ]", cap=cap))
		addr_out, _ = run_cmd(f"ip addr show {iface}")
		if addr_out: print(addr_out)
		
		# 2. Link Speed and Duplex (only when ethtool is installed)
		print()
		print(tui.section("[ Link Status ]", cap=cap))
		if shutil.which("ethtool"):
			eth_out, _ = run_cmd(f"ethtool {iface} 2>/dev/null | grep -E 'Speed|Duplex|Link detected'")
			if eth_out: print(eth_out)
		else:
			print("ethtool is not installed; link status unavailable.")
		
		# 3. Power Saving (primarily for WiFi, only when iw is installed)
		print()
		print(tui.section("[ Power Management ]", cap=cap))
		if shutil.which("iw"):
			iw_out, _ = run_cmd(f"iw dev {iface} get power_save 2>/dev/null")
			if iw_out: print(iw_out)
			else: print("Power management info unavailable (or not a wireless device).")
		else:
			print("iw is not installed; wireless power info unavailable.")
	
	tui.ask_text("\nPress Enter to return...")

def restart_adapter(iface, cap=None):
	"""Disables and re-enables the network adapter. Returns True on success."""
	if cap is None:
		cap = tui.detect()
	system = get_platform()
	print(tui.style(f"Restarting {iface}...", fg="fg-warn", cap=cap))
	if system == "windows":
		ok = run_step(f'netsh interface set interface name="{iface}" admin=disabled', cap)
		time.sleep(2)
		ok = run_step(f'netsh interface set interface name="{iface}" admin=enabled', cap) and ok
	elif system == "linux":
		if not require_tool("nmcli", cap):
			return False
		ok = run_step(f"nmcli device disconnect {iface}", cap)
		time.sleep(2)
		ok = run_step(f"nmcli device connect {iface}", cap) and ok
	else:
		print(tui.style(f"Error: adapter restart is not supported on {system}.",
						fg="fg-error", cap=cap), file=sys.stderr)
		return False
	if not ok:
		return False
	print(tui.style("Restart command issued.", fg="fg-success", cap=cap))
	time.sleep(1)
	return True

def get_manual_input(iface, current_configs, cap=None):
	if cap is None:
		cap = tui.detect()
	print()
	# The static-IP plan is one block: the interface line, boxed at the page
	# width, ahead of the three address prompts.
	print(tui.panel(None, [tui.style("Setting up static IP for: {}".format(
		tui.style(iface, fg="header-fg", bold=True, cap=cap)),
		fg="header-fg", bold=True, cap=cap)],
		width=PAGE_WIDTH, cap=cap))
	prev = current_configs.get(iface, {})
	
	ip = tui.ask_text("IP Address [{}]: ".format(prev.get('ip', '')), prev.get('ip'))
	mask = tui.ask_text("Subnet Mask/Prefix [{}]: ".format(prev.get('mask', '255.255.255.0')),
						prev.get('mask', '255.255.255.0'))
	gw = tui.ask_text("Gateway [{}]: ".format(prev.get('gw', '')), prev.get('gw'))
	
	# DNS logic removed from IP setup and moved to dedicated menu
	config = {"ip": ip, "mask": mask, "gw": gw, "dns": prev.get('dns', [])}
	return config

def apply_dns(iface, mode, dns_list=None, cap=None):
	"""Applies DNS configuration separately. Returns True on success."""
	if cap is None:
		cap = tui.detect()
	system = get_platform()
	print(tui.style("Updating DNS settings...", fg="fg-warn", cap=cap))
	
	if mode == "auto":
		if system == "windows":
			ok = run_step(f'netsh interface ipv4 set dnsservers name="{iface}" source=dhcp', cap)
		elif system == "linux":
			if not require_tool("nmcli", cap):
				return False
			ok = run_step(f"nmcli device modify {iface} ipv4.ignore-auto-dns no", cap)
			ok = run_step(f"nmcli device reapply {iface}", cap) and ok
		else:
			print(tui.style(f"Error: DNS changes are not supported on {system}.",
							fg="fg-error", cap=cap), file=sys.stderr)
			return False
		if not ok:
			return False
		print(tui.style("DNS set to Automatic (DHCP).", fg="fg-success", cap=cap))
	
	elif mode == "manual" and dns_list:
		if system == "windows":
			ok = True
			for i, dns_ip in enumerate(dns_list):
				if i == 0:
					cmd = f'netsh interface ipv4 set dnsservers name="{iface}" static address={dns_ip} validate=no'
				else:
					cmd = f'netsh interface ipv4 add dnsservers name="{iface}" address={dns_ip} index={i+1} validate=no'
				ok = run_step(cmd, cap) and ok
		elif system == "linux":
			if not require_tool("nmcli", cap):
				return False
			# nmcli wants one comma-separated list, not space-separated addresses.
			dns_str = ','.join(dns_list)
			ok = run_step(f"nmcli device modify {iface} ipv4.dns '{dns_str}' ipv4.ignore-auto-dns yes", cap)
			ok = run_step(f"nmcli device reapply {iface}", cap) and ok
		else:
			print(tui.style(f"Error: DNS changes are not supported on {system}.",
							fg="fg-error", cap=cap), file=sys.stderr)
			return False
		if not ok:
			return False
		print(tui.style(f"DNS set to Manual: {', '.join(dns_list)}", fg="fg-success", cap=cap))
	else:
		print(tui.style("Error: no DNS servers supplied for manual mode.",
						fg="fg-error", cap=cap), file=sys.stderr)
		return False
	
	time.sleep(1)
	return True

def apply_config(iface, mode, config=None, cap=None):
	"""Applies IP addressing configuration. Returns True on success."""
	if cap is None:
		cap = tui.detect()
	system = get_platform()
	print(tui.style("Applying IP configuration...", fg="fg-warn", cap=cap))
	
	if mode == "dhcp":
		if system == "windows":
			ok = run_step(f'netsh interface ipv4 set address name="{iface}" source=dhcp', cap)
		elif system == "linux":
			if not require_tool("nmcli", cap):
				return False
			ok = run_step(f"nmcli device modify {iface} ipv4.method auto", cap)
			ok = run_step(f"nmcli device reapply {iface}", cap) and ok
		else:
			print(tui.style(f"Error: IP configuration is not supported on {system}.",
							fg="fg-error", cap=cap), file=sys.stderr)
			return False
		if not ok:
			return False
		print(tui.style(f"Interface {iface} set to DHCP.", fg="fg-success", cap=cap))
		
	elif mode == "static" and config:
		if system == "windows":
			ok = run_step(f'netsh interface ipv4 set address name="{iface}" static {config["ip"]} {config["mask"]} {config["gw"]}', cap)
		elif system == "linux":
			if not require_tool("nmcli", cap):
				return False
			# nmcli takes a CIDR prefix, so dotted masks are converted first.
			prefix = mask_to_prefix(config["mask"])
			if prefix is None:
				print(tui.style(f"Error: '{config['mask']}' is not a valid subnet mask or prefix length.",
								fg="fg-error", cap=cap), file=sys.stderr)
				return False
			ok = run_step(f"nmcli device modify {iface} ipv4.addresses {config['ip']}/{prefix} ipv4.gateway {config['gw']} ipv4.method manual", cap)
			ok = run_step(f"nmcli device reapply {iface}", cap) and ok
		else:
			print(tui.style(f"Error: IP configuration is not supported on {system}.",
							fg="fg-error", cap=cap), file=sys.stderr)
			return False
		if not ok:
			return False
		print(tui.style(f"Interface {iface} set to Static IP: {config['ip']}",
						fg="fg-success", cap=cap))
	else:
		print(tui.style("Error: no static configuration supplied.", fg="fg-error", cap=cap),
			  file=sys.stderr)
		return False
	
	time.sleep(1)
	return True

def interface_menu(selected_iface, cap=None):
	"""Intermediate menu for a specific interface."""
	if cap is None:
		cap = tui.detect()
	while True:
		configs = load_configs()
		print()
		print(page(f"Managing: {selected_iface}", "Network adapter menu", [
			"Switch IP Mode (DHCP/Static)",
			"Set DNS (Auto/Manual)",
			"Restart Network Adapter",
			"Show Network Info",
			"Exit (Back to Interface Selection)",
		], cap=cap))

		choice = tui.ask_text("\nSelect option (or Enter to go back): ")
		if not choice:
			break
		
		if choice == "1":
			print()
			print(menu([
				"Switch to DHCP",
				"Switch to Static IP",
			], cap=cap))
			mode_choice = tui.ask_text("Select mode: ")
			
			if mode_choice == "1":
				apply_config(selected_iface, "dhcp", cap=cap)
			elif mode_choice == "2":
				if selected_iface not in configs or tui.ask_text("Edit saved config? (y/n): ").lower() == 'y':
					configs[selected_iface] = get_manual_input(selected_iface, configs, cap)
					save_configs(configs)
				apply_config(selected_iface, "static", configs[selected_iface], cap)
			else:
				print(tui.style("Invalid mode.", fg="fg-error", cap=cap))

		elif choice == "2":
			print()
			print(menu([
				"Set DNS to Auto (DHCP)",
				"Set DNS to Manual",
			], cap=cap))
			dns_choice = tui.ask_text("Select DNS mode: ")
			
			if dns_choice == "1":
				apply_dns(selected_iface, "auto", cap=cap)
			elif dns_choice == "2":
				prev_dns = configs.get(selected_iface, {}).get('dns', [])
				dns_input = tui.ask_text(
					"Enter DNS servers (comma separated) [{}]: ".format(', '.join(prev_dns)))
				if dns_input:
					dns_list = [d.strip() for d in dns_input.split(',')]
					if selected_iface not in configs: configs[selected_iface] = {}
					configs[selected_iface]['dns'] = dns_list
					save_configs(configs)
				else:
					dns_list = prev_dns
				
				if dns_list:
					apply_dns(selected_iface, "manual", dns_list, cap)
				else:
					print(tui.style("No DNS servers provided.", fg="fg-error", cap=cap))
			else:
				print(tui.style("Invalid choice.", fg="fg-error", cap=cap))
				
		elif choice == "3":
			restart_adapter(selected_iface, cap)
		elif choice == "4":
			show_network_info(selected_iface, cap)
		elif choice == "5":
			break
		else:
			print(tui.style("Invalid choice.", fg="fg-error", cap=cap))

def main():
	# Bootstrap the console, then resolve capabilities once for the whole run
	# and thread them through every menu, prompt and status line.
	tui.init_ansi()
	cap = tui.detect()
	
	system = get_platform()
	if system not in ("windows", "linux"):
		print(tui.style(f"Error: netconfig is not supported on {system or 'this platform'}. Supported platforms: Windows (netsh) and Linux (nmcli).",
						fg="fg-error", cap=cap), file=sys.stderr)
		return 1

	if not elevate_privileges(cap):
		print(tui.style("Error: This script requires administrative/root privileges to run.",
						fg="fg-error", bold=True, cap=cap))
		return 1

	while True:
		interfaces = get_interfaces(cap)
		if not interfaces:
			print(tui.style("No network interfaces found.", fg="fg-error", cap=cap))
			tui.ask_text("Press Enter to refresh or Ctrl+C to quit...")
			continue

		print()
		print(page("Available Interfaces", "Select adapter number",
				   list(interfaces) + ["Quit"], cap=cap))

		try:
			choice_str = tui.ask_text("\nSelect interface (or Enter to quit): ")
			if not choice_str.strip():
				break
			
			choice = int(choice_str) - 1
			if choice == len(interfaces):
				break
			if 0 <= choice < len(interfaces):
				interface_menu(interfaces[choice], cap)
			else:
				print(tui.style("Invalid number.", fg="fg-error", cap=cap))
		except ValueError:
			print(tui.style("Please enter a valid number.", fg="fg-error", cap=cap))
		except KeyboardInterrupt:
			break
	return 0

if __name__ == "__main__":
	sys.exit(main())
