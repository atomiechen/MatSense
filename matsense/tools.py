import yaml
import copy
import pkgutil
import ast
import numpy as np

from pyparsing import (Literal, CaselessLiteral, Word, Combine, Group, Optional,
					   ZeroOrMore, Forward, nums, alphas, oneOf)
import math
import operator
import argparse


## blank config
TEMPLATE_PATH = "blank_template.yaml"
_data = pkgutil.get_data(__name__, TEMPLATE_PATH)
BLANK = yaml.safe_load(_data)
## argparse additional argument suffix
DEST_SUFFIX = '_specified'


def parse_ip_port(content):
	paras = content.split(":")
	ip = paras[0]
	port = None
	if len(paras) >= 2:
		port = int(paras[1])
	return (ip, port)


def dump_ip_port(ip_port):
	ip, port = ip_port
	return str(ip)+":"+str(port)


def check_shape(n):
	try:
		n[1]
		n = (n[0], n[1])
	except:
		try: 
			n[0]
			n = (n[0], n[0])
		except:
			n = (n, n)
	return n


def parse_mask(string_in):
	rows = string_in.splitlines()
	mask = [row.split() for row in rows]
	mask = np.array(mask, dtype=int)
	return mask

def dump_mask(mask_array):
	lines = []
	for row in mask_array:
		str_list = [str(item) for item in row]
		lines.append(" ".join(str_list))
	return "\n".join(lines)

## recursion, fill dict_target according to dict_default
def __recurse(dict_default, dict_target):
	for key in dict_default:
		if key in dict_target:
			if dict_target[key] is None:
				dict_target[key] = copy.deepcopy(dict_default[key])
			elif isinstance(dict_default[key], dict):
				__recurse(dict_default[key], dict_target[key])
		else:
			dict_target[key] = copy.deepcopy(dict_default[key])


def check_config(config):
	## recurse to fill empty fields
	__recurse(BLANK, config)
	## some transformation for certain fields
	if config['sensor']['shape'] is not None:
		config['sensor']['shape'] = check_shape(config['sensor']['shape'])
		config['sensor']['total'] = config['sensor']['shape'][0] * config['sensor']['shape'][1]
	if config['process']['interp'] is not None:
		config['process']['interp'] = check_shape(config['process']['interp'])
	if isinstance(config['sensor']['mask'], str):
		config['sensor']['mask'] = parse_mask(config['sensor']['mask'])
	if isinstance(config['connection']['server_address'], str):
		config['connection']['server_address'] = parse_ip_port(config['connection']['server_address'])
	if isinstance(config['connection']['client_address'], str):
		config['connection']['client_address'] = parse_ip_port(config['connection']['client_address'])
	if isinstance(config['process']['V0'], str):
		nsp = NumericStringParser()
		config['process']['V0'] = nsp.eval(config['process']['V0'])
		# ## dangerous to use 'eval'
		# config['process']['V0'] = eval(config['process']['V0'])


def parse_config(content):
	config = yaml.safe_load(content)
	check_config(config)
	return config


def load_config(filename):
	with open(filename, 'r', encoding='utf-8') as fin:
		config = yaml.safe_load(fin)
	check_config(config)
	return config


def dump_config(config):
	config_copy = copy.deepcopy(config)

	## some transformation for certain fields
	if config_copy['sensor']['mask'] is not None:
		config_copy['sensor']['mask'] = dump_mask(config_copy['sensor']['mask'])
	if config_copy['connection']['server_address'] is not None:
		config_copy['connection']['server_address'] = dump_ip_port(config_copy['connection']['server_address'])
	if config_copy['connection']['client_address'] is not None:
		config_copy['connection']['client_address'] = dump_ip_port(config_copy['connection']['client_address'])

	return yaml.safe_dump(config_copy)


def blank_config():
	return copy.deepcopy(BLANK)


def combine_config(configA, configB):
	config = copy.deepcopy(configA)
	__recurse(configB, config)
	check_config(config)
	return config


def print_sensor(config, tab=''):
	print(f"{tab}Sensor shape: {config['sensor']['shape']}")
	print(f"{tab}Sensor size:  {config['sensor']['total']}")
	print(f"{tab}Sensor mask:  {'' if config['sensor']['mask'] is not None else None}")
	if config['sensor']['mask'] is not None:
		print(f"{config['sensor']['mask']}")


## ref: https://stackoverflow.com/a/2371789/11854304
class NumericStringParser(object):
	'''
	Most of this code comes from the fourFn.py pyparsing example

	'''

	def pushFirst(self, strg, loc, toks):
		self.exprStack.append(toks[0])

	def pushUMinus(self, strg, loc, toks):
		if toks and toks[0] == '-':
			self.exprStack.append('unary -')

	def __init__(self):
		"""
		expop   :: '^'
		multop  :: '*' | '/'
		addop   :: '+' | '-'
		integer :: ['+' | '-'] '0'..'9'+
		atom    :: PI | E | real | fn '(' expr ')' | '(' expr ')'
		factor  :: atom [ expop factor ]*
		term    :: factor [ multop factor ]*
		expr    :: term [ addop term ]*
		"""
		point = Literal(".")
		e = CaselessLiteral("E")
		fnumber = Combine(Word("+-" + nums, nums) +
						  Optional(point + Optional(Word(nums))) +
						  Optional(e + Word("+-" + nums, nums)))
		ident = Word(alphas, alphas + nums + "_$")
		plus = Literal("+")
		minus = Literal("-")
		mult = Literal("*")
		div = Literal("/")
		lpar = Literal("(").suppress()
		rpar = Literal(")").suppress()
		addop = plus | minus
		multop = mult | div
		expop = Literal("^")
		pi = CaselessLiteral("PI")
		expr = Forward()
		atom = ((Optional(oneOf("- +")) +
				 (ident + lpar + expr + rpar | pi | e | fnumber).setParseAction(self.pushFirst))
				| Optional(oneOf("- +")) + Group(lpar + expr + rpar)
				).setParseAction(self.pushUMinus)
		# by defining exponentiation as "atom [ ^ factor ]..." instead of
		# "atom [ ^ atom ]...", we get right-to-left exponents, instead of left-to-right
		# that is, 2^3^2 = 2^(3^2), not (2^3)^2.
		factor = Forward()
		factor << atom + \
			ZeroOrMore((expop + factor).setParseAction(self.pushFirst))
		term = factor + \
			ZeroOrMore((multop + factor).setParseAction(self.pushFirst))
		expr << term + \
			ZeroOrMore((addop + term).setParseAction(self.pushFirst))
		# addop_term = ( addop + term ).setParseAction( self.pushFirst )
		# general_term = term + ZeroOrMore( addop_term ) | OneOrMore( addop_term)
		# expr <<  general_term
		self.bnf = expr
		# map operator symbols to corresponding arithmetic operations
		epsilon = 1e-12
		self.opn = {"+": operator.add,
					"-": operator.sub,
					"*": operator.mul,
					"/": operator.truediv,
					"^": operator.pow}
		self.fn = {"sin": math.sin,
				   "cos": math.cos,
				   "tan": math.tan,
				   "exp": math.exp,
				   "abs": abs,
				   "trunc": lambda a: int(a),
				   "round": round,
				   "sgn": lambda a: (a>0)-(a<0)}

	def evaluateStack(self, s):
		op = s.pop()
		if op == 'unary -':
			return -self.evaluateStack(s)
		if op in "+-*/^":
			op2 = self.evaluateStack(s)
			op1 = self.evaluateStack(s)
			return self.opn[op](op1, op2)
		elif op == "PI":
			return math.pi  # 3.1415926535
		elif op == "E":
			return math.e  # 2.718281828
		elif op in self.fn:
			return self.fn[op](self.evaluateStack(s))
		elif op[0].isalpha():
			return 0
		else:
			return float(op)

	def eval(self, num_string, parseAll=True):
		self.exprStack = []
		results = self.bnf.parseString(num_string, parseAll)
		val = self.evaluateStack(self.exprStack[:])
		return val

## If the user specified a value (whether it equals default or not), a new 
## renamed attribute will be set True to record this event.
## If the code fails, fall back to orginal behaviors.
def make_action(action_keyword, dest_suffix=DEST_SUFFIX):
	try:
		## ref: argparse source code, and https://stackoverflow.com/a/50936474/11854304
		action_base_class = argparse.ArgumentParser()._registry_get('action', action_keyword)
		# print(action_base_class)
		class FooAction(action_base_class):
			def __call__(self, parser, namespace, values, option_string=None):
				super().__call__(parser, namespace, values, option_string)
				# setattr(namespace, self.dest, values)
				setattr(namespace, self.dest+dest_suffix, True)
		return FooAction
	except:
		return action_keyword


if __name__ == '__main__':
	a = parse_ip_port("192.168.1.1:255")
	b = parse_ip_port("192.168.1.1")
	c = check_shape([3,4])
	nsp = NumericStringParser()
	d = nsp.eval("255/3.6*3.3")
	print(a, b, c, d)
