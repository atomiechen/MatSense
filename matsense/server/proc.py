from math import exp, hypot, pi, sin
from enum import Enum
import numpy as np
import time
from datetime import datetime
from typing import Iterable
from struct import calcsize, pack, unpack, unpack_from

from serial import Serial
from multiprocessing import Array  # 共享内存

from .flag import FLAG
from .exception import SerialTimeout, FileEnd
from ..tools import check_shape
from ..filemanager import parse_line, write_line


class FILTER_SPATIAL(Enum):
	NONE = "none"  # no spatial filter
	IDEAL = "ideal"  # ideal kernel
	BUTTERWORTH = "butterworth"  # butterworth kernel
	GAUSSIAN = "gaussian"  # gaussian kernel


class FILTER_TEMPORAL(Enum):
	NONE = "none"  # no temporal filter
	MA = "moving average"  # moving average
	RW = "rectangular window"  # rectangular window filter (sinc)


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
		self.fin = open(self.filenames[self.file_idx], 'r')
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


class DataHandler:

	def __init__(*args, **kwargs):
		pass

	def prepare(self, generator):
		pass

	def handle(self, data):
		pass

	def final(self):
		pass


class DataHandlerPressure(DataHandler):

	## data mode
	my_raw = False

	## default filters
	my_filter_spatial = FILTER_SPATIAL.GAUSSIAN
	my_filter_temporal = FILTER_TEMPORAL.RW

	## voltage-resistance conversion
	my_convert = True
	V0 = 255
	R0_RECI = 1  ## a constant to multiply the value

	## process parameters
	my_SF_D0 = 3.5
	my_BUTTER_ORDER = 2
	my_LP_SIZE = 15
	my_LP_W = 0.04
	my_INIT_CALI_FRAMES = 200
	my_WIN_SIZE = 0

	def __init__(self, **kwargs):
		self.mask = None

		## output intermediate result
		## 0: convert voltage to reciprocal resistance
		## 1: convert & spatial filter
		## 2: convert & spatial filter & temporal filter
		self.intermediate = 0
		self.data_inter = None

		self.config(**kwargs)

	def config(self, *, n, raw=None, V0=None, R0_RECI=None, convert=None, 
		mask=None, filter_spatial=None, filter_spatial_cutoff=None, 
		butterworth_order=None, filter_temporal=None, 
		filter_temporal_size=None, rw_cutoff=None, cali_frames=None, 
		cali_win_size=None, 
		intermediate=None,
		**kwargs):

		self.n = check_shape(n)
		self.total = self.n[0] * self.n[1]
		self.cols = self.n[1]//2 + 1

		if raw is not None:
			self.my_raw = raw
		if V0:
			self.V0 = V0
		if R0_RECI:
			self.R0_RECI = R0_RECI
		if convert is not None:
			self.my_convert = convert
		if mask is not None:
			self.mask = mask
		if filter_spatial is not None:
			try:
				self.my_filter_spatial = FILTER_SPATIAL(filter_spatial)
			except:
				print(f"Invalid spatial filter: '{filter_spatial}'! Use {self.my_filter_spatial.value} instead.")
		if filter_spatial_cutoff is not None:
			self.my_SF_D0 = filter_spatial_cutoff
		if butterworth_order is not None:
			self.my_BUTTER_ORDER = butterworth_order
		if filter_temporal is not None:
			try:
				self.my_filter_temporal = FILTER_TEMPORAL(filter_temporal)
			except:
				print(f"Invalid temporal filter: '{filter_temporal}'! Use {self.my_filter_temporal.value} instead.")
		if filter_temporal_size is not None:
			self.my_LP_SIZE = filter_temporal_size
		if rw_cutoff is not None:
			self.my_LP_W = rw_cutoff
		if cali_frames is not None:
			self.my_INIT_CALI_FRAMES = cali_frames
		if cali_win_size is not None:
			self.my_WIN_SIZE = cali_win_size
		if intermediate is not None:
			self.intermediate = intermediate

	@staticmethod
	def calReciprocalResistance(voltage, v0, r0_reci):
		if v0 - voltage <= 0:
			return 0
		return r0_reci * voltage / (v0 - voltage)

	@staticmethod
	def calReci_numpy_array(np_array, v0, r0_reci):
		np_array[np_array >= v0] = 0
		np_array /= (v0 - np_array)
		np_array *= r0_reci

	@staticmethod
	def getNextIndex(idx, size):
		return (idx+1) if idx != (size-1) else 0

	def handle_raw_frame(self, data):
		self.data_tmp = data
		self.data_reshape = self.data_tmp.reshape(self.n[0], self.n[1])
		if self.mask is not None:
			self.data_reshape *= self.mask
		if self.my_convert:
			# for i in range(self.total):
			# 	self.data_tmp[i] = self.calReciprocalResistance(self.data_tmp[i], self.V0, self.R0_RECI)
			self.calReci_numpy_array(self.data_tmp, self.V0, self.R0_RECI)

	def prepare(self, generator):
		self.generator = generator
		if not self.my_raw:
			self.prepare_spatial()
			self.prepare_temporal()
			self.prepare_cali()
		self.print_proc()

	def handle(self, data, data_inter=None):
		self.handle_raw_frame(data)
		self.data_inter = data_inter

		## output intermediate result
		if self.data_inter is not None and self.intermediate == 0:
			self.data_inter[:] = self.data_tmp[:]

		if not self.my_raw:
			self.filter()
			self.calibrate()
		elif self.data_inter is not None and self.intermediate != 0:
			## output intermediate result, making data_inter not blank
			self.data_inter[:] = self.data_tmp[:]

	def prepare_cali(self):
		if self.my_INIT_CALI_FRAMES <= 0:
			return

		print("Initiating calibration...");
		self.data_zero = np.zeros(self.total, dtype=float)
		self.data_win = np.zeros((self.my_WIN_SIZE, self.total), dtype=float)
		self.win_frame_idx = 0
		## for preparing calibration
		frame_cnt = 0
		# ## accumulate data
		while frame_cnt < self.my_INIT_CALI_FRAMES:
			# self.get_raw_frame()
			data = next(self.generator)
			self.handle_raw_frame(data)

			self.filter()
			self.data_zero += self.data_tmp
			frame_cnt += 1
		## get average
		self.data_zero /= frame_cnt
		## calculate data_win
		self.data_win[:] = self.data_zero

	def calibrate(self):
		if self.my_INIT_CALI_FRAMES <= 0:
			return
		stored = self.data_tmp.copy()
		## calibrate
		self.data_tmp -= self.data_zero
		## the value should be positive
		self.data_tmp[self.data_tmp < 0] = 0
		## adjust window if using dynamic window
		if self.my_WIN_SIZE > 0:
			## update data_zero (zero position) and data_win (history data)
			self.data_zero += (stored - self.data_win[self.win_frame_idx]) / self.my_WIN_SIZE
			self.data_win[self.win_frame_idx] = stored
			## update frame index
			self.win_frame_idx = self.getNextIndex(self.win_frame_idx, self.my_WIN_SIZE)

	def filter(self):
		self.spatial_filter()
		## output intermediate result
		if self.data_inter is not None and self.intermediate == 1:
			self.data_inter[:] = self.data_tmp[:]

		self.temporal_filter()
		## output intermediate result
		if self.data_inter is not None and self.intermediate == 2:
			self.data_inter[:] = self.data_tmp[:]

	def prepare_temporal(self):
		if self.my_filter_temporal == FILTER_TEMPORAL.NONE:
			return

		print("Initiating temporal filter...");
		self.data_filter = np.zeros((self.my_LP_SIZE-1, self.total), dtype=float)
		self.kernel_lp = np.zeros(self.my_LP_SIZE, dtype=float)
		self.filter_frame_idx = 0
		self.need_cache = self.my_LP_SIZE - 1

		if self.my_filter_temporal == FILTER_TEMPORAL.MA:
			## moving average
			self.kernel_lp[:] = 1 / self.my_LP_SIZE
		elif self.my_filter_temporal == FILTER_TEMPORAL.RW:
			## FIR Rectangular window filter (sinc low pass)
			sum_all = 0
			for t in range(self.my_LP_SIZE):
				shifted = t - (self.my_LP_SIZE-1) / 2
				if shifted == 0:
					## limit: t -> 0, sin(t)/t -> 1
					self.kernel_lp[t] = 2 * pi * self.my_LP_W
				else:
					self.kernel_lp[t] = sin(2 * pi * self.my_LP_W * shifted) / shifted
				sum_all += self.kernel_lp[t]
			self.kernel_lp /= sum_all
		else:
			raise Exception("Unknown temporal filter!")

		if self.need_cache > 0:
			print(f"Cache {self.need_cache} frames for filter.")
			while self.need_cache > 0:
				# self.get_raw_frame()
				data = next(self.generator)
				self.handle_raw_frame(data)

				self.filter()
				self.need_cache -= 1

	def temporal_filter(self):
		if self.my_filter_temporal == FILTER_TEMPORAL.NONE:
			return

		stored = self.data_tmp.copy()
		## convolve
		self.data_tmp *= self.kernel_lp[0]
		## oldest point in data_filter is firstly visited
		for t in range(1, self.my_LP_SIZE):
			self.data_tmp += self.data_filter[self.filter_frame_idx] * self.kernel_lp[t]
			self.filter_frame_idx = self.getNextIndex(self.filter_frame_idx, self.my_LP_SIZE-1)
		self.data_filter[self.filter_frame_idx] = stored
		## update to next index
		self.filter_frame_idx = self.getNextIndex(self.filter_frame_idx, self.my_LP_SIZE-1)

	def prepare_spatial(self):
		def gaussianLP(distance):
			return exp(-distance**2/(2*(self.my_SF_D0)**2))

		def butterworthLP(distance):
			return 1 / (1 + (distance / self.my_SF_D0)**(2 * self.my_BUTTER_ORDER))

		def idealFilterLP(distance):
			if distance <= self.my_SF_D0:
				return 1
			else:
				return 0

		if self.my_filter_spatial == FILTER_SPATIAL.NONE:
			return

		if self.my_filter_spatial == FILTER_SPATIAL.IDEAL:
			freq_window = idealFilterLP
		elif self.my_filter_spatial == FILTER_SPATIAL.BUTTERWORTH:
			freq_window = butterworthLP
		elif self.my_filter_spatial == FILTER_SPATIAL.GAUSSIAN:
			freq_window = gaussianLP
		else:
			raise Exception("Unknown spatial filter!")

		row_divide = self.n[0] // 2
		self.kernel_sf = np.zeros((self.n[0], self.cols), dtype=float)
		for i in range(row_divide + 1):
			for j in range(self.cols):
				distance = hypot(i, j)
				self.kernel_sf[i][j] = freq_window(distance)
		for i in range(row_divide + 1, self.n[0]):
			for j in range(self.cols):
				distance = hypot(self.n[0]-i, j)
				self.kernel_sf[i][j] = freq_window(distance)

	def spatial_filter(self):
		if self.my_filter_spatial == FILTER_SPATIAL.NONE:
			return
		# self.data_tmp = self.data_tmp.reshape(self.n[0], self.n[1])
		freq = np.fft.rfft2(self.data_reshape)
		freq *= self.kernel_sf
		## must specify shape when the final axis number is odd
		self.data_reshape[:] = np.fft.irfft2(freq, self.data_reshape.shape)

	def print_proc(self):
		print(f"Voltage-resistance conversion: {self.my_convert}")
		print(f"Data mode: {'raw' if self.my_raw else 'processed'}")
		if not self.my_raw:
			## collect spatial filter info
			arg_list_s = {}
			if self.my_filter_spatial == FILTER_SPATIAL.BUTTERWORTH:
				arg_list_s["order"] = self.my_BUTTER_ORDER
			if self.my_filter_spatial != FILTER_SPATIAL.NONE:
				arg_list_s["cut-off freqency"] = self.my_SF_D0

			## collect temporal filter info
			arg_list_t = {}
			if self.my_filter_temporal == FILTER_TEMPORAL.RW:
				arg_list_t["cut-off normalized freqency"] = self.my_LP_W
			if self.my_filter_temporal != FILTER_TEMPORAL.NONE:
				arg_list_t["kernel size"] = self.my_LP_SIZE

			## output to screen
			print(f"  - Spatial filter: {self.my_filter_spatial.value}")
			for value, key in arg_list_s.items():
				print(f"    {value}: {key}")
			print(f"  - Temporal filter: {self.my_filter_temporal.value}")
			for value, key in arg_list_t.items():
				print(f"    {value}: {key}")

			print(f"  - Calibration: {'No' if self.my_INIT_CALI_FRAMES == 0 else ''}")
			if self.my_INIT_CALI_FRAMES != 0:
				print(f"    Initializing frames:     {self.my_INIT_CALI_FRAMES}")
				if self.my_WIN_SIZE == 0:
					print("    Static calibration")
				else:
					print("    Dynamic calibration")
					print(f"    Calibration window size: {self.my_WIN_SIZE}")


class DataHandlerIMU(DataHandler):
	pass


class Proc:

	## fps checking
	FPS_CHECK_TIME = 1  # seconds of interval to check fps

	## for warming up, make CPU schedule more time for serial reading
	WARM_UP = 1  # seconds

	## filename received from server
	FILENAME_TEMPLATE = "record_%Y%m%d%H%M%S.csv"
	FILENAME_TEMPLATE_RAW = "record_%Y%m%d%H%M%S_raw.csv"


	def __init__(self, n, data_setter, data_out, data_raw, data_imu, idx_out, **kwargs):
		## sensor info
		self.n = check_shape(n)
		self.total = self.n[0] * self.n[1]

		## default data source
		self.data_setter = data_setter

		## recording
		self.record_raw = False
		self.filename = None
		self.filename_id = 0
		self.tags = None
		## copy tags from data setter to output file,
		## if False, generate tags using current frame index and timestamp
		self.copy_tags = False

		## for multiprocessing communication
		self.pipe_conn = None

		self.imu = False

		self.config(**kwargs)
		kwargs['n'] = self.n
		self.handler_pressure = DataHandlerPressure(**kwargs)
		self.handler_imu = DataHandlerIMU(**kwargs)

		## intermediate data
		self.data_tmp = np.zeros(self.total, dtype=float)
		self.data_inter = np.zeros(self.total, dtype=float)

		## shared data
		self.data_out = data_out
		self.data_raw = data_raw
		self.data_imu = data_imu
		self.idx_out = idx_out


	def config(self, *, warm_up=None, pipe_conn=None,
		output_filename=None, copy_tags=None, imu=None, **kwargs):
		if warm_up is not None:
			self.WARM_UP = warm_up
		if pipe_conn is not None:
			self.pipe_conn = pipe_conn
		if output_filename is not None:
			self.filename = output_filename
		if copy_tags is not None:
			self.copy_tags = copy_tags
		if imu is not None:
			self.imu = imu

	def reset(self):
		## for output
		self.idx_out.value = 0
		## for fps checking
		self.last_frame_idx = 0
		self.last_time = self.start_time

	def get_raw_frame(self):
		self.tags = self.data_setter(self.data_tmp, self.data_imu)
		self.idx_out.value += 1

	def post_action(self):
		if self.cur_time - self.last_time >= self.FPS_CHECK_TIME:
			duration = self.cur_time - self.last_time
			run_duration = self.cur_time - self.start_time
			frames = self.idx_out.value - self.last_frame_idx
			print(f"  frame rate: {frames/duration:.3f} fps  running time: {run_duration:.3f} s")
			if self.imu:
				print(f"  {self.data_imu[:]}")
			self.last_frame_idx = self.idx_out.value
			self.last_time = self.cur_time
		if self.filename:
			if self.record_raw:
				data_ptr = self.data_raw
			else:
				data_ptr = self.data_out
			if not self.copy_tags:
				timestamp = int(self.cur_time*1000000)
				self.tags = [self.idx_out.value, timestamp]
			write_line(self.filename, data_ptr, tags=self.tags)

	def loop_proc(self):
		print("Running processing...")
		while True:
			## check signals from the other process
			if self.pipe_conn is not None:
				if self.pipe_conn.poll():
					msg = self.pipe_conn.recv()
					# print(f"msg={msg}")
					flag = msg[0]
					if flag == FLAG.FLAG_STOP:
						break
					if flag in (FLAG.FLAG_REC_DATA, FLAG.FLAG_REC_RAW):
						self.record_raw = True if flag == FLAG.FLAG_REC_RAW else True
						filename = msg[1]
						if filename == "":
							if flag == FLAG.FLAG_REC_RAW:
								filename = datetime.now().strftime(self.FILENAME_TEMPLATE_RAW)
							else:
								filename = datetime.now().strftime(self.FILENAME_TEMPLATE)
						try:
							with open(filename, 'a') as fout:
								pass
							if self.filename is not None:
								print(f"stop recording:   {self.filename}")
							self.filename = filename
							print(f"recording to:     {self.filename}")
							self.pipe_conn.send((FLAG.FLAG_REC_RET_SUCCESS,self.filename))
						except:
							print(f"failed to record: {self.filename}")
							self.pipe_conn.send((FLAG.FLAG_REC_RET_FAIL,))

					elif flag == FLAG.FLAG_REC_STOP:
						if self.filename is not None:
							print(f"stop recording:   {self.filename}")
						self.filename = None
						self.filename_id = 0
					elif flag == FLAG.FLAG_REC_BREAK:
						self.filename_id += 1

			try:
				self.get_raw_frame()
			except SerialTimeout:
				continue
			except FileEnd:
				print(f"Processing time: {time.time()-self.start_time:.3f} s")
				break
			self.cur_time = time.time()
			self.data_raw[:] = self.data_tmp
			if not self.my_raw:
				self.filter()
				self.calibrate()
			self.data_out[:] = self.data_tmp
			self.post_action()

	def warm_up(self):
		print("Warming up processing...")
		begin = time.time()
		while time.time() - begin < self.WARM_UP:
			try:
				self.get_raw_frame()
			except SerialTimeout:
				pass

	def run_org(self):
		if self.WARM_UP > 0:
			self.warm_up()

		self.start_time = time.time()
		self.reset()
		self.print_proc()

		if not self.my_raw:
			self.prepare_spatial()
			self.prepare_temporal()
			self.prepare_cali()
		self.loop_proc()

	def run(self):
		if self.WARM_UP > 0:
			self.warm_up()

		self.start_time = time.time()
		self.reset()


		def gen_pressure():
			while True:
				self.get_raw_frame()
				yield self.data_tmp

		def gen_imu():
			while True:
				self.get_raw_frame()
				yield self.data_imu

		self.handler_pressure.prepare(gen_pressure())
		self.handler_imu.prepare(gen_imu())

		print("Running processing...")
		while True:
			## check signals from the other process
			if self.pipe_conn is not None:
				if self.pipe_conn.poll():
					msg = self.pipe_conn.recv()
					# print(f"msg={msg}")
					flag = msg[0]
					if flag == FLAG.FLAG_STOP:
						break
					if flag in (FLAG.FLAG_REC_DATA, FLAG.FLAG_REC_RAW):
						self.record_raw = True if flag == FLAG.FLAG_REC_RAW else True
						filename = msg[1]
						if filename == "":
							if flag == FLAG.FLAG_REC_RAW:
								filename = datetime.now().strftime(self.FILENAME_TEMPLATE_RAW)
							else:
								filename = datetime.now().strftime(self.FILENAME_TEMPLATE)
						try:
							with open(filename, 'a') as fout:
								pass
							if self.filename is not None:
								print(f"stop recording:   {self.filename}")
							self.filename = filename
							print(f"recording to:     {self.filename}")
							self.pipe_conn.send((FLAG.FLAG_REC_RET_SUCCESS,self.filename))
						except:
							print(f"failed to record: {self.filename}")
							self.pipe_conn.send((FLAG.FLAG_REC_RET_FAIL,))

					elif flag == FLAG.FLAG_REC_STOP:
						if self.filename is not None:
							print(f"stop recording:   {self.filename}")
						self.filename = None
						self.filename_id = 0
					elif flag == FLAG.FLAG_REC_BREAK:
						self.filename_id += 1

			try:
				self.get_raw_frame()
			except SerialTimeout:
				continue
			except FileEnd:
				print(f"Processing time: {time.time()-self.start_time:.3f} s")
				break
			self.cur_time = time.time()

			self.handler_pressure.handle(self.data_tmp, self.data_inter)
			self.handler_imu.handle(self.data_imu)

			self.data_raw[:] = self.data_inter
			self.data_out[:] = self.data_tmp
			self.post_action()

		self.handler_pressure.final()
		self.handler_imu.final()


if __name__ == '__main__':
	my_setter = DataSetterSerial(16*16, 500000, 'COM4')
	my_proc = Proc(16, my_setter)
	# my_proc.run()
