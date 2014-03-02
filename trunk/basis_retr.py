import sys
import re
from StringIO import StringIO # just need this one method
import BaseHTTPServer
import urllib2
import urllib
import os.path
from cookielib import CookieJar, FileCookieJar, LWPCookieJar
import json
import csv #for csv conversion
import datetime
import calendar
import xor
# need to comment this out for py2exe?
def qw(s):
	return tuple(s.split())

DEBUG = False #or True
CFG_ITEMS = {'loginid':'', 'passwd':'', 'enc_passwd':'', 'savedir':'', 'userid':'', 'save_pwd':'', 'config_filepath':'', 'json_csv':'', 'month':(0,'Jan'), 'year':2014, 'csv_lineterminator':'\n'}

class Config:
	"""Persist config object in a file.  Provide encoding and decoding of password"""
	CFG_FILENAME = "band_retr.cfg" # this needs to be outside Config class for now, since initializer wants to set 
	
	def __init__(self, **kwattrs):
		self.save_pwd = 0
		for k in CFG_ITEMS.keys():
			if k in kwattrs:
				setattr(self, k, kwattrs[k])
			else:
				setattr(self, k, CFG_ITEMS[k])

	def Load(self, filepath = None):
		self.config_filepath = filepath or Config.CFG_FILENAME
#		if not os.path.exists(self.config_filepath):
#			print "config file path doesn't exist"
#			return
			
		try:
			with open(self.config_filepath, "r") as f:
				jresult = f.read()
		except IOError as e:
			print "Didn't load config file: "+ e.strerror 
			return # return None if didn't load, so caller can add data (e.g., on first run) and save it later.
			
		j = json.loads(jresult)
		# set attrs in config
		for k, v in j.items():
			setattr(self, k, v)
		if self.enc_passwd:
			self.passwd = xor.xor_crypt_string(self.enc_passwd, decode=True)
		
		
	def Save(self, fpath = None):
		"""Save Config info before close"""
		if fpath:
			self.config_filepath = fpath
		if self.save_pwd > 0: # only persist password if asked to 
			# "checked" value in 'save pwd' UI button is 0 if unchecked 1 if checked
			# code up (obsfuscate) password for local storage
			# NOTE: this is NOT secure encryption.
			self.enc_passwd = xor.xor_crypt_string(self.passwd, encode=True)
		else:
			self.enc_passwd = ""
		p = self.passwd
		delattr(self, 'passwd') # don't dump passwd
		jresult = json.dumps(self, default=lambda o: o.__dict__)
		setattr(self, 'passwd', p) # reinstate
		#try:
		with open(self.config_filepath, "w") as f:
			f.write(jresult)
		#except IOError as e:
		#print "Didn't save config file: "+ e.strerror 
	
class BasisRetr:
	COOKIE_FILENAME= "band_retr.cookie"
	LOGIN_URL = 'https://app.mybasis.com/login'
	UID_URL = 'https://app.mybasis.com/api/v1/user/me.json'
	METRICS_URL = 'https://app.mybasis.com/api/v1/chart/{userid}.json?interval=60&units=s&start_date={date}&start_offset=0&end_offset=0&summary=true&bodystates=true&heartrate=true&steps=true&calories=true&gsr=true&skin_temp=true&air_temp=true'
	ACTIVITIES_URL ='https://app.mybasis.com/api/v2/users/me/days/{date}/activities?expand=activities&type=run,walk,bike,sleep'
	SLEEP_URL = 'https://app.mybasis.com/api/v2/users/me/days/{date}/activities?expand=activities&type=sleep'
	SLEEP_EVENTS_URL = 'https://app.mybasis.com/api/v2/users/me/days/{date}/activities?type=sleep&event.type=toss_and_turn&expand=activities.stages,activities.events'
	def __init__(self, loadconfig = None, **kwattrs):
		# create config info
		self.cfg = Config(**kwattrs)
		if loadconfig:
			self.cfg.Load()
		else:
			self.Save()
		# url opener for website retrieves
		opener = urllib2.build_opener()
		self.cj = LWPCookieJar(BasisRetr.COOKIE_FILENAME)
		self.session_cookie = None
		if os.path.exists(BasisRetr.COOKIE_FILENAME):
			self.cj.load()
			self.CheckSessionCookie() # set session cookie if it exists and hasn't expired
		# need to use build_opener to submit cookies and post form data
		self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cj))

	def CheckLogin(self):
		# the test below gives HTTP Error 401: Unauthorized if don't get cookie each time
		# I wonder if cookielib::FileCookieJar might do the right thing
		# i.e., save all cookies, not just session cookie.
		if not self.cfg.userid or not self.session_token:
			self.Login()

	def Login(self, login = None, passwd = None):
		"""Log in to basis website to get session (access) token via cookie. Don't need to pass in loginid and password if want to use stored info."""
		if login:
			self.cfg.loginid = login
		if passwd:
			self.cfg.passwd = passwd

		form_data = {'next': 'https://app.mybasis.com',
			'submit': 'Login',
			'username': self.cfg.loginid,
			'password': self.cfg.passwd}
		enc_form_data = urllib.urlencode(form_data)
		f = self.opener.open(BasisRetr.LOGIN_URL, enc_form_data)

		content = f.read()
		#$ do we need to close f?
		m = re.search('error_string\s*=\s*"(.+)"', content, re.MULTILINE)
		if m:
			raise Exception(m.group(1))
		
		self.CheckSessionCookie()
		
		# make sure we got the access token
		if not self.session_token:
			self.Status("Didn't find an access token in:"+["({}={}), ".format(c.name.c.value) for c in self.cj])
		#	for cookie in self.cj:
		#		print "("+cookie.name+"="+cookie.value+") ",
		else:
			self.Status("Logged in, Got Access Token = "+self.session_token)
		
	def CheckSessionCookie(self):
		for cookie in self.cj:
			if cookie.name == 'access_token':
				self.session_token = cookie.value

	def GetUserID(self):
		"""Retrieve the long hex string that uniquely identifies a user from the Basis website."""
		if not self.session_token:
			raise Exception('no token', 'no access token found-may be internet connectivity or bad login info.')
		self.opener.addheaders = [('X-Basis-Authorization', "OAuth "+self.session_token)]
		f = self.opener.open(BasisRetr.UID_URL)
		content = f.read()
		jresult = json.loads(content)
		#print json.dumps(jresult)
		self.cfg.userid= None
		if 'id' in jresult:
			self.cfg.userid = jresult['id']

	def GetMetricsForDay(self, date):
		# Need userid in order to get metrics
		if not self.cfg.userid:
			self.Status("BasisRetr::GetMetrics: No userid available; getting from website.")
			self.GetUserID()
			self.Status("Retrieved userid from website.")
		"""
		metrics = ['heartrate', 'steps', 'calories', 'gsr', 'skin_temp', 'air_temp']
		params = 'interval=60&units=s&start_date='+date+'&start_offset=0&end_offset=0&summary=true&bodystates=true'
		for m in metrics:
			params +="&"+m+"=tue"
		"""
		# Form the URL
		url = BasisRetr.METRICS_URL.format(userid=self.cfg.userid)#, params=params)
		return self.GetJsonData(url)
		
	def GetActivitiesForDay(self, date):
		url = BasisRetr.ACTIVITIES_URL.format(date = date)
		return self.GetJsonData(url)

	def GetSleepForDay(self, date):
		url = BasisRetr.SLEEP_URL.format(date=date)
		return self.GetJsonData(url)

	def GetSleepEventsForDay(self,date):
		url = BasisRetr.SLEEP_EVENTS_URL.format(date=date)
		return self.GetJsonData(url)
		
	def GetJsonData(self, url):
		if DEBUG:
			print url
			return
		try:			
			f = self.opener.open(url)
			jresult= json.loads(f.read())
		except urllib2.HTTPError as e:
			reason = BaseHTTPServer.BaseHTTPRequestHandler.responses[e.code]
			jresult = {'code': e.code, 'error':reason, 'url':url} 
			#content = '{{"code":"{code}", "error":"{msg}","url":"{url}"}}'.format(code=e.code, msg=reason, url=url)
		
		#jresult = json.loads(content)
		if 'code' in jresult and jresult['code'] == 401: # try logging in
			self.Status("Auth error, Logging in for new session token.")
			self.Login()
			try:	# try again
				f = self.opener.open(url)
				jresult= json.loads(f.read())
			except urllib2.HTTPError as e:
				reason = BaseHTTPServer.BaseHTTPRequestHandler.responses[e.code]
				jresult = {'code': e.code, 'error':reason, 'url':url} 
		return jresult #json.loads(content)

	def SaveData(self, data, fname):
		fpath = os.path.join(os.path.abspath(self.cfg.savedir), fname)
		try:
			fh = file(os.path.abspath(fpath), "w")
			fh.write(data)
		except IOError, v:
			self.Status("problem saving file to:"+fpath+"\n--Error: "+v)
		fh.close()


	################################
	##
	##				Methods for turning json data into csv
	##
	def StartMetricsCSV(self):
		csv_file = StringIO()
		writer = csv.writer(csv_file, lineterminator=self.cfg.csv_lineterminator)
		writer.writerow(['date', 'time', 'skin_temp', 'air_temp', 'heartrate', 'steps', 'gsr', 'calories'])
		result = csv_file.getvalue()
		csv_file.close()
		return result

	def AddMetricsCSV(self,j):
		csv_file = StringIO()
		writer = csv.writer(csv_file, lineterminator=self.cfg.csv_lineterminator)
		
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

			# get datetime as string
			timestamp = datetime.datetime.fromtimestamp(unix_time_utc).__str__()
			dt, tm = timestamp[:10], timestamp[11:]
			writer.writerow([dt, tm, skin_temp, air_temp, heartrate, steps, gsr, calories])
		csv_result = csv_file.getvalue()
		csv_file.close()
		return csv_result
			
	def StartActivitiesCSV(self):
		csv_file = StringIO()
		writer = csv.writer(csv_file, lineterminator=self.cfg.csv_lineterminator)
		writer.writerow(['start_date', 'start_time', 'end_date','end_time', 'type', 'calories', 'actual_seconds',  'steps'])
		result = csv_file.getvalue()
		csv_file.close()
		return result

	def AddActivitiesCSV(self, j):
		csv_file = StringIO()
		writer = csv.writer(csv_file, lineterminator=self.cfg.csv_lineterminator)
		if 'content' not in j or 'activities' not in j['content']:
			err = "Err in BasisRetr::AddActivitiesCSV: didn't get activities, got",json.dumps(j, indent=2)
			return err
		activities = j['content']['activities']
		for i in range(len(activities)):
			a = activities[i]
			start_timestamp = a['start_time']['timestamp']
			start_time = datetime.datetime.fromtimestamp(start_timestamp).__str__()
			s_dt, s_tm = start_time[:10], start_time[11:]
			end_timestamp = a['end_time']['timestamp']
			end_time = datetime.datetime.fromtimestamp(end_timestamp).__str__()
			e_dt, e_tm = end_time[:10], end_time[11:]
			steps = 'steps' in a and a['steps'] or 0
			writer.writerow([s_dt, s_tm, e_dt, e_tm, a['type'], a['calories'], a['actual_seconds'], steps])
		csv_result = csv_file.getvalue()
		csv_file.close()
		return csv_result

	def GetMonthConstraint(self, yr, mo):
		# if today is before the end of the month, then constrain end-date.
		days_in_month = calendar.monthrange(yr, mo+1)[1]
		end_of_month = datetime.date(yr, mo+1, days_in_month)
		today = datetime.date.today()
		if today < end_of_month:
			end = today.day # don't collect data for the future.
		else: # go to end of month
			end = days_in_month
		return days_in_month, end
		
	def GetActivityCsvForMonth(self, yr, mo, start = 1, end = None):
		"""Retrieve json files and convert into csv.  Append all CSVs into a single file."""
		
		days_in_month, end = self.GetMonthConstraint(yr, mo)
		result = self.StartActivitiesCSV() # create headers for csv file
		for dy in range(start,end+1):
			date = '%s-%02d-%02d' % (yr, mo+1, dy)
			self.Status("Getting activity data for "+date)
			
			fname = '{}_basis_activities_summary.json'.format(date)
			json_path = os.path.join(os.path.abspath(self.cfg.savedir), fname)
			if not os.path.isfile(json_path):
				# download the json file
				jresult = self.GetActivitiesForDay(date)
			else:
				# load json file
				with open(json_path, 'r') as content:
					jresult = json.loads(content.read())
			result += self.AddActivitiesCSV(jresult)
		fname = "{:04d}-{:02d}_basis_activities.csv".format(yr, mo+1)
		self.SaveData(result, fname)
		self.Status("Saved activities as "+fname)
		return result
		
	def StartSleepCSV(self):
		csv_file = StringIO()
		writer = csv.writer(csv_file, lineterminator=self.cfg.csv_lineterminator)
		writer.writerow(['start_date', 'start_time', 'end_date','end_time', 'calories', 'actual_seconds', 'heart_rate', 'rem_minutes', 'light_minutes', 'deep_minutes', 'quality', 'toss_and_turn', 'unknown_minutes',  'interruption_minutes'])
		result = csv_file.getvalue()
		csv_file.close()
		return result

	def AddSleepCSV(self, j):
		csv_file = StringIO()
		#with csv_file:
		writer = csv.writer(csv_file, lineterminator=self.cfg.csv_lineterminator)
		if 'content' not in j or 'activities' not in j['content']:
			err = "Err in BasisRetr::AddActivitiesCSV: didn't get activities, got",json.dumps(j, indent=2)
			return err
		activities = j['content']['activities']
		for i in range(len(activities)):
			a = activities[i]
			
			start_timestamp = a['start_time']['timestamp']
			start_time = datetime.datetime.fromtimestamp(start_timestamp).__str__()
			s_dt, s_tm = start_time[:10], start_time[11:]
			
			end_timestamp = a['end_time']['timestamp']
			end_time = datetime.datetime.fromtimestamp(end_timestamp).__str__()
			e_dt, e_tm = end_time[:10], end_time[11:]
			
			s = a['sleep']
			writer.writerow([s_dt, s_tm, e_dt, e_tm, a['calories'], a['actual_seconds'], a['heart_rate']['avg'], s['rem_minutes'], s['light_minutes'], s['deep_minutes'], s['quality'], s['toss_and_turn'], s['unknown_minutes'], s['interruption_minutes']]) # removed a['type']; it's obvious from the other params
		csv_result = csv_file.getvalue()
		csv_file.close()
		return csv_result

	def StartSleepEventsCSV(self):
		csv_file = StringIO()
		writer = csv.writer(csv_file, lineterminator=self.cfg.csv_lineterminator)
		#writer.writerow(['start_date', 'start_time', 'end_date','end_time', 'type'])
		writer.writerow(['start_date', 'start_time', 'minutes', 'type'])
		result = csv_file.getvalue()
		csv_file.close()
		return result

	def AddSleepEventsCSV(self, j):
		"""Sleep events are more complicated and nested. Within [0..n] activities, there are [0..n] stages, each with a start and end time.  There are also [0..n] events (I think only "toss_and_turn").  Both stages and events are parsed below, then combined and sorted by time via tuples.  The tuples are then turned into csv rows."""
		csv_file = StringIO()
		writer = csv.writer(csv_file, lineterminator=self.cfg.csv_lineterminator)
		if 'content' not in j or 'activities' not in j['content']:
			err = "Err in BasisRetr::AddSleepEventsCSV: didn't get activities, got",json.dumps(j, indent=2)
			return err
		activities= j['content']['activities']
		# first, get data from "stages"
		result = []
		for i in range(len(activities)):
			a = activities[i]
			if 'stages' not in a:
				err = "Err in BasisRetr::AddSleepEventsCSV: didn't get stages, got",json.dumps(j, indent=2)
				return err
				
			stages = a['stages']
			for j in range(len(stages)):
				s = stages[j]
				start_timestamp = s['start_time']['timestamp']				
				duration = s['minutes']
				result.append( (start_timestamp, duration, s['type']) )
				# old version, using start and end times
				#end_timestamp = s['end_time']['timestamp']
				#result.append( (start_timestamp, end_timestamp, s['type']) )
				
			# next is toss-turn events
			events = a['events']
			for j in range(len(events)):
				e = events[j]
				start_timestamp = e['time']['timestamp']
				duration = 0
				result.append( (start_timestamp, duration, e['type']) )
				#end_timestamp = e['time']['timestamp']
				#result.append( (start_timestamp, end_timestamp, e['type']) )
			
			# now, sort results by start_timestamp
			result.sort(key=lambda tup: tup[0])
			# and write to csv
			#for start_timestamp, end_timestamp, type in result:
			for start_timestamp, duration, type in result:
				# convert datetime object to local date-time string, then separate the string into date [:10] and time [11:].
				start_time = datetime.datetime.fromtimestamp(start_timestamp).__str__()
				s_dt, s_tm = start_time[:10], start_time[11:]
				#end_time = datetime.datetime.fromtimestamp(end_timestamp).__str__()
				#e_dt, e_tm = end_time[:10], end_time[11:]
				writer.writerow([s_dt, s_tm, duration, type]) # removed a['type']; it's obvious from the other params
		csv_result = csv_file.getvalue()
		csv_file.close()
		return csv_result

	SLEEP_SUMMARY_FNAME = "basis_sleep_summary"
	def GetSleepCsvForMonth(self, yr, mo, start = 1, end = None):
		"""Retrieve json files and convert into csv.  Append all CSVs into a single file."""
		#days_in_month = calendar.monthrange(yr, mo+1)[1]
		days_in_month, end = self.GetMonthConstraint(yr, mo)
		#if not end: # default to the number of days in the month, or today, whichever is later.
		#	end = days_in_month
		result = self.StartSleepCSV()
		for dy in range(start,end+1):
			date = '%s-%02d-%02d' % (yr, mo+1, dy)
			self.Status("Getting sleep events for "+date)
			fname = '{}_{}.json'.format(date,BasisRetr.SLEEP_SUMMARY_FNAME)
			json_path = os.path.join(os.path.abspath(self.cfg.savedir), fname)
			if not os.path.isfile(json_path): # don't have json file, so download it.
				jresult = self.GetSleepForDay(date)
			else: # load existing json file
				with open(json_path, 'r') as content:
					jresult = json.loads(content.read())
			result += self.AddSleepCSV(jresult)
		#fname = "{:04d}-{:02d}_basis_sleep.csv".format(yr, mo+1)
		fname = '{:04d}-{:02d}_{}.csv'.format(yr, mo+1,BasisRetr.SLEEP_SUMMARY_FNAME)
		self.SaveData(result, fname)
		self.Status("Saved sleep events to "+fname)
		return result

	def OnClose(self):
		"""Save Config file and file-based cookiejar"""
		self.cfg.Save()
		self.cj.save(BasisRetr.COOKIE_FILENAME)

	def Status(self, s):
		pass
##
##		End BasisRetr
##
#######################

"""
#from Bandsaw
def SaveCsv(fpath, j):
	with open(fpath, 'wb') as csv_file:
		writer = csv.writer(csv_file)
		writer.writerow(['timestamp', 'skin_temp', 'air_temp', 'heartrate', 'steps', 'gsr', 'calories'])
	append_to_csv(fpath, j)

def append_to_csv(fpath,j):
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
	"""
		
import pprint
def ppp(object):
	"""debugging support: pretty print any object"""
	pprint.PrettyPrinter().pprint(object)

"""def main():
	try_csv()
	return
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
	b.SaveJsonData(m, date+"_basis_metrics.json")
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
	
	

def try_csv():	
	date = '2014-01'
	csv_path = 'C:\\temp\\%s_basis_activities.csv' % date
	print GetActivityCsvForMonth(2014, 01, start=28)
	
	with open(csv_path, 'wb') as csv_file:
		csv_file.write(result)
"""	
def main():
	#b = BasisRetr(loginid='rg1@rawds.com', passwd='abcde', saving_pwd=1)
	print "EXECUTING MAIN IN basis_retr.py"
	b = BasisRetr(loadconfig=1)#, config_filepath=CFG_FILENAME)
	
if __name__ == "__main__":
	# allow immediate display of console output
	sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)
	main()
	
""" Version Log
v0: correctly retrieving metrics and activities.  About to abstract out config saver
v1: first try converting activites json file to csv.  Next step is to get many files.
v2: converted csv writing code to work on StringIO instead of file directly.  Also doing a month at a time.
v3: got GetActivityCsvForMonth() as simple function.  Now integrate with basis_retr class.
v4: before refactoring state retention.
v5: saving and loading Config class.  Next step is to incorporate save and load.
v6: updated config class.  Pulled URLs out of functions and into class vars.
v7: (aligned with BasisRetriever v8). Got refactored metrics, activities, and sleep downloading correctly, csv + json.  Also got month of activities downloading correctly.
v8: (aligned with BasisRetriever v9). Created sleep (detail) events download feature. Got status event callback working (so BasisRetriever can show status in status bar). Constraining month summaries to only get data for up to today.
"""
