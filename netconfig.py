# Network interface configurator
"""
			NETWORK CONFIG TOOL
			===================
This utility manages network interface configurations, allowing users to
seamlessly toggle between DHCP and Static IP modes. It maintains a local 
database of manual configurations for quick switching.

FEATURES:
	- Cross-platform support (Windows netsh / Linux nmcli).
	- Persistent storage for Static IP profiles (networks.json).
	- Quick-restart functionality for network adapters.
	- Real-time network configuration inspection (Verbose).
	- Automatic admin/root privilege elevation.

USAGE:
	python netconfig.py

INTERMEDIATE OPTIONS:
	- Switch Mode: Toggle between dynamic and manual addressing.
	- Restart: Cycles the adapter (Disable -> Enable).
	- Show Info: Displays Verbose IP, MAC, MTU, and Power info.
"""

import os
import sys
import json
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

def elevate_privileges():
	"""Attempts to relaunch the script with administrative privileges."""
	system = get_platform()
	
	# Check if already admin
	if system == "windows":
		import ctypes
		is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
	else:
		is_admin = os.getuid() == 0

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
		else:
			# Re-run with sudo on Linux
			args = ['sudo', sys.executable] + sys.argv
			os.execvp('sudo', args)
			
		sys.exit(0) # Exit the non-privileged instance
	except Exception as e:
		print(f"{CLR_RED}Elevation failed: {e}{CLR_RESET}")
		return False

def load_configs():
	if os.path.exists(CONFIG_FILE):
		try:
			with open(CONFIG_FILE, 'r') as f:
				return json.load(f)
		except:
			return {}
	return {}

def save_configs(configs):
	with open(CONFIG_FILE, 'w') as f:
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
	else:
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

	else:
		# Linux implementation
		# 1. IP and MAC
		print(f"\n{CLR_CYAN}[ IP & Hardware Details ]{CLR_RESET}")
		addr_out, _ = run_cmd(f"ip addr show {iface}")
		if addr_out: print(addr_out)
		
		# 2. Link Speed and Duplex (if supported)
		print(f"\n{CLR_CYAN}[ Link Status ]{CLR_RESET}")
		eth_out, _ = run_cmd(f"ethtool {iface} 2>/dev/null | grep -E 'Speed|Duplex|Link detected'")
		if eth_out: print(eth_out)
		
		# 3. Power Saving (primarily for WiFi)
		print(f"\n{CLR_CYAN}[ Power Management ]{CLR_RESET}")
		iw_out, _ = run_cmd(f"iw dev {iface} get power_save 2>/dev/null")
		if iw_out: print(iw_out)
		else: print("Power management info unavailable (or not a wireless device).")
	
	input(f"\n{CLR_ORANGE}Press Enter to return...{CLR_RESET}")

def restart_adapter(iface):
	"""Disables and re-enables the network adapter."""
	system = get_platform()
	print(f"{CLR_ORANGE}Restarting {iface}...{CLR_RESET}")
	if system == "windows":
		run_cmd(f'netsh interface set interface name="{iface}" admin=disabled')
		time.sleep(2)
		run_cmd(f'netsh interface set interface name="{iface}" admin=enabled')
	else:
		run_cmd(f"nmcli device disconnect {iface}")
		time.sleep(2)
		run_cmd(f"nmcli device connect {iface}")
	print(f"{CLR_GREEN}Restart command issued.{CLR_RESET}")
	time.sleep(1)

def get_manual_input(iface, current_configs):
	print(f"\n{CLR_PURPLE}Setting up static IP for: {CLR_BOLD}{iface}{CLR_RESET}")
	prev = current_configs.get(iface, {})
	
	ip = input(f"{CLR_CYAN}IP Address{CLR_RESET} [{prev.get('ip', '')}]: ") or prev.get('ip')
	mask = input(f"{CLR_CYAN}Subnet Mask/Prefix{CLR_RESET} [{prev.get('mask', '255.255.255.0')}]: ") or prev.get('mask', '255.255.255.0')
	gw = input(f"{CLR_CYAN}Gateway{CLR_RESET} [{prev.get('gw', '')}]: ") or prev.get('gw')
	
	dns_choice = input(f"{CLR_ORANGE}Set custom DNS? (y/n): {CLR_RESET}").lower()
	dns = []
	if dns_choice == 'y':
		dns_input = input(f"{CLR_CYAN}Enter DNS servers (comma separated): {CLR_RESET}")
		dns = [d.strip() for d in dns_input.split(',')]
	else:
		dns = prev.get('dns', [])
		
	config = {"ip": ip, "mask": mask, "gw": gw, "dns": dns}
	return config

def apply_config(iface, mode, config=None, keep_dns=False):
	system = get_platform()
	print(f"{CLR_ORANGE}Applying configuration...{CLR_RESET}")
	
	if mode == "dhcp":
		if system == "windows":
			run_cmd(f'netsh interface ipv4 set address name="{iface}" source=dhcp')
			if not keep_dns:
				run_cmd(f'netsh interface ipv4 set dnsservers name="{iface}" source=dhcp')
		else:
			if keep_dns:
				run_cmd(f"nmcli device modify {iface} ipv4.method auto ipv4.ignore-auto-dns yes")
			else:
				run_cmd(f"nmcli device modify {iface} ipv4.method auto ipv4.ignore-auto-dns no")
			run_cmd(f"nmcli device reapply {iface}")
		
		dns_status = "kept" if keep_dns else "reset to automatic"
		print(f"{CLR_GREEN}Interface {iface} set to DHCP (DNS {dns_status}).{CLR_RESET}")
		
	elif mode == "static" and config:
		if system == "windows":
			# Set IP Configuration
			run_cmd(f'netsh interface ipv4 set address name="{iface}" static {config["ip"]} {config["mask"]} {config["gw"]}')
			# Set DNS Configuration
			if config["dns"]:
				for i, dns_ip in enumerate(config["dns"]):
					if i == 0:
						# Primary DNS
						cmd = f'netsh interface ipv4 set dnsservers name="{iface}" static address={dns_ip} validate=no'
					else:
						# Secondary DNS
						cmd = f'netsh interface ipv4 add dnsservers name="{iface}" address={dns_ip} index={i+1} validate=no'
					run_cmd(cmd)
			else:
				# If no DNS provided in static config, fall back to DHCP for DNS only
				run_cmd(f'netsh interface ipv4 set dnsservers name="{iface}" source=dhcp')
		else:
			prefix = config["mask"]
			run_cmd(f"nmcli device modify {iface} ipv4.addresses {config['ip']}/{prefix} ipv4.gateway {config['gw']} ipv4.method manual")
			if config["dns"]:
				dns_str = ' '.join(config["dns"])
				run_cmd(f"nmcli device modify {iface} ipv4.dns '{dns_str}'")
			run_cmd(f"nmcli device reapply {iface}")
		print(f"{CLR_GREEN}Interface {iface} set to Static IP: {config['ip']}{CLR_RESET}")
	
	time.sleep(1)

def interface_menu(selected_iface):
	"""Intermediate menu for a specific interface."""
	while True:
		configs = load_configs()
		print(f"\n{CLR_PURPLE}{CLR_BOLD}--- Managing: {selected_iface} ---{CLR_RESET}")
		print(f"{CLR_CYAN}1.{CLR_RESET} Switch Network Mode (DHCP/Static)")
		print(f"{CLR_CYAN}2.{CLR_RESET} Restart Network Adapter")
		print(f"{CLR_CYAN}3.{CLR_RESET} Show Network Info")
		print(f"{CLR_RED}4.{CLR_RESET} Exit (Back to Interface Selection)")
		
		choice = input(f"\n{CLR_BOLD}Select option: {CLR_RESET}")
		
		if choice == "1":
			print(f"\n{CLR_CYAN}1.{CLR_RESET} Switch to {CLR_GREEN}DHCP{CLR_RESET}")
			print(f"{CLR_CYAN}2.{CLR_RESET} Switch to {CLR_ORANGE}Static IP{CLR_RESET}")
			mode_choice = input(f"{CLR_BOLD}Select mode: {CLR_RESET}")
			
			if mode_choice == "1":
				keep = input(f"{CLR_ORANGE}Keep current manual DNS settings? (y/n): {CLR_RESET}").lower() == 'y'
				apply_config(selected_iface, "dhcp", keep_dns=keep)
			elif mode_choice == "2":
				if selected_iface not in configs or input(f"{CLR_ORANGE}Edit saved config? (y/n): {CLR_RESET}").lower() == 'y':
					configs[selected_iface] = get_manual_input(selected_iface, configs)
					save_configs(configs)
				apply_config(selected_iface, "static", configs[selected_iface])
			else:
				print(f"{CLR_RED}Invalid mode.{CLR_RESET}")
				
		elif choice == "2":
			restart_adapter(selected_iface)
		elif choice == "3":
			show_network_info(selected_iface)
		elif choice == "4":
			break
		else:
			print(f"{CLR_RED}Invalid choice.{CLR_RESET}")

def main():
	init_ansi()
	
	if not (sys.platform.startswith('win') or sys.platform.startswith('linux')):
		print(f"{CLR_RED}Unsupported OS.{CLR_RESET}")
		return

	if not elevate_privileges():
		print(f"{CLR_RED}{CLR_BOLD}Error: This script requires administrative/root privileges to run.{CLR_RESET}")
		return

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
			choice_str = input(f"\n{CLR_BOLD}Select interface (number): {CLR_RESET}")
			if not choice_str.strip(): continue
			
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

if __name__ == "__main__":
	main()