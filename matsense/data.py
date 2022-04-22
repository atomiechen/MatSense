import argparse
import copy
import numpy as np
from datetime import datetime

from matsense.filemanager import write_line, clear_file
from matsense.datasetter import DataSetterFile
from matsense.process import Processor, DataHandlerPressure
from matsense.tools import (
	int2datetime, load_config, blank_config, check_config, make_action, DEST_SUFFIX
)

N = 16
FPS = 194
ZLIM = 3
OUTPUT_FILENAME_TEMPLATE = "processed_%Y%m%d%H%M%S.csv"
OUTPUT_FILENAME = datetime.now().strftime(OUTPUT_FILENAME_TEMPLATE)


def prepare_config(args):
	## load config and combine commandline arguments
	if args.config:
		config = load_config(args.config)
	else:
		config = blank_config()

	## priority: commandline arguments > config file > program defaults
	if config['sensor']['shape'] is None or hasattr(args, 'n'+DEST_SUFFIX):
		config['sensor']['shape'] = args.n
	if config['data_mode']['process'] is None:
		config['data_mode']['process'] = False
	if config['data']['in_filenames'] is None or len(args.filenames) > 0:
		config['data']['in_filenames'] = args.filenames
	if config['data']['out_filename'] is None or hasattr(args, 'output'+DEST_SUFFIX):
		if args.output is None:
			args.output = OUTPUT_FILENAME
		config['data']['out_filename'] = args.output
	if config['visual']['zlim'] is None or hasattr(args, 'zlim'+DEST_SUFFIX):
		config['visual']['zlim'] = args.zlim
	if config['visual']['fps'] is None or hasattr(args, 'fps'+DEST_SUFFIX):
		config['visual']['fps'] = args.fps
	if config['visual']['pyqtgraph'] is None or hasattr(args, 'pyqtgraph'+DEST_SUFFIX):
		config['visual']['pyqtgraph'] = args.pyqtgraph
	if config['visual']['scatter'] is None or hasattr(args, 'scatter'+DEST_SUFFIX):
		config['visual']['scatter'] = args.scatter

	## some modifications
	if hasattr(args, 'output'+DEST_SUFFIX):
		config['data_mode']['process'] = True
	if config['process']['interp'] is None:
		config['process']['interp'] = copy.deepcopy(config['sensor']['shape'])

	check_config(config)
	return config


def main():
	description = "Visualize data, or process data via -o flag"
	parser = argparse.ArgumentParser(description=description, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
	parser.add_argument('filenames', nargs='*', action='store', help="input file(s) that contain matrix sensor data")
	parser.add_argument('-n', dest='n', action=make_action('store'), default=[N], type=int, nargs='+', help="specify sensor shape")
	parser.add_argument('-z', '--zlim', dest='zlim', action=make_action('store'), default=ZLIM, type=float, help="z-axis limit")
	parser.add_argument('-f', dest='fps', action=make_action('store'), default=FPS, type=int, help="frames per second")
	parser.add_argument('--scatter', dest='scatter', action=make_action('store_true'), default=False, help="show scatter plot")
	parser.add_argument('--pyqtgraph', dest='pyqtgraph', action=make_action('store_true'), default=False, help="use pyqtgraph to plot")
	parser.add_argument('-o', dest='output', nargs='?', action=make_action('store'), default=OUTPUT_FILENAME, help="output processed data to file")
	parser.add_argument('--config', dest='config', action=make_action('store'), default=None, help="specify configuration file")
	args = parser.parse_args()
	config = prepare_config(args)

	filenames = config['data']['in_filenames']
	if not filenames:
		print("MUST provide input file(s) to continue.")
		return

	print(f"reading file(s): {filenames}")
	my_setter = DataSetterFile(
		config['sensor']['total'], 
		config['data']['in_filenames'], 
	)
	## prepare data array
	data_tmp = np.zeros(config['sensor']['total'], dtype=float)

	if config['data_mode']['process']:
		print("Data process mode:")

		my_handler = DataHandlerPressure(
			n=config['sensor']['shape'],
			raw=config['process']['raw'],
			V0=config['process']['V0'],
			R0_RECI=config['process']['R0_RECI'],
			convert=config['process']['convert'],
			resi_opposite=config['process']['resi_opposite'],
			resi_delta=config['process']['resi_delta'],
			mask=config['sensor']['mask'],
			filter_spatial=config['process']['filter_spatial'],
			filter_spatial_cutoff=config['process']['filter_spatial_cutoff'],
			butterworth_order=config['process']['butterworth_order'],
			filter_temporal=config['process']['filter_temporal'],
			filter_temporal_size=config['process']['filter_temporal_size'],
			rw_cutoff=config['process']['rw_cutoff'],
			cali_frames=config['process']['cali_frames'],
			cali_win_size=config['process']['cali_win_size'],
            cali_threshold=config['process']['cali_threshold'],
            cali_win_buffer_size=config['process']['cali_win_buffer_size'],
			intermediate=config['process']['intermediate'],
		)
		my_processor = Processor(
			config['process']['interp'], 
			blob=config['process']['blob'], 
			threshold=config['process']['threshold'],
			order=config['process']['interp_order'],
			total=config['process']['blob_num'],
			special=config['process']['special_check'],
			original_shape=config['sensor']['shape'],
		)
		my_processor.print_info()

		print(f"writing to file: {config['data']['out_filename']}")
		## clear file content
		clear_file(config['data']['out_filename'])

		## prepare handler
		def gen_data():
			while True:
				my_setter(data_tmp)
				yield data_tmp

		my_handler.prepare(gen_data())
		## loop to process
		cnt = 0
		for data_tmp, tags in my_setter.gen(data_tmp):
			my_handler.handle(data_tmp)
			data_tmp = my_processor.transform(data_tmp, reshape=True)
			write_line(config['data']['out_filename'], data_tmp, tags)
			cnt += 1

		print(f"output {cnt} lines to {config['data']['out_filename']}")

	else:
		print("Data visualization mode")

		content = ([], [])
		for data_tmp, tags in my_setter.gen(data_tmp):
			data_reshape = data_tmp.reshape(config['sensor']['shape'])
			frame_idx, date_time = tags
			date_time = int2datetime(date_time)
			content[0].append(np.array(data_reshape))
			content[1].append(f"frame idx: {frame_idx}  {date_time}")

		if config['visual']['pyqtgraph']:
			from matsense.visual.player_pyqtgraph import Player3DPyqtgraph as Player
		else:
			from matsense.visual.player_matplot import Player3DMatplot as Player
		my_player = Player(
			N=config['sensor']['shape'],
			zlim=config['visual']['zlim'], 
			scatter=config['visual']['scatter'],
			show_value=config['visual']['show_value'],
			widgets=True,
		)
		my_player.run_interactive(dataset=content[0], infoset=content[1], fps=config['visual']['fps'])


if __name__ == '__main__':
	main()
