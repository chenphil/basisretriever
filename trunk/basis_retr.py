import sys
import re
import urllib2
import urllib
import os.path
from cookielib import CookieJar
import json
import csv #for csv conversion
import datetime
# need to comment this out for py2exe?
#sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

class BasisRetr:
	LOGIN_URL = 'https://app.mybasis.com/login'
	UID_URL = 'https://app.mybasis.com/api/v1/user/me.json'
	
	def __init__(self, loginid, passwd, savedir, userid = None):
		# if there's a config file, get 
		self.access_token = None # session token from website
		try: # need all three passed in; if not, then barf
			self.loginid = loginid
			self.passwd = passwd
			self.savedir = savedir
			self.userid = userid
		except Exception, v:
			print "Didn't get required variable", `v`

	def Login(self):
		"""Log in to basis website to get session (access) token"""
		opener = urllib2.build_opener()
		self.cj = CookieJar()
		self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cj))
		form_data = {'next': 'https://app.mybasis.com',
			'submit': 'Login',
			'username': self.loginid,
			'password': self.passwd}
		enc_form_data = urllib.urlencode(form_data)
		f = self.opener.open(BasisRetr.LOGIN_URL, enc_form_data)
		content = f.read()
		m = re.search('error_string\s*=\s*"(.+)"', content, re.MULTILINE)
		if m:
			raise Exception(m.group(1))
		
		for cookie in self.cj:
			if cookie.name == 'access_token':
				self.access_token = cookie.value
			# saving the refresh token because we can.  Not really using it, though
			if cookie.name == 'refresh_token':
				self.refresh_token = cookie.value
		
		# make sure we got the access token
		if not self.access_token:
			print "Didn't find an access token in:",
			for cookie in self.cj:
				print "("+cookie.name+"="+cookie.value+") ",
		else:
			print "Logged in, Got Access Token = ",self.access_token
		
	def GetUserID(self):
		"""Retrieve the long hex string that uniquely identifies a user from the Basis website."""
		if not self.access_token:
			raise Exception('no token', 'no access token found-may be internet connectivity or bad login info.')
		self.opener.addheaders = [('X-Basis-Authorization', "OAuth "+self.access_token)]
		f = self.opener.open(BasisRetr.UID_URL)
		content = f.read()
		jresult = json.loads(content)
		#print json.dumps(jresult)
		self.userid= None
		if 'id' in jresult:
			self.userid = jresult['id']

	def GetMetricsForDay(self, date):
		# Need userid in order to get metrics
		print "checking uid=",self.userid
		if not self.userid:
			self.GetUserID()
			print "retrieved userid from website=",self.userid
		metrics = ['heartrate', 'steps', 'calories', 'gsr', 'skin_temp', 'air_temp']
		params = 'interval=60&units=s&start_date='+date+'&start_offset=0&end_offset=0&summary=true&bodystates=true'
		for m in metrics:
			params +="&"+m+"=tue"
		
		url = "https://app.mybasis.com/api/v1/chart/"+self.userid+".json?"+params

		return self.GetJsonData(url)
		
	def GetActivitiesForDay(self, date):
		url = "https://app.mybasis.com/api/v2/users/me/days/"+date+"/activities?expand=activities&type=run,walk,bike,sleep"
		return self.GetJsonData(url)

	def GetSleepForDay(self, date):
		url = "https://app.mybasis.com/api/v2/users/me/days/"+date+"/activities?expand=activities&type=sleep"
		return self.GetJsonData(url)

	def GetJsonData(self, url):
		print url
		f = self.opener.open(url)
		content = f.read()
		return json.loads(content)

	def SaveDataForDay(self, json_data, fname):
		fpath = os.path.join(os.path.abspath(self.savedir), fname)
		try:
			fh = file(os.path.abspath(fpath), "w")
			fh.write(json.dumps(json_data))
		except IOError, v:
			print "problem saving file to:"+fpath+"\n--Error: "+v
		fh.close()
				

#from Bandsaw
def SaveCsv(fpath, j):
	with open(fpath, 'wb') as csv_file:
		writer = csv.writer(csv_file)
		writer.writerow(['timestamp', 'skin_temp', 'air_temp', 'heartrate', 'steps', 'gsr', 'calories'])
	append_to_csv(fpath, j)

def append_to_csv(fpath,j):
	"""Takes JSON and flattens into CSVs."""
	with open(fpath, 'ab') as csv_file:
		writer = csv.writer(csv_file)
		if 'endtime' not in j:
			return
		for i in range((j['endtime'] - j['starttime']) / j['interval']):
			unix_time_utc = j['starttime'] + i*j['interval']

			skin_temp = j['metrics']['skin_temp']['values'][i]
			air_temp = j['metrics']['air_temp']['values'][i]
			heartrate = j['metrics']['heartrate']['values'][i]
			steps = j['metrics']['steps']['values'][i]
			gsr = j['metrics']['gsr']['values'][i]
			calories = j['metrics']['calories']['values'][i]

			timestamp = datetime.datetime.fromtimestamp(unix_time_utc)
			writer.writerow([timestamp, skin_temp, air_temp, heartrate, steps, gsr, calories])

	
import pprint
def ppp(object):
	"""debugging support: pretty print any object"""
	pprint.PrettyPrinter().pprint(object)

CFG_FILENAME = "band_retr.cfg"
def main():
	date='2014-01-20'
	cfg = LoadConfig(CFG_FILENAME)
	loginid = 'loginid' in cfg and cfg['loginid'] or 'rg1@rawds.com'
	passwd = 'passwd' in cfg and cfg['passwd'] or 'Mainlab5'
	savedir = 'savedir' in cfg and cfg['savedir'] or './data'
	userid = 'userid' in cfg and cfg['userid'] or None
	b = BasisRetr(loginid, passwd, savedir, userid)
	
	try:
		b.Login()
		print "Logged in successfully"
	except Exception, e:
		print "Login Error:",e
		return
				
	print "getting metrics for "+date
	m = b.GetMetricsForDay(date)
	b.SaveDataForDay(m, date+"_basis_metrics.json")
	print "getting activites for "+date
	m = b.GetActivitiesForDay(date)
	b.SaveDataForDay(m, date+"_basis_activities.json")
	m = b.GetSleepForDay(date)
	b.SaveDataForDay(m, date+"_basis_sleep.json")
	cfg['loginid'] = b.loginid
	cfg['passwd'] = b.passwd
	cfg['savedir'] = b.savedir
	cfg['userid'] = b.userid
	SaveConfig(CFG_FILENAME, cfg)

try: # for saving config data
	import cPickle as pickle
except ImportError:
	import pickle # fall back on Python version

def LoadConfig(fname):
	try:
		fh = file(fname, "r")
		cfg = pickle.load(fh)
		fh.close()
	except IOError, v:
		print "didn't load file: "+ v 
		return # return None if didn't load, so caller can add data (e.g., on first run) and save it later.
	#print "passwd=",self.cfg['passwd'], 'em=',self.cfg['userid']
	return cfg

def SaveConfig(fname, cfg):
	"""Save Config info before close"""
	fh = None
	try:
		fh = file(fname, "w")
		pickle.dump(cfg, fh)
	except IOError, v:
		print("didn't save file: "+ v)
	if fh: fh.close()

if __name__ == "__main__":
	main()
	
""" Version Log
v0: correctly retrieving metrics and activities.  About to abstract out config saver
v1: fixed bug: name collision for BasisRetrApp- Changed to BasisRetr.
"""