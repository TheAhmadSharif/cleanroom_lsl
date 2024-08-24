from time import time, localtime, strftime, sleep
import pygatt
import platform
from binascii import hexlify
from functools import partial
import mne_lsl.lsl

# Define constants
interface = 'COM5' if platform.system() == 'Windows' else '/dev/ttyACM0'
address = '00:55:DA:BB:86:C9'
ATTR_AF7 = "273e0004-4c4d-454d-96be-f03bac821358"

class Muse:    
    def __init__(self, address, callback_eeg=None, backend='dongle', preset=None):
        self.address = address
        self.callback_eeg = callback_eeg
        self.backend = backend
        self.preset = preset

    def connect(self):
        print("Connecting to the device...")
        self.adapter = pygatt.GATTToolBackend()
        self.adapter.start()
        self.device = self.adapter.connect(self.address)
        if self.preset:
            self.select_preset(self.preset)
        
        return True
    
    def select_preset(self, preset):
        pass
    
    def disconnect(self):
        if self.device:
            self.device.disconnect()
        if self.adapter:
            self.adapter.stop()
    def resume(self):
        self._write_cmd_str("d")

    def _write_cmd(self, cmd):
        self.device.char_write_handle(0x000E, cmd, False)

    def _write_cmd_str(self, cmd):
        self._write_cmd([len(cmd) + 1, *(ord(char) for char in cmd), ord("\n")])

    def handle_data(self, handle, value):
        print("Received data: %s" % hexlify(value), handle)

    def start(self):
        self.resume()
    def _subscribe_eeg(self):
        self.device.subscribe(ATTR_AF7, callback=self._handle_eeg)
def main():
    muse = Muse(
                address=address,
                callback_eeg=push_eeg,
                callback_ppg=None,
                callback_acc=None,
                callback_gyro=None,
                preset=None,
                backend=None
            )
    
    try:
        if muse.connect():
            print(f"Connected to {address}")
            muse.start()
            while True:
                sleep(1)  # Keep the script running

    except pygatt.exceptions.NotConnectedError:
        print(f"Connection lost. Reconnecting to {address}...")
        muse.disconnect()
        sleep(2)  # Wait a bit before trying to reconnect
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        muse.disconnect()

if __name__ == "__main__":
    main()
