import sys, os, pprint
import tkFileDialog, tkFont
import re
from Tkinter import *
from datetime import date
import xor # for saving passwords
import calendar
from basis_retr import *
import helpDialog
import subprocess # for launching files
#from scrollable_frame import *

try: # for saving config data
	import cPickle as pickle
except ImportError:
	import pickle # fall back on Python version

# Note: bsaw.py already set python's console output buffer to zero.  Don't do again or crash.
def qw(s):
	return tuple(s.split())

class BasisRetrApp(Frame):
	"""Application object and UI"""
	
	YEARS = [`yr` for yr in range(2013,2019)]
	#YEARS=qw('2013 2014 2015 2016 2017 2018')
	DEFAULT_YEAR = '2014'
	DATE_FMT = "%04d-%02d-%02d"
	COL_NAMES = qw('Date Metrics Download Sleep Download')
	#COL_NAMES = qw('Date Metrics Download Activity Download Sleep Download')
	#UI_ELEMENT_NAMES = qw('savedir loginid passwd month year save_pwd json_csv')
	
	def __init__(self, root=None,basepath="/"):
		Frame.__init__(self)
		self.logged_in = False
		
		#self.userid = None # should use BasisRetrApp's version, not duplicate it here?
		self.ui = {
				'savedir':StringVar(), 
				'loginid':StringVar(),
				'passwd':StringVar(),
				'month':StringVar(),
				'year':StringVar(),
				'save_pwd':IntVar(),
				'json_csv':StringVar()
			}
		
		self.bretr = BasisRetr(loadconfig = True)
		self.bretr.Status = self.Status
		self.master.title( "Basis Data Retriever" )
		self.createWidgets()
		self.bretr.cfg.Load()
		#self.LoadConfig(CONFIG_FILENAME, self.ui)
		self.SetUiFromConfig()
		self.PopulateData()
		
	def OnClose(self):
		self.GetConfigFromUI()
		try:
			self.bretr.OnClose()
			#self.SaveConfig(CONFIG_FILENAME, self.ui)
		except Exception, v: # ignore if problem
			print "Got Exception during save Config on close:",`v`
		master.destroy()

	def ShowHelp(self):
		# dialog is destroyed when user closes it.  Nothing else to do here.
		helpDialog.Help(master,
		"""Basis Retriever
Retrieve personal data from the Basis Website.

Usage:
1st line in application window: Enter directory to save data

2nd line: Enter login id and password. 
IMPORTANT NOTE: clicking the "Save Password" checkbox
encodes your password so that it is not stored on your 
computer in plain text.  YOUR PASSWORD IS NOT 
ENCRYPTED-- it is easily decoded.  If this is a concern to 
you, do not check Save Password, and enter your 
password each time you run this program.

Select a month and year on the left side of the window.

This app keeps track of 3 different types of data you can
download for a given date:
 - metrics for an entire day, in json format.
     Filename format is YYYY-MM-DD_basis_metrics.json
 - Activity list in json format. 
     Filename format is YYYY-MM-DD_basis_activities.json
 - metrics for an entire day, in csv format. 
     Filename format is YYYY-MM-DD_basis.csv

The initial display shows, for each day, the file size for each 
type of data.  If there's no file for that day, '--' is shown. Click the button to the right of '--' to retrieve it from the basis website and save it.

Once the data is successfully downloaded, the filesize appears.
""")

	def ShowAbout(self):
		helpDialog.Help(master,
		"""Basis Retriever
Copyright (c) 2014, Rich Knopman

This application may be modified and redistributed
under the BSD license. See License.txt for specifics.""")
		
	############################
	##
	##		Populate the UI with widgets, then data
	##
	def createWidgets(self):
		self.dir_text = []
		
		# 1st row: directory select for saving data
		config_frame = Frame(self.master)
		config_frame.pack(side=TOP,fill=X)
		
		# Login ID and password
		Label( config_frame, text='MyBasis: Login ID', padx=5).pack( side=LEFT)
		self.loginid_text = Entry(config_frame, width=15,  # path entry
			textvariable = self.ui['loginid'])
		self.loginid_text.pack(side=LEFT, fill=X)

		Label( config_frame, text='Password', padx=5).pack( side=LEFT)
		self.passwd_text = Entry(config_frame, width=10,  show="*",
			textvariable = self.ui['passwd'])
		self.passwd_text.pack(side=LEFT, fill=X)
		Checkbutton(config_frame, text='Save Pwd', variable=self.ui['save_pwd']).pack(side=LEFT)
		
		# Directory selection
		Label( config_frame, text='Save Dir', padx=5).pack( side=LEFT)
		self.dir_text = Entry(config_frame, width=30,  # path entry
			textvariable = self.ui['savedir'])
		self.dir_text.pack(side=LEFT, fill=X, expand=20)
		self.button1 = Button( config_frame, text = "...", command=self.UserSelectDirectory) #button for dir select dialog
		self.button1.pack(side=LEFT)

		# Info buttons on the right.
		Button(config_frame, text="?", command = self.ShowHelp, padx=5).pack(side=RIGHT)
		Label(config_frame, text=" ").pack(side=RIGHT)
		Button(config_frame, text="About", command = self.ShowAbout, padx=5).pack(side=RIGHT)
		Label(config_frame, text=" ").pack(side=RIGHT)

		# Left-hand Column: Month-Year selectors
		moyr_frame = Frame(self.master)
		moyr_frame.pack(side=LEFT, fill=Y)
		self.AddYearSelector(moyr_frame)
		self.AddMonthSelector(moyr_frame)
		self.AddJsonCsvSelector(moyr_frame)
		self.AddAdditionalButtons(moyr_frame)
		
		# table for data and buttons to collect it
		self.data_frame = Frame(self.master) 
		self.data_frame.pack(side = LEFT, fill=Y)
		self.status_bar = StatusBar(self.master)
		# Gave up trying ScrollableFrame(master = self.master). Multiple columns is working fine.

	def AddYearSelector(self, parent):
		"""Create dropdown selector for years"""
		Label(parent, text='Year').pack(side=TOP)
		yr_option = OptionMenu(parent, self.ui['year'], *BasisRetrApp.YEARS)
		yr_option.pack(side=TOP)
		#yr_option.bind("<ButtonRelease-1>", self.OnMoYrChange)
		self.ui['year'].set(BasisRetrApp.DEFAULT_YEAR)
		self.ui['year'].trace("w", self.OnUIChange)#OnOptionChange)
		
	def AddMonthSelector(self, parent):
		"""Create Listbox for user to select a month"""
		# calendar.mo_abbr has an extra entry at index zero, need to ignore that, hence the -1
		Label(parent, text='Month').pack(side=TOP)
		self.mo = Listbox(parent, listvariable=self.ui['month'], height=len(calendar.month_abbr)-1, width=5, font = ("Arial",12))
		self.mo.pack(side=TOP)
		self.mo.bind("<<ListboxSelect>>",self.OnUIChange)#OnMoYrChange)
		# build listbox using month names
		for i,mname in enumerate(calendar.month_abbr):
			if i==0: continue # ignore month # 0--doesn't refer to anything
			self.mo.insert(i-1, " "+mname)

	def AddJsonCsvSelector(self, parent):
		"""Create dropdown selector for years"""
		Label(parent, text='Work in').pack(side=TOP)
		json_csv_option = OptionMenu(parent, self.ui['json_csv'], *['json', 'csv'])
		json_csv_option.pack(side=TOP)
		#json_csv_option.bind("<ButtonRelease-1>", self.OnMoYrChange)
		#json_csv_option.bind("<<ListboxSelect>>", self.OnMoYrChange)
		self.ui['json_csv'].set('csv')
		self.ui['json_csv'].trace("w", self.OnUIChange)#OnOptionChange)

	def AddAdditionalButtons(self, parent):
		self.mo_act = Label(parent, text='act_siz')
		self.mo_act.pack(side=TOP)
		dl_actys = Button( parent, text = "D/L Acty's")
		dl_actys.pack(side=TOP)
		dl_actys.bind("<ButtonRelease-1>", self.OnGetActivitiesForMonth)
		self.mo_sleep = Label(parent, text='slp_siz')
		self.mo_sleep.pack(side=TOP)
		dl_sleep = Button( parent, text = "D/L Sleep")
		dl_sleep.pack(side=TOP)
		dl_sleep.bind("<ButtonRelease-1>", self.OnGetSleepForMonth)
		
	def PopulateData(self, day=None):
		"""Scan user-selected directory, show info on files for selected month, along with download buttons.  Can update UI for a single day only (by setting 'day' param) or for the entire month (day = None).""" 
		# Data for month is shown in 2 columns.
		# Left side (columns 0-6) is first half of month
		# Right side (columns 7-13) is for 2nd half

		# yr and mo are  both strings from the UI-- coerce to int
		yr, mo = int(self.GetUI('year')), int(self.GetUI('month')[0])
		json_csv = self.GetUI('json_csv')
		days_in_month = calendar.monthrange(yr, mo+1)[1]
		
		# First, retrieve the file info, filtered for only this month.
		metrics_sizes, activities_sizes, sleep_sizes = self.GetFileData(yr, mo,days_in_month, json_csv)
		
		# make date range: either entire month or for a single day if one was passed in.
		if day: 
			date_range = range(day-1, day)
		else: # redraw entire month
			date_range = range(days_in_month)
			# the following clears the frame so that when we redraw,
			# bits from the prior frame don't show through
			# THOUGH the clear/redraw process is jarring
			self.data_frame.forget()
			self.data_frame = Frame(self.master) 
			self.data_frame.pack(side = LEFT, fill=BOTH)
		fr = self.data_frame
		
		# header row-- create column headings
		for coff in [0,7]: # left hand side, then right hand side
			for (c, lbl) in enumerate(BasisRetrApp.COL_NAMES):
				Label(fr, text=lbl).grid(row=0, column=coff+c)
				
		# Column and row offsets for dealing with columns
		coff = 0 
		roff = 1 # start at 1 to account for column heading
		# TkFont.Font requires root frame ("master" here) to exist, so can't make it a class variable.
		LINK_FONT= tkFont.Font(size=9,underline=1)
		for r in date_range:
			if r >= int(days_in_month/2): 
				# shift offsets for right hand side columns
				coff = 7
				roff = -int(days_in_month/2)+1 # +1= account for header row
				# if displaying a month in the future, prevent the rows from scrunching up vertically.
				fr.grid_rowconfigure(r+roff, minsize = 25)
				
			# column zero: date
			d = date(yr, mo+1, r+1)
			dy = calendar.day_abbr[d.weekday()]
			# highlight weekend days
			bgcolor = d.weekday() in [5,6] and 'yellow' or None
			# show dates in the future with gray text
			today = date.today()
			# show future dates as gray
			fgcolor =  d > today and "gray" or None
			
			dt= ("%04d-%02d-%02d"% (yr,mo+1,r+1)) # also used for filenames in click handlers below
			
			Label(fr, text=dt+" "+dy, anchor=W,fg=fgcolor, bg = bgcolor).grid(row=r+roff, column=coff+0, sticky=W+E+N+S )
			
			# dates in the future are empty rows
			if fgcolor == "gray":
				continue
				
			# column 1: metrics file size or "--" if no file
			lbl = Label(fr, text=str(metrics_sizes[r] or "  --  "), font=metrics_sizes[r] and LINK_FONT or None, fg = metrics_sizes[r] and "blue" or None)
			lbl.grid(row=r+roff, column=coff+1)
			lbl.bind("<Button-1>",lambda e, d=dt:self.OpenFile("{}_basis_metrics.{}".format(d, json_csv)))
			
			# column 2: metrics download button
			btext = 'metrics %02d' % (r+1)
			b = Button(fr, text=btext,borderwidth=1)
			b.grid(row=r+roff, column = coff+2, ipady=0)
			b.bind("<ButtonRelease-1>", self.OnGetDayData)

			# column 3: activities file size or "--" if no file
			lbl=Label(fr, text=str(sleep_sizes[r] or "--"))
			lbl = Label(fr, text=str(sleep_sizes[r] or "  --  "), font=sleep_sizes[r] and LINK_FONT or None, fg = sleep_sizes[r] and "blue" or None)
			lbl.grid(row=r+roff, column=coff+3)
			lbl.bind("<Button-1>",lambda e, d=dt:self.OpenFile("{}_basis_sleep.{}".format(d, json_csv)))
			
			# column 4: activities download button
			btext = 'sleep %02d' % (r+1)
			b = Button(fr, text=btext,borderwidth=1)
			b.grid(row=r+roff, column = coff+4)
			b.bind("<ButtonRelease-1>", self.OnGetDayData)

			"""
			# column 3: activities file size or "--" if no file
			lbl=Label(fr, text=str(activities_sizes[r] or "--"), borderwidth=2)
			lbl.grid(row=r+roff, column=coff+3)
			lbl.bind("<Button-1>",lambda e, d=dt:self.OpenFile("{}_basis_activities.{}".format(d, json_csv)))
			
			# column 4: activities download button
			btext = 'activities %02d' % (r+1)
			b = Button(fr, text=btext)
			b.grid(row=r+roff, column = coff+4)
			b.bind("<ButtonRelease-1>", self.OnGetDayData)

			# column 5: Sleep file size or "--" if no file
			lbl = Label(fr, text=str(sleep_sizes[r] or "--"), borderwidth=2)
			lbl.grid(row=r+roff, column=coff+5)
			lbl.bind("<Button-1>",lambda e, d=dt:self.OpenFile("{}_basis_sleep.{}".format(d, json_csv)))
			
			# column 6: CSV download button
			btext = 'sleep %02d' % (r+1)
			b = Button(fr, text=btext)
			b.grid(row=r+roff, column = coff+6)
			b.bind("<ButtonRelease-1>", self.OnGetDayData)
			"""
			# Update all-month statistics
			fname = "{:04d}-{:02d}_basis_activities_summary.csv".format(yr, mo+1)
			self.FormatSummaryCell(fname, self.mo_act)
			"""
			fpath = os.path.join(os.path.abspath(self.bretr.cfg.savedir), fname)
			if os.path.isfile(fpath):
				label = os.path.getsize(fpath)
				#lbl = Label(fr, text=str(act_size or "  --  "), font=act_size and LINK_FONT or None, fg = act_size and "blue" or None)
				self.mo_act['text']=label
				self.mo_act['fg'] = "blue"
				self.mo_act['font'] = LINK_FONT
				self.mo_act.bind("<Button-1>",lambda e, d=dt:self.OpenFile(fname))
			else:
				label="--"
				self.mo_act['text']=label
				self.mo_act['fg'] = None
				self.mo_act['font'] = None
			"""
			fname = "{:04d}-{:02d}_basis_sleep_summary.csv".format(yr, mo+1)
			self.FormatSummaryCell(fname, self.mo_sleep)
			"""fpath = os.path.join(os.path.abspath(self.bretr.cfg.savedir), fname)
			if os.path.isfile(fpath):
				label = os.path.getsize(fpath)
			else:
				label="--"
			self.mo_sleep['text']=label
			"""
	def FormatSummaryCell(self, fname, button):
		# TkFont.Font requires root frame ("master" here) to exist, so can't make it a class variable.
		LINK_FONT= tkFont.Font(size=9,underline=1)
		fpath = os.path.join(os.path.abspath(self.bretr.cfg.savedir), fname)
		if os.path.isfile(fpath):
			label = os.path.getsize(fpath)
			#lbl = Label(fr, text=str(act_size or "  --  "), font=act_size and LINK_FONT or None, fg = act_size and "blue" or None)
			button['text']=label
			button['fg'] = "blue"
			button['font'] = LINK_FONT
			button.bind("<Button-1>",lambda e:self.OpenFile(fname))
		else:
			label="--"
			button['text']=label
			button['fg'] = None
			button['font'] = None

	def OpenFile(self, fname):
		fpath = os.path.join(os.path.abspath(self.bretr.cfg.savedir), fname)
		if not os.path.isfile(fpath):
			self.Status("clicked '{}', but didn't open.".format(fpath))
		else:
			self.Status("Opening '{}'.".format(fname))
			if 0:# ismac:
				path = os.path.realpath(os.path.join(dir, fname))
				findertools.launch(path)
			else: # assume windows for now
				# could also do a generic "open" for file.  Directories don't work here, though.
				cmd = 'cmd /c "start '+escape_win_path_spaces(fpath)+'"'
				try:
					p = subprocess.Popen(cmd, shell = True)
				except Exception as e:
					print("Tried to open file but didn't: "+ `type(e)`+"=>"+`e`)

	METRICS_RE= re.compile("metrics")
	ACTIVITIES_RE = re.compile("activities")
	SLEEP_RE = re.compile('sleep')
	def GetFileData(self, yr, mo, days_in_month, json_csv):
		"""Walk through directory (including subdirectories) and gather file sizes"""
		#self.GetConfigFromUI()
		top_folder = self.GetUI('savedir')
		#top_folder = self.bretr.cfg.savedir
		YrMo_re= re.compile('%04d-%02d-(\d\d)' % (yr, mo+1))
		type_re = re.compile('\.'+json_csv+'$')
		# regexs for determining, from the filename, what kind of data is in the file 
		metrics= [None]*days_in_month
		activities = [None]*days_in_month
		sleep = [None]*days_in_month
		for top_folder, dirs, files in os.walk(top_folder, topdown=False):
			for name in files: # look for y-m match first
				d = type_re.search(name)
				m = YrMo_re.search(name)
				if not m or not d: continue 	# file is from another month or not the right type
					
				day = int(m.group(1))
				path = os.path.realpath(os.path.join(top_folder, name))
				size = os.path.getsize(path)
				#if name=="2014-02-02_basis_sleep.csv":
				#	print "found name", name, BasisRetrApp.SLEEP_RE.search(name)

				try:
					if BasisRetrApp.METRICS_RE.search(name):
						metrics[day-1] = size
					if BasisRetrApp.ACTIVITIES_RE.search(name):
						activities[day-1] = size
					if BasisRetrApp.SLEEP_RE.search(name):
						sleep[day-1] = size
				except Exception, v:
					self.Status("Error gathering metrics for day"+`day`+":",`v`)
		return metrics, activities, sleep

	############################
	##
	##			Data Retrieval from Basis Website
	##
	# Need to log in to Basis website at the beginning to get session cookie
	def CheckLogin(self):
		if not self.logged_in:
			self.Login()
			self.logged_in = True

	def Login(self):
		# first, gather data for login: email and password
		self.GetConfigFromUI() # this does the right thing so that login works without any params
		#email, passwd, savedir = cfg['loginid'], cfg['passwd'], cfg['savedir']
		"""
		email = self.ui['loginid'].get()
		passwd = self.ui['passwd'].get()
		savedir = self.ui['savedir'].get()
		self.bretr = BasisRetr(email, passwd, savedir, self.userid)
		"""
		#try:
		self.bretr.Login()
		#except Exception, v:
		#	self.Status("Login Error:"+`v`)
			
	def OnGetDayData(self, evt):
		"""Get either metrics or activities json data from Basis website.  For now, button name is how we get the date and type of data to download."""
		
		btn = evt.widget.config('text')[-1] # get the text shown on the button
		type, day = btn[0], int(btn[1])
		# Get button text as btn.config('text')[-1].  This returns a tuple split by spaces.  date num is last item in tuple.
		mo, yr = int(self.GetUI('month')[0]+1), int(self.GetUI('year'))
		#month = cfg.month[0]+1 # correct zero-based month (0 = Jan)
		#year = int(cfg.year)
		date = "%04d-%02d-%02d" % (yr, mo, day)
		self.Status("Checking Login")
		self.bretr.CheckLogin() # ensure we're logged in
		self.Status("getting "+type+" for "+date)
		# figure out which data to get
		data = None
		# filenames for json and csv
		jfname = "{date}_basis_{type}.json".format(date=date, type=type)
		jfpath = os.path.join(os.path.abspath(self.bretr.cfg.savedir), jfname)
		cfname = "{date}_basis_{type}.csv".format(date=date, type=type)
		cfpath = os.path.join(os.path.abspath(self.bretr.cfg.savedir), cfname)		
		
		do_csv = self.GetUI('json_csv') == 'csv'
		have_json_for_csv = os.path.exists(jfpath) and do_csv
		if have_json_for_csv: # have json data; just read it in
			with open(jfpath, "r") as f:
				data = f.read()
				jdata = json.loads(data)
				
		# if needed, download json data from website and save to file
		if not have_json_for_csv:
			if type == 'metrics':
				jdata = self.bretr.GetMetricsForDay(date)
			elif type == 'activities':
				jdata = self.bretr.GetActivitiesForDay(date)
			#elif type == 'sleep':
			#	jdata = self.bretr.GetSleepForDay(date)
			elif type == 'sleep':
				jdata = self.bretr.GetSleepEventsForDay(date)
			# this should be an option
			self.bretr.SaveData(json.dumps(jdata), jfname)
			
		cdata = None
		if do_csv:
			if type == 'metrics':
				cdata = self.bretr.StartMetricsCSV()
				cdata += self.bretr.AddMetricsCSV(jdata)
			if type == 'activities':
				cdata = self.bretr.StartActivitiesCSV()
				cdata += self.bretr.AddActivitiesCSV(jdata)
			if type == 'sleep':
				cdata = self.bretr.StartSleepEventsCSV()
				cdata += self.bretr.AddSleepEventsCSV(jdata)
				#print "got docsv=",do_csv,"=",cdata
#		except Exception, v:
#			self.Status("Problem getting data from basis website:"+`v`)
		#if jdata:
		#	print "getday, data=",json.dumps(jdata)[0:200]
		#	self.bretr.SaveData(json.dumps(jdata), fname)
		if cdata:
			self.bretr.SaveData(cdata, cfname)
			##$$ clean this up.  Pass entire path to above save method 
			fpath = os.path.join(os.path.abspath(self.GetUI('savedir')), cfname)
			self.Status("Saved "+type+" at "+fpath)
			# Update data in list
		self.PopulateData(day)
		
	def OnGetCsvData(self, evt):
		"""Convert json metrics to csv format.  If json metrics not yet downloaded yet, then do that first and only save csv"""
		#self.GetConfigFromUI() # get the text shown on the button
		#cfg = self.bretr.cfg
		btn = evt.widget.config('text')[-1]
		type, day = btn[0], int(btn[1])
		# Get button text as btn.config('text')[-1].  This returns a tuple split by spaces.  date num is last item in tuple.
		mo, yr = int(self.GetUI('month')[0]), int(self.GetUI('year'))
		
		#month = cfgmonth+1 # correct zero-based month (0 = Jan)
		#year = int(cfg.year)
		date = "%04d-%02d-%02d" % (year, month, day)

		#first, read json file
		fname = date+"_basis_metrics.json"
		self.Status("getting "+type+" for "+date)
		fpath = os.path.join(os.path.abspath(self.bretr.cfg.savedir), fname)

		if not os.path.exists(fpath):
			# download json first
			self.CheckLogin()
			json_data = self.bsaw.GetMetricsForDay(date)
			self.Status("Got json data for ",date)
		else: # just read the data from the exsiting file
			with open(fpath, "r") as f:
				data = f.read()
			json_data = json.loads(data)
		
		fname = date + "_basis.csv"
		fpath = os.path.join(os.path.abspath(self.bretr.cfg.savedir), fname)
		SaveCsv(fpath, json_data)
		self.Status("Saved activities data to "+fpath)
		self.PopulateData(day)

	def OnGetActivitiesForMonth(self, evt):
		"""Get a month's worth of activities"""
		yr, mo = int(self.GetUI('year')), int(self.GetUI('month')[0])
		#self.bretr = BasisRetr(email, passwd, savedir, self.userid)
		#yr, mo = int(cfg.year), int(cfg.month[0])
		self.bretr.GetActivityCsvForMonth(yr, mo)
		self.PopulateData()

	def OnGetSleepForMonth(self, evt):
		"""Get a month's worth of sleep data"""
		yr, mo = int(self.GetUI('year')), int(self.GetUI('month')[0])
		self.bretr.GetSleepCsvForMonth(yr, mo)
		self.PopulateData()

	###########################
	##
	##		UI Helpers and Event Handlers
	##
	def GetUI(self, label):
		"""Get a widget's value based on the key name in self.ui"""
		if label == "month":
			w = self.mo
			cs = w.curselection()
			if len(cs)>0: # make sure a month was actually selected
				index = int(cs[0])
			else:
				index = 0 # default to first month of year
				self.mo.selection_set(index)

			value = w.get(index)
			return index, value
		else:
			return self.ui[label].get()

	def OnUIChange(self, *args):#name, index, op):
		"""Respond to UI context changes (year, month, json/csv) by redrawing table for month.  Different event handlers have different method signatures, but we ignore them (via *args) because we don't care."""
		self.PopulateData()
		
	#def OnMoYrChange(self, evt):
	#	self.PopulateData()

	def Status(self, txt):
		self.status_bar.set(txt)

	def UserSelectDirectory(self):
		currentdir = self.ui['savedir'].get()
		dirname = tkFileDialog.askdirectory(parent=self,initialdir=currentdir,title='Please select a directory')
		self.dir_text.delete(0,END)
		self.dir_text.insert(0,dirname)
		self.focus_set()
		if dirname: # don't change anything if user hit escape (i.e., dirname =="")
			self.ui['savedir'].set(os.path.realpath(dirname))
			self.PopulateData()
	
	###########################
	##
	##				Save and load config data
	##
	"""
	def LoadConfig(self, fpath, ui):
		try:
			fh = file(fpath, "r")
			cfg = pickle.load(fh)
			fh.close()
		except Exception, v:
			self.Status("didn't load file: "+ `v`) 
			return # return None if didn't load, so caller can add data (e.g., on first run) and save it later.
		# TKinter is messy- there's no straightforward way to set a listbox via strVar() like the other UI elements.
		# 		Need to handle them (i.e., month dropdown) separately 
	"""
	def SetUiFromConfig(self):
		"""Set the value of each UI element from config"""
		cfg = self.bretr.cfg#.__dict__
		for k in self.ui.keys():
			if not hasattr(cfg,k): continue # not in cfg: continue
			v = getattr(cfg,k)
			if k == 'month':
				self.mo.selection_set(v[0])
			#elif k =='passwd': # decode from what was stored in file
			#	p = xor.xor_crypt_string(v, decode=True)
			#	ui[k].set(p)
			elif k in self.ui.keys():
				self.ui[k].set(v)
		# userid (hex string unique to user) is not part of the ui, but is helpful to
		# save between sessions
		#if 'userid' in cfg: 
		#	self.userid = cfg['userid']

	def GetConfigFromUI(self):
		"""For each UI item, set config from the UI's value"""
		cfg = self.bretr.cfg
		for k, v in self.ui.items():
			#print k, k in cfg.__dict__
			if k not in cfg.__dict__:
				continue
			if k == 'month': # Tk handles listboxes differently than other UI element types
				try:
					setattr(cfg,k,self.mo.curselection()[0])
				except:
					pass
			else:
				setattr(cfg,k,v.get())

	"""def SaveConfig(self, fpath, cfg):
	#	Save Config info before close
		fh = None
		# turn StringVar, IntVar, etc. into dict
		savecfg = {}
		for k,v in cfg.items():
			# As with loadConfig above, getting a listbox's state is different than other Tkinter widgets
			if k == 'month':
				try:
					savecfg[k] = self.mo.curselection()[0]
					#print self.mo.curselection(),"got month = ",savecfg[k], type(savecfg[k])
				except:
					pass
			elif k == 'passwd':
				saving_pwd = cfg['save_pwd'].get()
				if saving_pwd > 0: # only persist password if asked to 
					# "checked" value in 'save pwd' button is 0 if unchecked 1 if checked
					# code up (obsfuscate) password for local storage
					# NOTE: this is NOT secure encryption.
					c = xor.xor_crypt_string(v.get(), encode=True)
					savecfg[k] = c
			else:
				savecfg[k] = v.get()
		# userid is different because it's not in the UI, 
		# but is persistant-- it doesn't change for a given account
		savecfg['userid'] = self.userid
		try:
			fh = file(fpath, "w")
			pickle.dump(savecfg, fh)
		except IOError, v:
			self.Status("didn't save file: "+ v)
		if fh: fh.close()
	"""
#####################
##
##				End of class BasisRetrApp

import pprint
def ppp(object):
	"""debugging support: pretty print any object"""
	pprint.PrettyPrinter().pprint(object)

def escape_win_path_spaces(path):
	"""turn each space in pathnames into " ".  Used when launching file in host os."""
	return re.sub(" ","\" \"",path,99)

class StatusBar:
	def __init__(self, master):
		self.label = Label(master, text="", bd=1, relief=SUNKEN, anchor=W)
		self.label.pack(side=BOTTOM, fill=X)

	def set(self, format, *args):
		self.label.config(text=format % args)
		self.label.update_idletasks()

	def clear(self):
		self.label.config(text="")
		self.label.update_idletasks()


def main():
	fr = BasisRetrApp(master)
	master.protocol("WM_DELETE_WINDOW", fr.OnClose)
	fr.mainloop()

master = Tk() # boy, it was mysterious that we had to set this var-


if __name__ == "__main__":
	main()

""" Version Log
v0: some initial UI. About to make year a dropdown select box.
v1: UI framework seems to be working correctly. About to add day-by-day table
v2: correctly downloading both metrics and activities as json data.  About to download csv and get scrollable grid (can't get to end of month as it falls off bottom of screen)
v3: CSV works.  Instead of scrollable for now, made days in 2 sets of columns-- wider, but don't have to deal with ScrollableFrame, which isn't working yet.  Also, now clearing frame when redrawing entire month.
	Next steps: save password scrambled, add column heads
v4: Cleanup, now saving password scrambled, column heads added, using status bar
v5: big cleanup, changing save-to folder now updates the ui
v6: Fixed name collision Bug: now referring to BasisRetr correctly.
v7: About to integrate with updated basis_retr.py (v6)
v8: (aligned with basis_retr v7.py): refactored metrics, activities, and sleep downloading correctly, csv + json.  Also got month of activities downloading correctly.  Launching csv files by clicking on file size number.
v9: (aligned with basis_retr v8): Fixed event handlers for option (drop-down) menus. Date grid now only allows selecting metrics and sleep to download-- changed activity and sleep summary data so that now it only downloads for an entire month (no more day-specific buttons).  Links to files now styled to look like browser hyperlinks. Weekend days now highlighted in yellow.
"""
