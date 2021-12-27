from socket import (
	socket, AF_INET, SOCK_DGRAM, timeout, 
	SOL_SOCKET, SO_REUSEADDR, SO_SNDBUF,
	gethostname, gethostbyname
)
try:
	from socket import AF_UNIX
	support_unix_socket = True
except ImportError:
	support_unix_socket = False
from struct import calcsize, pack, unpack, unpack_from
from os import unlink

from .flag import FLAG
from ..cmd import CMD


class Userver:

	UDP = False
	## UNIX domain socket address
	SERVER_FILE = "/var/tmp/unix.socket.server"
	## UDP socket address
	hostname = gethostname()

	try:
		ip_address = gethostbyname(hostname)
	except:
		ip_address = gethostbyname("localhost")

	# SERVER_HOST = "localhost"
	SERVER_HOST = ip_address
	SERVER_PORT = 25530
	SERVER_IPADDR = (SERVER_HOST, SERVER_PORT)

	TOTAL = 16 * 16
	TIMEOUT = 0.1
	BUF_SIZE = 2048
	REC_ID = 0

	def __init__(self, data_out, data_raw, data_imu, idx_out, server_addr=None, **kwargs):
		## for multiprocessing communication
		self.pipe_conn = None

		self.config(**kwargs)
		self.data_out = data_out
		self.data_raw = data_raw
		self.data_imu = data_imu
		self.idx_out = idx_out
		self.server_addr = server_addr

		self.binded = False
		self.frame_format = f"={self.TOTAL}di"
		self.frame_size = calcsize(self.frame_format)

		self.init_socket()

	def config(self, *, total=None, udp=None, timeout=None, pipe_conn=None):
		if total is not None:
			self.TOTAL = total
		if udp is not None:
			self.UDP = udp
		if timeout is not None:
			self.TIMEOUT = timeout
		if pipe_conn is not None:
			self.pipe_conn = pipe_conn

	def init_socket(self):
		if not support_unix_socket:
			## this machine does not support UNIX domain socket
			self.UDP = True
		if self.UDP:
			## UDP socket
			self.my_socket = socket(AF_INET, SOCK_DGRAM)
		else:
			## UNIX domain socket
			self.my_socket = socket(AF_UNIX, SOCK_DGRAM)

		self.my_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
		self.my_socket.setsockopt(SOL_SOCKET, SO_SNDBUF, self.frame_size*2)
		self.my_socket.settimeout(self.TIMEOUT)

		if not self.server_addr:
			if self.UDP:
				self.server_addr = self.SERVER_IPADDR
			else:
				self.server_addr = self.SERVER_FILE
		else:
			## check if ip-port address needs to be filled
			if self.UDP:
				tmp_addr = list(self.server_addr)
				if tmp_addr[0] is None:
					tmp_addr[0] = self.SERVER_HOST
				if tmp_addr[1] is None:
					tmp_addr[1] = self.SERVER_PORT
				self.server_addr = tuple(tmp_addr)
		self.my_socket.bind(self.server_addr)
		self.binded = True

	def exit(self):
		self.my_socket.close()
		if self.binded and not self.UDP:
			unlink(self.server_addr)
		print("Service stopped.")

	def __enter__(self):
		return self

	def __exit__(self, type, value, traceback):
		self.exit()

	def proc_cmd(self):
		if self.data[0] == CMD.CLOSE:
			reply = pack("=B", 0)
			self.my_socket.sendto(reply, self.client_addr)
			self.pipe_conn.send((FLAG.FLAG_REC_STOP,))
			return CMD.CLOSE
		elif self.data[0] == CMD.DATA:
			reply = pack(self.frame_format, *(self.data_out), self.idx_out.value)
			self.my_socket.sendto(reply, self.client_addr)
		elif self.data[0] == CMD.RAW:
			reply = pack(self.frame_format, *(self.data_raw), self.idx_out.value)
			self.my_socket.sendto(reply, self.client_addr)
		elif self.data[0] in (CMD.REC_DATA, CMD.REC_RAW):
			if self.data[0] == CMD.REC_DATA:  ## processed data
				self.pipe_conn.send((FLAG.FLAG_REC_DATA, str(self.data[1:], encoding = "utf-8")))
			else:  ## raw data
				self.pipe_conn.send((FLAG.FLAG_REC_RAW, str(self.data[1:], encoding = "utf-8")))
			msg = self.pipe_conn.recv()
			flag = msg[0]
			if flag == FLAG.FLAG_REC_RET_SUCCESS:
				reply = pack("=B", 0) + msg[1].encode('utf-8')
			else:
				reply = pack("=B", 255)
			self.my_socket.sendto(reply, self.client_addr)
		elif self.data[0] == CMD.REC_STOP:
			reply = pack("=B", 0)
			self.pipe_conn.send((FLAG.FLAG_REC_STOP,))
			self.my_socket.sendto(reply, self.client_addr)
		elif self.data[0] == CMD.RESTART:
			## TODO
			pass
		elif self.data[0] == CMD.PARAS:
			## TODO
			pass
		elif self.data[0] == CMD.REC_BREAK:
			reply = pack("=B", 0)
			self.my_socket.sendto(reply, self.client_addr)
			self.pipe_conn.send((FLAG.FLAG_REC_BREAK,))
		elif self.data[0] == CMD.DATA_IMU:
			reply = pack("=6di", *(self.data_imu), self.idx_out.value)
			self.my_socket.sendto(reply, self.client_addr)

	def print_service(self):
		if self.UDP:
			protocol_str = 'UDP'
		else:
			protocol_str = 'UNIX domain datagram'
		print(f"Service protocol: {protocol_str}")
		print(f"  - Server address: {self.server_addr}")

	def run_service(self):
		self.print_service()
		print(f"Running service...")
		while True:
			## check signals from the other process
			if self.pipe_conn is not None:
				if self.pipe_conn.poll():
					flag = self.pipe_conn.recv()
					if flag == FLAG.FLAG_STOP:
						break

			## try to receive requests from client(s)
			try:
				self.data, self.client_addr = self.my_socket.recvfrom(self.BUF_SIZE)
				ret = self.proc_cmd()
				if ret == CMD.CLOSE:
					self.pipe_conn.send((FLAG.FLAG_STOP,))
					break
			except timeout:
				pass
			except (FileNotFoundError, ConnectionResetError):
				print("client off-line")

