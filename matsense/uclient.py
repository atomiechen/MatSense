"""
Communicate with server via UNIX domain datagram socket.

"""

from socket import (
	socket, AF_INET, SOCK_DGRAM, timeout, 
	gethostname, gethostbyname
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

from .tools import check_shape
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
	BUF_SIZE = 4096

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

	def recv_paras(self):
		"""receive process parameters from server
		
		Returns:
			list: variable-length list containing:

			**ret** (*bytes*): 1 byte of return value, 0 for success and
			255 for failure

			**i** (*int*): initiating frame number

			**w** (*int*): calibration window size

			**f** (*int*): filter index
			
			and other parameters corresponding to the filter.
		"""		
		paras = unpack_from("=B3i", self.data)
		start = calcsize("=B3i")
		my_filter = paras[-1]
		if my_filter == 1:  # exponential smoothing
			paras += unpack_from("=2d", self.data, start)
		elif my_filter == 2:  # moving average
			paras += unpack_from("=i", self.data, start)
		elif my_filter == 3:  # sinc low-pass
			paras += unpack_from("=id", self.data, start)
		return paras

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

	def interactive_cmd(self, my_cmd):
		"""interactive command parser

		Show hints to help input specific parameters.
		
		Args:
			my_cmd (CMD): a predefined command
		"""
		if my_cmd not in CMD.__members__.values():
			print("Unknown command!")
			return

		try:
			if my_cmd == CMD.CLOSE:
				self.send_cmd(my_cmd)
			elif my_cmd in (CMD.DATA, CMD.RAW):
				self.send_cmd(my_cmd)
				frame_idx = self.recv_frame()[1]
				print(f"frame_idx: {frame_idx}")
			elif my_cmd in (CMD.REC_DATA, CMD.REC_RAW):
				print(f"recording filename:")
				my_filename = input("|> ").strip()
				self.send_cmd(my_cmd, my_filename)
				ret, recv_filename = self.recv_string()
				if ret == 0:
					if my_cmd == CMD.REC_DATA:
						data_mode = "processed"
					else:
						data_mode = "raw"
					print(f"recording {data_mode} data to file: {recv_filename}")
				else:
					print(f"fail to write to file: {recv_filename}")
			elif my_cmd == CMD.REC_STOP:
				self.send_cmd(my_cmd)
				ret, recv_str = self.recv_string()
				if ret == 0:
					print("stop recording")
				else:
					print("fail to stop recording!")
			elif my_cmd == CMD.RESTART:
				try:
					print(f"initiating frame number:")
					obtained = input("|> ").strip()
					if obtained:
						my_initcali = int(obtained)
					else:
						my_initcali = -1
					print(f"{my_initcali}")
					print(f"calibration window size:")
					obtained = input("|> ").strip()
					if obtained:
						my_win = int(obtained)
					else:
						my_win = -1
					print(f"{my_win}")
					print(f"filter:")
					obtained = input("|> ").strip()
					if obtained:
						my_filter = int(obtained)
					else:
						my_filter = -1
					print(f"{my_filter}")
					args = [my_initcali, my_win, my_filter]
					if my_filter == 1:
						print(f"exponential smoothing.")
						print(f"alpha:")
						obtained = input("|> ").strip()
						if obtained:
							my_alpha = float(obtained)
						else:
							my_alpha = -1.0
						print(f"{my_alpha}")
						print(f"beta:")
						obtained = input("|> ").strip()
						if obtained:
							my_beta = float(obtained)
						else:
							my_beta = -1.0
						print(f"{my_beta}")
						args.append(my_alpha)
						args.append(my_beta)
					elif my_filter == 2:
						print(f"moving average.")
						print(f"kernel size:")
						obtained = input("|> ").strip()
						if obtained:
							my_ma_size = int(obtained)
						else:
							my_ma_size = -1
						print(f"{my_ma_size}")
						args.append(my_ma_size)
					elif my_filter == 3:
						print(f"sinc low-pass filter.")
						print(f"kernel size:")
						obtained = input("|> ").strip()
						if obtained:
							my_lp_size = int(obtained)
						else:
							my_lp_size = -1
						print(f"{my_lp_size}")
						print(f"cut-off frequency:")
						obtained = input("|> ").strip()
						if obtained:
							my_lp_w = float(obtained)
						else:
							my_lp_w = -1.0
						print(f"{my_lp_size}")
						args.append(my_lp_size)
						args.append(my_lp_w)

					self.send_cmd(my_cmd, args=args)
					results = self.recv_paras()
					if results[0] == 0:
						print(f"server restarting...")
					else:
						print("fail to restart server")
					self.print_paras(results[1:])
				except ValueError:
					print("invalid arguments to restart server")
			elif my_cmd == CMD.PARAS:
				self.send_cmd(my_cmd)
				results = self.recv_paras()
				self.print_paras(results[1:])
			elif my_cmd == CMD.REC_BREAK:
				self.send_cmd(my_cmd)
				ret, recv_str = self.recv_string()
				if ret == 0:
					print("successfully break")
				else:
					print("fail to break!")
			elif my_cmd == CMD.DATA_IMU:
				self.send_cmd(my_cmd)
				data_imu, frame_idx = self.recv_imu()
				print(f"IMU data: {data_imu}")
				print(f"frame_idx: {frame_idx}")

		except (FileNotFoundError, ConnectionResetError):
			print("server off-line")
		except ConnectionRefusedError:
			print("server refused connection")
		except timeout:
			print("server no response")

	def print_paras(self, paras):
		print(f"Server parameters:")
		print(f"  initiating frame number: {paras[0]}")
		print(f"  calibration window size: {paras[1]}")
		print(f"  filter:  {paras[2]}")
		my_filter = paras[2]
		if my_filter == 0:
			print(f"    None")
		elif my_filter == 1:
			print(f"    exponential smoothing")
			print(f"    * ALPHA: {paras[3]}")
			print(f"    * BETA:  {paras[4]}")
		elif my_filter == 2:
			print(f"    moving average")
			print(f"    * kernel size: {paras[3]}")
		elif my_filter == 3:
			print(f"    sinc low-pass filter")
			print(f"    * kernel size:       {paras[3]}")
			print(f"    * cut-off frequency: {paras[4]}")


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
