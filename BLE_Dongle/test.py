import sounddevice as sd
import numpy as np
import pandas as pd
fs = 44100
df_alert = pd.read_csv('alert.csv')
start_data = df_alert['Amplitude'].values
start_max_val = np.max(np.abs(start_data))
normalized_data_start = start_data / np.max(np.abs(start_data))


sd.play(normalized_data_start, fs)



'''
from playsound import playsound
playsound('alert.mp3')
'''
