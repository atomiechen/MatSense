from collections import deque
import time
import matplotlib.pyplot as plt
from matplotlib import animation
from matplotlib.offsetbox import AnchoredText
import sys

from .player import Player


class Player1D(Player):

	backend = "matplotlib"

	## channels: number of data channels
	## timespan: visible time span, in seconds
	## ytop & ybottom: y-axis range, auto calculated by Matplotlib if not set
	## fps: frame rate, in frames per second
	## show_value: show value on top or not
	def __init__(self, channels=1, timespan=5, ytop=None, ybottom=None, show_value=True, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.channels = channels
		self.timespan = timespan
		self.ytop = ytop
		self.ybottom = ybottom
		self.show_value = show_value

		## data
		self.x = deque([])
		self.y = []
		for i in range(self.channels):
			self.y.append(deque([]))
		self.cur_x = 0

		## visualization
		self.fig = plt.figure()
		self.ax = self.fig.add_subplot(1,1,1)

		## timestamps
		self.start_time = None
		self.cur_time = None
		self.pause_time = None

	def _draw(self, data):
		if self.start_time is None:
			self.start_time = time.time()
			self.cur_time = self.start_time
		else:
			self.cur_time = time.time()

		self.cur_x = self.cur_time - self.start_time
		self.x.append(self.cur_x)
		try:
			for i in range(self.channels):
				self.y[i].append(data[i])
		except:
			self.y[0].append(data)

		if self.cur_x - self.x[0] > self.timespan:
			self.x.popleft()
			for i in range(self.channels):
				self.y[i].popleft()

		self.ax.clear()
		for i in range(self.channels):
			self.ax.plot(self.x, self.y[i])
		self.ax.set_xlim(left=max(-0.1, self.cur_x-self.timespan), right=self.cur_x+self.timespan*0.3)
		if self.ytop is not None:
			self.ax.set_ylim(top=self.ytop)
		if self.ybottom is not None:
			self.ax.set_ylim(bottom=self.ybottom)

		if self.show_value:
			value_str = f"Value: "
			try:
				value_str += ", ".join([str(data[i]) for i in range(self.channels)])
			except:
				value_str += f"{data}"

			plt.text(0.01, 1.02, value_str, transform=plt.gca().transAxes)
			# self.ax.add_artist(
			# 	AnchoredText(
			# 		value_str, loc='lower left', pad=0.4, borderpad=0,
			# 		bbox_to_anchor=(0., 1.), 
			# 		bbox_transform=plt.gca().transAxes, 
			# 		prop=dict(size=10), frameon=False))


	def _start(self):
		super()._start()
		plt.show()

	def _close(self):
		super()._close()
		plt.close()

	def toggle_pause(self, *args, **kwargs):
		self.pause ^= True
		## make sure the curve is continuous
		if self.pause:
			self.pause_time = time.time()
		else:
			self.start_time += time.time() - self.pause_time

	def _prepare_stream(self):
		self.fig.canvas.mpl_connect('key_press_event', self.on_key_stream)
		timeout = 1000 / self.fps
		self.ani = animation.FuncAnimation(self.fig, self.update_stream, interval=timeout)

	def on_key_stream(self, event):
		sys.stdout.flush()
		if event.key == ' ':
			self.toggle_pause()
		elif event.key == 'q':
			self._close()


if __name__ == '__main__':
	import random
	def gen_random():
		while True:
			yield random.random(), random.random()

	my_generator = gen_random()
	my_player = Player1D(generator=my_generator, channels=2, timespan=10, ybottom=-0.1, 
						ytop=1.1, show_value=True)
	my_player.run_stream()

