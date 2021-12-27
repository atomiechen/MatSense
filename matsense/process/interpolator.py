import numpy as np
from scipy import ndimage

class Interpolator:

	"""interpolate input 2D data

	Use positional arguments to set N; use keyword arguments to set 
	other parameters.

	Note:
		The interpolator will do nothing if the input and ouput sizes
		are the same.
	
	Attributes:
		N (int): interpolated to size N × N
		order (int, optional): interpolation order. Defaults to 3.
	"""
	
	def __init__(self, N, **kwargs):
		"""constructor
		
		Args:
			N (int): interpolated to size N × N
			**kwargs: keyword arguments passed to config()
		"""
		self.n = N
		## keyword arguments
		self.order = 3
		self.config(**kwargs)

		self.output = np.zeros(self.n, dtype=float)

	def config(self, *, order=None):
		if order is not None:
			self.order = order

	def interpolate(self, data, **kwargs):
		"""interpolate given data
		
		Args:
			data (array): 2D square array to interpolate
			**kwargs: keyword arguments passed to config()
		
		Returns:
			array: interpolated 2D square array, or the original data if
			the size does not change
		
		Raises:
			Exception: not a square data array
		"""
		self.config(**kwargs)
		shape = np.shape(data)
		# if shape[0] != shape[1]:
			# raise Exception(f"Not a square array! get {shape[0]} * {shape[1]} instead")
		ratio = [self.n[0]/shape[0], self.n[1]/shape[1]]
		if ratio == 1:  # do nothing
			return data
		else:  # zoom
			ndimage.zoom(data, zoom=ratio, output=self.output, order=self.order)
			return self.output

	def gen_wrapper(self, generator, **kwargs):
		"""generator wrapper to generate interpolated data
		
		Args:
			generator (GeneratorType): generator of 2D square array
			**kwargs: keyword arguments passed to config()
		
		Yields:
			numpy.ndarray: interpolated 2D square array
		"""
		for data in generator:
			yield self.interpolate(data, **kwargs)
