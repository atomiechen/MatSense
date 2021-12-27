import numpy as np
from collections import deque
import os

class BlobParser:

	"""parse blob(s) from 2D data

	Use positional arguments to set N; use keyword arguments to set 
	other parameters.

	Note:
		The parsed out values are relative to threshold, and will be 0
		if below the threshold.
	
	Attributes:
		N (int): square array side size
		threshold (float): threshold to detect blobs
		total (int): total blobs to detect each frame
	
	"""
	
	def __init__(self, N, **kwargs):
		"""constructor
		
		Args:
			N (int): square array side size
			**kwargs: keyword arguments passed to config()
		"""
		self.n = N
		## keyword arguments
		self.threshold = 0.1  ## threshold to detect blobs
		self.total = 3  ## total blobs to detect each frame
		self.normalize = True  ## normalize parsed coordinates
		self.special = False  ## special check for certain hardwares
		self.config(**kwargs)

		self.data2d = np.zeros([self.n[0], self.n[1]], dtype=float)
		self.flag2d = np.zeros([self.n[0], self.n[1]], dtype=int)
		self.dataout = np.zeros([self.n[0], self.n[1]], dtype=float)
		self.queue = deque()
		self.weighted_r = 0
		self.weighted_c = 0
		self.parsed_value = 0
		self.centers = []
		self.values = []
		self.blob_cnt = 0  ## total parsed blobs
		self.blob_idx = -1  ## selected blob ID

	def config(self, *, threshold=None, total=None, normalize=None, special=None):
		if threshold is not None:
			self.threshold = threshold
		if total is not None:
			self.total = total
		if normalize is not None:
			self.normalize = normalize
		if special is not None:
			self.special = special

	def transform(self, data, **kwargs):
		"""transform data to that only have a blob filtered out
		
		Args:
			data (array): array of size N × N
			**kwargs: keyword arguments passed to config()
		
		Returns:
			numpy.ndarray: transformed data
		"""
		self.parse(data, **kwargs)
		self.dataout[:] = 0
		if self.blob_idx >= 0:
			indices = (self.flag2d == self.blob_idx) & (data > self.threshold)
			self.dataout[indices] = data[indices] - self.threshold
		return self.dataout

	def parse(self, data, **kwargs):
		"""parse data and get intended points
		
		Args:
			data (array): array of size N × N
			**kwargs: keyword arguments passed to config()
		
		Returns:
			tuple: 3-element tuple containing:
		
			**row**: parsed weighted row index, normalized if set
		
			**col**: parsed weighted column index, normalized if set
		
			**val**: parsed value, 0 means no blob detected
		"""
		self.config(**kwargs)
		threshold = self.threshold
		total = self.total

		np.copyto(self.data2d, data)
		self.flag2d[:] = -1
		self.blob_cnt = 0
		control = threshold
		cal_threshold = threshold * 0.5
		while total > 0:
			max_idx = np.argmax(self.data2d)
			max_r, max_c = np.unravel_index(max_idx, self.data2d.shape)
			max_value = self.data2d[max_r, max_c]
			if max_value > max(control, threshold):
				self.blob_cnt += 1
				total -= 1
				control = max_value * 0.5
				blob_idx = self.blob_cnt - 1
				result = self.flood(max_r, max_c, cal_threshold, control, blob_idx)
				modified = max_value - threshold  # modified > 0
				if len(self.centers) < self.blob_cnt:
					self.centers.append(result)
					self.values.append(modified)
				else:
					self.centers[blob_idx] = result
					self.values[blob_idx] = modified
			else:
				break
		row, col, val = self.filter()
		if self.normalize:
			return row/(self.n[0]-1), col/(self.n[1]-1), val
		else:
			return row, col, val

	def gen_wrapper(self, generator, **kwargs):
		"""generator wrapper to generate blob-parsed data
		
		Args:
			generator (GeneratorType): generator of arrays of size N × N
			**kwargs: keyword arguments passed to config()
		
		Yields:
			numpy.ndarray: transformed data
		"""
		for data in generator:
			yield self.transform(data, **kwargs)

	def gen_points(self, generator, **kwargs):
		"""generator of parsed points
		
		Args:
			generator (GeneratorType): generator of arrays of size N × N
			**kwargs: keyword arguments passed to config()
		
		Yields:
			tuple: 3-element tuple containing:
		
			**row**: parsed weighted row index, normalized if set
		
			**col**: parsed weighted column index, normalized if set
		
			**val**: parsed value, 0 means no blob detected
		"""
		for data in generator:
			yield self.parse(data, **kwargs)

	def check_pos(self, row, col, threshold, control, max_gradient, cur_value, blob_idx):
		if row < 0 or row >= self.n[0] or col < 0 or col >= self.n[1]:
			return False, 0
		if self.flag2d[row][col] != -1:
			return False, 0
		val = self.data2d[row][col]
		cur_gradient = cur_value - val
		if val >= threshold:
			self.queue.append((row, col))
			self.flag2d[row][col] = blob_idx
			return True, cur_gradient
		# if val >= 0.5 * threshold and cur_gradient >= max_gradient:
		# 	self.queue.append((row, col))
		# 	self.flag2d[row][col] = blob_idx
		# 	return True, cur_gradient
		return False, -1

	def flood(self, row, col, threshold, control, blob_idx):
		r_sum = 0
		c_sum = 0
		w_sum = 0
		max_gradient = 0.01 * 15 / (max(self.n[0],self.n[1])-1)
		# max_gradient = 0
		self.queue.clear()
		self.queue.append((row, col))
		self.flag2d[row][col] = blob_idx
		while self.queue:
			tmp_r, tmp_c = self.queue.popleft()
			cur_value = self.data2d[tmp_r][tmp_c]
			self.data2d[tmp_r][tmp_c] = threshold - 1
			# self.flag2d[tmp_r][tmp_c] = blob_idx
			if cur_value >= control:
				r_sum += cur_value * tmp_r
				c_sum += cur_value * tmp_c
				w_sum += cur_value

			ret1 = self.check_pos(tmp_r, tmp_c-1, threshold, control, max_gradient, cur_value, blob_idx)
			ret2 = self.check_pos(tmp_r, tmp_c+1, threshold, control, max_gradient, cur_value, blob_idx)
			ret3 = self.check_pos(tmp_r-1, tmp_c, threshold, control, max_gradient, cur_value, blob_idx)
			ret4 = self.check_pos(tmp_r+1, tmp_c, threshold, control, max_gradient, cur_value, blob_idx)

		if w_sum > 0:
			return r_sum / w_sum, c_sum / w_sum
		else:
			raise Exception("w_sum <= 0, Unknown error!")

	def filter(self):
		blob_idx = -1  # idx starts from 0
		if self.blob_cnt >= 1:
			if self.special:
				blob_idx = self.special_check()
			else:
				blob_idx = 0

		self.blob_idx = blob_idx
		if blob_idx >= 0:
			self.parsed_value = self.values[blob_idx]
			self.weighted_r = self.centers[blob_idx][0]
			self.weighted_c = self.centers[blob_idx][1]
		else:
			self.parsed_value = 0
		return self.weighted_r, self.weighted_c, self.parsed_value

	def special_check(self):
		## special case to exclude due to hardware problem
		blob_idx = 0
		if self.centers[0][1] <= 0.06 * (self.n[1] - 1):
			blob_idx = -1
			# print(f"sepcial case {self.centers[0][1]} {self.blob_cnt}")
			if self.blob_cnt >= 2:
				for i in range(1, self.blob_cnt):
					if self.centers[i][1] >= 0.93 * (self.n[1] - 1):
						blob_idx = i
						# print(f"  find correct blob {i} {self.centers[0][1]} {self.centers[i][1]} {self.blob_cnt}")
						break
					# else:
						# print(f" no {i} {self.centers[0][1]} {self.centers[i][1]} {self.blob_cnt}")
		# else:
			# print(f"ordinary {self.centers[0][1]} {self.blob_cnt}")
		return blob_idx

	def print_result(self):
		point_r = int(round(self.weighted_r))
		point_c = int(round(self.weighted_c))
		os.system("clear")
		# os.system("cls")
		for row in range(self.n[0]-1, -1, -1):
			for col in range(self.n[1]):
				flag = self.flag2d[row][col]
				if flag == 0:
					print("－", end='')
				else:
					if row == point_r and col == point_c:
						print("〇", end='')
					elif flag == 1:
						print("１", end='')
					elif flag == 2:
						print("２", end='')
					elif flag == 3:
						print("３", end='')
					elif flag == 4:
						print("４", end='')
					elif flag == 5:
						print("５", end='')
					else:
						print("＋", end='')
			print()
		print(self.weighted_r, self.weighted_c)
