from .muse import Muse
from .models import Sample
import time
from multiprocessing import Process, Queue

from queue import Empty
from functools import partial
import mne_lsl.lsl


def play_sound():
    for x in range(2):
        print('\007')
        time.sleep(1)


def _target(queue, address=None, backend=None, interface=None, name=None):
    def add_to_queue(data, timestamps):
        for i in range(12):
            queue.put(Sample(timestamps[i], data[:, i]))

    try:
        
        ##################################################

       
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

        ##################################################
        muse = Muse(
            address=address,
            callback=add_to_queue,
            callback_eeg=push_eeg,
            backend=backend,
            interface=interface,
            name=name
        )

        connect = muse.connect()
        print('Connected', connect)
        
        muse.start()
        initial_time = time.strftime("%H:%M:%S", time.localtime(time.time()))

        print('Streaming ...', initial_time )
        play_sound()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print()
            print('Start Time__', initial_time, "__End time __", time.strftime("%H:%M:%S", time.localtime(time.time())) )
            print()
        finally:
            muse.stop()
            muse.disconnect()
            print("Disconnected ")
            play_sound()
            print('Start Time__', initial_time, "__End time __", time.strftime("%H:%M:%S", time.localtime(time.time())) )
    except Exception as e:
        # queue.put(e)
        print()
        print(f"An error occurred: {e}", '___ 75 ___')
        print()

def get_raw(timeout=30, **kwargs):
    q = Queue()
    p = Process(target=_target, args=(q,), kwargs=kwargs)
    p.daemon = True
    p.start()
    
    try:
        while True:
            try:
                item = q.get(timeout=timeout)
                if isinstance(item, Exception):
                    raise item
                else:
                    yield item
            except Empty:
                print("Queue is empty, stopping the stream.")
                play_sound()
                break  # Stop the loop if the queue is empty
    except Exception as e:
        print(f"An error occurred: {e}")
        play_sound()
    finally:
        print("Stopped Streaming")
        play_sound()
        print("__End time __", time.strftime("%H:%M:%S", time.localtime(time.time())) )
