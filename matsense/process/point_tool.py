import math

class Smoother:
	def __init__(self, alpha, beta=0):
		self.alpha = alpha
		self.beta = beta
		self.last_value = 0
		self.last_trend = 0

	@property
	def alpha(self):
		return self._alpha
	
	@alpha.setter
	def alpha(self, value):
		if 0 <= value <= 1:
			self._alpha = value
		else:
			raise Exception("alpha should be a value in [0, 1]")

	@property
	def beta(self):
		return self._beta

	@beta.setter
	def beta(self, value):
		if 0 <= value <= 1:
			self._beta = value
		else:
			raise Exception("beta should be a value in [0, 1]")

	def update(self, val):
		val = self.alpha*val + (1-self.alpha)*(self.last_value+self.last_trend)
		self.last_trend = self.beta*(val-self.last_value)+(1-self.beta)*self.last_trend
		self.last_value = val
		return val


class PointSmoother:
	def __init__(self, init=(0, 0, 0), **kwargs):
		self.coor0 = Smoother(1)
		self.coor1 = Smoother(1)
		self.value = Smoother(1)
		self.set_still(*init)
		self.config(**kwargs)

	def config(self, *, alpha=None):
		if alpha is not None:
			self.coor0.alpha = alpha
			self.coor1.alpha = alpha
			self.value.alpha = alpha

	def set_still(self, coor0, coor1, value):
		self.coor0.last_value = coor0
		self.coor1.last_value = coor1
		self.value.last_value = value

	def smooth(self, coor0, coor1, value, **kwargs):
		self.config(**kwargs)
		coor0 = self.coor0.update(coor0)
		coor1 = self.coor1.update(coor1)
		value = self.value.update(value)
		return coor0, coor1, value

	def gen_points_wrapper(self, generator, **kwargs):
		for coor0, coor1, value in generator:
			yield self.smooth(coor0, coor1, value, **kwargs)


class CursorController:
	@staticmethod
	def map_coor(row, col, 
			ratioX=1, ratioY=1, offsetX=0, offsetY=0,
			rmax=1, rmin=0, cmax=1, cmin=0):
		x = ratioX * (col - cmin) / (cmax - cmin) + offsetX
		y = ratioY * (rmax - row) / (rmax - rmin) + offsetY
		return x, y

	def __init__(self, ratioX=1, ratioY=1, offsetX=0, offsetY=0, rmax=1, rmin=0, cmax=1, cmin=0, **kwargs):
		self.ratioX = ratioX
		self.ratioY = ratioY
		self.offsetX = offsetX
		self.offsetY = offsetY
		self.rmax = rmax
		self.rmin = rmin
		self.cmax = cmax
		self.cmin = cmin
		self.last_x = 0
		self.last_y = 0
		self.moving = False  # the cursor is moving or not
		self.bound = 0
		self.mapcoor = False  # directly map coordinates or relatively
		self.trackpoint = False  # use ThinkPad's TrackPoint control style
		self.alpha = 1  # no smoothing
		self.config(**kwargs)

		self.pointsmoother = PointSmoother()

	def config(self, *, bound=None, mapcoor=None, alpha=None, trackpoint=None):
		if bound is not None:
			self.bound = bound
		if mapcoor is not None:
			self.mapcoor = mapcoor
		if alpha is not None:
			self.alpha = alpha
		if trackpoint is not None:
			self.trackpoint = trackpoint

	def move(self, x, y, val):
		if val > self.bound:
			if not self.moving:
				## make diff 0
				self.last_x = x
				self.last_y = y
				self.pointsmoother.set_still(0, 0, val)
			self.moving = True
			# print(f"{x - self.last_x} {y - self.last_y} {x} {y}")
		else:
			self.moving = False
			## make diff 0
			self.last_x = x
			self.last_y = y
			self.pointsmoother.set_still(0, 0, val)
		diff_x = x - self.last_x
		diff_y = y - self.last_y
		self.last_x = x
		self.last_y = y
		diff_x, diff_y, val = self.pointsmoother.smooth(diff_x, diff_y, 
								val, alpha=self.alpha)
		return self.moving, diff_x, diff_y, val

	def move_to(self, x, y, val):
		if val > self.bound:
			self.moving = True
		else:
			self.moving = False
		x, y, val = self.pointsmoother.smooth(x, y, val, alpha=self.alpha)
		return self.moving, x, y, val

	def move_trackpoint(self, x, y, val):
		if val > self.bound:
			if not self.moving:
				## make diff 0
				self.last_x = x
				self.last_y = y
				self.pointsmoother.set_still(0, 0, val)
			self.moving = True
		else:
			self.moving = False
			## make diff 0
			self.last_x = x
			self.last_y = y
			self.pointsmoother.set_still(0, 0, val)
		diff_x = x - self.last_x
		diff_y = y - self.last_y
		diff_x, diff_y, val = self.pointsmoother.smooth(diff_x, diff_y, 
								val, alpha=self.alpha)

		### 修正的正确实验使用的条件
		r = math.hypot(diff_x, diff_y)
		U = 30
		k = 18.889
		b = 5
		###

		if r != 0:
			new_r = U * (1/(1+math.exp(b-k*r)) - 1/(1+math.exp(b)))
			new_x = diff_x / r * new_r
			new_y = diff_y / r * new_r
			diff_x = new_x
			diff_y = new_y
		return self.moving, diff_x, diff_y, val

	def update(self, row, col, val, **kwargs):
		self.config(**kwargs)
		x, y = self.map_coor(row, col, 
				self.ratioX, self.ratioY, self.offsetX, self.offsetY,
				self.rmax, self.rmin, self.cmax, self.cmin)
		if self.mapcoor:
			return self.move_to(x, y, val)
		elif self.trackpoint:
			return self.move_trackpoint(x, y, val)
		else:
			return self.move(x, y, val)

	def gen_coors(self, generator, **kwargs):
		for row, col, val in generator:
			yield self.update(row, col, val, **kwargs)

	def print_info(self):
		print("Cursor details:")
		if self.mapcoor:
			msg = "direct (absolute)"
		else:
			msg = "indirect (relative)"
		print(f"  Coordinates mapping: {msg}")
		print(f"  Smooth points:       alpha = {self.alpha}")


if __name__ == '__main__':
	p = PointSmoother(alpha=0.3, init=(0.3, 0.5, 15))
	ret = p.smooth(0.5, 0.8, 10)
	print(ret)
	ret = p.smooth(0.5, 0.8, 10)
	print(ret)
	ret = p.smooth(0.5, 0.8, 10)
	print(ret)
	ret = p.smooth(0.5, 0.8, 10, alpha=0.7)
	print(ret)
	ret = p.smooth(0.5, 0.8, 10, alpha=0.3)
	print(ret)
	ret = p.smooth(0.5, 0.8, 10, alpha=1)
	print(ret)

	c = CursorController()
	ret = c.map_coor(0.2, 0.3, 100, 100)
	print(ret)
