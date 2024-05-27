from enum import Enum
from math import exp, hypot, pi, sin
import numpy as np
from collections import deque
from ..tools import check_shape


class FILTER_SPATIAL(Enum):
	NONE = "none"  # no spatial filter
	IDEAL = "ideal"  # ideal kernel
	BUTTERWORTH = "butterworth"  # butterworth kernel
	GAUSSIAN = "gaussian"  # gaussian kernel


class FILTER_TEMPORAL(Enum):
	NONE = "none"  # no temporal filter
	MA = "moving average"  # moving average
	RW = "rectangular window"  # rectangular window filter (sinc)


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
	my_resi_opposite = True
	my_resi_delta = True # count pressure as delta_R / R0
	V0 = 255
	R0_RECI = 1  ## a constant to multiply the value
	R0_START = 0 ## start resistance

	## process parameters
	my_SF_D0 = 3.5
	my_BUTTER_ORDER = 2
	my_LP_SIZE = 15
	my_LP_W = 0.04
	my_INIT_CALI_FRAMES = 200
	my_WIN_SIZE = 0
	my_WIN_BUFFER_SIZE = 5
	my_CALI_THRESHOLD = 3

	def __init__(self, **kwargs):
		self.mask = None

		## output intermediate result
		## 0: convert voltage to reciprocal resistance
		## 1: convert & spatial filter
		## 2: convert & spatial filter & temporal filter
		self.intermediate = 0
		self.data_inter = None

		self.config(**kwargs)
		self.print_proc()

	def config(self, *, n, raw=None, V0=None, R0_RECI=None, convert=None, 
		mask=None, filter_spatial=None, filter_spatial_cutoff=None, 
		butterworth_order=None, filter_temporal=None, 
		filter_temporal_size=None, rw_cutoff=None, cali_frames=None, 
		cali_win_size=None, cali_win_buffer_size=None,
		intermediate=None, 
		resi_opposite=None, resi_delta=None, cali_threshold=None,
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
		if resi_opposite is not None:
			self.my_resi_opposite = resi_opposite
		if resi_delta is not None:
			self.my_resi_delta = resi_delta
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
		if cali_threshold is not None:
			self.my_CALI_THRESHOLD = cali_threshold
		if cali_win_buffer_size is not None:
			self.my_WIN_BUFFER_SIZE = cali_win_buffer_size

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
	def calOppo_numpy_array(np_array, v0, r0_reci):
		np_array[np_array >= v0] = 0
		np_array /= (v0 - np_array)
		np_array *= r0_reci
		np_array[np_array != 0] = -1 / np_array[np_array != 0]

	@staticmethod
	def getNextIndex(idx, size):
		return (idx+1) if idx != (size-1) else 0

	def calDelta_numpy_array(self, np_array, v0, r0_reci):
		np_array[np_array >= v0] = 0
		np_array /= (v0 - np_array)
		np_array *= r0_reci
		np_array[np_array != 0] = 1 / np_array[np_array != 0]
		# print(np_array)
		np_array[np_array!=0] = abs(np_array[np_array!=0] - self.R0_START[np_array!=0]) / self.R0_START[np_array!=0]
		np_array *= 10
		# print(np_array)

	def handle_raw_frame(self, data):
		self.data_tmp = data
		self.data_reshape = self.data_tmp.reshape(self.n[0], self.n[1])
		if self.mask is not None:
			self.data_reshape *= self.mask
		if self.my_convert:
			# for i in range(self.total):
			# 	self.data_tmp[i] = self.calReciprocalResistance(self.data_tmp[i], self.V0, self.R0_RECI)
			if self.my_resi_opposite:
				self.calOppo_numpy_array(self.data_tmp, self.V0, self.R0_RECI)
			elif self.my_resi_delta:
				self.calDelta_numpy_array(self.data_tmp, self.V0, self.R0_RECI)
			else:
				self.calReci_numpy_array(self.data_tmp, self.V0, self.R0_RECI)

	def prepare(self, generator):
		self.generator = generator
		if not self.my_raw:
			self.cal_start_R0() # called if my_resi_delta is True
			self.prepare_spatial()
			self.prepare_temporal()
			self.prepare_cali() # called if my_INIT_CALI_FRAMES > 0 and my_resi_delta is False

	def handle(self, data, data_inter=None):
		self.handle_raw_frame(data)
		self.data_inter = data_inter

		## output intermediate result
		if self.data_inter is not None and self.intermediate == 0:
			self.data_inter[:] = self.data_tmp[:]

		if not self.my_raw:
			self.filter()
			if not self.my_resi_delta:
				self.calibrate()
		elif self.data_inter is not None and self.intermediate != 0:
			## output intermediate result, making data_inter not blank
			self.data_inter[:] = self.data_tmp[:]

	def prepare_cali(self):
		if self.my_INIT_CALI_FRAMES <= 0 or self.my_resi_delta:
			return

		print("Initiating calibration...")
		self.data_zero = np.zeros(self.total, dtype=float)
		self.data_win = np.zeros((self.my_WIN_SIZE, self.total), dtype=float)
		self.win_frame_idx = 0
		self.data_win_buffer = deque(maxlen=self.my_WIN_BUFFER_SIZE)
		self.win_buffer_frame_idx = 0
		self.need_to_clean_buffer = False # if True then clean the buffer at next full time
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
		for _ in range(self.my_WIN_BUFFER_SIZE):
			self.data_win_buffer.append(self.data_zero)
        ## save data_min in last WIN_SIZE frames
		# self.data_min = deque(maxlen=self.my_WIN_SIZE)
		# self.data_min.append((self.data_zero.copy(), self.win_frame_idx))
		self.win_frame_idx = self.getNextIndex(self.win_frame_idx, self.my_WIN_SIZE)
		self.win_buffer_frame_idx = self.getNextIndex(self.win_buffer_frame_idx, self.my_WIN_BUFFER_SIZE)

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

			## use average number as data_zero
			# self.data_zero += (stored - self.data_win[self.win_frame_idx]) / self.my_WIN_SIZE

			## use min number as data_zero
			# if (self.data_min[0][1] == self.win_frame_idx):
			# 	self.data_min.popleft()
			# self.data_zero = self.data_min[0][0]
			# while (self.data_min[-1][0].sum() > stored.sum()):
			# 	self.data_min.pop()
			# 	if (len(self.data_min) == 0):
			# 		break
			# self.data_min.append((stored, self.win_frame_idx))

			## use average number as data_zero, but delete the odd ones
			add_to_data_zero = True
			for id, stored_data in enumerate(stored):
				data_at_one_point = stored_data - self.data_zero[id]
				if (data_at_one_point > self.my_CALI_THRESHOLD):
					# pressure over data_zero + threshold
					add_to_data_zero = False
					self.need_to_clean_buffer = True
					if len(self.data_win_buffer) == self.my_WIN_BUFFER_SIZE:
						self.data_win_buffer.clear()
					break
			if (add_to_data_zero):
				if len(self.data_win_buffer) < self.my_WIN_BUFFER_SIZE:
					self.data_win_buffer.append(stored)
				else:
					if self.need_to_clean_buffer:
						self.data_win_buffer.clear()
						self.need_to_clean_buffer = False
						self.data_win_buffer.append(stored)
					else:
						cur_data = self.data_win_buffer.popleft()
						self.data_win_buffer.append(stored)
						## store in data_win
						self.data_zero += (cur_data - self.data_win[self.win_frame_idx]) / self.my_WIN_SIZE
						self.data_win[self.win_frame_idx] = cur_data
						self.win_frame_idx = self.getNextIndex(self.win_frame_idx, self.my_WIN_SIZE)

			# ## store in data_win
			# self.data_win[self.win_frame_idx] = stored
			# ## update frame index
			# self.win_frame_idx = self.getNextIndex(self.win_frame_idx, self.my_WIN_SIZE)

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

		print("Initiating temporal filter...")
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

	def cal_start_R0(self):
		if not self.my_resi_delta:
			return
		# calcualte average start R0
		frame_cnt = 0
		data = next(self.generator)
		r0 = np.zeros(data.shape)
		R0_AVE_TIMES = 10
		# ## accumulate data
		while frame_cnt < R0_AVE_TIMES: # use 10 frames to calculate
			data = next(self.generator)
			data = data.reshape(self.n[0], self.n[1])
			if self.mask is not None:
				data *= self.mask
			self.calOppo_numpy_array(data, self.V0, self.R0_RECI)
			r0 += -1 * data.flatten()
			frame_cnt += 1
		self.R0_START = r0 / R0_AVE_TIMES
		print("start R0: ", self.R0_START)

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
			print(f"  - Resistance mode: {'delta_R / R0' if self.my_resi_delta else ('-R' if self.my_resi_opposite else '1/R')}")
			print(f"  - Spatial filter: {self.my_filter_spatial.value}")
			for value, key in arg_list_s.items():
				print(f"    {value}: {key}")
			print(f"  - Temporal filter: {self.my_filter_temporal.value}")
			for value, key in arg_list_t.items():
				print(f"    {value}: {key}")

			print(f"  - Calibration: {'No' if self.my_INIT_CALI_FRAMES == 0 or self.my_resi_delta else ''}")
			if self.my_INIT_CALI_FRAMES != 0 and not self.my_resi_delta:
				print(f"    Initializing frames:     {self.my_INIT_CALI_FRAMES}")
				if self.my_WIN_SIZE == 0:
					print("    Static calibration")
				else:
					print("    Dynamic calibration")
					print(f"    Calibration window size: {self.my_WIN_SIZE}")


class DataHandlerIMU(DataHandler):
	pass
