############# Muse ##############
import bitstring
import mne_lsl.lsl
import numpy as np
from time import time, localtime, strftime
import pygatt
import logging
import argparse
import sys
import platform

log_level = logging.ERROR
backend = 'dongle'
interface = 'COM5' if platform.system() == 'Windows' else '/dev/ttyACM0'

############# Muse ##############

from functools import partial
from time import time, localtime, strftime, sleep
import logging
from pprint import pprint
# address = '00:55:DA:BB:86:C9'

from playsound import playsound
######### Constants #########
ATTR_STREAM_TOGGLE = "273e0001-4c4d-454d-96be-f03bac821358"  
ATTR_TP9 = "273e0003-4c4d-454d-96be-f03bac821358" 
ATTR_AF7 = "273e0004-4c4d-454d-96be-f03bac821358" 
ATTR_AF8 = "273e0005-4c4d-454d-96be-f03bac821358" 
ATTR_TP10 = "273e0006-4c4d-454d-96be-f03bac821358"
ATTR_TELEMETRY = "273e000b-4c4d-454d-96be-f03bac821358"
MUSE_NB_EEG_CHANNELS = 5
MUSE_SAMPLING_EEG_RATE = 256
LSL_EEG_CHUNK = 12

####################################################


class Muse:
    """Muse EEG headband"""

    def __init__(
        self,
        address,
        callback_eeg=None,
        callback_control=None,
        callback_telemetry=None,
        callback_acc=None,
        callback_gyro=None,
        callback_ppg=None,
        preset=None,
        disable_light=False,
        backend=backend
        
    ):


        self.counter = 0
        self.last_battery_print_time = 0 

        self.address = address
        self.backend = backend
        self.callback_eeg = callback_eeg
        self.callback_telemetry = callback_telemetry
        self.callback_control = callback_control


        self.enable_eeg = not callback_eeg is None
        self.enable_control = not callback_control is None
        self.enable_telemetry = not callback_telemetry is None


        self.preset = preset
        self.disable_light = disable_light

    def connect(self):
        """Connect to the device"""

        print(f"Connecting to {self.address}...", '–––', strftime("%H:%M:%S", localtime(time())), '______')
        # self.adapter =  pygatt.GATTToolBackend()

        if self.backend == 'bgapi':
            self.adapter = pygatt.BGAPIBackend(serial_port=interface)
        else:
            self.adapter = pygatt.GATTToolBackend()


        self.adapter.start()
        self.device = self.adapter.connect(self.address)

        if self.preset not in ["none", "None"]:
            self.select_preset(self.preset)

        # subscribes to EEG stream
        if self.enable_eeg:
            self._subscribe_eeg()

        if self.enable_control:
            self._subscribe_control()

        if self.enable_telemetry:
            self._subscribe_telemetry()

        if self.disable_light:
            self._disable_light()

        self.last_timestamp = mne_lsl.lsl.local_clock()

        return True

    def _write_cmd(self, cmd):
        """Wrapper to write a command to the Muse device.
        cmd -- list of bytes"""
        self.device.char_write_handle(0x000E, cmd, False)

    def _write_cmd_str(self, cmd):
        """Wrapper to encode and write a command string to the Muse device.
        cmd -- string to send"""
        self._write_cmd([len(cmd) + 1, *(ord(char) for char in cmd), ord("\n")])

    def ask_control(self):
        self._write_cmd_str("s")

    def ask_device_info(self):
        self._write_cmd_str("v1")

    def ask_reset(self):
        """Undocumented command reset for '*1'
        The message received is a singleton with:
        "rc": return status, if 0 is OK
        """
        self._write_cmd_str("*1")

    def start(self):
        """Start streaming."""
        self.first_sample = True
        self._init_sample()
        self.last_tm = 0
        self._init_control()
        self.resume()

    def resume(self):
        """Resume streaming, sending 'd' command"""
        self._write_cmd_str("d")

    def stop(self):
        """Stop streaming."""
        self._write_cmd_str("h")

    def keep_alive(self):
        """Keep streaming, sending 'k' command"""
        self._write_cmd_str("k")

    def select_preset(self, preset="p21"):
        if type(preset) is int:
            preset = str(preset)
        if preset[0] == "p":
            preset = preset[1:]
        preset = bytes(preset, "utf-8")
        self._write_cmd([0x04, 0x70, *preset, 0x0A])

    def disconnect(self):
        """disconnect."""
        self.device.disconnect()
        if self.adapter:
            self.adapter.stop()

    def _subscribe_eeg(self):
        """subscribe to eeg stream."""
        self.device.subscribe(ATTR_TP9, callback=self._handle_eeg)
        self.device.subscribe(ATTR_AF7, callback=self._handle_eeg)
        self.device.subscribe(ATTR_AF8, callback=self._handle_eeg)
        self.device.subscribe(ATTR_TP10, callback=self._handle_eeg)

    def _unpack_eeg_channel(self, packet):
        aa = bitstring.Bits(bytes=packet)
        pattern = "uint:16,uint:12,uint:12,uint:12,uint:12,uint:12,uint:12, \
                   uint:12,uint:12,uint:12,uint:12,uint:12,uint:12"

        res = aa.unpack(pattern)
        packetIndex = res[0]
        data = res[1:]
        data = 0.48828125 * (np.array(data) - 2048)
        return packetIndex, data

    def _init_sample(self):
        """initialize array to store the samples"""
        self.timestamps = np.full(5, np.nan)
        self.data = np.zeros((5, 12))

    def _init_ppg_sample(self):
        """Initialise array to store PPG samples

        Must be separate from the EEG packets since they occur with a different sampling rate. Ideally the counters
        would always match, but this is not guaranteed
        """
        self.timestamps_ppg = np.full(3, np.nan)
        self.data_ppg = np.zeros((3, 6))

    def _init_timestamp_correction(self):
        self.sample_index = 0
        self.sample_index_ppg = 0
        self._P = 1e-4
        t0 = mne_lsl.lsl.local_clock()
        self.reg_params = np.array([t0, 1.0 / 256])  # EEG Sampling Rate = 256 Hz
        self.reg_ppg_sample_rate = np.array([t0, 1.0 / 64])  # PPG Sampling Rate = 64 Hz

    def _update_timestamp_correction(self, t_source, t_receiver):
        """Update regression for dejittering

        This is based on Recursive least square.
        See https://arxiv.org/pdf/1308.3846.pdf.
        """

        # remove the offset
        t_receiver = t_receiver - self.reg_params[0]

        # least square estimation
        P = self._P
        R = self.reg_params[1]
        P = P - ((P**2) * (t_source**2)) / (1 - (P * (t_source**2)))
        R = R + P * t_source * (t_receiver - t_source * R)

        # update parameters
        self.reg_params[1] = R
        self._P = P

    def _handle_eeg(self, handle, data):
        """Callback for receiving a sample.

        samples are received in this order : 44, 41, 38, 32, 35
        wait until we get 35 and call the data callback
        """
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
        # last data received
        if handle == 35:
            if tm != self.last_tm + 1:
                if (tm - self.last_tm) != -65535:  # counter reset
                    print("missing sample %d : %d" % (tm, self.last_tm))
                    # correct sample index for timestamp estimation
                    self.sample_index += 12 * (tm - self.last_tm + 1)

            self.last_tm = tm

            # calculate index of time samples
            idxs = np.arange(0, 12) + self.sample_index
            self.sample_index += 12

            self._update_timestamp_correction(idxs[-1], np.nanmin(self.timestamps))
            timestamps = self.reg_params[1] * idxs + self.reg_params[0]
            self.callback_eeg(self.data, timestamps)
            self.last_timestamp = timestamps[-1]
            self._init_sample()


    def _init_control(self):
        """Variable to store the current incoming message."""
        self._current_msg = ""

    def _subscribe_control(self):
        self.device.subscribe(ATTR_STREAM_TOGGLE, callback=self._handle_control)

        self._init_control()

    def _handle_control(self, handle, packet):
        
        if handle != 14:
            return

        # Decode data
        bit_decoder = bitstring.Bits(bytes=packet)
        pattern = "uint:8,uint:8,uint:8,uint:8,uint:8,uint:8,uint:8,uint:8,uint:8,uint:8, \
                    uint:8,uint:8,uint:8,uint:8,uint:8,uint:8,uint:8,uint:8,uint:8,uint:8"

        chars = bit_decoder.unpack(pattern)

        # Length of the string
        n_incoming = chars[0]

        # Parse as chars, only useful bytes
        incoming_message = "".join(map(chr, chars[1:]))[:n_incoming]

        # Add to current message
        self._current_msg += incoming_message

        if incoming_message[-1] == "}":  # Message ended completely
            self.callback_control(self._current_msg)

            self._init_control()

    def _subscribe_telemetry(self):
        self.device.subscribe(ATTR_TELEMETRY, callback=self._handle_telemetry)

    def _handle_telemetry(self, handle, packet):
        """Handle the telemetry (battery, temperature and stuff) incoming data"""

        if handle != 26:  # handle 0x1a
            return

        bit_decoder = bitstring.Bits(bytes=packet)
        pattern = "uint:16,uint:16,uint:16,uint:16,uint:16"  # The rest is 0 padding
        data = bit_decoder.unpack(pattern)

        battery = data[1] / 512
        self.counter = self.counter + 1

        current_time = time()
        if current_time - self.last_battery_print_time >= 600:
            print("Battery ______", battery, ' % ______', strftime("%H:%M:%S", localtime(current_time)), '______')
            self.last_battery_print_time = current_time  # Update the last print time


 

    def _disable_light(self):
        self._write_cmd_str("L0")

####################################################  
####################################################
####################  Stream    ####################
####################################################
####################################################


def stop_bluetooth(backend, didconnect):
    if backend == 'bgapi':
        pygatt.BGAPIBackend(serial_port=interface).stop()
  

initial_time = None
alert_played = False 
def stream(address, ppg=False, acc=False, gyro=False, preset=None, backend=backend):
    global initial_time
    global alert_played 
    def start_stream():
        didConnect = False
        try:
            eeg_info = mne_lsl.lsl.StreamInfo(
                "Muse",
                stype="EEG",
                n_channels=5,
                sfreq=256,
                dtype="float32",
                source_id=f"Muse_{address}",
            )
            eeg_info.desc.append_child_value("manufacturer", "Muse")
            eeg_info.set_channel_names(["TP9", "AF7", "AF8", "TP10", "AUX"])
            eeg_info.set_channel_types(["eeg"] * 5)
            eeg_info.set_channel_units("microvolts")

            eeg_outlet = mne_lsl.lsl.StreamOutlet(eeg_info, chunk_size=6)

            def push(data, timestamps, outlet):
                outlet.push_chunk(data.T, timestamps[-1])

            push_eeg = partial(push, outlet=eeg_outlet)
            muse = Muse(
                address=address,
                callback_eeg=push_eeg,
                callback_ppg=None,
                callback_acc=None,
                callback_gyro=None,
                preset=preset,
                backend=backend
            )
            
            didConnect = muse.connect()

            if didConnect:
                
                muse.start()
                muse._subscribe_telemetry()
                initial_time = strftime("%H:%M:%S", localtime(time())) 

                print(f"Streaming... EEG", '___', initial_time)

                _counter = 1

                while True:
                    _counter += 1
                    if mne_lsl.lsl.local_clock() - muse.last_timestamp > 5:
                        print(" Resume Start ", strftime("%H:%M:%S", localtime(time())) )
                        muse.resume()
                        print("No data received for 5 seconds. Reconnecting...")
                        raise Exception("No data received, attempting to reconnect.")
                    
                    try:
                        sleep(1)
                    except KeyboardInterrupt:
                        print("Stream interrupted. Stopping...")
                        playsound('alert.mp3')
                        muse.disconnect()
                        return False

        except Exception as e:
            print(f"An error occurred: {e}", strftime("%H:%M:%S", localtime(time())))
            stop_bluetooth(backend, didConnect)
            return False


    while True:
        try:
            success = start_stream()
            if success:
                break

        except Exception as e:
            print(f"Error during streaming: {e}")
            if not alert_played:  # Check if alert has been played
                playsound('alert.mp3')
                alert_played = True 
        print('Start Time__', initial_time, "__End time __", strftime("%Y-%m-%d %H:%M:%S", localtime(time()))) 
        sleep(1)
        print("Attempting to reconnect ...")
        sleep(.25)  # Delay before trying to reconnect


########################## 


parser = argparse.ArgumentParser(description="Start an LSL stream from Muse headset")
parser.add_argument(
    "-a",
    "--address",
    dest="address",
    type=str,
    default='',
    help="Device MAC address.",
)

parser.add_argument(
    "-b",
    "--backend",
    dest="backend",
    type=str,
    default='bgapi',
    help="Device MAC address.",
)

args = parser.parse_args(sys.argv[1:])

##########################

if not args.address:
    print("Please provide address")
    sys.exit(1)  


stream(args.address, ppg=False, acc=False, gyro=False, preset="p50", backend=args.backend)