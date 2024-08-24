from time import time, localtime, strftime, sleep
import pygatt
import platform
from binascii import hexlify

interface = 'COM5' if platform.system() == 'Windows' else '/dev/ttyACM0'

address = '00:55:DA:BB:86:C9'

adapter = pygatt.GATTToolBackend()
ATTR_AF7 = "273e0004-4c4d-454d-96be-f03bac821358" 

def handle_data(handle, value):
    """
    handle -- integer, characteristic read handle the data was received on
    value -- bytearray, the data returned in the notification
    """
    print("Received data: %s" % hexlify(value), handle)


try:
    print("Starting adapter and connecting to the device...")
    adapter.start()
    device = adapter.connect(address)
    device.subscribe(ATTR_AF7,
                     callback=handle_data)
    print(f"Connected to {address}")

    while True:
        device.subscribe(ATTR_AF7,
                     callback=handle_data)
        sleep(1)

except pygatt.exceptions.NotConnectedError:
    # Handle the case where the connection is lost
    print(f"Connection lost. Reconnecting to {address}...")
    adapter.stop()
    sleep(2)  # Wait a bit before trying to reconnect
except Exception as e:
    # Catch-all for any other exceptions
    print(f"An unexpected error occurred: {e}")
    adapter.stop()