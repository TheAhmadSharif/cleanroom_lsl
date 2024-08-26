import asyncio
from bleak import BleakClient
import bitstring
import mne_lsl.lsl
from time import time, localtime, strftime, sleep
import logging
import argparse
import sys
import platform
import numpy as np
from functools import partial

log_level = logging.ERROR
backend = 'dongle'
interface = 'COM5' if platform.system() == 'Windows' else '/dev/ttyACM0'

######### Constants #########
ATTR_STREAM_TOGGLE = "273e0001-4c4d-454d-96be-f03bac821358"  
ATTR_TP9 = "273e0003-4c4d-454d-96be-f03bac821358" 
ATTR_AF7 = "273e0004-4c4d-454d-96be-f03bac821358" 
ATTR_AF8 = "273e0005-4c4d-454d-96be-f03bac821358" 
ATTR_TP10 = "273e0006-4c4d-454d-96be-f03bac821358"
ATTR_TELEMETRY = "273e000b-4c4d-454d-96be-f03bac821358"

class Muse:
    """Muse EEG headband"""

    def __init__(self, address, callback_eeg=None, callback_control=None, callback_telemetry=None,
                 callback_acc=None, callback_gyro=None, callback_ppg=None, preset=None, disable_light=False, backend=backend):
        self.counter = 0
        self.last_battery_print_time = 0 
        self.address = address
        self.backend = backend
        self.callback_eeg = callback_eeg
        self.callback_telemetry = callback_telemetry
        self.callback_control = callback_control
        self.enable_eeg = callback_eeg is not None
        self.enable_control = callback_control is not None
        self.enable_telemetry = callback_telemetry is not None
        self.preset = preset
        self.disable_light = disable_light
        self.client = None

    async def connect(self):
        """Connect to the device using BleakClient"""

        print(f"Connecting to {self.address}...", '______', strftime("%H:%M:%S", localtime(time())), '______')

        self.client = BleakClient(self.address)
        await self.client.connect()

        if self.preset not in ["none", "None"]:
            await self.select_preset(self.preset)
        
        if self.enable_eeg:
            await self._subscribe_eeg()

        if self.enable_control:
            await self._subscribe_control()

        if self.enable_telemetry:
            await self._subscribe_telemetry()

        if self.disable_light:
            await self._disable_light()

        self.last_timestamp = mne_lsl.lsl.local_clock()
        return True

    async def _write_cmd(self, cmd):
        """Wrapper to write a command to the Muse device."""
        await self.client.write_gatt_char(ATTR_STREAM_TOGGLE, bytes(cmd))

    async def _write_cmd_str(self, cmd):
        """Wrapper to encode and write a command string to the Muse device."""
        await self._write_cmd([len(cmd) + 1, *(ord(char) for char in cmd), ord("\n")])

    async def start(self):
        """Start streaming."""
        self.first_sample = True
        self._init_sample()
        self.last_tm = 0
        self._init_control()
        await self.keep_alive()
        await self.resume()

    async def resume(self):
        """Resume streaming, sending 'd' command"""
        await self._write_cmd_str("d")

    async def stop(self):
        """Stop streaming."""
        await self._write_cmd_str("h")

    async def keep_alive(self):
        """Keep streaming, sending 'k' command"""
        await self._write_cmd_str("k")

    async def select_preset(self, preset="p21"):
        if type(preset) is int:
            preset = str(preset)
        if preset[0] == "p":
            preset = preset[1:]
        await self._write_cmd([0x04, 0x70, *bytes(preset, "utf-8"), 0x0A])

    async def disconnect(self):
        """Disconnect the device."""
        await self.client.disconnect()
        self.client = None

    async def _subscribe_eeg(self):
        """Subscribe to EEG stream."""
        await self.client.start_notify(ATTR_TP9, self._handle_eeg)
        await self.client.start_notify(ATTR_AF7, self._handle_eeg)
        await self.client.start_notify(ATTR_AF8, self._handle_eeg)
        await self.client.start_notify(ATTR_TP10, self._handle_eeg)

    def _unpack_eeg_channel(self, packet):
        aa = bitstring.Bits(bytes=packet)
        pattern = ("uint:16,uint:12,uint:12,uint:12,uint:12,uint:12,uint:12,"
                   "uint:12,uint:12,uint:12,uint:12,uint:12,uint:12")
        res = aa.unpack(pattern)
        packetIndex = res[0]
        data = res[1:]
        data = 0.48828125 * (np.array(data) - 2048)
        return packetIndex, data

    def _init_sample(self):
        """Initialize array to store the samples."""
        self.timestamps = np.full(5, np.nan)
        self.data = np.zeros((5, 12))

    def _init_timestamp_correction(self):
        self.sample_index = 0
        self._P = 1e-4
        t0 = mne_lsl.lsl.local_clock()
        self.reg_params = np.array([t0, 1.0 / 256])  # EEG Sampling Rate = 256 Hz

    def _update_timestamp_correction(self, t_source, t_receiver):
        """Update regression for dejittering"""
        t_receiver = t_receiver - self.reg_params[0]
        P = self._P
        R = self.reg_params[1]
        P = P - ((P**2) * (t_source**2)) / (1 - (P * (t_source**2)))
        R = R + P * t_source * (t_receiver - t_source * R)
        self.reg_params[1] = R
        self._P = P

    def _handle_eeg(self, handle, data):
        """Callback for receiving a sample."""
        self.counter += 1
        if self.first_sample:
            self._init_timestamp_correction()
            self.first_sample = False
        timestamp = mne_lsl.lsl.local_clock()
        index = int((handle - 32) / 3)
        tm, d = self._unpack_eeg_channel(data)
        if self.last_tm == 0:
            self.last_tm = tm - 1
        self.data[index] = d
        self.timestamps[index] = timestamp
        if handle == 35:
            if tm != self.last_tm + 1:
                if (tm - self.last_tm) != -65535:  # counter reset
                    print("missing sample %d : %d" % (tm, self.last_tm))
                    self.sample_index += 12 * (tm - self.last_tm + 1)
            self.last_tm = tm
            idxs = np.arange(0, 12) + self.sample_index
            self.sample_index += 12
            self._update_timestamp_correction(idxs[-1], np.nanmin(self.timestamps))
            timestamps = self.reg_params[1] * idxs + self.reg_params[0]
            self.callback_eeg(self.data, timestamps)
            self.last_timestamp = timestamps[-1]
            self._init_sample()

    async def _subscribe_control(self):
        await self.client.start_notify(ATTR_STREAM_TOGGLE, self._handle_control)
        self._init_control()

    def _init_control(self):
        """Variable to store the current incoming message."""
        self._current_msg = ""

    async def _handle_control(self, handle, packet):
        if handle != 14:
            return
        bit_decoder = bitstring.Bits(bytes=packet)
        pattern = ("uint:8,uint:8,uint:8,uint:8,uint:8,uint:8,uint:8,uint:8,"
                   "uint:8,uint:8,uint:8,uint:8,uint:8,uint:8,uint:8,uint:8,"
                   "uint:8,uint:8,uint:8,uint:8")
        chars = bit_decoder.unpack(pattern)
        n_incoming = chars[0]
        incoming_message = "".join(map(chr, chars[1:]))[:n_incoming]
        self._current_msg += incoming_message
        if incoming_message[-1] == "}":
            self.callback_control(self._current_msg)
            self._init_control()

    async def _subscribe_telemetry(self):
        await self.client.start_notify(ATTR_TELEMETRY, self._handle_telemetry)

   
