#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""
MIT License

Copyright (c) 2019 sistemicorp

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import _thread
import time
import pyb
import micropython
import array
import machine
import os

from upyrpc_const import *
from upyrpc_server import MicroPyServer

micropython.alloc_emergency_exception_buf(100)
__DEBUG_FILE = "upyrpc_main"


class uPyRPC(MicroPyServer):
    """ Async MicroPython Server
    - runs in its own thread

    cmds: Are in this format: {"method": <class_method>, "args": <args>}
    ret: Are in this format: {"method": <class_method>, "value": <value>}

    Notes:
        1. Every RPC method should put a return object into the return queue, like so,

            self._ret.put({"method": "pwm", "value": {'value': 'scheduled'}, "success": True})


    """
    VERSION = "0.2"
    SERVER_CMD_SLEEP_MS = 100  # polling time for processing new commands

    LED_RED    = 1
    LED_GREEN  = 2
    LED_YELLOW = 3
    LED_BLUE   = 4

    # Valid ADC pins to read voltage.
    # 1) X1 is NOT included because it its reserved for jig closed detection
    # 2)
    ADC_VALID_PINS = ["X2",  "X3",  "X4",  "X5",  "X6",  "X7",  "X8",
                      "X11", "X12", "X19", "X20", "X21", "X22", "Y11", "Y8"]
    ADC_VALID_INTERNALS = ["VBAT", "TEMP", "VREF", "VDD"]
    ADC_READ_MULTI_TIMER = 8
    ADC_MAX_FREQ = 10000
    ADC_MAX_SAMPLES = 1000

    PWM_MAX_FREQ = 10000

    JIG_CLOSED_TIMER = 4
    JIG_CLOSED_TIMER_FREQ = 1  # Hz
    JIG_CLOSED_PIN = "X1"

    SUPPLY_NAMES = ["V1", "V2"]

    def __init__(self, debug=False):
        super().__init__(debug)
        self._debug_flag = True  # set True to catch any class init errors

        # use dict to store static data
        self.ctx = {
            "threads": {},         # threads
            "gpio": {},            # gpios used are named here
            "timers": {},          # timers running are listed here
            "pwm": {},             # pwms
            "adc_read_multi": {},  # cache args
        }

        self._debug_flag = debug
        self.reset({})

    def _is_timer_running(self, timer_name):
        return timer_name in self.ctx["timer"]

    def _init_gpio(self, name, pin, mode, pull=pyb.Pin.PULL_NONE):
        self.ctx["gpio"][name] = pyb.Pin(pin, mode, pull)

    # ===================================================================================
    # Methods
    # NOTES:
    # 1. !! DON'T access public API, ret/peek/update/cmd, functions, access the queue's directly
    #    Else probably get into a lock lockup

    def reset(self, args):
        """ Reset the board to known state
        - gets called on init

        :return:
        """
        pyb.LED(LED_RED).on()
        pyb.LED(LED_GREEN).on()
        pyb.LED(LED_YELLOW).on()
        pyb.LED(LED_BLUE).on()

        # turn off threads, all threads should be in a while loop, looking at the state
        # of self.ctx["threads"][<name>], and exit if this is False.  Set all names to False...
        for t in self.ctx["threads"]:
            self.ctx["threads"][t] = False

        # to de-init a pin, turn it back to an input, disabled PULL-UP/DN
        # remove it from the gpio dict
        for p in self.ctx["gpio"]:
            name = self.ctx["gpio"][p].names()[1]
            temp = pyb.Pin(name, pyb.Pin.IN, pyb.Pin.PULL_NONE)
            self.ctx["gpio"].pop(p)

        # turn off timers
        for t in self.ctx["timers"]:
            pass  # TODO: cancel

        pyb.LED(LED_RED).off()
        pyb.LED(LED_GREEN).off()
        pyb.LED(LED_YELLOW).off()
        pyb.LED(LED_BLUE).off()
        self._ret.put({"method": "reset", "value": {}, "success": True})

    def unique_id(self, args):
        """ Get the Unique ID of the Micro Pyboard

        args: None
        :return:
        """
        id_bytes = machine.unique_id()
        res = ""
        for b in id_bytes:
            res = ("%02x" % b) + res
        self._ret.put({"method": "unique_id", "value": {'value':res}, "success": True})

    def debug(self, args):
        """ enable debugging

        args: { 'enable': True/False }
        :param enable: boolean
        :return: self.VERSION
        """
        self._debug_flag = args.get("enable", False)
        self._ret.put({"method": "debug", "value": {'value': self._debug_flag}, "success": True})

    def version(self, args):
        """ version

        :param args: not used
        :return: self.VERSION
        """
        self._debug("testing message", 164, __DEBUG_FILE, "version")  # note line number is manually set
        uname = str(os.uname())
        # uname looks like: "(sysname='pyboard', nodename='pyboard', release='1.11.0', version='v1.11 on 2019-05-29', machine='PYBv1.1 with STM32F405RG')"
        # turn this into a dict
        items = list(uname.replace("(", "").replace(")", "").replace("'", "").split(","))
        uname = {}
        for item in items:
            key = item.split("=")[0].strip()
            value = item.split("=")[1].strip()
            uname[key] = value
        self._ret.put({"method": "version", "value": {'version': self.VERSION, "uname": uname}, "success": True})

    def _toggle_led(self, led, on_ms, off_ms, once=False):
        """ Toggle LED function - this is run on a thread
        - to exit the thread, just exit this function

        :param led:
        :param on_ms:
        :param off_ms:
        :param once:
        :return:
        """
        thread_name = "led{}".format(led)
        while self.ctx["threads"][thread_name]:
            pyb.LED(led).on()
            time.sleep_ms(on_ms)
            if off_ms:
                pyb.LED(led).off()
                time.sleep_ms(off_ms)
            if once: break

        self.ctx["threads"][thread_name] = False
        pyb.LED(led).off()

    def led_toggle(self, args):
        """ Toggle LED on
        - a led is toggled on its own thread

        args: { 'led': <#>, 'on_ms': <#>, 'off_ms': <#> }
        :param led: one of LED_*
        :param on_ms: milli seconds on, if 0 the led will be turned off
        :param off_ms: milli seconds off
        :param once: if set, LED is toggled on for on_ms and then off, does not repeat
        :return: success (True/False)
        """
        led = args.get("led", None)
        on_ms = args.get("on_ms", 500)
        off_ms = args.get("off_ms", 500)
        once = args.get("once", False)
        if led not in [self.LED_BLUE, self.LED_GREEN, self.LED_RED, self.LED_YELLOW]:
            value = {'err': "unknown led {}".format(led)}
            self._ret.put({"method": "led_toggle", "value": value, "success": False})
            return

        thread_name = "led{}".format(led)
        if on_ms > 0:
            if thread_name not in self.ctx["threads"] or not self.ctx["threads"][thread_name]:
                self.ctx["threads"][thread_name] = True
                _thread.start_new_thread(self._toggle_led, (led, on_ms, off_ms, once))

        else:
            if thread_name in self.ctx["threads"]:
                self.ctx["threads"][thread_name] = False

        self._ret.put({"method": "led_toggle", "value": {'value': True}, "success": True})

    def led(self, args):
        """ LED on/off
        :param args: "enable": [True|False, ...]
                     "led": [1|2|3|4, ...]
        :return:  {'led': led, 'enable': enable}
        """
        set = args.get("set", [])

        for led, enable in set:
            if led not in [self.LED_BLUE, self.LED_GREEN, self.LED_RED, self.LED_YELLOW]:
                value = {'err': "unknown led {}".format(led)}
                self._ret.put({"method": "led", "value": value, "success": False})

            if enable: pyb.LED(led).on()
            else: pyb.LED(led).off()

        self._ret.put({"method": "led", "value": {}, "success": True})

    def init_gpio(self, args):
        """ init gpio
        - a gpio must be set before it can be used
        - see https://docs.micropython.org/en/latest/library/pyb.Pin.html#pyb-pin

        args:
        :param name: assign name to gpio for reference
        :param pin: pin name of gpio, X1,X2, ...
        :param mode: one of pyb.Pin.IN, Pin.OUT_PP, Pin.OUT_OD, ..
        :param pull: one of pyb.Pin.PULL_NONE, pyb.Pin.PULL_UP, pyb.Pin.PULL_DN
        :return: None
        """
        name = args.get("name", None)
        pin = args.get("pin", None)
        mode = args.get("mode")
        pull = args.get("pull", pyb.Pin.PULL_NONE)

        if mode == PYB_PIN_IN: mode = pyb.Pin.IN
        elif mode == PYB_PIN_OUT_PP: mode = pyb.Pin.OUT_PP
        elif mode == PYB_PIN_OUT_OD: mode = pyb.Pin.OUT_OD
        else:
            self._ret.put({"method": "init_gpio", "value": {'err': 'invalid mode'}, "success": False})
            return

        if pull == PYB_PIN_PULLNONE: pull = pyb.Pin.PULL_NONE
        elif pull == PYB_PIN_PULLDN: pull = pyb.Pin.PULL_DOWN
        elif pull == PYB_PIN_PULLUP: pull = pyb.Pin.PULL_UP
        else:
            self._ret.put({"method": "init_gpio", "value": {'err': 'invalid pull'}, "success": False})
            return

        value = {}
        if name in self.ctx['gpio']: value["action"] = "updating previously created"
        else:  value["action"] = "creating"

        self._init_gpio(name, pin, mode, pull)
        self._ret.put({"method": "init_gpio", "value": value, "success": True})

    def get_gpio(self, args):
        pin = args.get("pin", None)
        if pin not in self.ctx["gpio"]:
            value = {'err': "{} has not been initialized".format(pin)}
            self._ret.put({"method": "get_gpio", "value": value, "success": False})
            return

        value = self.ctx["gpio"][pin].value()
        self._ret.put({"method": "get_gpio", "value": {'value': value}, "success": True})

    def set_gpio(self, args):
        name = args.get("name", None)
        value = args.get("value", True)

        if name not in self.ctx["gpio"]:
            value = {'err': "{} has not been initialized".format(name)}
            self._ret.put({"method": "set_gpio", "value": value, "success": False})
            return

        if value: self.ctx["gpio"][name].high()
        else: self.ctx["gpio"][name].low()
        self._ret.put({"method": "set_gpio", "value": {}, "success": True})

    def adc_read(self, args):
        """ (simple) read ADC on a pin
        - this is a blocking call

        args:
        :param pin: pin name of gpio, X1, X2, ... or VBAT, TEMP, VREF, VDD
        :param samples: number of samples to take and then calculate average, default 1
        :param sample_ms: number of milliseconds between samples, default 1
        :return:
        """
        pin = args.get("pin", None)
        if pin not in self.ADC_VALID_PINS and pin not in self.ADC_VALID_INTERNALS:
            value = {'err': "{} pin is not valid".format(pin)}
            self._ret.put({"method": "adc_read", "value": value, "success": False})
            return

        samples = args.get("samples", 1)
        sample_ms = args.get("sample_ms", 1)

        # print("DEBUG: test")

        adc = None
        adc_read = None
        if pin in self.ADC_VALID_PINS:
            adc = pyb.ADC(pyb.Pin('{}'.format(pin)))
            adc_read = adc.read

        else:
            adc = pyb.ADCAll(12, 0x70000)

            if pin == "TEMP":
                adc_read = adc.read_core_temp
            elif pin == "VBAT":
                adc_read = adc.read_core_vbat
            elif pin == "VREF":
                adc_read = adc.read_core_vref
            elif pin == "VDD":
                adc_read = adc.read_vref

        if adc is None or adc_read is None:
            value = {'err': "{} pin is not valid (internal error)".format(pin)}
            self._ret.put({"method": "adc_read", "value": value, "success": False})
            return

        results = []
        for i in range(samples):
            results.append(float(adc_read()))
            if sample_ms:
                time.sleep_ms(sample_ms)

        sum = 0
        for r in results: sum += r
        result = float(sum / len(results))

        value = {'value': result, "samples": samples}
        self._ret.put({"method": "adc_read", "value": value, "success": True})

    def _adc_read_multi(self, _):
        """ async callback for adc_read_multi
        - args for this function are cached in self.ctx["adc_read_multi"]

        :param _: not used
        :return:
        """
        args = self.ctx["adc_read_multi"]
        freq = args.get("freq", 100)
        samples = args.get("samples", 100)
        pins = args.get("pins", None)

        adcs = []
        results = []
        for pin in pins:
            adcs.append(pyb.ADC(pyb.Pin('{}'.format(pin))))
            results.append(array.array('H', (0 for i in range(samples))))

        tim = pyb.Timer(self.ADC_READ_MULTI_TIMER, freq=freq)  # Create timer
        pyb.ADC.read_timed_multi(adcs, results, tim)
        tim.deinit()

        # reformat results to be a simple list
        value = {"samples": samples, "freq": freq}
        for idx, result in enumerate(results):
            value[pins[idx]] = [r for r in result]

        self._ret.put({"method": "adc_read_multi_results", "value": value, "success": True})

    def adc_read_multi(self, args):
        """ ADC read multiple pins, multiple times, at a given frequency
        - this is non-blocking, the action is scheduled later

        args:
        :param pins: list of pins name of gpio, X1, X2, ... or vbat, temp, vref, core_vref
        :param freq: frequency of taking samples (1 - 10kHz), default 100 Hz
        :param samples: total samples to take (1 - 1000), default 100
        :return:
        """
        freq = args.get("freq", 100)
        if not (0 < freq <= self.ADC_MAX_FREQ):
            value = {'err': "freq not within range supported, 0 < f <= {}".format(self.ADC_MAX_FREQ)}
            self._ret.put({"method": "adc_read_multi", "value": value, "success": False})
            return

        samples = args.get("samples", 100)
        if not (0 < samples <= self.ADC_MAX_SAMPLES):
            value = {'err': "samples not within range supported, 0 < s <= {}".format(self.ADC_MAX_SAMPLES)}
            self._ret.put({"method": "adc_read_multi", "value": value, "success": False})
            return

        pins = args.get("pins", None)
        if not isinstance(pins, list):
            value = {'err': "pins must be a list"}
            self._ret.put({"method": "adc_read_multi", "value": value, "success": False})
            return
        for pin in pins:
            if pin not in self.ADC_VALID_PINS:
                value = {'err': "{} pin is not valid".format(pin)}
                self._ret.put({"method": "adc_read_multi", "value": value, "success": False})
                return

        # everything is good, store the params
        self.ctx["adc_read_multi"] = args

        # schedule adc multi to run later
        micropython.schedule(self._adc_read_multi, 0)
        self._ret.put({"method": "adc_read_multi", "value": {'value': 'scheduled'}, "success": True})

    def pwm(self, args):
        """ PWM
        - a pin must be set up first

        :param args: 'freq': <value>
        :return:
        """
        name = args.get("name", None)
        pin = args.get("pin", None)
        freq = args.get("freq", 0)
        timer = args.get("timer", 0)
        duty_cycle = args.get("duty_cycle", 50)
        channel = args.get("channel", 1)
        enable = args.get("enable", True)

        if not enable:
            if name not in self.ctx["timers"]:
                value = {'err': "{} timer is not valid".format(name)}
                self._ret.put({"method": "pwm", "value": value, "success": False})
                return
            self.ctx["timers"][name].deinit()
            self._ret.put({"method": "pwm", "value": {'value': '{} disabled'.format(name)}, "success": True})
            return

        if pin not in self.ctx["gpio"]:
            value = {'err': "{} pin is not valid".format(pin)}
            self._ret.put({"method": "pwm", "value": value, "success": False})
            return
        if not (0 < freq <= self.PWM_MAX_FREQ):
            value = {'err': "freq not within range supported, 0 < f <= {}".format(self.PWM_MAX_FREQ)}
            self._ret.put({"method": "pwm", "value": value, "success": False})
            return

        p = self.ctx["gpio"][pin]

        self.ctx["timers"][name] = pyb.Timer(timer, freq=freq)
        self.ctx["pwm"][name] = self.ctx["timers"][name].channel(channel, pyb.Timer.PWM, pin=p)
        self.ctx["pwm"][name].pulse_width_percent(duty_cycle)
        self._ret.put({"method": "pwm", "value": {'value': 'scheduled'}, "success": True})

    def _long_running_example(self, delay):
        """ own thread started by long_running_task_example
        - blick LED to indicate things are happening...
        :param delay: seconds
        :return:
        """
        count = 0
        while count < delay:
            time.sleep(1)
            count += 1
            pyb.LED(LED_GREEN).on()
            time.sleep_ms(100)
            pyb.LED(LED_GREEN).off()

        self._ret.put({"method": "long_running_example", "value": {'value': 'completed'}, "success": True})

    def long_running_example(self, args):
        """ Example of how to implement a long running task

        :param args: "delay_s": <int>, delay in seconds
        :return:
        """
        delay_s = args.get("delay_s", 0)
        if delay_s > 0:
            _thread.start_new_thread(self._long_running_example, (delay_s,))
            self._ret.put({"method": "long_running_example", "value": {'value': 'scheduled'}, "success": True})
            return

        self._ret.put({"method": "long_running_example", "value": {'err': 'delay_s invalid'}, "success": False})

    # PyBoard
    # ===============================================================================================
    # External to PyBoard APIs


upyrpc = uPyRPC(debug=True)
_thread.start_new_thread(upyrpc._run, ())
