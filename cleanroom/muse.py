"""
Low-level Muse headset interaction.

This module comes from https://github.com/NeuroTechX/bci-workshop/
"""

import bitstring
import pygatt
import numpy as np
from time import time, sleep
import sys
import platform

from time import localtime, strftime

ATTR_TP9 = '273e0003-4c4d-454d-96be-f03bac821358' # 0x1f-0x21
ATTR_AF7 = '273e0004-4c4d-454d-96be-f03bac821358' # fp1 0x22-0x24
ATTR_AF8 = '273e0005-4c4d-454d-96be-f03bac821358' # fp2 0x25-0x27
ATTR_TP10 = '273e0006-4c4d-454d-96be-f03bac821358' # 0x28-0x2a
ATTR_TELEMETRY = "273e000b-4c4d-454d-96be-f03bac821358"


interface = 'COM5' if platform.system() == 'Windows' else '/dev/ttyACM0'
class Muse():
    """Muse 2016 headband"""

    def __init__(self, address=None, 
                 callback=None, 
                 callback_eeg=None,
                 eeg=True, accelero=False,
                 giro=False, backend='auto', interface=None, time_func=time,
                 name=None):
        """Initialize"""
        self.address = address
        self.name = name
        self.callback = callback
        self.callback_eeg = callback_eeg
        self.eeg = eeg
        self.accelero = accelero
        self.giro = giro
        self.interface = interface
        self.time_func = time_func

        if backend in ['gatt', 'bgapi']:
            if backend == 'bgapi':
                self.backend = 'bgapi'
            else:
                self.backend = 'gatt'
        else:
            raise(ValueError('Backend must be auto, gatt or bgapi'))

    def connect(self, interface=None, backend='auto'):
        """Connect to the device"""

        if self.backend == 'gatt':
            self.interface = self.interface or 'hci0'
            self.adapter = pygatt.GATTToolBackend(self.interface)
        else:
            self.adapter = pygatt.BGAPIBackend(serial_port=self.interface)

        self.adapter.start()

        if self.address is None:
            address = self.find_muse_address(self.name)
            if address is None:
                raise(ValueError("Can't find Muse Device"))
            else:
                self.address = address
        self.device = self.adapter.connect(self.address)

        # subscribes to EEG stream
        if self.eeg:
            self._subscribe_eeg()

        # subscribes to Accelerometer
        if self.accelero:
            raise(NotImplementedError('Accelerometer not implemented'))

        # subscribes to Giroscope
        if self.giro:
            raise(NotImplementedError('Giroscope not implemented'))

    def find_muse_address(self, name=None):
        """look for ble device with a muse in the name"""
        list_devices = self.adapter.scan(timeout=10.5)

        for device in list_devices:
            print(device)

            if name:
                if device['name'] == name:
                    print('Found device %s : %s' % (device['name'],
                                                    device['address']))
                    return device['address']
            elif device['name'] is not None and 'Muse' in device['name']:
                print('Found device %s : %s' % (device['name'],
                                                device['address']))
                return device['address']

        return None

    def start(self):
        """Start streaming."""
        self._init_sample()
        self.last_tm = 0
        self.device.char_write_handle(0x000e, [0x02, 0x64, 0x0a], False)

    def stop(self):
        """Stop streaming."""
        self.device.char_write_handle(0x000e, [0x02, 0x68, 0x0a], False)

    def disconnect(self):
        """disconnect."""
        self.device.disconnect()
        self.adapter.stop()

    def _subscribe_eeg(self):
        """subscribe to eeg stream."""
        self.device.subscribe(ATTR_TP9,
                              callback=self._handle_eeg)
        self.device.subscribe(ATTR_AF7,
                              callback=self._handle_eeg)
        self.device.subscribe(ATTR_AF8,
                              callback=self._handle_eeg)
        self.device.subscribe(ATTR_TP10,
                              callback=self._handle_eeg)
        

    def _subscribe_telemetry(self):
        self.device.subscribe(ATTR_TELEMETRY, callback=self._handle_telemetry)

    def _unpack_eeg_channel(self, packet):
        """Decode data packet of one eeg channel.

        Each packet is encoded with a 16bit timestamp followed by 12 time
        samples with a 12 bit resolution.
        """
        aa = bitstring.Bits(bytes=packet)
        pattern = "uint:16,uint:12,uint:12,uint:12,uint:12,uint:12,uint:12, \
                   uint:12,uint:12,uint:12,uint:12,uint:12,uint:12"
        res = aa.unpack(pattern)
        timestamp = res[0]
        data = res[1:]
        # 12 bits on a 2 mVpp range
        data = 0.48828125 * (np.array(data) - 2048)
        return timestamp, data

    def _init_sample(self):
        """initialize array to store the samples"""
        self.timestamps = np.zeros(5)
        self.data = np.zeros((5, 12))

    def _handle_eeg(self, handle, data):
        """Calback for receiving a sample.

        sample are received in this oder : 44, 41, 38, 32, 35
        wait until we get 35 and call the data callback
        """

        timestamp = self.time_func()
        index = int((handle - 32) / 3)
        tm, d = self._unpack_eeg_channel(data)

        if self.last_tm == 0:
            self.last_tm = tm - 1

        self.data[index] = d
        self.timestamps[index] = timestamp
        # last data received
        if handle == 35:
            if tm != self.last_tm + 1:
                print("missing sample %d : %d" % (tm, self.last_tm))
            self.last_tm = tm
            # affect as timestamps the first timestamps - 12 sample
            timestamps = np.arange(-12, 0) / 256.
            timestamps += np.min(self.timestamps[self.timestamps != 0])
            self.callback(self.data, timestamps)
            self.callback_eeg(self.data, timestamps)
            self._init_sample()
    

    def _handle_telemetry(self, handle, packet):
        """Handle the telemetry (battery, temperature and stuff) incoming data"""

        if handle != 26:  # handle 0x1a
            return

        bit_decoder = bitstring.Bits(bytes=packet)
        pattern = "uint:16,uint:16,uint:16,uint:16,uint:16"  # The rest is 0 padding
        data = bit_decoder.unpack(pattern)

        battery = data[1] / 512

        print("Battery __", battery, localtime(time()), '________________')
