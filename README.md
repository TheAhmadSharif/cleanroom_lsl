# Cleanroom

Integrate LSL library [A Muse S headset](https://github.com/ysimonson/cleanroom) 

<p align="center">
    <img src="https://raw.github.com/ysimonson/cleanroom/master/demo.gif">
</p>

## Hardware requirements

* [A Muse 2016 headset](http://www.choosemuse.com/)
* If you are on mac or windows, a [BLED112 bluetooth LE dongle](https://www.silabs.com/products/wireless/bluetooth/bluetooth-low-energy-modules/bled112-bluetooth-smart-dongle), as pygatt requires it.

## Getting started

1) Plug in the dongle and turn on your Muse headset.
2) Clone this repo: `git clone git@github.com:ysimonson/cleanroom.git`.
3) Setup virtualenv: `virtualenv -p python3 venv`.
4) Install dependencies `pip install -r requirements.txt`.
5) Start the server: `python web.py`.
6) Wait for the server to connect to your Muse headset.
7) Navigate to `http://localhost:8888`.
