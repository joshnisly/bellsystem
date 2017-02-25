#!/usr/bin/python

import os
import sys
import time

import RPi.GPIO as GPIO

import bells

BELLS_FILE = sys.argv[1]

BELLS_MAPPING = [
    7,
    12,
    13,
    29,
    31,
    32,
    33,
    35,
]


def run_forever():
    bells_def = None
    bells_mod_time = None

    previously_active = []

    for bell in range(0, len(BELLS_MAPPING)):
        _enable(bell, False)

    while True:
        mod_time = os.stat(BELLS_FILE).st_mtime
        if not bells_def or mod_time != bells_mod_time:
            bells_def = bells.Bells()
            bells_def.load_from_file(BELLS_FILE)
            bells_mod_time = mod_time

        activations = bells_def.get_active_bells()

        for bell in previously_active:
            if not bell in activations:
                _enable(bell, False)

        for bell in activations:
            _enable(bell, True)

        previously_active = activations

        time.sleep(0.1)


def _enable(bell, enable):
    pin = BELLS_MAPPING[bell]
    state = 0 if enable else 1
    GPIO.output(pin, state)


def _setup():
    GPIO.setmode(GPIO.BOARD)
    for pin in BELLS_MAPPING:
        GPIO.setup(pin, GPIO.OUT)

if __name__ == '__main__':
    _setup()
    run_forever()
