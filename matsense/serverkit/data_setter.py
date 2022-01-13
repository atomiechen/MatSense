from enum import Enum
import time
from datetime import datetime
from struct import calcsize, pack, unpack, unpack_from
from serial import Serial

from .exception import SerialTimeout, FileEnd
from ..filemanager import parse_line


class DATA_PROTOCOL(Enum):
	SIMPLE = "simple"  # 255 as delimiter
	SECURE = "secure"  # secure protocol using escape character


class DataSetterSerial:

	## original protocol
	DELIM = 0xFF
	## robust protocol
	HEAD = 0x5B
	TAIL = 0x5D
	ESCAPE = 0x5C
	ESCAPE_ESCAPE = 0x00
	ESCAPE_HEAD = 0x01
	ESCAPE_TAIL = 0x02

	imu = False
	protocol = DATA_PROTOCOL.SIMPLE

	def __init__(self, total, baudrate, port, timeout=None, **kwargs):
		self.my_serial = self.connect_serial(baudrate, port, timeout)
		self.total = total
		self.start_time = time.time()
		self.config(**kwargs)

		self.frame_size = (self.total + 12) if self.imu else self.total

	def config(self, *, imu=None, protocol=None):
		if imu is not None:
			self.imu = imu
		if protocol is not None:
			try:
				self.protocol = DATA_PROTOCOL(protocol)
			except:
				print(f"Invalid data protocol: '{protocol}'! Use {self.protocol} instead.")

	@staticmethod
	def connect_serial(baudrate, port, timeout=None):
		# 超时设置,None：永远等待操作，0为立即返回请求结果，其他值为等待超时时间(单位为秒）
		ser = Serial(port, baudrate, timeout=timeout)
		print("串口详情参数：", ser)
		return ser

	def read_byte(self):
		recv = self.my_serial.read()
		if len(recv) != 1:
			raise SerialTimeout
		return recv[0]

	def put_frame_simple(self, data_pressure):
		frame = []
		while True:
			recv = self.read_byte()
			if recv == self.DELIM:
				if len(frame) != self.total:
					print(f"Wrong frame size: {len(frame)}")
					frame = []
				else:
					data_pressure[:self.total] = frame
					break
			else:
				frame.append(recv)

	def put_frame_secure(self, data_pressure, data_imu):
		## ref: https://blog.csdn.net/weixin_43277501/article/details/104805286
		frame = bytearray()
		begin = False
		while True:
			recv = self.read_byte()
			if begin:
				if recv == self.ESCAPE:
					## escape bytes
					recv = self.read_byte()
					if recv == self.ESCAPE_ESCAPE:
						frame.append(self.ESCAPE)
					elif recv == self.ESCAPE_HEAD:
						frame.append(self.HEAD)
					elif recv == self.ESCAPE_TAIL:
						frame.append(self.TAIL)
					else:
						print(f"Wrong ESCAPE byte: {recv}")
				elif recv == self.TAIL:
					## end a frame
					if len(frame) != self.frame_size:
						## wrong length, re-fetch a frame
						print(f"Wrong frame size: {len(frame)}")
						frame = bytearray()
						begin = False
					else:
						pos = self.total
						data_pressure[:pos] = frame[:pos]
						if self.imu:
							for i in range(6):
								data_imu[i] = unpack_from(f"=h", frame, pos)[0]
								pos += calcsize(f"=h")
						break
				else:
					frame.append(recv)
			elif recv == self.HEAD:
				## begin a frame
				begin = True

	def __call__(self, data_pressure, data_imu=None, *args, **kwargs):
		if self.protocol == DATA_PROTOCOL.SIMPLE:
			self.put_frame_simple(data_pressure)
		elif self.protocol == DATA_PROTOCOL.SECURE:
			self.put_frame_secure(data_pressure, data_imu)


class DataSetterDebug(DataSetterSerial):
	def __init__(*args, **kwargs):
		pass

	def __call__(*args, **kwargs):
		time.sleep(0.01)


class DataSetterFile:
	## file as data source
	def __init__(self, total, filenames):
		self.total = total
		if isinstance(filenames, str):
			filenames = [filenames]
		self.filenames = filenames

		self.file_idx = 0
		self.fin = None

	def open_next_file(self):
		self.fin = open(self.filenames[self.file_idx], 'r', encoding='utf-8')
		self.file_idx += 1

	def __call__(self, data_tmp, *args, **kwargs):
		## first time to open a file

		if self.fin is None:
			if self.file_idx < len(self.filenames):
				self.open_next_file()
			else:
				raise Exception("No file provided!")

		while True:
			line = self.fin.readline()
			if line:
				## get new line
				break
			else:
				## reach end of file
				self.fin.close()
				if self.file_idx == len(self.filenames):
					raise FileEnd
				else:
					self.open_next_file()

		_, frame_idx, data_time = parse_line(line, self.total, ',', data_out=data_tmp)
		return frame_idx, int(datetime.timestamp(data_time)*1000000)
