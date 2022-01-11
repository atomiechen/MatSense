from enum import IntEnum


class FLAG(IntEnum):

	## aboud program state
	FLAG_RUN = 0
	FLAG_STOP = 1
	FLAG_RESTART = 2

	## about data recording
	FLAG_REC_STOP = 3
	FLAG_REC_DATA = 4
	FLAG_REC_RAW = 5

	FLAG_REC_RET_SUCCESS = 7
	FLAG_REC_RET_STOP = 8
	FLAG_REC_RET_FAIL = 9
