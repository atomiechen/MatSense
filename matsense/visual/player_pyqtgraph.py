import sys
from threading import Thread
import pyqtgraph as pg
import pyqtgraph.opengl as gl
import OpenGL.GL as ogl
from pyqtgraph.Qt import QtCore, QtGui

from numpy import array, linspace, arange
from .player import Player3D


## ref: https://stackoverflow.com/questions/56890547/how-to-add-axis-features-labels-ticks-values-to-a-3d-plot-with-glviewwidget
class CustomTextItem(gl.GLGraphicsItem.GLGraphicsItem):
	def __init__(self, X, Y, Z, text):
		gl.GLGraphicsItem.GLGraphicsItem.__init__(self)
		self.text = text
		self.X = X
		self.Y = Y
		self.Z = Z

	def setGLViewWidget(self, GLViewWidget):
		self.GLViewWidget = GLViewWidget

	def setText(self, text):
		self.text = text
		self.update()

	def setX(self, X):
		self.X = X
		self.update()

	def setY(self, Y):
		self.Y = Y
		self.update()

	def setZ(self, Z):
		self.Z = Z
		self.update()

	def paint(self):
		self.GLViewWidget.qglColor(QtCore.Qt.black)
		self.GLViewWidget.renderText(self.X, self.Y, self.Z, self.text)


class Custom3DAxis(gl.GLAxisItem):
	"""Class defined to extend 'gl.GLAxisItem'."""
	def __init__(self, parent, color=(0,0,0,.6)):
		gl.GLAxisItem.__init__(self)
		self.parent = parent
		self.c = color
		self.xLabel = self.yLabel = self.zLabel = None
		self.xTicks = self.yTicks = self.zTicks = None
		self.xScale = self.yScale = self.zScale = 1

	def add_labels(self):
		"""Adds axes labels."""
		x,y,z = self.size()
		tf = self.transform()
		#X label
		self.xLabel = CustomTextItem(X=x*1.1, Y=-y/20, Z=-z/20, text="X")
		self.xLabel.setGLViewWidget(self.parent)
		self.xLabel.applyTransform(tf, local=False)
		self.parent.addItem(self.xLabel)
		#Y label
		self.yLabel = CustomTextItem(X=-x/20, Y=y*1.1, Z=-z/20, text="Y")
		self.yLabel.setGLViewWidget(self.parent)
		self.yLabel.applyTransform(tf, local=False)
		self.parent.addItem(self.yLabel)
		#Z label
		self.zLabel = CustomTextItem(X=-x/20, Y=-y/20, Z=z*1.1, text="Z")
		self.zLabel.setGLViewWidget(self.parent)
		self.zLabel.applyTransform(tf, local=False)
		self.parent.addItem(self.zLabel)

	def add_tick_values(self, xtpos=[], ytpos=[], ztpos=[]):
		"""Adds ticks values."""
		x,y,z = self.size()
		tf = self.transform()
		#X label
		self.xTicks = []
		for xt in xtpos:
			val = CustomTextItem(X=xt*self.xScale, Y=-y/20, Z=-z/20, text=str(round(xt, 2)))  # 只显示到四舍五入小数点后2位
			val.setGLViewWidget(self.parent)
			val.applyTransform(tf, local=False)
			self.parent.addItem(val)
			self.xTicks.append(val)
		#Y label
		self.yTicks = []
		for yt in ytpos:
			val = CustomTextItem(X=-x/20, Y=yt*self.yScale, Z=-z/20, text=str(round(yt, 2)))  # 只显示到四舍五入小数点后2位
			val.setGLViewWidget(self.parent)
			val.applyTransform(tf, local=False)
			self.parent.addItem(val)
			self.yTicks.append(val)
		#Z label
		self.zTicks = []
		for zt in ztpos:
			val = CustomTextItem(X=-x/20, Y=-y/20, Z=zt*self.zScale, text=str(round(zt, 2)))  # 只显示到四舍五入小数点后2位
			val.setGLViewWidget(self.parent)
			val.applyTransform(tf, local=False)
			self.parent.addItem(val)
			self.zTicks.append(val)

	def paint(self):
		self.setupGLState()
		if self.antialias:
			ogl.glEnable(ogl.GL_LINE_SMOOTH)
			ogl.glHint(ogl.GL_LINE_SMOOTH_HINT, ogl.GL_NICEST)
		ogl.glBegin(ogl.GL_LINES)

		x,y,z = self.size()
		#Draw Z
		ogl.glColor4f(self.c[0], self.c[1], self.c[2], self.c[3])
		ogl.glVertex3f(0, 0, 0)
		ogl.glVertex3f(0, 0, z)
		#Draw Y
		ogl.glColor4f(self.c[0], self.c[1], self.c[2], self.c[3])
		ogl.glVertex3f(0, 0, 0)
		ogl.glVertex3f(0, y, 0)
		#Draw X
		ogl.glColor4f(self.c[0], self.c[1], self.c[2], self.c[3])
		ogl.glVertex3f(0, 0, 0)
		ogl.glVertex3f(x, 0, 0)
		ogl.glEnd()

	def translate(self, dx, dy, dz, local=False):
		gl.GLAxisItem.translate(self, dx, dy, dz, local)
		if self.xLabel and self.yLabel and self.zLabel:
			tr = pg.Transform3D()
			tr.translate(dx, dy, dz)
			self.xLabel.applyTransform(tr, local=local)
			self.yLabel.applyTransform(tr, local=local)
			self.zLabel.applyTransform(tr, local=local)
		if self.xTicks and self.yTicks and self.zTicks:
			tr = pg.Transform3D()
			tr.translate(dx, dy, dz)
			for item in self.xTicks:
				item.applyTransform(tr, local=local)
			for item in self.yTicks:
				item.applyTransform(tr, local=local)
			for item in self.zTicks:
				item.applyTransform(tr, local=local)

	def setTickScale(self, x, y, z):
		self.xScale = x
		self.yScale = y
		self.zScale = z
		if self.xTicks and self.yTicks and self.zTicks:
			tr = pg.Transform3D()
			tr.scale(x, 1, 1)
			for item in self.xTicks:
				item.applyTransform(tr, local=True)
			tr = pg.Transform3D()
			tr.scale(1, y, 1)
			for item in self.yTicks:
				item.applyTransform(tr, local=True)
			tr = pg.Transform3D()
			tr.scale(1, 1, z)
			for item in self.zTicks:
				item.applyTransform(tr, local=True)


class Player3DPyqtgraph(Player3D, QtGui.QWidget):

	"""3D player using **pyqtgraph** backend.
	
	"""
	
	backend = "pyqtgraph"
	## ref: https://stackoverflow.com/questions/27475940/pyqt-connect-to-keypressevent
	keyPressed = QtCore.pyqtSignal(object)

	def __init__(self, *args, **kwargs):
		"""constructor
		
		Args:
			*args: positional arguments passed to base class.
			widgets (bool, optional): show the control widgets. Defaults
				to True.
			**kwargs: keyword arguments passed to base class.
		"""
		app = QtGui.QApplication([])
		super().__init__(*args, **kwargs)

		## collect all KeyPress event, using overridden keyPressEvent()
		self.grabKeyboard()

		self.setWindowTitle('3D data')
		self.resize(600, 550)  # resize window

		## remove input hook
		QtCore.pyqtRemoveInputHook()

		## a root vertical layout
		layout = QtGui.QVBoxLayout(self)
		# layout.setContentsMargins(0, 0, 0, 0)
		
		## reference size of according to data size
		ref_size = max(self.N[0], self.N[1])
		box_size = (self.N[0], self.N[1], ref_size)

		## add 3D plot view
		view = gl.GLViewWidget()
		# view.setWindowTitle('pressure sensor data')
		## Create a GL view widget to display data
		background_color = app.palette().color(QtGui.QPalette.Background)
		view.setBackgroundColor(background_color)
		view.setCameraPosition(distance=1.8*ref_size)
		# view.resize(600, 550)  # resize window
		view.pan(0, 0, 0.5*ref_size)  # move the camera up
		## rotate camera
		view.orbit(azim=-30, elev=0)
		layout.addWidget(view)

		## Add a grid to the view
		g = gl.GLGridItem()
		g.setDepthValue(10)  # draw grid after surfaces since they may be translucent
		g.setSize(*box_size)
		view.addItem(g)

		## create a surface plot, tell it to use the 'heightColor' shader
		## since this does not require normal vectors to render (thus we 
		## can set computeNormals=False to save time when the mesh updates)
		z_scale = box_size[2] / self.zlim
		pic_surf = gl.GLSurfacePlotItem(shader='heightColor', computeNormals=False, smooth=True)
		pic_surf.shader()['colorMap'] = array([0.2, 2, 0.5, 0.2, 1, 1, 0.2, 0, 2])
		pic_surf.translate(-self.N[0]*0.5+0.5, -self.N[1]*0.5+0.5, 0)
		pic_surf.scale(1, 1, z_scale)
		view.addItem(pic_surf)

		axis = Custom3DAxis(view, color=(0.2,0.2,0.2,.6))
		axis.setSize(*box_size)
		# x_pos = [self.N[0]*0.25, self.N[0]*0.5, self.N[0]*0.75, self.N[0]]
		x_pos = arange(1, self.N[0]+1, 1)
		# y_pos = [self.N[1]*0.25, self.N[1]*0.5, self.N[1]*0.75, self.N[1]]
		y_pos = arange(1, self.N[1]+1, 1)
		z_pos = linspace(0, self.zlim, 6)
		axis.add_tick_values(xtpos=x_pos, ytpos=y_pos, ztpos=z_pos)
		axis.add_labels()
		axis.setTickScale(1, 1, z_scale)
		axis.translate(-self.N[0]*0.5, -self.N[1]*0.5, 0)
		view.addItem(axis)

		self.x = arange(0, self.N[0], 1)
		# self.y = arange(self.N-1, -1, -1)
		self.y = arange(0, self.N[1], 1)
		self.pic_surf = pic_surf
		self.app = app
		self.layout = layout
		self.view = view

	def _start(self):
		super()._start()
		self.show()
		if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
			QtGui.QApplication.instance().exec_()

	def _close(self):
		super()._close()
		QtGui.QApplication.instance().quit()

	def _draw(self, data):
		self.pic_surf.setData(x=self.x, y=self.y, z=data)

	def _prepare_stream(self):
		self.keyPressed.connect(self.on_key_stream)
		timeout = 1000 / self.fps
		self.timer = QtCore.QTimer()
		self.timer.timeout.connect(self.update_stream)
		self.timer.start(timeout)

	def _prepare_interactive(self):
		if self.widgets:
			self.setup_widgets()
		self.keyPressed.connect(self.on_key_interactive)
		timeout = 1000 / self.fps
		self.timer = QtCore.QTimer()
		self.timer.timeout.connect(self.update_interactive)
		self.timer.start(timeout)

	def on_key_stream(self, event):
		if event.key() == QtCore.Qt.Key_Space:
			self.toggle_pause()
		elif event.key() == QtCore.Qt.Key_Q:
			self._close()

	def on_key_interactive(self, event):
		if event.key() == QtCore.Qt.Key_Space:
			self.toggle_pause()
		elif event.key() == QtCore.Qt.Key_Q:
			self._close()
		elif event.key() == QtCore.Qt.Key_J:
			## use thread to prevent blocking of GUI
			t = Thread(target=self.jump)
			t.start()
		else:
			if event.key() == QtCore.Qt.Key_Right:
				self.forward()
			elif event.key() == QtCore.Qt.Key_Left:
				self.backward()
			elif event.key() == QtCore.Qt.Key_Period:
				self.oneforward()
			elif event.key() == QtCore.Qt.Key_Comma:
				self.onebackward()
			elif event.key() == QtCore.Qt.Key_A:
				self.gotofirst()
			elif event.key() == QtCore.Qt.Key_E:
				self.gotolast()

	## override
	def keyPressEvent(self, event):
		self.keyPressed.emit(event)

	def setup_widgets(self):
		self.resize(600, 580)  # resize window

		## ref: https://stackoverflow.com/a/59014582/11854304
		self.sublayout = QtGui.QHBoxLayout()
		self.layout.addLayout(self.sublayout)
		# QStyles sometimes create *huge* margins (6-10 pixels) around 
		# layout contents; we don't really need those in here
		self.sublayout.setContentsMargins(0, 0, 0, 0)
		self.sublayout.addStretch(10)
		# when adding a QSlider to a QLayout and specifying an alignment
		# the opposite of the orientation *has* to be omitted to ensure 
		# that it's centered in the other direction
		self.slider = QtGui.QSlider(QtCore.Qt.Horizontal)
		self.slider.setMaximum(self.max_idx)
		self.sublayout.addWidget(self.slider, alignment=QtCore.Qt.AlignVCenter)
		# use an arbitrary text for the minimum width to minimize size 
		# flickering on value changes
		self.label = QtGui.QLabel()
		self.label.setMinimumWidth(self.fontMetrics().width("8.8888e+88"))
		self.label.setAlignment(QtCore.Qt.AlignCenter)
		self.sublayout.addWidget(self.label, alignment=QtCore.Qt.AlignVCenter)

		self.sublayout.addStretch(10)
		self.sublayout.setStretchFactor(self.slider, 70)
		self.sublayout.setStretchFactor(self.label, 10)

		self.sublayout2 = QtGui.QHBoxLayout()
		self.layout.addLayout(self.sublayout2)
		self.sublayout2.setContentsMargins(0, 0, 0, 0)

		self.sublayout2.addStretch(10)
		self.button_back = QtGui.QToolButton()
		self.button_oneback = QtGui.QToolButton()
		self.button_play = QtGui.QToolButton()
		self.button_oneforward = QtGui.QToolButton()
		self.button_forward = QtGui.QToolButton()
		self.button_back.setIcon(self.style().standardIcon(QtGui.QStyle.SP_MediaSkipBackward))
		self.button_oneback.setIcon(self.style().standardIcon(QtGui.QStyle.SP_MediaSeekBackward))
		self.button_play.setIcon(self.style().standardIcon(QtGui.QStyle.SP_MediaPlay))
		self.button_oneforward.setIcon(self.style().standardIcon(QtGui.QStyle.SP_MediaSeekForward))
		self.button_forward.setIcon(self.style().standardIcon(QtGui.QStyle.SP_MediaSkipForward))
		self.button_back.clicked.connect(self.backward)
		self.button_oneback.clicked.connect(self.onebackward)
		self.button_play.clicked.connect(self.toggle_pause)
		self.button_oneforward.clicked.connect(self.oneforward)
		self.button_forward.clicked.connect(self.forward)
		self.sublayout2.addWidget(self.button_back, alignment=QtCore.Qt.AlignVCenter)
		self.sublayout2.addWidget(self.button_oneback, alignment=QtCore.Qt.AlignVCenter)
		self.sublayout2.addWidget(self.button_play, alignment=QtCore.Qt.AlignVCenter)
		self.sublayout2.addWidget(self.button_oneforward, alignment=QtCore.Qt.AlignVCenter)
		self.sublayout2.addWidget(self.button_forward, alignment=QtCore.Qt.AlignVCenter)
		self.sublayout2.addStretch(10)

		self.layout.setStretchFactor(self.view, 90)
		self.layout.setStretchFactor(self.sublayout, 5)
		self.layout.setStretchFactor(self.sublayout2, 5)

		self.slider.setTracking(True)
		self.slider.setValue(self.cur_idx)
		self.label.setText(f"{self.cur_idx+1} / {self.max_idx+1}")
		self.slider.valueChanged.connect(self.slider_set_idx)

	def slider_set_idx(self, event):
		self.cur_idx = int(self.slider.value())
		self.label.setText(f"{self.cur_idx+1} / {self.max_idx+1}")
		self.repaint()  ## make immediate GUI change
		super().draw_slice()

	## override
	def draw_slice(self):
		if self.widgets and self.started:
			self.slider.setValue(self.cur_idx)
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
	my_player = Player3DPyqtgraph(zlim=3)
	## you can use either
	my_player.run_stream(fps=100, generator=gen(arr))
	## or
	# my_player.run(MODE.STREAM, fps=100, generator=gen(arr))
	p.join()
