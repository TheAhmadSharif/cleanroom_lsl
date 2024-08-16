"""Models"""

import json


class Sample:
    """A sampling of sensor data at a specific time"""

    def __init__(self, timestamp, data):
        """
        Constructs a new sample.

        timestamp: A (float) UNIX timestamp of when the sample was collected.
        data: A numpy array of sensor data.
        """

        self.timestamp = timestamp
        self.data = data

        ##############################
        '''eeg_info = mne_lsl.lsl.StreamInfo(
            "Muse",
            stype="EEG",
            n_channels=5,
            sfreq=256,
            dtype="float32",
            source_id="Muse",
        )
        eeg_info.desc.append_child_value("manufacturer", "Muse")
        eeg_info.set_channel_names(["TP9", "AF7", "AF8", "TP10", "AUX"])
        eeg_info.set_channel_types(["eeg"] * 5)
        eeg_info.set_channel_units("microvolts")

        eeg_outlet = mne_lsl.lsl.StreamOutlet(eeg_info, chunk_size=6)

        def push(data, timestamps, outlet):
            outlet.push_chunk(data.T, timestamps[-1])

        partial(push, outlet=eeg_outlet) '''

        ##############################

        # print(self.data, '___ Data ___')

    def to_json(self):
        return json.dumps(dict(timestamp=self.timestamp, data=self.data.tolist()))
