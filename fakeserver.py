#!/usr/bin/env python3
"""
			FAKE SERVER SCREENSAVER
			=======================
Simulates a terminal screensaver with rapid "hacker" typing.
Generates infinite scrolling text in various styles.

Usage:
	python fakeserver.py [-s SPEED] [-t {python,cpp,plaintext}]

Options:
	-s, --speed   Speed in Words Per Minute (WPM). Default: 600
	-t, --type    Style of output (python, cpp, plaintext). Default: plaintext

Requirements:
	- pynput (pip install pynput)
"""

import sys
import time
import random
import argparse
import threading
import os

try:
	from pynput import keyboard
except ImportError:
	print("\033[0;31mError: 'pynput' library is not installed.\033[0m")
	print("Please install it using: pip install pynput")
	sys.exit(1)

# --- Vocabularies for different styles ---

PYTHON_VOCAB = [
	"def __init__(self, *args, **kwargs):",
	"    super().__init__()",
	"    self.connected = False",
	"async def stream_data(session, url):",
	"    async with session.get(url) as response:",
	"        data = await response.read()",
	"        return data.decode('utf-8')",
	"class SocketWrapper(object):",
	"    @classmethod",
	"    def bind(cls, host='0.0.0.0', port=8080):",
	"        pass",
	"import hashlib",
	"import asyncio",
	"from concurrent.futures import ThreadPoolExecutor",
	"m = hashlib.sha256()",
	"m.update(b'Nobody inspects the spammish repetition')",
	"digest = m.hexdigest()",
	"yield from _generate_hash_chain()",
	"if __name__ == '__main__':",
	"    sys.exit(main())",
	"        raise ConnectionError('Proxy timeout')",
	"    try:",
	"    except ValueError as e:",
	"        logger.error(f'Decryption failed: {e}')",
	"def parse_arguments(args=None):",
	"    for key, value in kwargs.items():",
	"        setattr(self, key, value)",
	"import socket",
	"import itertools",
	"from bs4 import BeautifulSoup",
	"def handle_client(client_socket):",
	"    request = client_socket.recv(1024)",
	"    if not request: break",
	"with open('config.json', 'r') as f:",
	"    config = json.load(f)",
	"    return [x for x in data if x.is_valid()]",
	"@dataclass",
	"class ProxyNode:",
	"    ip: str",
	"    port: int",
	"def encrypt_payload(data, key):",
	"    cipher = AES.new(key, AES.MODE_CBC, iv)",
	"    return base64.b64encode(cipher.encrypt(pad(data, AES.block_size)))",
	"if isinstance(obj, bytes): obj = obj.decode()"
]

CPP_VOCAB = [
	"#include <iostream>",
	"#include <vector>",
	"#include <memory>",
	"using namespace std;",
	"template <typename T>",
	"class ConnectionPool {",
	"public:",
	"    ConnectionPool(size_t pool_size);",
	"    ~ConnectionPool();",
	"    std::shared_ptr<Connection> acquire();",
	"private:",
	"    std::vector<std::unique_ptr<Connection>> m_pool;",
	"};",
	"int main(int argc, char** argv) {",
	"    void* ptr = malloc(sizeof(struct Packet));",
	"    if (!ptr) return -1;",
	"    *reinterpret_cast<uint32_t*>(ptr) = 0xDEADBEEF;",
	"    std::cout << \"Initialization sequence complete.\" << std::endl;",
	"    return 0;",
	"}",
	"#define MAX_RETRIES 5",
	"inline void fast_copy(void* dst, const void* src, size_t n) {",
	"    memcpy(dst, src, n);",
	"}",
	"volatile int lock = 0;",
	"__asm__ __volatile__(\"rep nop\");",
	"#include <thread>",
	"#include <mutex>",
	"#include <sys/socket.h>",
	"std::mutex g_queue_mutex;",
	"std::condition_variable g_queue_cv;",
	"void WorkerThread::run() {",
	"    std::unique_lock<std::mutex> lock(g_queue_mutex);",
	"    g_queue_cv.wait(lock, []{ return !task_queue.empty(); });",
	"    auto task = task_queue.front();",
	"    task_queue.pop();",
	"lock.unlock();",
	"task->execute();",
	"struct sockaddr_in server_addr;",
	"server_addr.sin_family = AF_INET;",
	"server_addr.sin_port = htons(PORT);",
	"inet_pton(AF_INET, \"127.0.0.1\", &server_addr.sin_addr);",
	"if (connect(sock, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0)",
	"    throw std::runtime_error(\"Connection failed\");",
	"uint8_t buffer[4096];",
	"ssize_t bytes_read = read(sock, buffer, sizeof(buffer));"
]

PLAINTEXT_VOCAB = [
	"Establishing secure connection to 192.168.1.104...",
	"Bypassing firewall [OK]",
	"Decrypting payload...",
	"[ERROR] Handshake failed. Retrying...",
	"ACCESS GRANTED",
	"Scanning ports 1-65535...",
	"Found open port: 22 (SSH)",
	"Found open port: 443 (HTTPS)",
	"Extracting configuration files...",
	"0x0000 48 65 6C 6C 6F 20 57 6F 72 6C 64 21 00 00 00 00",
	"0x0010 DE AD BE EF 00 00 00 00 00 00 00 00 00 00 00 00",
	"WARNING: Intusion detected. Rerouting traffic...",
	"Initializing rootkit...",
	"Downloading encrypted packet [========= ] 90%",
	"SYS_HALT overridden. Continuing execution.",
	"ping -c 4 8.8.8.8",
	"64 bytes from 8.8.8.8: icmp_seq=1 ttl=118 time=14.2 ms",
	"Connecting to proxy chain...",
	"Node 1: 104.22.45.1 [OK]",
	"Node 2: 198.51.100.22 [OK]",
	"Node 3: 203.0.113.109 [OK]",
	"Target acquired. Initiating brute force...",
	"Trying admin:admin... [FAILED]",
	"Trying root:toor... [FAILED]",
	"Trying guest:guest... [SUCCESS]",
	"Privilege escalation in progress...",
	"Injecting shellcode into process 4092",
	"Buffer overflow achieved.",
	"Dumping SAM database...",
	"Hash: 5d41402abc4b2a76b9719d911017c592",
	"Wiping access logs...",
	"rm -rf /var/log/syslog",
	"Covering tracks... [DONE]",
	"Disabling localized antivirus solutions...",
	"Establishing reverse shell on port 4444...",
	"Listening for incoming connections...",
	"0x0020 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F 10"
]

def generate_line(style):
	"""Returns a randomly selected line based on the chosen style."""
	if style == 'python':
		return random.choice(PYTHON_VOCAB)
	elif style == 'cpp':
		return random.choice(CPP_VOCAB)
	else:
		return random.choice(PLAINTEXT_VOCAB)

def main():
	parser = argparse.ArgumentParser(description="Terminal screensaver simulating hacker code.")
	parser.add_argument(
		'-s', '--speed', 
		type=int, 
		default=600, 
		help="Typing speed in Words Per Minute (WPM). Default: 600"
	)
	parser.add_argument(
		'-t', '--type', 
		type=str, 
		choices=['python', 'cpp', 'plaintext'], 
		default='plaintext', 
		help="Style of code to generate. Default: plaintext"
	)

	args = parser.parse_args()

	chars_per_min = args.speed * 5.0
	delay_per_char = 60.0 / chars_per_min if chars_per_min > 0 else 0

	# Set text color to green
	sys.stdout.write("\033[32m")
	sys.stdout.flush()

	stop_event = threading.Event()

	def on_press(key):
		if key == keyboard.Key.esc:
			stop_event.set()
			return False  # Stop listener

	# Start listener in a background thread
	listener = keyboard.Listener(on_press=on_press)
	listener.start()

	try:
		while not stop_event.is_set():
			line = generate_line(args.type)
			
			for char in line:
				if stop_event.is_set():
					break
				
				sys.stdout.write(char)
				sys.stdout.flush()
				
				jitter = random.uniform(0.5, 1.5)
				stop_event.wait(delay_per_char * jitter)
			
			if stop_event.is_set():
				break
			
			sys.stdout.write('\n')
			sys.stdout.flush()
			stop_event.wait(delay_per_char * 10)

	except KeyboardInterrupt:
		pass
	finally:
		listener.stop()
		sys.stdout.write("\033[0m\n")
		sys.stdout.flush()
		sys.exit(0)

if __name__ == "__main__":
	main()