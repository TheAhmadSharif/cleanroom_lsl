import subprocess
import time
subprocess.call(["ffplay", "-nodisp", "-autoexit", "alert.mp3"])
print('\007')