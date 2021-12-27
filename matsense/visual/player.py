"""
Visualize 3D data via a window player.

"""

from enum import IntEnum
try:
	import readline
except ImportError:
	pass
from numpy import reshape
from types import GeneratorType


class MODE(IntEnum):

	"""Pre-defined visualization modes.
	
	Attributes:
	    STREAM (int): constantly get stream data and visualize
	    INTERACTIVE (int): Description
	"""
	
	STREAM = 0
	INTERACTIVE = 1


class Player:
	backend = "None (should be altered by subclass)"  # backend used for visualization

	def __init__(self, *args, **kwargs):
		super().__init__()
		## variables for interactive playing
		self.cur_idx = 0  # current data slice index
		self.max_idx = 0  # max data slice index
		self.pause = True  # state of playing/pause
		self.started = False  # has started or not
		## keyword parameters
		self._generator = None
		self._dataset = None
		self._infoset = None
		self.step = 50
		self.fps = 200
		self.widgets = True  ## show widgets
		self.config(**kwargs)

	def config(self, *, generator=None, dataset=None, infoset=None, 
		step=None, fps=None, widgets=None, **kwargs):
		"""configure keyword parameters
		
		"""		
		if generator:
			self.generator = generator
		if dataset:
			self.dataset = dataset
		if infoset:
			self.infoset = infoset
		if step:
			self.step = step
		if fps:
			self.fps = fps
		if widgets is not None:
			self.widgets = widgets

	@property
	def generator(self):
		return self._generator
	
	@generator.setter
	def generator(self, value):
		if not isinstance(value, GeneratorType):
			raise Exception("generator must be GeneratorType!")
		else:
			self._generator = value

	@property
	def dataset(self):
		return self._dataset

	@dataset.setter
	def dataset(self, value):
		try:
			value[0]
		except:
			raise Exception("dataset must be indexable container!")
		self._dataset = value
		self.max_idx = len(self._dataset) - 1

	@property
	def infoset(self):
		return self._infoset

	@infoset.setter
	def infoset(self, value):
		try:
			value[0]
		except:
			raise Exception("infoset must be indexable container!")
		self._infoset = value

	@property
	def step(self):
		return self._step
	
	@step.setter
	def step(self, value):
		try:
			value = int(value)
		except:
			raise Exception("step must be an integer!")
		if value <= 0:
			raise Exception("step must be greater than 0!")
		self._step = value

	@property
	def fps(self):
		return self._fps

	@fps.setter
	def fps(self, value):
		if value <= 0:
			raise Exception("fps must be greater than 0!")
		self._fps = value
	
	
	def run(self, mode=MODE.STREAM, **kwargs):
		"""run player given a specific mode
		
		Args:
			mode (MODE, optional): player mode, either MODE.STREAM or 
				MODE.INTERACTIVE. Defaults to MODE.STREAM.
			**kwargs: keyword arguments passed to config() via 
				corresponding run_*() method
		
		Raises:
			NotImplementedError: when receiving unknown mode
		"""		
		if mode == MODE.STREAM:
			self.run_stream(**kwargs)
		elif mode == MODE.INTERACTIVE:
			self.run_interactive(**kwargs)
		else:
			raise NotImplementedError(f"run() with unknown mode {mode}")

	def run_stream(self, **kwargs):
		"""run the player in stream mode
		
		Args:
			**kwargs: keyword arguments passed to config()
		
		Raises:
			Exception: generator not set
		"""
		self.config(**kwargs)
		if not self.generator:
			raise Exception("generator not set")
		self.pause = False
		self.print_startup()
		self._prepare_stream()  ## need to be implemented in subclass
		self._start()

	def run_interactive(self, **kwargs):
		"""run the player in interactive mode
		
		Args:
			**kwargs: keyword arguments passed to config()
		
		Raises:
			Exception: dataset not set
		"""
		self.config(**kwargs)
		if not self.dataset:
			raise Exception("dataset not set")
		self.pause = True
		self.cur_idx = 0
		self.print_startup()
		self._prepare_interactive()  ## need to be implemented in subclass
		self.draw_slice()
		self._start()

	def print_startup(self):
		print(f"Visualization backend: {self.backend}")

	def draw_slice(self):
		data_raw = self.dataset[self.cur_idx]
		self._draw(data_raw)
		self.print_slice()

	def print_slice(self):
		try:
			info = f"{self.infoset[self.cur_idx]}"
		except:
			info = None
		print(f'cur_idx: {self.cur_idx+1}  {info}')

	def update_interactive(self, *args, **kwargs):
		if not self.pause:
			self.cur_idx += 1
			if self.cur_idx >= self.max_idx:
				self.cur_idx = self.max_idx
				self.pause = True
			self.draw_slice()

	def update_stream(self, *args, **kwargs):
		if not self.pause:
			try:
				data_raw = next(self.generator)
				self._draw(data_raw)	
			except StopIteration:
				self._close()

	def toggle_pause(self, *args, **kwargs):
		self.pause ^= True
		print("Paused" if self.pause else "Playing")

	def jump(self):
		if not self.pause:
			self.pause = True
			print("Paused")
		print(f"Jump to index X (int) such that 1 <= X <= {self.max_idx+1}")
		num_str = input(">> ")
		num_str = num_str.strip()
		try:
			num = int(num_str) - 1
			if num >= 0 and num <= self.max_idx:
				self.cur_idx = num
				self.draw_slice()
			else:
				print("invalid input!")
		except:
			print("drop input.")

	def forward(self, *args, **kwargs):
		self.cur_idx += self.step
		self.cur_idx = self.max_idx if self.cur_idx > self.max_idx else self.cur_idx
		self.draw_slice()
		print(f"Fast forward:  {self.step} frames")

	def backward(self, *args, **kwargs):
		self.cur_idx -= self.step
		self.cur_idx = 0 if self.cur_idx < 0 else self.cur_idx
		self.draw_slice()
		print(f"Fast backward: {self.step} frames")

	def oneforward(self, *args, **kwargs):
		self.cur_idx += 1
		self.cur_idx = self.max_idx if self.cur_idx > self.max_idx else self.cur_idx
		self.draw_slice()
		print("Next frame")

	def onebackward(self, *args, **kwargs):
		self.cur_idx -= 1
		self.cur_idx = 0 if self.cur_idx < 0 else self.cur_idx
		self.draw_slice()
		print("Previous frame")

	def gotofirst(self, *args, **kwargs):
		self.cur_idx = 0
		self.draw_slice()
		print("First frame")

	def gotolast(self, *args, **kwargs):
		self.cur_idx = self.max_idx
		self.pause = True
		self.draw_slice()
		print("Last frame")

	def _start(self):
		self.started = True
		"""start the visualization system, can be overridden
		"""

	def _close(self):
		self.started = False
		"""close the visualization system, can be overridden
		"""

	def _draw(self, data):
		"""draw the given data, should be overridden
		
		Args:
			data (array): 1-dimensional array of data
		
		Raises:
			NotImplementedError: Not implemented
		"""
		raise NotImplementedError("_draw()")

	def _prepare_stream(self):
		"""prepare steps before running in stream mode
		
		Raises:
			NotImplementedError: Not implemented
		"""
		raise NotImplementedError("_prepare_stream()")

	def _prepare_interactive(self):
		"""prepare steps before running in interactive mode
		
		Raises:
			NotImplementedError: Not implemented
		"""
		raise NotImplementedError("_prepare_interactive()")


class Player3D(Player):

	"""Base class of 3D player for data visualization

	Use positional arguments to set zlim and N; use keyword arguments to
	set other parameters.
	
	Attributes:
		zlim (int/float, optional): z-axis max value. Defaults to 3.
		N (int, optional): sensor side length. Defaults to 16.
		generator (GeneratorType, optional): generator to yield 
			data for stream mode. Defaults to None.
		dataset (indexable container, optional): data set for 
			interactive mode. Defaults to None.
		infoset (indexable container of str, optional): additional 
			information set for interactive mode, should have the 
			same size as dataset. Defaults to None.
		step (int, optional): fast forward/backward step for 
			interactive mode. Defaults to 50.
		fps (int/float, optional): frames per second when playing. 
			Defaults to 200.
	"""
	
	def __init__(self, zlim=3, N=16, *args, **kwargs):	
		"""constructor
		
		Args:
			zlim (int/float, optional): z-axis max value. Defaults to 3.
			N (int, optional): sensor side length. Defaults to 16.
			**kwargs: keyword arguments passed to config()
		"""		
		super().__init__(*args, **kwargs)
		self.zlim = zlim
		self.N = N

	@property
	def zlim(self):
		return self._zlim

	@zlim.setter
	def zlim(self, value):
		if value <= 0:
			raise Exception("zlim must be greater than 0!")
		else:
			self._zlim = value
	
	@property
	def N(self):
		return self._N
	
	@N.setter
	def N(self, value):
		if isinstance(value, int):
			value = [value, value]

		try:
			value[0], value[1]
			self._N = value
		except:
			raise Exception("invalid N type!")


if __name__ == '__main__':
	my_player = Player3D(3, N=1, dataset=[1,2,3])
	try:
		my_player.run(MODE.INTERACTIVE)
	except NotImplementedError as e:
		print(f"Not implemented: {e}")
