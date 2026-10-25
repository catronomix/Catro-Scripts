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

# Configuration file for storing manual profiles
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "networks.json")

# ANSI Color Constants
CLR_PURPLE = '\033[38;2;170;0;255m'
CLR_CYAN   = '\033[0;36m'
CLR_GREEN  = '\033[0;32m'
CLR_ORANGE = '\033[93m'
CLR_RED    = '\033[0;31m'
CLR_RESET  = '\033[0m'
CLR_BOLD   = '\033[1m'

def init_ansi():
	"""Enables ANSI escape sequences on Windows."""
	if platform.system().lower() == "windows":
		os.system('color')

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

def require_tool(name):
	"""Checks that an external tool exists; prints a red error and returns False if not."""
	if shutil.which(name) is None:
		print(f"{CLR_RED}Error: required tool '{name}' is not installed or not on PATH.{CLR_RESET}", file=sys.stderr)
		return False
	return True

def run_step(cmd):
	"""Runs one command for a write operation; returns False and reports the failure."""
	_, err = run_cmd(cmd)
	if err:
		print(f"{CLR_RED}Error: command failed: {cmd}{CLR_RESET}", file=sys.stderr)
		for line in err.splitlines():
			print(f"{CLR_RED}  {line}{CLR_RESET}", file=sys.stderr)
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

def elevate_privileges():
	"""Attempts to relaunch the script with administrative privileges."""
	system = get_platform()
	
	# Check if already admin
	if system == "windows":
		import ctypes
		is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
	elif system == "linux":
		is_admin = os.getuid() == 0
	else:
		print(f"{CLR_RED}Error: elevation is not supported on {system}.{CLR_RESET}", file=sys.stderr)
		return False

	if is_admin:
		return True

	print(f"{CLR_ORANGE}Requesting administrative privileges...{CLR_RESET}")
	
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
			print(f"{CLR_RED}Error: elevation is not supported on {system}.{CLR_RESET}", file=sys.stderr)
			return False
			
		sys.exit(0) # Exit the non-privileged instance
	except Exception as e:
		print(f"{CLR_RED}Elevation failed: {e}{CLR_RESET}")
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

def get_interfaces():
	"""Lists available network interfaces."""
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
		if not require_tool("ip"):
			return []
		out, _ = run_cmd("ip -o link show | awk -F': ' '{print $2}'")
		if out:
			interfaces = [iface for iface in out.splitlines() if iface != "lo"]
			
	return sorted(list(set(interfaces)))

def show_network_info(iface):
	"""Displays detailed configuration including MAC, Power, and MTU."""
	system = get_platform()
	print(f"\n{CLR_PURPLE}{CLR_BOLD}--- Verbose Info: {iface} ---{CLR_RESET}")
	
	if system == "windows":
		# 1. IP Configuration
		print(f"\n{CLR_CYAN}[ IP Configuration ]{CLR_RESET}")
		ip_out, _ = run_cmd(f'netsh interface ipv4 show config name="{iface}"')
		if ip_out:
			print(ip_out.replace("IP Address:", f"{CLR_GREEN}IP Address:{CLR_RESET}"))
		
		# 2. Hardware and Performance via PowerShell
		print(f"\n{CLR_CYAN}[ Hardware Details ]{CLR_RESET}")
		ps_cmd = (
			f"Get-NetAdapter -Name '{iface}' | "
			"Select-Object -Property MACAddress, Status, LinkSpeed, MTU, MediaType, PhysicalMediaType | "
			"Format-List"
		)
		hw_out, _ = run_cmd(f'powershell -Command "{ps_cmd}"')
		if hw_out: print(hw_out)
		
		# 3. Power Management
		print(f"{CLR_CYAN}[ Power Management ]{CLR_RESET}")
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
		if not require_tool("ip"):
			input(f"\n{CLR_ORANGE}Press Enter to return...{CLR_RESET}")
			return
		print(f"\n{CLR_CYAN}[ IP & Hardware Details ]{CLR_RESET}")
		addr_out, _ = run_cmd(f"ip addr show {iface}")
		if addr_out: print(addr_out)
		
		# 2. Link Speed and Duplex (only when ethtool is installed)
		print(f"\n{CLR_CYAN}[ Link Status ]{CLR_RESET}")
		if shutil.which("ethtool"):
			eth_out, _ = run_cmd(f"ethtool {iface} 2>/dev/null | grep -E 'Speed|Duplex|Link detected'")
			if eth_out: print(eth_out)
		else:
			print("ethtool is not installed; link status unavailable.")
		
		# 3. Power Saving (primarily for WiFi, only when iw is installed)
		print(f"\n{CLR_CYAN}[ Power Management ]{CLR_RESET}")
		if shutil.which("iw"):
			iw_out, _ = run_cmd(f"iw dev {iface} get power_save 2>/dev/null")
			if iw_out: print(iw_out)
			else: print("Power management info unavailable (or not a wireless device).")
		else:
			print("iw is not installed; wireless power info unavailable.")
	
	input(f"\n{CLR_ORANGE}Press Enter to return...{CLR_RESET}")

def restart_adapter(iface):
	"""Disables and re-enables the network adapter. Returns True on success."""
	system = get_platform()
	print(f"{CLR_ORANGE}Restarting {iface}...{CLR_RESET}")
	if system == "windows":
		ok = run_step(f'netsh interface set interface name="{iface}" admin=disabled')
		time.sleep(2)
		ok = run_step(f'netsh interface set interface name="{iface}" admin=enabled') and ok
	elif system == "linux":
		if not require_tool("nmcli"):
			return False
		ok = run_step(f"nmcli device disconnect {iface}")
		time.sleep(2)
		ok = run_step(f"nmcli device connect {iface}") and ok
	else:
		print(f"{CLR_RED}Error: adapter restart is not supported on {system}.{CLR_RESET}", file=sys.stderr)
		return False
	if not ok:
		return False
	print(f"{CLR_GREEN}Restart command issued.{CLR_RESET}")
	time.sleep(1)
	return True

def get_manual_input(iface, current_configs):
	print(f"\n{CLR_PURPLE}Setting up static IP for: {CLR_BOLD}{iface}{CLR_RESET}")
	prev = current_configs.get(iface, {})
	
	ip = input(f"{CLR_CYAN}IP Address{CLR_RESET} [{prev.get('ip', '')}]: ") or prev.get('ip')
	mask = input(f"{CLR_CYAN}Subnet Mask/Prefix{CLR_RESET} [{prev.get('mask', '255.255.255.0')}]: ") or prev.get('mask', '255.255.255.0')
	gw = input(f"{CLR_CYAN}Gateway{CLR_RESET} [{prev.get('gw', '')}]: ") or prev.get('gw')
	
	# DNS logic removed from IP setup and moved to dedicated menu
	config = {"ip": ip, "mask": mask, "gw": gw, "dns": prev.get('dns', [])}
	return config

def apply_dns(iface, mode, dns_list=None):
	"""Applies DNS configuration separately. Returns True on success."""
	system = get_platform()
	print(f"{CLR_ORANGE}Updating DNS settings...{CLR_RESET}")
	
	if mode == "auto":
		if system == "windows":
			ok = run_step(f'netsh interface ipv4 set dnsservers name="{iface}" source=dhcp')
		elif system == "linux":
			if not require_tool("nmcli"):
				return False
			ok = run_step(f"nmcli device modify {iface} ipv4.ignore-auto-dns no")
			ok = run_step(f"nmcli device reapply {iface}") and ok
		else:
			print(f"{CLR_RED}Error: DNS changes are not supported on {system}.{CLR_RESET}", file=sys.stderr)
			return False
		if not ok:
			return False
		print(f"{CLR_GREEN}DNS set to Automatic (DHCP).{CLR_RESET}")
	
	elif mode == "manual" and dns_list:
		if system == "windows":
			ok = True
			for i, dns_ip in enumerate(dns_list):
				if i == 0:
					cmd = f'netsh interface ipv4 set dnsservers name="{iface}" static address={dns_ip} validate=no'
				else:
					cmd = f'netsh interface ipv4 add dnsservers name="{iface}" address={dns_ip} index={i+1} validate=no'
				ok = run_step(cmd) and ok
		elif system == "linux":
			if not require_tool("nmcli"):
				return False
			# nmcli wants one comma-separated list, not space-separated addresses.
			dns_str = ','.join(dns_list)
			ok = run_step(f"nmcli device modify {iface} ipv4.dns '{dns_str}' ipv4.ignore-auto-dns yes")
			ok = run_step(f"nmcli device reapply {iface}") and ok
		else:
			print(f"{CLR_RED}Error: DNS changes are not supported on {system}.{CLR_RESET}", file=sys.stderr)
			return False
		if not ok:
			return False
		print(f"{CLR_GREEN}DNS set to Manual: {', '.join(dns_list)}{CLR_RESET}")
	else:
		print(f"{CLR_RED}Error: no DNS servers supplied for manual mode.{CLR_RESET}", file=sys.stderr)
		return False
	
	time.sleep(1)
	return True

def apply_config(iface, mode, config=None):
	"""Applies IP addressing configuration. Returns True on success."""
	system = get_platform()
	print(f"{CLR_ORANGE}Applying IP configuration...{CLR_RESET}")
	
	if mode == "dhcp":
		if system == "windows":
			ok = run_step(f'netsh interface ipv4 set address name="{iface}" source=dhcp')
		elif system == "linux":
			if not require_tool("nmcli"):
				return False
			ok = run_step(f"nmcli device modify {iface} ipv4.method auto")
			ok = run_step(f"nmcli device reapply {iface}") and ok
		else:
			print(f"{CLR_RED}Error: IP configuration is not supported on {system}.{CLR_RESET}", file=sys.stderr)
			return False
		if not ok:
			return False
		print(f"{CLR_GREEN}Interface {iface} set to DHCP.{CLR_RESET}")
		
	elif mode == "static" and config:
		if system == "windows":
			ok = run_step(f'netsh interface ipv4 set address name="{iface}" static {config["ip"]} {config["mask"]} {config["gw"]}')
		elif system == "linux":
			if not require_tool("nmcli"):
				return False
			# nmcli takes a CIDR prefix, so dotted masks are converted first.
			prefix = mask_to_prefix(config["mask"])
			if prefix is None:
				print(f"{CLR_RED}Error: '{config['mask']}' is not a valid subnet mask or prefix length.{CLR_RESET}", file=sys.stderr)
				return False
			ok = run_step(f"nmcli device modify {iface} ipv4.addresses {config['ip']}/{prefix} ipv4.gateway {config['gw']} ipv4.method manual")
			ok = run_step(f"nmcli device reapply {iface}") and ok
		else:
			print(f"{CLR_RED}Error: IP configuration is not supported on {system}.{CLR_RESET}", file=sys.stderr)
			return False
		if not ok:
			return False
		print(f"{CLR_GREEN}Interface {iface} set to Static IP: {config['ip']}{CLR_RESET}")
	else:
		print(f"{CLR_RED}Error: no static configuration supplied.{CLR_RESET}", file=sys.stderr)
		return False
	
	time.sleep(1)
	return True

def interface_menu(selected_iface):
	"""Intermediate menu for a specific interface."""
	while True:
		configs = load_configs()
		print(f"\n{CLR_PURPLE}{CLR_BOLD}--- Managing: {selected_iface} ---{CLR_RESET}")
		print(f"{CLR_CYAN}1.{CLR_RESET} Switch IP Mode (DHCP/Static)")
		print(f"{CLR_CYAN}2.{CLR_RESET} Set DNS (Auto/Manual)")
		print(f"{CLR_CYAN}3.{CLR_RESET} Restart Network Adapter")
		print(f"{CLR_CYAN}4.{CLR_RESET} Show Network Info")
		print(f"{CLR_RED}5.{CLR_RESET} Exit (Back to Interface Selection)")
		
		choice = input(f"\n{CLR_BOLD}Select option (or Enter to go back): {CLR_RESET}")
		if not choice.strip():
			break
		
		if choice == "1":
			print(f"\n{CLR_CYAN}1.{CLR_RESET} Switch to {CLR_GREEN}DHCP{CLR_RESET}")
			print(f"{CLR_CYAN}2.{CLR_RESET} Switch to {CLR_ORANGE}Static IP{CLR_RESET}")
			mode_choice = input(f"{CLR_BOLD}Select mode: {CLR_RESET}")
			
			if mode_choice == "1":
				apply_config(selected_iface, "dhcp")
			elif mode_choice == "2":
				if selected_iface not in configs or input(f"{CLR_ORANGE}Edit saved config? (y/n): {CLR_RESET}").lower() == 'y':
					configs[selected_iface] = get_manual_input(selected_iface, configs)
					save_configs(configs)
				apply_config(selected_iface, "static", configs[selected_iface])
			else:
				print(f"{CLR_RED}Invalid mode.{CLR_RESET}")

		elif choice == "2":
			print(f"\n{CLR_CYAN}1.{CLR_RESET} Set DNS to {CLR_GREEN}Auto (DHCP){CLR_RESET}")
			print(f"{CLR_CYAN}2.{CLR_RESET} Set DNS to {CLR_ORANGE}Manual{CLR_RESET}")
			dns_choice = input(f"{CLR_BOLD}Select DNS mode: {CLR_RESET}")
			
			if dns_choice == "1":
				apply_dns(selected_iface, "auto")
			elif dns_choice == "2":
				prev_dns = configs.get(selected_iface, {}).get('dns', [])
				dns_input = input(f"{CLR_CYAN}Enter DNS servers (comma separated) {CLR_RESET}[{', '.join(prev_dns)}]: ")
				if dns_input:
					dns_list = [d.strip() for d in dns_input.split(',')]
					if selected_iface not in configs: configs[selected_iface] = {}
					configs[selected_iface]['dns'] = dns_list
					save_configs(configs)
				else:
					dns_list = prev_dns
				
				if dns_list:
					apply_dns(selected_iface, "manual", dns_list)
				else:
					print(f"{CLR_RED}No DNS servers provided.{CLR_RESET}")
			else:
				print(f"{CLR_RED}Invalid choice.{CLR_RESET}")
				
		elif choice == "3":
			restart_adapter(selected_iface)
		elif choice == "4":
			show_network_info(selected_iface)
		elif choice == "5":
			break
		else:
			print(f"{CLR_RED}Invalid choice.{CLR_RESET}")

def main():
	init_ansi()
	
	system = get_platform()
	if system not in ("windows", "linux"):
		print(f"{CLR_RED}Error: netconfig is not supported on {system or 'this platform'}. Supported platforms: Windows (netsh) and Linux (nmcli).{CLR_RESET}", file=sys.stderr)
		return 1

	if not elevate_privileges():
		print(f"{CLR_RED}{CLR_BOLD}Error: This script requires administrative/root privileges to run.{CLR_RESET}")
		return 1

	while True:
		interfaces = get_interfaces()
		if not interfaces:
			print(f"{CLR_RED}No network interfaces found.{CLR_RESET}")
			input("Press Enter to refresh or Ctrl+C to quit...")
			continue

		print(f"\n{CLR_PURPLE}{CLR_BOLD}=== Available Interfaces ==={CLR_RESET}")
		for i, iface in enumerate(interfaces):
			print(f"{CLR_CYAN}{i + 1}.{CLR_RESET} {iface}")
		print(f"{CLR_RED}{len(interfaces) + 1}. Quit{CLR_RESET}")

		try:
			choice_str = input(f"\n{CLR_BOLD}Select interface (or Enter to quit): {CLR_RESET}")
			if not choice_str.strip():
				break
			
			choice = int(choice_str) - 1
			if choice == len(interfaces):
				break
			if 0 <= choice < len(interfaces):
				interface_menu(interfaces[choice])
			else:
				print(f"{CLR_RED}Invalid number.{CLR_RESET}")
		except ValueError:
			print(f"{CLR_RED}Please enter a valid number.{CLR_RESET}")
		except KeyboardInterrupt:
			break
	return 0

if __name__ == "__main__":
	sys.exit(main())