from Tkinter import *
class Help:
	def __init__(self, master, text):
		self.toplevel = Toplevel(master)
		frame = Frame(self.toplevel)#, bg="Yellow")
		frame.pack(expand=YES, fill=BOTH)
		t = Label(frame, text=text, padx=20, pady=5, justify=LEFT)
		t.pack()
		b = Button(frame, text="Done", padx=50, command=self.quit)
		b.pack()
		self.toplevel.title("Help")
		self.toplevel.protocol("WM_DELETE_WINDOW", self.quit)

	def show(self):
		self.toplevel.wait_visibility()

	def quit(self, event=None):
		self.toplevel.destroy()