#!/usr/bin/python

import datetime
import RPi.GPIO as GPIO
import subprocess
import time

import screen


def main():
    while True:
        try:
            GPIO.setmode(GPIO.BOARD)
            lcd = screen.HD44780()
            ip_addr = subprocess.check_output("ifconfig eth0 | grep 'inet addr' | awk '{print $2}' | awk -F: '{print $2}'", shell=True).strip()
            lcd.clear()
            lcd.message('IP ' + ip_addr + '\n' + datetime.datetime.now().strftime('%m/%d %H:%M:%S'))

            time.sleep(1)
        except Exception:
            import traceback
            traceback.print_exc()
            pass


if __name__ == '__main__':
    GPIO.setwarnings(False)
    main()

