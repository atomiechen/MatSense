import time


class PressureSelector:
	QUICK_RELEASE = 0
	DWELL = 1
	TIME_QR = 0.3
	TIME_DW = 1

	def __init__(self, levels, mode="quickrelease", timeout=None):
		self.levels = levels
		if mode == "quickrelease":
			self.mode = self.QUICK_RELEASE
			self.timeout = self.TIME_QR
		elif mode == "dwell":
			self.mode = self.DWELL
			self.timeout = self.TIME_DW
		else:
			raise Exception(f"Unknown selection mode string: {mode}")
		if timeout is not None:
			self.timeout = timeout

		self.cur_time = 0  # current timestamp
		self.cur_region = 0  # current region
		self.last_region = 0  # last region
		self.lock_region = 0  # control selection output
		self.N = len(levels) + 1  # total level number
		self.time_table = [0] * self.N  # recording each level's time
		for idx, _ in enumerate(self.time_table):
			self.time_table[idx] = [0, 0]

	def get_selection(self, val):
		self.proc_region(val)
		if self.mode == self.QUICK_RELEASE:
			return self.check_quick_release(val), self.cur_region
		elif self.mode == self.DWELL:
			return self.check_dwell(val), self.cur_region
		else:
			raise Exception(f"Unknown selection mode code: {self.mode}")

	def proc_region(self, val):
		self.cur_time = time.time()
		self.last_region = self.cur_region
		for idx, item in enumerate(self.levels):
			if val <= item:
				self.cur_region = idx
				break
		if val > self.levels[-1]:
			self.cur_region = self.N - 1

		if self.cur_region != self.last_region:
			self.time_table[self.last_region][1] = self.cur_time  ## exit time
			self.time_table[self.cur_region][0] = self.cur_time  ## enter time

	def check_quick_release(self, val):
		ret = -1
		if self.cur_region == 0 and self.lock_region != 0:
			for i in range(self.N-1, 0, -1):
				## region 0 enter time - region i exit time
				duration = self.time_table[0][0] - self.time_table[i][1]
				if duration <= self.timeout:
					ret = i
					self.lock_region = 0  # lock region
					break
		elif self.cur_region != 0:
			self.lock_region = self.cur_region  # clear lock
		return ret

	def check_dwell(self, val):
		ret = -1
		if self.cur_region != self.lock_region:
			self.lock_region = 0  # clear lock
			## current time - current region enter time
			duration = self.cur_time - self.time_table[self.cur_region][0]
			if duration >= self.timeout:
				ret = self.cur_region
				self.lock_region = self.cur_region  # lock region
		return ret
