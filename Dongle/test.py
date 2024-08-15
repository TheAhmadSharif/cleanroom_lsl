import platform


if(platform.system() == "Windows"):
     interface = 'COM5'
else:
    interface = '/dev/ttyACM0'
