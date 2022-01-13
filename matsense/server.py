from serial.tools.list_ports import comports
import argparse
from datetime import datetime

from multiprocessing import Process  # 进程
from multiprocessing import Array  # 共享内存
from multiprocessing import Value  # 共享内存
from multiprocessing import Pipe  # 进程间通信管道

import traceback

from matsense.serverkit import (
	Proc, Userver, DataSetterSerial, DataSetterDebug, DataSetterFile,
	FLAG, CustomException
)
from matsense.tools import (
	load_config, blank_config, check_config, print_sensor, 
    make_action, DEST_SUFFIX
)
from matsense.filemanager import clear_file


N = 16  # sensor side length
BAUDRATE = 500000
TIMEOUT = 1  # in seconds
devices_found = comports()
PORT = None
try:
	## default use the last port on the list
	PORT = devices_found[-1].device
except:
	pass

UDP = False
NO_CONVERT = False

ZLIM = 3
FPS = 100

DEBUG = False
OUTPUT_FILENAME_TEMPLATE = "processed_%Y%m%d%H%M%S.csv"
OUTPUT_FILENAME = datetime.now().strftime(OUTPUT_FILENAME_TEMPLATE)

INTERMEDIATE = 0


def enumerate_ports():
	# 查看可用端口
	print("All serial ports:")
	for item in devices_found:
		print(item)

def task_serial(paras):
	ret = None
	try:
		if paras['config']['server_mode']['debug']:
			my_setter = DataSetterDebug()
		else:
			my_setter = DataSetterSerial(
				paras['config']['sensor']['total'], 
				paras['config']['serial']['baudrate'], 
				paras['config']['serial']['port'], 
				paras['config']['serial']['timeout'],
				imu=paras['config']['serial']['imu'],
				protocol=paras['config']['serial']['protocol'],
			)
		my_proc = Proc(
			paras['config']['sensor']['shape'], 
			my_setter, 
			paras['data_out'], 
			paras['data_raw'], 
			paras['data_imu'], 
			paras['idx_out'],
			raw=paras['config']['server_mode']['raw'],
			warm_up=paras['config']['process']['warm_up'],
			V0=paras['config']['process']['V0'],
			R0_RECI=paras['config']['process']['R0_RECI'],
			convert=paras['config']['process']['convert'],
			mask=paras['config']['sensor']['mask'],
			filter_spatial=paras['config']['process']['filter_spatial'],
			filter_spatial_cutoff=paras['config']['process']['filter_spatial_cutoff'],
			butterworth_order=paras['config']['process']['butterworth_order'],
			filter_temporal=paras['config']['process']['filter_temporal'],
			filter_temporal_size=paras['config']['process']['filter_temporal_size'],
			rw_cutoff=paras['config']['process']['rw_cutoff'],
			cali_frames=paras['config']['process']['cali_frames'],
			cali_win_size=paras['config']['process']['cali_win_size'],
			pipe_conn=paras['pipe_proc'],
			copy_tags=False,
			imu=paras['config']['serial']['imu'],
			intermediate=paras['config']['process']['intermediate']
		)
		ret = my_proc.run()
	except KeyboardInterrupt:
		pass
	except CustomException as e:
		print(e)
	except BaseException as e:
		traceback.print_exc()
		# print(e)
	finally:
		## close the other process
		paras['pipe_proc'].send((FLAG.FLAG_STOP,))
	print("Processing stopped.")
	return ret

def task_server(paras):
	try:
		with Userver(
			paras['data_out'], 
			paras['data_raw'], 
			paras['data_imu'], 
			paras['idx_out'], 
			paras['config']['connection']['server_address'], 
			total=paras['config']['sensor']['total'],
			udp=paras['config']['connection']['udp'],
			pipe_conn=paras['pipe_server'],
			config_copy=paras['config'],
		) as my_server:
			my_server.run_service()
	except KeyboardInterrupt:
		pass
	except CustomException as e:
		print(e)
	except BaseException as e:
		traceback.print_exc()
		# print(e)
	finally:
		## close the other process
		paras['pipe_server'].send((FLAG.FLAG_STOP,))

def task_file(paras):
	print(f"Processed data saved to: {paras['config']['server_mode']['out_filename']}")
	my_setter = DataSetterFile(
		paras['config']['sensor']['total'], 
		paras['config']['server_mode']['in_filenames'], 
	)
	my_proc = Proc(
		paras['config']['sensor']['shape'], 
		my_setter, 
		paras['data_out'], 
		paras['data_raw'], 
		paras['idx_out'],
		raw=False,
		warm_up=0,
		V0=paras['config']['process']['V0'],
		R0_RECI=paras['config']['process']['R0_RECI'],
		convert=paras['config']['process']['convert'],
		mask=paras['config']['sensor']['mask'],
		filter_spatial=paras['config']['process']['filter_spatial'],
		filter_spatial_cutoff=paras['config']['process']['filter_spatial_cutoff'],
		butterworth_order=paras['config']['process']['butterworth_order'],
		filter_temporal=paras['config']['process']['filter_temporal'],
		filter_temporal_size=paras['config']['process']['filter_temporal_size'],
		rw_cutoff=paras['config']['process']['rw_cutoff'],
		cali_frames=paras['config']['process']['cali_frames'],
		cali_win_size=paras['config']['process']['cali_win_size'],
		pipe_conn=None,
		output_filename=paras['config']['server_mode']['out_filename'],
		copy_tags=True,
	)
	## clear file content
	clear_file(paras['config']['server_mode']['out_filename'])
	my_proc.run()

def prepare_config(args):
	## load config and combine commandline arguments
	if args.config:
		config = load_config(args.config)
	else:
		config = blank_config()
	## priority: commandline arguments > config file > program defaults
	if config['sensor']['shape'] is None or hasattr(args, 'n'+DEST_SUFFIX):
		config['sensor']['shape'] = args.n
	if config['serial']['baudrate'] is None or hasattr(args, 'baudrate'+DEST_SUFFIX):
		config['serial']['baudrate'] = args.baudrate
	if config['serial']['timeout'] is None or hasattr(args, 'timeout'+DEST_SUFFIX):
		config['serial']['timeout'] = args.timeout
	if config['serial']['port'] is None or hasattr(args, 'port'+DEST_SUFFIX):
		config['serial']['port'] = args.port
	if config['connection']['udp'] is None or hasattr(args, 'udp'+DEST_SUFFIX):
		config['connection']['udp'] = args.udp
	if config['connection']['server_address'] is None or hasattr(args, 'address'+DEST_SUFFIX):
		config['connection']['server_address'] = args.address
	if config['process']['convert'] is None or hasattr(args, 'no_convert'+DEST_SUFFIX):
		config['process']['convert'] = not args.no_convert
	if config['visual']['zlim'] is None or hasattr(args, 'zlim'+DEST_SUFFIX):
		config['visual']['zlim'] = args.zlim
	if config['visual']['fps'] is None or hasattr(args, 'fps'+DEST_SUFFIX):
		config['visual']['fps'] = args.fps
	if config['visual']['pyqtgraph'] is None or hasattr(args, 'pyqtgraph'+DEST_SUFFIX):
		config['visual']['pyqtgraph'] = args.pyqtgraph
	if config['visual']['scatter'] is None or hasattr(args, 'scatter'+DEST_SUFFIX):
		config['visual']['scatter'] = args.scatter
	if config['server_mode']['service'] is None or hasattr(args, 'noservice'+DEST_SUFFIX):
		config['server_mode']['service'] = not args.noservice
	if config['server_mode']['raw'] is None or hasattr(args, 'raw'+DEST_SUFFIX):
		config['server_mode']['raw'] = args.raw
	if config['server_mode']['visualize'] is None or hasattr(args, 'visualize'+DEST_SUFFIX):
		config['server_mode']['visualize'] = args.visualize
	if config['server_mode']['enumerate'] is None or hasattr(args, 'enumerate'+DEST_SUFFIX):
		config['server_mode']['enumerate'] = args.enumerate
	if config['server_mode']['debug'] is None or hasattr(args, 'debug'+DEST_SUFFIX):
		config['server_mode']['debug'] = args.debug
	if config['server_mode']['out_filename'] is None or hasattr(args, 'output'+DEST_SUFFIX):
		config['server_mode']['out_filename'] = args.output
	if config['serial']['imu'] is None or hasattr(args, 'imu'+DEST_SUFFIX):
		config['serial']['imu'] = args.imu
	if config['process']['intermediate'] is None or hasattr(args, 'intermediate'+DEST_SUFFIX):
		config['process']['intermediate'] = args.intermediate

	## some modifications
	if args.filenames:
		config['server_mode']['use_file'] = True
		config['server_mode']['in_filenames'] = args.filenames

	check_config(config)
	return config

def run(config):
	ret = None

	## enumerate serial ports
	if config['server_mode']['enumerate']:
		enumerate_ports()
		return

	print_sensor(config)

	## shared variables
	## output data array
	data_out = Array('d', config['sensor']['total'])  # d for double
	## raw data array
	data_raw = Array('d', config['sensor']['total'])  # d for double
	## imu data array
	data_imu = Array('d', 6)  # d for double
	## frame index
	idx_out = Value('i')  # i for signed int
	## Proc-Userver communication pipe
	pipe_proc, pipe_server = Pipe(duplex=True)

	## function parameters
	paras = {
		"config": config,
		"data_out": data_out,
		"data_raw": data_raw,
		"data_imu": data_imu,
		"idx_out": idx_out,
		"pipe_proc": pipe_proc,
		"pipe_server": pipe_server,
	}

	if config['server_mode']['use_file']:
		task_file(paras)
		return

	if config['server_mode']['visualize']:
		p = Process(target=task_serial, args=(paras,))
		p.start()

		if not config['visual']['pyqtgraph']:
			from matsense.visual.player_matplot import Player3DMatplot as Player
			print("Activate visualization using matplotlib")
		else:
			from matsense.visual.player_pyqtgraph import Player3DPyqtgraph as Player
			print("Activate visualization using pyqtgraph")
		## visualization must be in main process
		from matsense.visual import gen_reshape
		my_player = Player(
			zlim=config['visual']['zlim'], 
			N=config['sensor']['shape'],
			scatter=config['visual']['scatter']
		)
		my_player.run_stream(
			generator=gen_reshape(data_out, config['sensor']['shape']), 
			fps=config['visual']['fps']
		)

		p.join()
	else:
		if config['server_mode']['service']:
			p_server = Process(target=task_server, args=(paras,))
			p_server.start()

		ret = task_serial(paras)

		if config['server_mode']['service']:
			p_server.join()
	
	del data_out
	del data_raw
	del data_imu
	del idx_out
	del pipe_proc, pipe_server

	return ret


def main():
	parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
	parser.add_argument('-e', dest='enumerate', action=make_action('store_true'), default=False, help="enumerate all serial ports")
	parser.add_argument('-p', dest='port', action=make_action('store'), default=PORT, help="specify serial port")
	parser.add_argument('-b', dest='baudrate', action=make_action('store'), default=BAUDRATE, type=int, help="specify baudrate")
	parser.add_argument('-t', dest='timeout', action=make_action('store'), default=TIMEOUT, type=float, help="specify timeout in seconds")
	parser.add_argument('-n', dest='n', action=make_action('store'), default=[N], type=int, nargs='+', help="specify sensor shape")
	parser.add_argument('--noservice', dest='noservice', action=make_action('store_true'), default=False, help="do not run service (only serial data receiving & processing)")
	parser.add_argument('-a', '--address', dest='address', action=make_action('store'), help="specify server socket address")
	parser.add_argument('-u', '--udp', dest='udp', action=make_action('store_true'), default=UDP, help="use UDP protocol")
	parser.add_argument('-r', '--raw', dest='raw', action=make_action('store_true'), default=False, help="raw data mode")
	parser.add_argument('-nc', '--no_convert', dest='no_convert', action=make_action('store_true'), default=NO_CONVERT, help="do not apply voltage-resistance conversion")
	parser.add_argument('-v', '--visualize', dest='visualize', action=make_action('store_true'), default=False, help="enable visualization")
	parser.add_argument('-z', '--zlim', dest='zlim', action=make_action('store'), default=ZLIM, type=float, help="z-axis limit")
	parser.add_argument('-f', dest='fps', action=make_action('store'), default=FPS, type=int, help="frames per second")
	parser.add_argument('--scatter', dest='scatter', action=make_action('store_true'), default=False, help="show scatter plot")
	parser.add_argument('--pyqtgraph', dest='pyqtgraph', action=make_action('store_true'), default=False, help="use pyqtgraph to plot")
	# parser.add_argument('-m', '--matplot', dest='matplot', action=make_action('store_true'), default=False, help="use matplotlib to plot")
	parser.add_argument('--config', dest='config', action=make_action('store'), default=None, help="specify configuration file")
	parser.add_argument('-d', '--debug', dest='debug', action=make_action('store_true'), default=DEBUG, help="debug mode")

	parser.add_argument('filenames', nargs='*', action='store', help="use file(s) as data source instead of serial port")
	parser.add_argument('-o', dest='output', action=make_action('store'), default=OUTPUT_FILENAME, help="output processed data to file")

	parser.add_argument('-i', '--imu', dest='imu', action=make_action('store_true'), default=False, help="support IMU")

	parser.add_argument('--intermediate', dest='intermediate', action=make_action('store'), default=INTERMEDIATE, type=int, help="specify intermediate result")

	args = parser.parse_args()
	config = prepare_config(args)

	while True:
		## run according to config
		ret = run(config)

		if ret != None:
			if ret[0] == 1:  ## restart
				config = ret[1]
				continue

		## exit program
		break


if __name__ == '__main__':
	main()
