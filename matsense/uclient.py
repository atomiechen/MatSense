"""
Communicate with server via UNIX domain datagram socket.

"""

from socket import (
	socket, AF_INET, SOCK_DGRAM, gethostname, gethostbyname,
	SOL_SOCKET, SO_SNDBUF
)
try:
	from socket import AF_UNIX
	support_unix_socket = True
except ImportError:
	support_unix_socket = False
from random import randint
from numpy import zeros
from os import unlink
import errno
from struct import calcsize, pack, unpack, unpack_from
from typing import Iterable
import time

from .tools import check_shape, parse_config
from .cmd import CMD


class Uclient:

	"""A client using UNIX domain datagram socket

	One can use the with-statements, or a try/finally pair, to make sure 
	close() is called to clean up binded file address.
	
	Attributes:
		N (int): sensor side length
		BUF_SIZE (int): max buffer size to receive data
		SERVER_FILE (str): server address
		CLIENT_FILE (str): client address
		CLIENT_FILE_PREFIX (str): client address prefix
		binded (bool): state of binding the client address
		my_socket (socket.socket): socket object
		data_parse (numpy.ndarray): currect saved frame data
	"""

	UDP = False
	## UNIX domain socket address
	CLIENT_FILE_PREFIX = "/var/tmp/unix.socket.client"
	SERVER_FILE = "/var/tmp/unix.socket.server"
	## UDP socket address
	hostname = gethostname()
	
	try:
		ip_address = gethostbyname(hostname)
	except:
		ip_address = gethostbyname("localhost")

	# CLIENT_HOST = "localhost"
	CLIENT_HOST = ip_address
	CLIENT_PORT_BASE = 25531
	# SERVER_HOST = "localhost"
	SERVER_HOST = ip_address
	SERVER_PORT = 25530
	SERVER_IPADDR = (SERVER_HOST, SERVER_PORT)

	N = 16
	TIMEOUT = 0.1
	BUF_SIZE = 8192

	def __init__(self, 
				client_addr=None, 
				server_addr=None, 
				**kwargs):
		"""constructor
				
		Args:
			address (str, optional): client address in UNIX domain. 
				Defaults to "" which generates a random address in
				format "/var/tmp/unix.socket.client.<6-digits>".
			server_addr (str, optional): server address. Defaults to 
				"/var/tmp/unix.socket.server".
			timeout (float, optional): socket timeout in seconds. 
				Defaults to 0.1.
		
		Raises:
			OSError: when client address already in use
		"""		

		self.config(**kwargs)
		self.client_addr = client_addr
		self.server_addr = server_addr

		self.binded = False
		self.N = check_shape(self.N)
		self.total = self.N[0] * self.N[1]
		self.data_parse = zeros(self.total, dtype=float)
		self.data_reshape = self.data_parse.reshape(self.N[0], self.N[1])
		self.data_imu = zeros(6, dtype=float)
		self.frame_idx = 0

		self.init_socket()

	def config(self, *, n=None, udp=None, timeout=None):
		if n is not None:
			self.N = n
		if udp is not None:
			self.UDP = udp
		if timeout:
			self.TIMEOUT = timeout

	def print_socket(self):
		if self.UDP:
			protocol_str = 'UDP'
		else:
			protocol_str = 'UNIX domain datagram'
		print(f"Socket protocol: {protocol_str}")
		print(f"  client address: {self.client_addr}")
		print(f"  server address: {self.server_addr}")

	def try_bind(self, address):
		try:
			self.my_socket.bind(address)
		except OSError as e:
			if e.errno == errno.EADDRINUSE:
				print("HINT: client address already in use, generating another one")
			else:
				raise e
			return False
		return True

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

		if self.client_addr:
			## check if ip address needs to be filled
			if self.UDP:
				tmp_addr = list(self.client_addr)
				if tmp_addr[0] is None:
					tmp_addr[0] = self.CLIENT_HOST
				if tmp_addr[1] is None:
					tmp_addr[1] = self.CLIENT_PORT_BASE
				self.client_addr = tuple(tmp_addr)
			self.my_socket.bind(self.client_addr)
		else:
			if self.UDP:
				self.client_addr = (self.CLIENT_HOST, self.CLIENT_PORT_BASE-1)
			while True:
				if self.UDP:
					## each attemp increase port number by one
					self.client_addr = (self.CLIENT_HOST, self.client_addr[1]+1)
				else:
					## add random 6 digits to the address (pad 0 to the head if necessary)
					self.client_addr = self.CLIENT_FILE_PREFIX + f".{randint(0, 999999):0>6}"
				if self.try_bind(self.client_addr):
					break
		self.binded = True
		self.my_socket.settimeout(self.TIMEOUT)
		self.my_socket.setsockopt(SOL_SOCKET, SO_SNDBUF, self.BUF_SIZE)

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

		self.print_socket()

	def close(self):
		"""close client, and unlink client address if binded
		"""		
		self.my_socket.close()
		if self.binded and not self.UDP:
			unlink(self.client_addr)
		print("client socket closed")

	def __enter__(self):
		return self

	def __exit__(self, type, value, traceback):
		self.close()

	def send_cmd(self, my_cmd, args=None):
		"""send command to server
		
		Args:
			my_cmd (CMD): a predefined command
			args (str/list/tuple, optional): additional arguments. 
				If str, append the encoded bytes of this string.
				If list or tuple, append int/double in bytes.
				Defaults to None.
		"""		
		my_msg = pack("=B", my_cmd)
		if isinstance(args, str):
			my_msg += args.encode("utf-8")
		elif isinstance(args, Iterable):
			for para in args:
				if isinstance(para, int):
					my_msg += pack("=i", para)
				elif isinstance(para, float):
					my_msg += pack("=d", para)
				else:
					raise Exception("Wrong parameter type!")

		self.my_socket.sendto(my_msg, self.server_addr)
		self.data, addr = self.my_socket.recvfrom(self.BUF_SIZE)

	def recv_frame(self):
		"""receive a frame from server
		
		Returns:
			tuple: 2-element tuple containing:

			**data_parse** (*numpy.ndarray*): a frame data

			**frame_idx** (*int*): the index of this frame
		"""		
		result = unpack_from(f"={self.total}di", self.data)
		self.data_parse[:] = result[:-1]
		self.frame_idx = result[-1]
		return self.data_parse, self.frame_idx

	def recv_string(self):
		"""receive a string from server
		
		Returns:
			tuple: 2-element tuple containing:

			**ret** (*bytes*): 1 byte of return value, 0 for success and
			255 for failure

			**label** (*str*): the returned string
		"""		
		if len(self.data) >= 2:
			label = self.data[1:].decode("utf-8")
		else:
			label = ""
		return self.data[0], label

	def recv_config(self):
		ret, config_str = self.recv_string()
		config = parse_config(config_str)
		return ret, config

	def recv_imu(self):
		result = unpack_from("=6di", self.data)
		self.data_imu[:] = result[:-1]
		self.frame_idx = result[-1]
		return self.data_imu, self.frame_idx

	def fetch_frame(self, input_arg=CMD.DATA, new=False):
		if new:
			## fetch a new pressure frame
			idx_prev = self.frame_idx
			self.fetch_frame_base(input_arg)
			while self.frame_idx == idx_prev:
				time.sleep(0.001)
				self.fetch_frame_base(input_arg)
		else:
			self.fetch_frame_base(input_arg)
		return self.data_reshape

	def fetch_frame_and_index(self, input_arg=CMD.DATA, new=False):
		self.fetch_frame(input_arg, new)
		return self.data_reshape, self.frame_idx

	def fetch_frame_base(self, input_arg):
		try:
			self.send_cmd(input_arg)
			self.recv_frame()
		except:
			pass

	def fetch_imu(self, new=False):
		if new:
			## fetch a new IMU frame
			idx_prev = self.frame_idx
			self.fetch_imu_base()
			while self.frame_idx == idx_prev:
				time.sleep(0.001)
				self.fetch_imu_base()
		else:
			self.fetch_imu_base()
		return self.data_imu

	def fetch_imu_and_index(self, new=False):
		self.fetch_imu(new)
		return self.data_imu, self.frame_idx

	def fetch_imu_base(self):
		try:
			self.send_cmd(CMD.DATA_IMU)
			self.recv_imu()
		except:
			pass

	def gen(self, input_arg=CMD.DATA):
		"""generate a data generator given specific command
		
		Args:
			input_arg (int): a predefined command, either CMD.DATA or
				CMD.RAW. Defaults to CMD.DATA.
		
		Yields:
			data_parse (numpy.ndarray): a frame data
		"""		
		while True:
			try:
				self.send_cmd(input_arg)
				self.recv_frame()
				yield self.data_reshape
			except GeneratorExit:
				return
			except:
				yield self.data_reshape

	def gen_frame_and_index(self, input_arg=CMD.DATA):
		while True:
			try:
				self.send_cmd(input_arg)
				self.recv_frame()
				yield self.data_reshape, self.frame_idx
			except GeneratorExit:
				return
			except:
				yield self.data_reshape, self.frame_idx

	def gen_imu(self):
		while True:
			try:
				self.send_cmd(CMD.DATA_IMU)
				self.recv_imu()
				yield self.data_imu
			except GeneratorExit:
				return
			except:
				yield self.data_imu

	def gen_imu_and_index(self):
		while True:
			try:
				self.send_cmd(CMD.DATA_IMU)
				self.recv_imu()
				yield self.data_imu, self.frame_idx
			except GeneratorExit:
				return
			except:
				yield self.data_imu, self.frame_idx


if __name__ == '__main__':
	with Uclient() as my_client:
		# generator = my_client.gen(CMD.DATA)
		# for data in generator:
		# 	print(data)
		print("write some code here.")

	## or you can use a try/finally pair to make sure close() is called
	try:
		my_client = Uclient("/var/tmp/tmp.client")
		print("write another bunch of code here.")
	finally:
		my_client.close()
