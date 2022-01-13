import argparse
import numpy as np

from matsense.filemanager import parse_line, write_line, clear_file
from matsense.serverkit import Proc
from matsense.process import Processor
from matsense.tools import check_shape

N = 16
INTERP = 16
FPS = 194
TH = 0.15
ZLIM = 3
CONVERT = False
V0 = 255
R0_RECI = 1  ## a constant to multiply the value


def main():
	description = "Visualize data, or process data via -o flag"
	parser = argparse.ArgumentParser(description=description, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
	parser.add_argument('filename', action='store')
	parser.add_argument('-n', dest='n', action='store', default=[N], type=int, nargs='+', help="specify sensor shape")
	parser.add_argument('-f', dest='fps', action='store', default=FPS, type=int, help="frames per second")
	parser.add_argument('--pyqtgraph', dest='pyqtgraph', action='store_true', default=False, help="use pyqtgraph to plot")
	# parser.add_argument('-m', '--matplot', dest='matplot', action='store_true', default=False, help="use mathplotlib to plot")
	parser.add_argument('-z', '--zlim', dest='zlim', action='store', default=ZLIM, type=float, help="z-axis limit")
	parser.add_argument('-o', dest='output', action='store', default=None, help="output processed data to file")
	parser.add_argument('--interp', dest='interp', action='store', default=[INTERP], type=int, nargs='+', help="interpolated side size")
	parser.add_argument('--noblob', dest='noblob', action='store_true', default=False, help="do not filter out blob")
	parser.add_argument('--th', dest='threshold', action='store', default=TH, type=float, help="blob filter threshold")
	parser.add_argument('--convert', dest='convert', action='store_true', default=CONVERT, help="apply voltage-resistance conversion")
	parser.add_argument('--v0', dest='v0', action='store', default=V0, type=float, help="refercence voltage for conversion")
	args = parser.parse_args()

	filename = args.filename
	print(f"reading file: {filename}")
	args.n = check_shape(args.n)
	args.interp = check_shape(args.interp)

	if args.output:
		print("Data process mode:")

		my_processor = Processor(
			args.interp, 
			blob=not args.noblob, 
			threshold=args.threshold
		)
		my_processor.print_info()

		print(f"writing to file: {args.output}")
		## clear file content
		clear_file(args.output)
		cnt = 0
		with open(filename, 'r', encoding='utf-8') as fin:
			for line in fin:
				data_parse, frame_idx, date_time = parse_line(line, args.n[0]*args.n[1], ',')
				data_out = my_processor.transform(data_parse, reshape=True)
				data_str = [f"{item:.6f}" for item in data_out]
				timestamp = int(date_time.timestamp()*1000000)
				write_line(args.output, data_str, tags=[frame_idx, timestamp])
				cnt += 1
		print(f"output {cnt} lines to {args.output}")
	else:
		print("Data visualization mode")
		content = ([], [])
		with open(filename, 'r', encoding='utf-8') as fin:
			for line in fin:
				data_parse, frame_idx, date_time = parse_line(line, args.n[0]*args.n[1], ',')
				if args.convert:
					Proc.calReci_numpy_array(data_parse, args.v0, R0_RECI)
				data_reshape = data_parse.reshape(args.n[0], args.n[1])
				content[0].append(np.array(data_reshape))
				content[1].append(f"frame idx: {frame_idx}  {date_time}")

		if args.pyqtgraph:
			from matsense.visual.player_pyqtgraph import Player3DPyqtgraph as Player
		else:
			from matsense.visual.player_matplot import Player3DMatplot as Player
		my_player = Player(zlim=args.zlim, widgets=True, N=args.n)
		my_player.run_interactive(dataset=content[0], infoset=content[1], fps=args.fps)


if __name__ == '__main__':
	main()
