import subprocess
import time
import os

subprocess.call(["ffplay", "-nodisp", "-autoexit", "alert.mp3"])
print('\007')

