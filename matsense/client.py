import argparse
try:
	import readline
except ImportError:
	pass
import copy
from socket import timeout

from matsense.cmd import CMD
from matsense.uclient import Uclient
from matsense.process import Processor
from matsense.tools import (
	load_config, blank_config, check_config, make_action, DEST_SUFFIX
)

N = 16
ZLIM = 3
FPS = 194
TH = 0.15
UDP = False

def print_paras(paras):
	print(f"Server parameters:")
	print(f"  initiating frame number: {paras[0]}")
	print(f"  calibration window size: {paras[1]}")
	print(f"  filter:  {paras[2]}")
	my_filter = paras[2]
	if my_filter == 0:
		print(f"    None")
	elif my_filter == 1:
		print(f"    exponential smoothing")
		print(f"    * ALPHA: {paras[3]}")
		print(f"    * BETA:  {paras[4]}")
	elif my_filter == 2:
		print(f"    moving average")
		print(f"    * kernel size: {paras[3]}")
	elif my_filter == 3:
		print(f"    sinc low-pass filter")
		print(f"    * kernel size:       {paras[3]}")
		print(f"    * cut-off frequency: {paras[4]}")

def interactive_cmd(my_client, my_cmd):
	"""interactive command parser

	Show hints to help input specific parameters.
	
	Args:
		my_cmd (CMD): a predefined command
	"""
	if my_cmd not in CMD.__members__.values():
		print("Unknown command!")
		return

	try:
		if my_cmd == CMD.CLOSE:
			my_client.send_cmd(my_cmd)
		elif my_cmd in (CMD.DATA, CMD.RAW):
			my_client.send_cmd(my_cmd)
			frame_idx = my_client.recv_frame()[1]
			print(f"frame_idx: {frame_idx}")
		elif my_cmd in (CMD.REC_DATA, CMD.REC_RAW):
			print(f"recording filename:")
			my_filename = input("|> ").strip()
			my_client.send_cmd(my_cmd, my_filename)
			ret, recv_filename = my_client.recv_string()
			if ret == 0:
				if my_cmd == CMD.REC_DATA:
					data_mode = "processed"
				else:
					data_mode = "raw"
				print(f"recording {data_mode} data to file: {recv_filename}")
			else:
				print(f"fail to write to file: {recv_filename}")
		elif my_cmd == CMD.REC_STOP:
			my_client.send_cmd(my_cmd)
			ret, recv_str = my_client.recv_string()
			if ret == 0:
				print("stop recording")
			else:
				print("fail to stop recording!")
		elif my_cmd == CMD.RESTART:
			try:
				print(f"initiating frame number:")
				obtained = input("|> ").strip()
				if obtained:
					my_initcali = int(obtained)
				else:
					my_initcali = -1
				print(f"{my_initcali}")
				print(f"calibration window size:")
				obtained = input("|> ").strip()
				if obtained:
					my_win = int(obtained)
				else:
					my_win = -1
				print(f"{my_win}")
				print(f"filter:")
				obtained = input("|> ").strip()
				if obtained:
					my_filter = int(obtained)
				else:
					my_filter = -1
				print(f"{my_filter}")
				args = [my_initcali, my_win, my_filter]
				if my_filter == 1:
					print(f"exponential smoothing.")
					print(f"alpha:")
					obtained = input("|> ").strip()
					if obtained:
						my_alpha = float(obtained)
					else:
						my_alpha = -1.0
					print(f"{my_alpha}")
					print(f"beta:")
					obtained = input("|> ").strip()
					if obtained:
						my_beta = float(obtained)
					else:
						my_beta = -1.0
					print(f"{my_beta}")
					args.append(my_alpha)
					args.append(my_beta)
				elif my_filter == 2:
					print(f"moving average.")
					print(f"kernel size:")
					obtained = input("|> ").strip()
					if obtained:
						my_ma_size = int(obtained)
					else:
						my_ma_size = -1
					print(f"{my_ma_size}")
					args.append(my_ma_size)
				elif my_filter == 3:
					print(f"sinc low-pass filter.")
					print(f"kernel size:")
					obtained = input("|> ").strip()
					if obtained:
						my_lp_size = int(obtained)
					else:
						my_lp_size = -1
					print(f"{my_lp_size}")
					print(f"cut-off frequency:")
					obtained = input("|> ").strip()
					if obtained:
						my_lp_w = float(obtained)
					else:
						my_lp_w = -1.0
					print(f"{my_lp_size}")
					args.append(my_lp_size)
					args.append(my_lp_w)

				my_client.send_cmd(my_cmd, args=args)
				results = my_client.recv_paras()
				if results[0] == 0:
					print(f"server restarting...")
				else:
					print("fail to restart server")
				print_paras(results[1:])
			except ValueError:
				print("invalid arguments to restart server")
		elif my_cmd == CMD.PARAS:
			my_client.send_cmd(my_cmd)
			results = my_client.recv_paras()
			print_paras(results[1:])
		elif my_cmd == CMD.REC_BREAK:
			my_client.send_cmd(my_cmd)
			ret, recv_str = my_client.recv_string()
			if ret == 0:
				print("successfully break")
			else:
				print("fail to break!")
		elif my_cmd == CMD.DATA_IMU:
			my_client.send_cmd(my_cmd)
			data_imu, frame_idx = my_client.recv_imu()
			print(f"IMU data: {data_imu}")
			print(f"frame_idx: {frame_idx}")

	except (FileNotFoundError, ConnectionResetError):
		print("server off-line")
	except ConnectionRefusedError:
		print("server refused connection")
	except timeout:
		print("server no response")

def run_client_interactive(my_client):
	while True:
		try:
			data = input('>> ').strip()
			if data and "quit".startswith(data) or data == "exit":
				return
		except (EOFError, KeyboardInterrupt):
			return

		try:
			data = data.strip().split()
			if not data:
				raise Exception
			my_cmd = int(data[0])
		except:
			continue

		interactive_cmd(my_client, my_cmd)

def prepare_config(args):
	## load config and combine commandline arguments
	if args.config:
		config = load_config(args.config)
	else:
		config = blank_config()
	## priority: commandline arguments > config file > program defaults
	if config['sensor']['shape'] is None or hasattr(args, 'n'+DEST_SUFFIX):
		config['sensor']['shape'] = args.n
	if config['connection']['udp'] is None or hasattr(args, 'udp'+DEST_SUFFIX):
		config['connection']['udp'] = args.udp
	if config['connection']['server_address'] is None or hasattr(args, 'server_address'+DEST_SUFFIX):
		config['connection']['server_address'] = args.server_address
	if config['connection']['client_address'] is None or hasattr(args, 'client_address'+DEST_SUFFIX):
		config['connection']['client_address'] = args.client_address
	if config['process']['interp'] is None or hasattr(args, 'interp'+DEST_SUFFIX):
		config['process']['interp'] = args.interp
	if config['process']['blob'] is None or hasattr(args, 'noblob'+DEST_SUFFIX):
		config['process']['blob'] = not args.noblob
	if config['process']['threshold'] is None or hasattr(args, 'threshold'+DEST_SUFFIX):
		config['process']['threshold'] = args.threshold
	if config['visual']['zlim'] is None or hasattr(args, 'zlim'+DEST_SUFFIX):
		config['visual']['zlim'] = args.zlim
	if config['visual']['fps'] is None or hasattr(args, 'fps'+DEST_SUFFIX):
		config['visual']['fps'] = args.fps
	if config['visual']['pyqtgraph'] is None or hasattr(args, 'matplot'+DEST_SUFFIX):
		config['visual']['pyqtgraph'] = not args.matplot
	if config['visual']['scatter'] is None or hasattr(args, 'scatter'+DEST_SUFFIX):
		config['visual']['scatter'] = args.scatter
	if config['visual']['show_value'] is None or hasattr(args, 'show_value'+DEST_SUFFIX):
		config['visual']['show_value'] = args.show_value
	if config['client_mode']['raw'] is None or hasattr(args, 'raw'+DEST_SUFFIX):
		config['client_mode']['raw'] = args.raw
	if config['client_mode']['interactive'] is None or hasattr(args, 'interactive'+DEST_SUFFIX):
		config['client_mode']['interactive'] = args.interactive
	check_config(config)

	## some modifications
	if config['process']['interp'] is None:
		config['process']['interp'] = copy.deepcopy(config['sensor']['shape'])

	return config


def main():
	parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
	parser.add_argument('--server_address', dest='server_address', action=make_action('store'), help="specify server socket address")
	parser.add_argument('--client_address', dest='client_address', action=make_action('store'), help="specify client socket address")
	parser.add_argument('-u', '--udp', dest='udp', action=make_action('store_true'), default=UDP, help="use UDP protocol")
	parser.add_argument('-r', '--raw', dest='raw', action=make_action('store_true'), default=False, help="plot raw data")
	parser.add_argument('-n', dest='n', action=make_action('store'), default=[N], type=int, nargs='+', help="specify sensor shape")
	parser.add_argument('--interp', dest='interp', action=make_action('store'), default=None, type=int, nargs='+', help="interpolated shape")
	parser.add_argument('--noblob', dest='noblob', action=make_action('store_true'), default=False, help="do not filter out blob")
	parser.add_argument('--th', dest='threshold', action=make_action('store'), default=TH, type=float, help="blob filter threshold")
	parser.add_argument('-i', '--interactive', dest='interactive', action=make_action('store_true'), default=False, help="interactive mode")
	parser.add_argument('-z', '--zlim', dest='zlim', action=make_action('store'), default=ZLIM, type=float, help="z-axis limit")
	parser.add_argument('-f', dest='fps', action=make_action('store'), default=FPS, type=int, help="frames per second")
	parser.add_argument('-m', '--matplot', dest='matplot', action=make_action('store_true'), default=False, help="use mathplotlib to plot")
	parser.add_argument('--config', dest='config', action=make_action('store'), default=None, help="specify configuration file")

	parser.add_argument('--scatter', dest='scatter', action=make_action('store_true'), default=False, help="show scatter plot")
	parser.add_argument('--show_value', dest='show_value', action=make_action('store_true'), default=False, help="show area value")

	args = parser.parse_args()
	config = prepare_config(args)

	with Uclient(
		config['connection']['client_address'], 
		config['connection']['server_address'], 
		udp=config['connection']['udp'], 
		n=config['sensor']['shape']
	) as my_client:
		if config['client_mode']['interactive']:
			print("Interactive mode")
			run_client_interactive(my_client)
		else:
			print("Plot mode")
			if config['visual']['pyqtgraph']:
				from matsense.visual.player_pyqtgraph import Player3DPyqtgraph as Player
			else:
				from matsense.visual.player_matplot import Player3DMatplot as Player
			if config['client_mode']['raw']:
				print("  raw data")
				input_arg = CMD.RAW
				config['process']['blob'] = False
			else:
				print("  processed data")
				input_arg = CMD.DATA

			my_processor = Processor(
				config['process']['interp'], 
				blob=config['process']['blob'], 
				threshold=config['process']['threshold'],
				order=config['process']['interp_order'],
				total=config['process']['blob_num'],
				special=config['process']['special_check'],
			)
			my_processor.print_info()
			my_player = Player(
				zlim=config['visual']['zlim'], 
				N=config['process']['interp'],
				scatter=config['visual']['scatter'],
				show_value=config['visual']['show_value']
			)

			my_generator = my_client.gen(input_arg)
			my_generator = my_processor.gen_wrapper(my_generator)
			my_player.run_stream(
				generator=my_generator, 
				fps=config['visual']['fps']
			)


if __name__ == '__main__':
	main()
