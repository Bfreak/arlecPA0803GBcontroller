from mainboardreader import mainboard_reader, working_mainboard_reader
from projectconfig import *
import _thread
import time

_thread.start_new_thread(mainboard_reader, ())

while True:
    print("running")
    time.sleep(10)