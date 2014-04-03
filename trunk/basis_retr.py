import sys
import re
from StringIO import StringIO # just need this one method
import BaseHTTPServer
import urllib2
import urllib
import os
import os.path
from cookielib import CookieJar, FileCookieJar, MozillaCookieJar
import json
import csv #for csv conversion
import datetime
import time # time.time in RetrieveJsonOrCached
import calendar
import optparse
from configfile import Config

# need to comment this out for py2exe!
#sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

def qw(s):
	return tuple(s.split())

DEBUG = False #or True
# The values below are only for initializing config file.
CFG_ITEMS = {
	'loginid':'', 
	'cookie_filename':'basis_retr.cookie',
	'passwd':'', 
	'enc_passwd':'', 
	'savedir':'', 
	'userid':'', 
	'save_pwd':0,
	'json_csv':'csv', 
	'month':(0,'Jan'), 
	'year':2014, 
	'nocache_days':1.5,
	'csv_lineterminator':'\n', 
	'session_token':'', 
	'act_metr':1, 
	'jsondir':'json', 
	'csv_metrics_colnames':['datetime', 'skin_temp', 'air_temp', 'heartrate', 'steps', 'gsr', 'calories'], 
	'csv_activity_type_colnames':['act_type', 'sleep_type', 'toss_turn'],
	'csv_activity_colnames':['start_dt', 'end_dt','type', 'calories', 'actual_seconds',  'steps'], 
	'csv_sleep_colnames':['start_dt','end_dt','calories', 'actual_seconds', 'heart_rate', 'rem_minutes', 'light_minutes', 'deep_minutes', 'quality', 'toss_and_turn', 'unknown_minutes',  'interruption_minutes'],
	'csv_sleep_evt_colnames':['start_dt','end_dt','duration','type']
}

	
class BasisRetr:
	"""The main entry points, once a BasisRetr object has been created, are: 1) GetDayData()-- download metrics, activity, sleep data for a single day from the basis website and save it, 2) GetActivityCsvForMonth()-- download activity summaries for an entire month, and 3) GetSleepCsvForMonth()--download sleep summaries for an entire month."""
	LOGIN_URL = 'https://app.mybasis.com/login'
	UID_URL = 'https://app.mybasis.com/api/v1/user/me.json'
	METRICS_URL = 'https://app.mybasis.com/api/v1/chart/{userid}.json?interval=60&units=s&start_date={date}&start_offset=0&end_offset=0&summary=true&bodystates=true&heartrate=true&steps=true&calories=true&gsr=true&skin_temp=true&air_temp=true'
	ACTIVITIES_URL ='https://app.mybasis.com/api/v2/users/me/days/{date}/activities?expand=activities&type=run,walk,bike,sleep'
	SLEEP_URL = 'https://app.mybasis.com/api/v2/users/me/days/{date}/activities?expand=activities&type=sleep'
	SLEEP_EVENTS_URL = 'https://app.mybasis.com/api/v2/users/me/days/{date}/activities?type=sleep&event.type=toss_and_turn&expand=activities.stages,activities.events'

	DATE_FORMAT = "%04d-%02d-%02d"
	
	# save-to filename.  date is prefix, format is suffix
	MO_ACTIVITY_FNAME_TEMPLATE = "{yr:04d}-{mo:02d}_basis_activities_summary.csv"
	MO_SLEEP_FNAME_TEMPLATE = "{yr:04d}-{mo:02d}_basis_sleep_summary.csv"
	# day sleep and activity filenames (for month summaries)
	DAY_ACTIVITY_FNAME_TEMPLATE = "{yr:04d}-{mo:02d}-{dy:02d}_basis_activities.json"
	DAY_SLEEP_FNAME_TEMPLATE = "{yr:04d}-{mo:02d}-{dy:02d}_basis_sleep.json"
	DAY_JSON_FNAME_TEMPLATE = "{date}_basis_{typ}.json"
	METRICS_FNAME_TEMPLATE = "{date}_basis_metrics.{ext}"
	SLEEP_FNAME_TEMPLATE= "{date}_basis_sleep.{format}"
	
	def __init__(self, loadconfig = None):
		# create config info
		self.cfg = Config(cfg_items = CFG_ITEMS)
		if loadconfig:
			self.cfg.Load()
		else:
			# if config file doesn't exist, save the defaults loaded above
			self.cfg.Save() #saves 
		# url opener for website retrieves
		opener = urllib2.build_opener()
		self.cj = MozillaCookieJar(self.cfg.cookie_filename)#BasisRetr.COOKIE_FILENAME)
		self.session_cookie = None
		if os.path.exists(self.cfg.cookie_filename):#BasisRetr.COOKIE_FILENAME):
			self.cj.load()
			self.CheckSessionCookie() # set session cookie if it exists and hasn't expired
		# need to use build_opener to submit cookies and post form data
		self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cj))

	def GetDayData(self, yr, mo, day, typ, save_csv, override_cache = False, act_metr= True):
		"""Main entry method for getting a day's worth of data, formatting, then saving it.  typ is the type of data: metrics, activities, or sleep.  Data is always saved in json format, but if save_csv is True, save to csv as well as json. override_cache ignores any already downloaded json.  act_metr, if True, saves sleep and activity state along with metrics."""
		date = BasisRetr.DATE_FORMAT % (yr, mo, day)
		ydate = self.GetYesterdayDateAsString(yr, mo, day)
		
		self.Status("Checking Login")
		self.CheckLogin() # ensure we're logged in
		self.Status("getting {} for {}".format(typ,date))
		# figure out which data to get
		data = None
		# filename 
		cfname = "{date}_basis_{typ}.csv".format(date=date, typ=typ)
				
		# if needed, download json data from website and save to file
		if typ == 'metrics':
			mjdata = self.RetrieveJsonOrCached(date, 'metrics', override_cache)
			### MOVE THIS ERROR CHECKING INTO THE ABOVE METHOD
			if type(mjdata) == str or mjdata == None: # simple error checking
				self.Status('OnGetDayData: Metrics json conversion failed.')
				print mjdata[:500]
				return
			# also load up actities
		if typ == 'activities' or act_metr:
			ajdata = self.RetrieveJsonOrCached(date, 'activities', override_cache)
			if type(ajdata) == str or ajdata == None: # simple error checking
				self.Status('OnGetDayData: Activities json conversion failed.')
				print ajdata[:500]
				return
		if typ == 'sleep' or act_metr:
			sjdata = self.RetrieveJsonOrCached(date, 'sleep', override_cache)
			if type(sjdata) == str or sjdata == None: # simple error checking
				self.Status('OnGetDayData: Sleep json conversion failed.')
				print sjdata[:500]
				return
			if act_metr: # add yesterday's sleep data
				sjdata2= self.RetrieveJsonOrCached(ydate, 'sleep')
		
		# Next, turn the list of python objects into a csv file.
		# If asked to (via act_metr), collect sleep and activity type, then add them to each timestamp.
		cdata = None
		if save_csv:
			if typ == 'activities' or act_metr:
				act_list = self.JsonActivitiesToList(ajdata)
				cdata = self.CreateCSVFromList(self.cfg.csv_activity_colnames, act_list)
			if typ == 'sleep' or act_metr:
				sleep_evts_list = self.JsonSleepEventsToList(sjdata)
				cdata = self.CreateCSVFromList(self.cfg.csv_sleep_evt_colnames, sleep_evts_list)
				if act_metr:
					# prepend yesterday's sleep events as they may start before midnight.
					sleep_evts_list[:0] = self.JsonSleepEventsToList(sjdata2)
			if typ == 'metrics':
				metrics_list = self.JsonMetricsToList(mjdata)
				if act_metr: # add activities to metrics               
					self.AddActivityTypeToMetrics(metrics_list, act_list, sleep_evts_list)
					header = self.cfg.csv_metrics_colnames + self.cfg.csv_activity_type_colnames
				else:
					header = self.cfg.csv_metrics_colnames
				cdata = self.CreateCSVFromList(header, metrics_list)
		
		# If we were able to make a csv file, save it.
		if cdata:
			fpath = os.path.join(os.path.abspath(self.cfg.savedir), cfname)
			self.SaveData(cdata, fpath)
			self.Status("Saved "+typ+" csv file at "+fpath)

	def CheckLogin(self):
		# the test below gives HTTP Error 401: Unauthorized if don't get cookie each time
		# I wonder if cookielib::FileCookieJar might do the right thing
		# i.e., save all cookies, not just session cookie.
		if not self.cfg.userid or not self.cfg.session_token:
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
		if not self.cfg.session_token:
			self.Status("Didn't find an access token in:"+["({}={}), ".format(c.name.c.value) for c in self.cj])
		else:
			self.Status("Logged in, Got Access Token = "+self.cfg.session_token)
		
	def CheckSessionCookie(self):
		for cookie in self.cj:
			if cookie.name == 'access_token':
				self.cfg.session_token = cookie.value

	def GetUserID(self):
		"""Retrieve the long hex string that uniquely identifies a user from the Basis website."""
		if not self.cfg.session_token:
			raise Exception('no token', 'no access token found-may be internet connectivity or bad login info.')
		self.opener.addheaders = [('X-Basis-Authorization', "OAuth "+self.cfg.session_token)]
		f = self.opener.open(BasisRetr.UID_URL)
		content = f.read()
		jresult = json.loads(content)
		self.cfg.userid= None
		if 'id' in jresult:
			self.cfg.userid = jresult['id']

	def GetYesterdayDateAsString(self, yr, mo, day):
		"""Need yesterday's date to get sleep events for a given calendar day. This is because sleep events, as downloaded from the Basis Website, start from the prior evening, when you actually went to sleep."""
		
		tday, tmo, tyr = day-1, mo, yr
		
		if tday <1: # previous month
			tmo -= 1
			if tmo < 1: # previous year
				tyr -= 1
				tmo = 12
			# once we adjusted the month, find the last day of that month 
			tday = calendar.monthrange(tyr, tmo)[1]
		tdate	 = BasisRetr.DATE_FORMAT % (tyr, tmo, tday)
		return tdate

	def RetrieveMetricsJsonForDay(self, date):
		# Need userid in order to get metrics
		if not self.cfg.userid:
			self.Status("BasisRetr::GetMetrics: No userid available; getting from website.")
			self.GetUserID()
			self.Status("Retrieved userid from website.")
		# Form the URL
		url = BasisRetr.METRICS_URL.format(date=date,userid=self.cfg.userid)
		return self.GetJsonData(url)
		
	def RetrieveActivitiesJsonForDay(self, date):
		url = BasisRetr.ACTIVITIES_URL.format(date = date)
		return self.GetJsonData(url)

	def RetrieveSleepSummaryJsonForDay(self, date):
		url = BasisRetr.SLEEP_URL.format(date=date)
		return self.GetJsonData(url)

	def RetrieveSleepEventsJsonForDay(self,date):
		url = BasisRetr.SLEEP_EVENTS_URL.format(date=date)
		return self.GetJsonData(url)

	def GetJsonStorageDir(self):
		"""Allow json storage dir to be absolute or relative (to csv dir) path."""
		if os.path.isabs(self.cfg.jsondir):
			return self.cfg.jsondir
		else:
			return os.path.join(os.path.abspath(self.cfg.savedir), self.cfg.jsondir)

	def RetrieveJsonOrCached(self, date, typ, user_override_cache = None):
		"""If json file exists in json dir, then just read that.  Otherwise, download from basis website.  If override_cache is set, always download from website."""
		fname = BasisRetr.DAY_JSON_FNAME_TEMPLATE.format(date=date, typ=typ)
		fpath = os.path.join(self.GetJsonStorageDir(), fname)
		# don't use cache if the saved data is very recent-- what's saved may have been before the end of the day.
		if os.path.isfile(fpath):
			# these calculations are in seconds since epoch
			days_prev = 3600*24*self.cfg.nocache_days
			last_mod_time = os.path.getmtime(fpath)
			target_time = time.mktime(datetime.datetime.strptime(date, "%Y-%m-%d").timetuple())
			force_override_cache = last_mod_time - target_time < days_prev
		# if file exists and we've said via UI, "don't override the cache", then read json from cache
		if os.path.isfile(fpath) and not user_override_cache and not force_override_cache:
			with open(fpath, "r") as f:
				data = f.read()
				jdata = json.loads(data)
				
		else: # retrieve data from website
			if typ == 'metrics':
				jdata = self.RetrieveMetricsJsonForDay(date)
			elif typ == 'activities':
				jdata = self.RetrieveActivitiesJsonForDay(date)
			elif typ == 'sleep':
				jdata = self.RetrieveSleepEventsJsonForDay(date)
			elif typ == 'sleep_summary':
				jdata = self.RetrieveSleepSummaryJsonForDay(date)
			#json_path = os.path.join(self.GetJsonStorageDir(), fname)
			# make sure directory exists
			if not os.path.isdir(self.GetJsonStorageDir()):
				os.makedirs(self.GetJsonStorageDir())
			self.SaveData(json.dumps(jdata), fpath)
		return jdata
	
		
	def GetJsonData(self, url):
		if DEBUG:
			print url
		if True:
			try:			
				f = self.opener.open(url)
				jresult= json.loads(f.read())
			except urllib2.HTTPError as e:
				reason = BaseHTTPServer.BaseHTTPRequestHandler.responses[e.code]
				jresult = {'code': e.code, 'error':reason, 'url':url} 
		
		# callback (if available) to UI manager to ensure it doesn't freeze
		if hasattr(self, 'FreezePrevention'):
			self.FreezePrevention()
		if 'code' in jresult and jresult['code'] == 401: # unauthorized.  try logging in
			self.Status("Auth error, Logging in for new session token.")
			self.Login()
			try:	# try again
				f = self.opener.open(url)
				jresult= json.loads(f.read())
			except urllib2.HTTPError as e:
				reason = BaseHTTPServer.BaseHTTPRequestHandler.responses[e.code]
				jresult = {'code': e.code, 'error':reason, 'url':url} 
		return jresult

	def SaveData(self, data, fpath):
		try:
			fh = file(os.path.abspath(fpath), "w")
			fh.write(data)
		except IOError, v:
			self.Status("problem saving file to:"+fpath+"\n--Error: "+`v`)
		try: # if problem is on open, then fh doesn't exist.
			fh.close()
		except:
			pass

	################################
	##
	##				Methods for extracting data from json into lists of dicts
	##
	def JsonMetricsToList(self,j):
		result = []
		
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
			date_time = datetime.datetime.fromtimestamp(unix_time_utc).__str__()
			dt, tm = date_time[:10], date_time[11:]
			result.append({'tstamp':unix_time_utc,'datetime':date_time, 'date':dt,'time':tm, 'skin_temp':skin_temp, 'air_temp':air_temp, 'heartrate':heartrate, 'steps':steps, 'gsr':gsr, 'calories':calories})
		return result

	def AddActivityTypeToMetrics(self, metrics_list, activity_list, sleep_list):
		"""Append activity type to each applicable minute of the day.  Assumes each list is monotonically increasing in time. This also presumes that activity and sleep data encompass metrics data."""
		metrics_span = metrics_list[0]['tstamp'], metrics_list[-1]['tstamp']
		# it's possible there were no activities for the day.
		# the below try doesn't do the right thing.  If len == 0, still tries to evaluate [0] and fails
		if type(activity_list) != list:
			print "AddActivityToMetrics: activity list should be array, but instead is string:",`activity_list`[:200]
			return
		if type(sleep_list) != list:
			print "AddActivityToMetrics: sleep events list should be array, but instead is string:",`sleep_list`[:200]
			return
		activity_span = len(activity_list)>0 and (activity_list[0]['start_tstamp'], activity_list[-1]['end_tstamp']) or metrics_span
		sleep_span = len(sleep_list) > 0 and (sleep_list[0]['start_tstamp'], sleep_list[-1]['end_tstamp']) or metrics_span
			
		a_i = 0 # index into activity list
		s_i = 0 # index into sleep events list
		t_i = 0# index into toss_turn sleep events
		# Go through metrics (each minute of the day)
		for mrow in metrics_list:
			if len(activity_list)>0:
				# first, look for the first activity whose start time comes before or at the timestamp
				while a_i < len(activity_list)-1 and mrow['tstamp']> activity_list[a_i]['end_tstamp']:
					# current activity starts before timestamp
					a_i +=1
				# a_i now points to the first activity that starts before current time stamp
				# if we're also before the end of the activity, then note it.
				# activity starts if anytime within the prior minute (therefore the -59)
				if mrow['tstamp'] >= activity_list[a_i]['start_tstamp']-59 and mrow['tstamp'] <= activity_list[a_i]['end_tstamp']:
					mrow['act_type'] = activity_list[a_i]['type']
			else:
				mrow['act_type'] = ""
			
			if len(sleep_list) > 0:
				# next, advance the sleep event pointer to the right place.
				while s_i < len(sleep_list)-1 and mrow['tstamp']> sleep_list[s_i]['end_tstamp']-59:
					# current activity starts before timestamp
					s_i +=1
				# would like to add toss_turn events to another column 
				while t_i < len(sleep_list)-1 and mrow['tstamp']> sleep_list[t_i]['start_tstamp'] or sleep_list[t_i]['type'] != 'toss_and_turn':
					t_i += 1
				# options here are to reuse the type column above. That makes for smaller files
				# instead, we're using a separate field.  This makes it easier for the user
				# to filter out "all sleep events" or "all activities" without having to 
				# enumerate them.
				# could also use separate field for toss_and_turn events
				if sleep_list[t_i]['type'] == 'toss_and_turn' and sleep_list[t_i]['start_tstamp'] == mrow['tstamp']:
					mrow['toss_turn'] = sleep_list[t_i]['type']
				else:
					mrow['toss_turn'] = ""
					
				if mrow['tstamp'] >= sleep_list[s_i]['start_tstamp']-59 and mrow['tstamp'] < sleep_list[s_i]['end_tstamp']:
					mrow['sleep_type'] = sleep_list[s_i]['type']
				else:
					mrow['sleep_type'] = ""

	def JsonActivitiesToList(self, j):
		"""Turn Json-structured activity data into a list of dict, each dict being an activity"""
		presult = []
		if 'content' not in j or 'activities' not in j['content']:
			err = "Err in BasisRetr::JsonActivitiesToList: didn't get activities, got",j[:200] #json.dumps(j, indent=2)
			return err
		activities = j['content']['activities']
		for i in range(len(activities)):
			a = activities[i]
			start_timestamp = a['start_time']['timestamp']
			start_dt = datetime.datetime.fromtimestamp(start_timestamp).__str__()
			start_date, start_time = start_dt[:10], start_dt[11:]
			end_timestamp = a['end_time']['timestamp']
			end_dt = datetime.datetime.fromtimestamp(end_timestamp).__str__()
			end_date, end_time = end_dt[:10], end_dt[11:]
			steps = 'steps' in a and a['steps'] or 0
			# finally, add info to tag metrics with activity type
			presult.append({'start_tstamp':start_timestamp, 'start_dt':start_dt, 'end_dt':end_dt,'start_date':start_date, 'start_time':start_time,'end_tstamp':end_timestamp, 'end_date':end_date, 'end_time':end_time, 'type':a['type'], 'calories':a['calories'],'actual_seconds':a['actual_seconds'], 'steps':steps})
		return presult

	def JsonSleepEventsToList(self, j):
		"""Sleep events are more complicated and nested. Within [0..n] activities, there are [0..n] stages, each with a start and end time.  There are also [0..n] events (I think only "toss_and_turn").  Both stages and events are parsed below, then combined and sorted by time via tuples.  The tuples are then turned into csv rows."""
		presult = [] # python array as needed for adding stages to metrics
		if 'content' not in j or 'activities' not in j['content']:
			err = "Err in BasisRetr::JsonSleepEventsToList: didn't get activities, got",json.dumps(j, indent=2)
			return err
		activities= j['content']['activities']
		# first, get data from "stages"
		result = []
		for i in range(len(activities)):
			a = activities[i]
			if 'stages' not in a:
				err = "Err in BasisRetr::JsonSleepEventsToList: didn't get stages, got",json.dumps(j, indent=2)
				return err
				
			stages = a['stages']
			for j in range(len(stages)):
				s = stages[j]
				start_timestamp = s['start_time']['timestamp']				
				start_dt = datetime.datetime.fromtimestamp(start_timestamp).__str__()
				start_date, start_time = start_dt[:10], start_dt[11:]
				end_timestamp = s['end_time']['timestamp']				
				end_dt = datetime.datetime.fromtimestamp(end_timestamp).__str__()
				end_date, end_time = end_dt[:10], end_dt[11:]
				duration = s['minutes']
				#print {'start_tstamp':start_timestamp, 'start_date':start_date, 'start_time':start_time,'end_tstamp':end_timestamp, 'end_date':end_date, 'end_time':end_time, 'duration':duration,'type':s['type']}
				
				presult.append({'start_tstamp':start_timestamp, 'start_date':start_date, 'start_time':start_time,'start_dt':start_dt, 'end_dt':end_dt,'end_tstamp':end_timestamp, 'end_date':end_date, 'end_time':end_time, 'duration':duration,'type':s['type']})
				
			# next is toss-turn events
			events = a['events']
			for j in range(len(events)):
				e = events[j]
				start_timestamp = e['time']['timestamp']
				start_dt = datetime.datetime.fromtimestamp(start_timestamp).__str__()
				start_date, start_time = start_dt[:10], start_dt[11:]
				
				duration = 0 # The only event is "toss-turn" which always have zero duration
				presult.append({'start_tstamp':start_timestamp, 'start_date':start_date, 'start_time':start_time,'end_tstamp':start_timestamp, 'end_date':start_date, 'end_time':start_time, 'duration':duration,'type':e['type']})
			
			# now, combine events and stages by sorting results by start_timestamp
			presult.sort(key=lambda row: row['start_tstamp'])
		return presult

	def JsonSleepSummaryToList(self, j):
		"""Turn Json-structured sleep event data into a list of dict, each dict being a sleep event"""
		presult = []
		if 'content' not in j or 'activities' not in j['content']:
			err = "Err in BasisRetr::AddActivitiesCSV: didn't get activities, got",json.dumps(j, indent=2)
			return err
		activities = j['content']['activities']
		for i in range(len(activities)):
			# The activity object has basic info: timestamps, calories, duration, heart rate
			a = activities[i]
			
			start_timestamp = a['start_time']['timestamp']
			start_dt = datetime.datetime.fromtimestamp(start_timestamp).__str__()
			start_date, start_time = start_dt[:10], start_dt[11:]
			
			end_timestamp = a['end_time']['timestamp']
			end_dt = datetime.datetime.fromtimestamp(end_timestamp).__str__()
			end_date, end_time = end_dt[:10], end_dt[11:]
			
			# The sleep part of the activity has sleep event durations
			s = a['sleep']
			
			presult.append({'start_tstamp':start_timestamp, 'start_date':start_date, 'start_time':start_time, 'start_dt':start_dt, 'end_dt':end_dt,'end_tstamp':end_timestamp, 'end_date':end_date, 'end_time':end_time, 'calories':a['calories'],'actual_seconds':a['actual_seconds'], 'heart_rate':a['heart_rate']['avg'], 'rem_minutes':s['rem_minutes'], 'light_minutes':s['light_minutes'], 'deep_minutes':s['deep_minutes'], 'quality':s['quality'], 'toss_and_turn':s['toss_and_turn'], 'unknown_minutes':s['unknown_minutes'], 'interruption_minutes':s['interruption_minutes']}) 
		return presult

	#############################
	##
	##			Turn array of python objects into csv text
	##
	def CreateCSVFromList(self, col_names, pdata):
		# Create csv "file" (actually string) using DictWriter
		csv_file = StringIO()
		writer = csv.DictWriter(csv_file, lineterminator=self.cfg.csv_lineterminator, 
			fieldnames = col_names, extrasaction='ignore')
		writer.writerow(dict((fn,fn) for fn in col_names))
		for row in pdata:
			writer.writerow(row)
		result = csv_file.getvalue() # grab value before closing file
		csv_file.close()
		return result
		
	##############################
	##
	##				Retrieve summary data for an entire month
	##
	def GetActivityCsvForMonth(self, yr, mo, start = 1, end = None, override_cache = False):
		"""Retrieve json files and convert into csv.  Append all CSVs into a single file."""
		
		days_in_month, end = self.GetMonthConstraint(yr, mo)
		if end ==0:
			self.Status("Future month, no data retrieved")
			return
		result = [] #self.StartActivitiesCSV() # create headers for csv file
		for dy in range(start,end+1):
			date = '%s-%02d-%02d' % (yr, mo, dy)
			self.Status("Getting activity data for "+date)
			
			# download the json file
			jresult = self.RetrieveJsonOrCached(date, 'activities')
			result.extend(self.JsonActivitiesToList(jresult))
			
		csv_data = self.CreateCSVFromList(self.cfg.csv_activity_colnames, result)
		fname = BasisRetr.MO_ACTIVITY_FNAME_TEMPLATE.format(yr=yr, mo=mo)
		csv_path = os.path.join(os.path.abspath(self.cfg.savedir), fname)
		self.SaveData(csv_data, csv_path)
		self.Status("Saved activities as "+csv_path)
		return result

	def GetSleepCsvForMonth(self, yr, mo, start = 1, end = None):
		"""Retrieve json files and convert into csv.  Append all CSVs into a single file."""
		days_in_month, end = self.GetMonthConstraint(yr, mo)
		# default to the number of days in the month, or today, whichever is later.
		if end ==0:
			self.Status("Future month, no data retrieved")
			return
		result = []
		for dy in range(start,end+1):
			date = '%s-%02d-%02d' % (yr, mo, dy)
			self.Status("Getting sleep events for "+date)
			jresult = self.RetrieveJsonOrCached(date, 'sleep')
			
			"""fname = BasisRetr.DAY_ACTIVITY_FNAME_TEMPLATE.format(yr=yr, mo=mo, day=dy)
			#fname = '{}_{}.json'.format(date,BasisRetr.MONTH_ACTIVITY_FNAME_SUFFIX)
			json_path = os.path.join(os.path.abspath(self.cfg.savedir), fname)
			if not os.path.isfile(json_path): # don't have json file, so download it.
				#jresult = self.RetrieveSleepSummaryJsonForDay(date)
				jresult = self.RetrieveJsonOrCached(date, 'sleep_summary')
			else: # load existing json file
				with open(json_path, 'r') as content:
					jresult = json.loads(content.read())
			"""
			result.extend(self.JsonSleepSummaryToList(jresult))
		fname = BasisRetr.MO_SLEEP_FNAME_TEMPLATE.format(yr=yr, mo=mo)
		csv_data = self.CreateCSVFromList(self.cfg.csv_sleep_colnames, result)
		csv_path = os.path.join(os.path.abspath(self.cfg.savedir), fname)
		self.SaveData(csv_data, csv_path)
		self.Status("Saved sleep events to "+csv_path)
		return result


	def GetMonthConstraint(self, yr, mo):
		"""If today is before the end of the month, then constrain end-date.  No need to try and retrieve dates in the future."""
		days_in_month = calendar.monthrange(yr, mo)[1]
		end_of_month = datetime.date(yr, mo, days_in_month)
		today = datetime.date.today()
		if yr > today.year or yr == today.year and mo > today.month:
			end = 0
		elif today < end_of_month:
			end = today.day # don't collect data for the future.
		else: # go to end of month
			end = days_in_month
		return days_in_month, end


	def OnClose(self):
		"""Save Config file and file-based cookiejar"""
		self.cfg.Save()
		try: # there seems to be a problem with cookie timestamp out of range of epoch on OS-X (10.6.8). Solution right now is to just ignore.
			self.cj.save(self.cfg.cookie_filename)#BasisRetr.COOKIE_FILENAME)
		except Exception, v:
			print "Problem Saving cookies on exit:", `v`
			
	def Status(self, s):
		"""Placeholder for owner to override (e.g., show messages in status bar)"""
		print datetime.datetime.now(),"Status:",s

##
##		End BasisRetr
##
#######################

import pprint
def ppp(object):
	"""debugging support: pretty print any object"""
	pprint.PrettyPrinter().pprint(object)

def pp2(o):
	for k,v in o.__dict__.items():
		if type(v) != list:
			print k,"=>",v

	
def execute(options):
	"""parse options and run basis_retr."""
	# before we start, we must have a date
	date_match= re.search("^(\d{4})-(\d\d)(-(\d\d))?$", options.date or "")
	
	if date_match:
		yr, mo, x, day = [x and int(x) for x in date_match.groups()]
	else:
		print "Date needs to be specified on command line-- couldn't find one. Stopping."
		return

	# default is to use cached params, specify --nocache option to not use them.
	b = BasisRetr(not options.nocache)
	# place certain options into config
	for o in qw("savedir loginid loginid passwd type jsondir"):
		if hasattr(options, o):
			val = getattr(options,o)
			#print 'found option for ',o, val
			if val:
				setattr(b.cfg, o, val)

	method = options.type
	# metric day with added activities columns, convert it to the basic method and set "add activities" flag.
	print method
	if method == 'dma'or method == 'mda': 
		method = 'dm'
		act_metr = 1

	do_csv = b.cfg.json_csv == 'csv'

	# for day metrics and day sleep, make sure date includes a day
	if 'd' in method and not day:
		print "Got month and year in date. Didn't get day, instead got ",options.date, " Stopping."
		return

	# method letters are dm=day metrics, ds = day sleep, ma = month activities, ms = month sleep. 
	# allow for dyslexia	
	if method == 'md' or method == 'dm':
		b.GetDayData(yr, mo, day, 'metrics', do_csv, options.nocache, act_metr)

	elif method == 'ds' or method == 'sd':
		b.GetDayData(yr, mo, day, 'sleep', do_csv, options.nocache)
		
	elif method == 'ma' or method == 'am':
		b.GetActivityCsvForMonth(yr, mo, override_cache =options.nocache)
		
	elif method == 'ms' or method == 'sm':
		b.GetSleepCsvForMonth(yr, mo) ##$$ no override_cache option

	#pp2(b.cfg)
	b.OnClose() # save config data
	

if __name__ == "__main__":
	# allow immediate display of console output
	sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)
	p = optparse.OptionParser()
	#options: email, password, type, addactivities, datestring, usecache, savedir, save_pwd
	p.add_option("-l", "--login_id", dest="loginid", help="Login ID (email) for basis Website") #, metavar="FILE")
	p.add_option("-p", "--password", dest="passwd", help="Login ID (email) for basis Website") #, metavar="FILE")
	p.add_option("-t", "--type", help="Data type: dm (or day_metrics), dma (or day_metrics_activities-- DEFAULT), ds (or day_sleep), ma (or months_activity), ms (or months_sleep)", default = 'dma') #, metavar="FILE")
	p.add_option("-d", "--date", help="Date: YYYY-MM-DD for day types, YYYY-MM for month types") #, metavar="FILE")
	p.add_option("-C", "--nocache", action='store_true', help="Save email, password (scrambled), savedir to a file so you don't have to specify them for each command", default = False) #, metavar="FILE")
	p.add_option("-s", "--savedir", help="Destination directory for retrieved files") #, metavar="FILE")
	p.add_option("-w", "--save_pwd", dest="savepwd", action='store_true',help="Save password to cache along with other data.", default = False) #, metavar="FILE")
	p.add_option("-V", "--no_csv", dest="json_csv", action="store_const", const="json",help="Normally data is converted to and saved as csv in addition to (raw) json. With -V, only json is stored.", default = 'csv') #, metavar="FILE")
	p.add_option("-j", "--jsondir", help="directory to store (raw) json data.  A relative path converts to a subdir beneath save_dir.", default = False) #, metavar="FILE")
	p.add_option("-o", "--override_cache", action = 'store_true', help="Override any cached json data files-- retrieve data fresh from server.", default = False) #, metavar="FILE")
	
	(options, args) = p.parse_args()
	execute(options)
	#main()
	
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
v9: (aligned with BasisRetriever v11, for release 0.2): more cleanup, some data validation before hitting basis's servers
v10: (aligned with BasisRetriever.py v13): refactored json conversion to result in array of python objects, then have a single "convert to csv" method.  This allows us to do additional processing (e.g., tagging metrics rows with activities or sleep) in the python realm, then convert to csv at the end. Also extracts which headers are saved in the csv files.
v11: (aligned with BasisRetriver.py v14): clean up and got monthly summaries working with refactored processing methods.
v12 (aligned with BasisRetriever.py v15): AddActivitiesToMetrics-- now makes activities part of the metrics list.
v13 (aligned with BasisRetriever.py v16): Sleep data integrated. Still need to confirm data is correct.
v14 (aligned with basis_retr.py v17): fixed bug where fail metrics collection if no sleep events for that day.  Also added "cache override" checkbox to allow forcing redownload of json file.
v15 (aligned with BasisRetriever.py v18): Got json display and json dir config working correctly.  Next step is to move the guts of OnGetDayData() into basis_retr.py in prep for command line implementation.  After that, move column names to config file. THen move Config class to separate file.
v16 (aligned with BasisRetriever.py v19): Moved main method for downloading a single day's data into basis_retr.py. Next, move column names to config file. Then move Config class to separate file.
v17 (also BasisRetriever.py v20): Column names in config file. Config class is now separate file. Next step is cleanup.
v18 (also BasisRetriever.py v21): Got initial command line version running.  Still need to test out options thoroughly.
v19 (also BasisRetriever.py v22): command line data retrieval tested and all versions seem to be working.  Added logic to wait some number of days before allowing cached data to stay. This helps ensure that we don't use cached data for a partially uploaded day.
v20 (also BasisRetriever.py v23): External changes: added explicit jsondir to UI and config. UI now shows only metrics buttons/sizes if Add activities to metrics is checked (as sleep events is superfluous in that case). Fixed bug where no data at all saved for a given month results in no info in UI at all (should be dates and dashes for sizes). Changed "future date" text color to "dark gray"
Internal: packaged CreateDirSelectorWidget into its own method (along with UserSelectDirectory).  Renamed FormatSummaryCell to MakeLabelClickable and made method more generic (can accept arbitrary pathnames or lambdas and arbitrary labels.
v21 (also BasisRetriever.py v24): Cleanup.  Also got datetime working as default fields.  Tightened up month summary data processing.
"""
