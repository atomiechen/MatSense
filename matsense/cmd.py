from enum import IntEnum

class CMD(IntEnum):

	"""Pre-defined commands for communication with server.
	
	Attributes:
		CLOSE (int): Close the server
		DATA (int): get processed data frame and frame index
		RAW (int): get raw data frame and frame index
		REC_DATA (int): record processed data to file
		REC_RAW (int): record raw data to file
		REC_STOP (int): stop recording
		RESTART (int): restart the server with processing parameters
		PARAS (int): get current processing parameters of the server
		REC_BREAK (int): stop current recording and start a new one
		DATA_IMU (int): get IMU data frame and frame index
	"""
	
	CLOSE = 0
	DATA = 1
	RAW = 2
	REC_DATA = 3
	REC_RAW = 4
	REC_STOP = 5
	RESTART = 6
	PARAS = 7
	REC_BREAK = 8
	DATA_IMU = 9
