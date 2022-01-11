import numpy as np
import time
from datetime import datetime

from .data_handler import DataHandlerIMU, DataHandlerPressure
from .flag import FLAG
from .exception import SerialTimeout, FileEnd
from ..tools import check_shape
from ..filemanager import write_line


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

	def warm_up(self):
		print("Warming up processing...")
		begin = time.time()
		while time.time() - begin < self.WARM_UP:
			try:
				self.get_raw_frame()
			except SerialTimeout:
				pass

	def run(self):
		ret = None

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
					if flag == FLAG.FLAG_RESTART:
						config_new = msg[1]
						## restart with new config
						ret = (1, config_new)
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
							with open(filename, 'a', encoding='utf-8') as fout:
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

		return ret
