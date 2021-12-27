import numpy as np

from .blob_parser import BlobParser
from .interpolator import Interpolator
from ..tools import check_shape


class Processor:
	def __init__(self, interp=16, **kwargs):
		self.interp = check_shape(interp)

		self.blob = True  # enable blob detection by default
		self.threshold = 0.1
		self.total = 3
		self.order = 3
		self.normalize = True  # normalize point coordinates to [0, 1]
		self.special = False  ## special check for certain hardwares
		self.config(**kwargs)

		self.interpolator = Interpolator(self.interp)
		self.blobparser = BlobParser(self.interp)
	
	def config(self, *, blob=None, threshold=None, total=None, 
				order=None, normalize=None, special=None):
		if blob is not None:
			self.blob = blob
		if threshold is not None:
			self.threshold = threshold
		if total is not None:
			self.total = total
		if order is not None:
			self.order = order
		if normalize is not None:
			self.normalize = normalize
		if special is not None:
			self.special = special

	def gen_wrapper(self, generator, **kwargs):
		self.config(**kwargs)
		generator = self.interpolator.gen_wrapper(generator, order=self.order)
		if self.blob:
			generator = self.blobparser.gen_wrapper(generator, 
							threshold=self.threshold, total=self.total, 
							special=self.special)
		return generator

	def gen_points(self, generator, **kwargs):
		self.config(**kwargs)
		if not self.blob:
			raise Exception("Must set blob=True")
		generator = self.interpolator.gen_wrapper(generator, order=self.order)
		generator = self.blobparser.gen_points(generator, 
						threshold=self.threshold, total=self.total, 
						normalize=self.normalize, special=self.special)
		return generator

	def transform(self, data, reshape=False, **kwargs):
		self.config(**kwargs)
		if reshape:
			size = np.shape(data)[0]
			side = int(size**0.5)
			data = np.reshape(data, (side, side))
		data_out = self.interpolator.interpolate(data, order=self.order)
		if self.blob:
			data_out = self.blobparser.transform(data_out,
						threshold=self.threshold, total=self.total,
						special=self.special)
		if reshape:
			data_out = np.reshape(data_out, self.interp[0] * self.interp[1])
		return data_out

	def parse(self, data, reshape=False, **kwargs):
		self.config(**kwargs)
		if not self.blob:
			raise Exception("Must set blob=True")
		if reshape:
			size = np.shape(data)[0]
			side = int(size**0.5)
			data = np.reshape(data, (side, side))
		data_out = self.interpolator.interpolate(data, order=self.order)
		return self.blobparser.parse(data_out, threshold=self.threshold, 
				total=self.total, normalize=self.normalize, 
				special=self.special)

	def print_info(self):
		print("Processor details:")
		msg_interp = "{0} × {1}".format(self.interp[0], self.interp[1])
		print(f"  Interpolation:          {msg_interp}")
		if self.blob:
			print(f"  Blob filtered out:      threshold = {self.threshold}")
			print(f"  Normalized coordinates: {self.normalize}")
		else:
			print(f"  No blob filtered out")
