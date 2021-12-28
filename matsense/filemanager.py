import os
import glob
import numpy as np
from datetime import datetime
from typing import Iterable


## Convenient module to instantly write to files by closing the file after each writing operation
## Helpful when there are multiple writings and the program may be interrupted midway

ENCODING = 'utf-8'

## check if the file root path exists, and create if not
def check_root(filename):
	root_dir, bare_filename = os.path.split(filename)
	if root_dir and not os.path.exists(root_dir):
		# os.mkdir(root_dir)
		os.makedirs(root_dir)

## write content to file
def write(filename, content, override=False):
	check_root(filename)
	mode = 'w' if override else 'a'
	with open(filename, mode, encoding=ENCODING) as fout:
		fout.write(content)

## write multiple lines to file
def writelines(filename, lines, override=False):
	check_root(filename)
	mode = 'w' if override else 'a'
	with open(filename, mode, encoding=ENCODING) as fout:
		fout.writelines(lines)

## read all lines in file into a list
def readlines(filename):
	with open(filename, 'r', encoding=ENCODING) as fin:
		ret = fin.readlines()
	return ret

## find all files according to pattern (including paths)
def findall(pattern):
	return glob.glob(pattern)

## parse a string line into matrix sensor format: 
## data_out (an array of points), frame_idx, date_time (or tags)
def parse_line(line, points=256, delim=',', data_out=None):
	paras = line.strip().split(delim)
	if data_out is None:
		data_out = np.zeros(points)
	try:
		for i in range(points):
			data_out[i] = float(paras[i])
	except:
		pass
	try:
		frame_idx = int(paras[points])
	except:
		frame_idx = -1
	try:
		time_stamp = int(paras[points+1]) / 1000000
		date_time = datetime.fromtimestamp(time_stamp)
	except:
		date_time = None
	return data_out, frame_idx, date_time

## write a line to file
## format: data (Iterable), tags (str / Iterable / other type except None)
def write_line(filename, data, tags=None, delim=',', override=False):
	items = [str(item) for item in data]
	if isinstance(tags, str):
		items.append(tags)
	elif isinstance(tags, Iterable):
		for tag in tags:
			items.append(str(tag))
	elif tags is not None:
		items.append(str(tags))
	content = delim.join(items) + "\n"
	write(filename, content, override=override)

## write multiple lines to file
## format: data (2d Iterable), tags (str / Iterable / other type except None)
def write_lines(filename, data, tags=None, delim=',', override=False):
	tags_list = []
	if isinstance(tags, str):
		tags_list.append(tags)
	elif isinstance(tags, Iterable):
		for tag in tags:
			tags_list.append(str(tag))
	elif tags is not None:
		tags_list.append(str(tags))
	lines = []
	for row in data:
		items = [str(item) for item in row]
		if tags_list:
			items += tags_list
		content = delim.join(items) + "\n"
		lines.append(content)
	writelines(filename, lines, override=override)

## clear file content
def clear_file(filename):
	check_root(filename)
	with open(filename, "w", encoding=ENCODING):
		pass
