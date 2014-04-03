import json
import xor # for encoding password
class Config:
	"""Persist config object in a file.  Provide encoding and decoding of password"""
	CFG_FILEPATH = "cfg.json"
	
	def __init__(self, cfg_items, **kwattrs):
		self.save_pwd = 0
		for k in cfg_items.keys():
			if k in kwattrs:
				setattr(self, k, kwattrs[k])
			else:
				setattr(self, k, cfg_items[k])

	def Load(self, fpath = None):
		config_filepath = fpath or Config.CFG_FILEPATH
	
		try:
			with open(config_filepath, "r") as f:
				jresult = f.read()
		except IOError as e:
			print "Didn't load config file: "+ e.strerror 
			return # return None if didn't load, so caller can add data (e.g., on first run) and save it later.
		try:
			j = json.loads(jresult)
		except ValueError as e:
			return "JSON interpretation problem",`e`
			
		# set attrs in config
		for k, v in j.items():
			setattr(self, k, v)
		if self.enc_passwd:
			self.passwd = xor.xor_crypt_string(self.enc_passwd, decode=True)
		
		
	def Save(self, fpath = None):
		"""Save Config info before close"""
		config_filepath = fpath or Config.CFG_FILEPATH
		if self.save_pwd > 0: # only persist password if asked to 
			# "checked" value in 'save pwd' UI button is 0 if unchecked 1 if checked
			# code up (obsfuscate) password for local storage
			# NOTE: this is NOT secure encryption.
			self.enc_passwd = xor.xor_crypt_string(self.passwd, encode=True)
		else:
			self.enc_passwd = ""
		p = self.passwd
		delattr(self, 'passwd') # don't dump passwd
		jresult = json.dumps(self, default=lambda o: o.__dict__, indent = 2, sort_keys = True)
		setattr(self, 'passwd', p) # reinstate
		with open(config_filepath, "w") as f:
			f.write(jresult)
