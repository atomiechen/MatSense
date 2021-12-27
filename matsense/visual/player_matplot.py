import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib.ticker import LinearLocator, FixedLocator, FormatStrFormatter
from mpl_toolkits.mplot3d import Axes3D
from matplotlib import animation
from matplotlib.offsetbox import AnchoredText
import mpl_toolkits.axes_grid1
import matplotlib.widgets
import sys

from .player import Player3D


class Player3DMatplot(Player3D):

	"""3D player using **matplotlib** backend.
	
	"""

	backend = "matplotlib"

	def __init__(self, *args, **kwargs):
		"""constructor
		
		Args:
			*args: positional arguments passed to base class.
			widgets (bool, optional): show the control widgets. Defaults
				to True.
			**kwargs: keyword arguments passed to base class.
		"""
		super().__init__(*args, **kwargs)
		### ref: https://stackoverflow.com/questions/5179589/continuous-3d-plotting-i-e-figure-update-using-python-matplotlib
		self.lowerCutoffLength = 1
		self.fig = plt.figure()
		## new API to set window title
		self.manager = plt.get_current_fig_manager()
		self.manager.set_window_title('3D data')
		self.ax = self.fig.add_subplot( 111, projection='3d' )
		self.ax.set_zlim3d( 0, self.zlim )

		rng1 = np.arange( 0, self.N[1], self.lowerCutoffLength )
		rng2 = np.arange( 0, self.N[0], self.lowerCutoffLength )
		self.X, self.Y = np.meshgrid(rng1, rng2)
		self.ax.w_zaxis.set_major_locator( LinearLocator( 10 ) )
		self.ax.w_zaxis.set_major_formatter( FormatStrFormatter( '%.03f' ) )
		## ref: https://matplotlib.org/stable/api/_as_gen/mpl_toolkits.mplot3d.axes3d.Axes3D.html#mpl_toolkits.mplot3d.axes3d.Axes3D.set_box_aspect
		self.ax.set_box_aspect((self.N[1], self.N[0], max(self.N[0], self.N[1])/4*3))

		## invert x axis
		self.ax.invert_xaxis()

		## rotate the camera
		self.ax.azim += 180  ## = 120

		self.scatter = False
		self.show_value = False
		self.config(**kwargs)

		heightR = np.zeros( self.X.shape )
		if self.scatter:
			self.X = self.X.reshape(-1)
			self.Y = self.Y.reshape(-1)
			heightR = heightR.reshape(-1)
			self.scatter_plot = self.ax.scatter(self.X, self.Y, heightR, marker='o')
		else:
			self.surf = self.ax.plot_surface( 
				self.X, self.Y, heightR, rstride=1, cstride=1, cmap=cm.YlOrRd,
				linewidth=0, antialiased=True )

		## for showing value
		if self.show_value:
			value_str = f"Area: 0"
			self.text2d = self.ax.text2D(0.01, 1.02, value_str, transform=self.ax.transAxes)

		print(f"show_value: {self.show_value}")

	def config(self, *, scatter=None, show_value=None, **kwargs):
		super().config(**kwargs)
		if scatter is not None:
			self.scatter = scatter
		if show_value is not None:
			self.show_value = show_value

	def _start(self):
		super()._start()
		plt.show()

	def _close(self):
		super()._close()
		plt.close()

	def _draw(self, data):
		data = np.array(data)
		if self.scatter:
			self.scatter_plot._offsets3d = (self.X, self.Y, data.reshape(-1))
		else:
			self.surf.remove()
			self.surf = self.ax.plot_surface( 
				self.X, self.Y, data, rstride=1, cstride=1, cmap=cm.YlOrRd,
				linewidth=0, antialiased=True )

		if self.show_value:
			area = np.sum(data>0)
			value_str = f"Area: {area}"
			self.text2d.set_text(value_str)

	def _prepare_stream(self):
		self.fig.canvas.mpl_connect('key_press_event', self.on_key_stream)
		timeout = 1000 / self.fps
		self.ani = animation.FuncAnimation(self.fig, self.update_stream, interval=timeout)

	def _prepare_interactive(self):
		if self.widgets:
			self.setup_widgets()
		self.fig.canvas.mpl_connect('key_press_event', self.on_key_interactive)
		timeout = 1000 / self.fps
		self.ani = animation.FuncAnimation(self.fig, self.update_interactive, interval=timeout)

	def on_key_stream(self, event):
		sys.stdout.flush()
		if event.key == ' ':
			self.toggle_pause()
		elif event.key == 'q':
			self._close()

	def on_key_interactive(self, event):
		sys.stdout.flush()
		if event.key == ' ':
			self.toggle_pause()
		elif event.key == 'q':
			self._close()
		elif event.key == 'j':
			self.jump()
		else:
			if event.key == 'right':
				self.forward()
			elif event.key == 'left':
				self.backward()
			elif event.key == '.':
				self.oneforward()
			elif event.key == ',':
				self.onebackward()
			elif event.key == 'a':
				self.gotofirst()
			elif event.key == 'e':
				self.gotolast()

	## ref: https://stackoverflow.com/a/46327978/11854304
	def setup_widgets(self):
		## [left, bottom, width, height] in fractions of figure
		playerax = self.fig.add_axes([0.15, 0.90, 0.7, 0.04])
		divider = mpl_toolkits.axes_grid1.make_axes_locatable(playerax)
		bax = divider.append_axes("right", size="80%", pad=0.05)
		sax = divider.append_axes("right", size="80%", pad=0.05)
		fax = divider.append_axes("right", size="80%", pad=0.05)
		ofax = divider.append_axes("right", size="100%", pad=0.05)
		sliderax = divider.append_axes("right", size="800%", pad=0.07)
		self.button_back = matplotlib.widgets.Button(playerax, label='$\u29CF$')
		self.button_oneback = matplotlib.widgets.Button(bax, label='$\u25C0$')
		self.button_stop = matplotlib.widgets.Button(sax, label='$\u25A0$')
		self.button_oneforward = matplotlib.widgets.Button(fax, label='$\u25B6$')
		self.button_forward = matplotlib.widgets.Button(ofax, label='$\u29D0$')
		self.button_oneback.on_clicked(self.onebackward)
		self.button_back.on_clicked(self.backward)
		self.button_stop.on_clicked(self.toggle_pause)
		self.button_forward.on_clicked(self.forward)
		self.button_oneforward.on_clicked(self.oneforward)
		self.slider = matplotlib.widgets.Slider(sliderax, '', 0, 
												self.max_idx)
		self.slider.valtext.set_text(f"{self.cur_idx+1} / {self.max_idx+1}")
		self.slider.on_changed(self.slider_set_idx)

	def slider_set_idx(self, value):
		self.cur_idx = int(self.slider.val)
		self.slider.valtext.set_text(f"{self.cur_idx+1} / {self.max_idx+1}")
		super().draw_slice()

	## override
	def draw_slice(self):
		if self.widgets and self.started:
			self.slider.set_val(self.cur_idx)
		else:
			super().draw_slice()


if __name__ == '__main__':
	import numpy as np
	def process_recv_serial_test(data_matrix):
		data_tmp = []
		cnt = 0
		check_size = 100
		while True:
			cnt += 1
			if cnt % check_size == 0:
				cnt = 0
				data_tmp = np.random.random(256)
				# 直接循环拷贝值，不需要加锁
				for i, item in enumerate(data_tmp):
					data_matrix[i] = item

	from multiprocessing import Process
	from multiprocessing import Array  # 共享内存
	from . import gen, MODE

	arr = Array('d', 256)
	p = Process(target=process_recv_serial_test, args=(arr,))
	p.start()
	my_player = Player3DMatplot(zlim=3)
	## you can use either
	my_player.run_stream(fps=100, generator=gen(arr))
	## or
	# my_player.run(MODE.STREAM, fps=100, generator=gen(arr))
	p.join()
