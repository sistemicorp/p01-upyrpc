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

How to use this driver:
1. See how UPYRPC_cli.py works.
2. Follow this pattern,

    port = "/dev/ttyACM0"
    pyb = UPYRPC(port)
    success, result = pyb.start_server()
    # check for success, and error handle...

    success, result = pyb.version()
    logging.info("{} {}".format(success, result))

    pyb.close()
"""
import time
import json
import threading

import ampy.pyboard as pyboard

from stublogger import StubLogger
from target.upyrpc_const import *

VERSION = "0.2.0"


class UPYRPC(pyboard.Pyboard):
    """ Extend the base pyboard class with a little exec helper method, exec_cmd
    to make it more script friendly

    There is a lock on self.server_cmd() to sequence clients

    """
    def __init__(self, device, baudrate=115200, user='micro', password='python', wait=0, rawdelay=0, loggerIn=None):
        super().__init__(device, baudrate, user, password, wait, rawdelay)

        if loggerIn: self.logger = loggerIn
        else: self.logger = StubLogger()

        self.device = device

        self.lock = threading.Lock()

    def server_cmd(self, cmds, repl_enter=True, repl_exit=True, blocking=True):
        """ execute a buffer on the open pyboard

        NOTE:  !! to get results back, the pyboard python code must wrap result in a print() !!

        :param buf: string of command(s)
        :return: success (True/False), result (if any)
        """
        if not isinstance(cmds, list):
            self.logger.error("cmd should be a list of micropython code (strings)")
            return False, "cmds should be a list"

        cmd = "\n".join(cmds)
        self.logger.debug("{} cmd: {}".format(self.device, cmd))

        with self.lock:
            # this was copied/ported from pyboard.py
            try:
                if repl_enter: self.enter_raw_repl()

                if blocking:
                    ret, ret_err = self.exec_raw(cmd + '\n', timeout=10, data_consumer=None)
                else:
                    self.exec_raw_no_follow(cmd)
                    ret_err = False
                    ret = None

            except pyboard.PyboardError as er:
                msg = "{}: {}".format(cmd, er)
                self.logger.error(msg)
                return False, msg
            except KeyboardInterrupt:
                return False, "KeyboardInterrupt"

            if repl_exit: self.exit_raw_repl()

            if ret_err:
                pyboard.stdout_write_bytes(ret_err)
                msg = "{}: {}".format(cmd, ret_err)
                self.logger.error(msg)
                return False, msg

            #print("A: {}".format(ret))
            if ret:
                pyb_str = ret.decode("utf-8")

                # expecting a JSON like dict object in string format, convert this string JSON to python dict
                # fix bad characters...
                fixed_string = pyb_str.replace("'", '"').replace("True", "true").replace("False", "false").replace("None", "null")
                try:
                    self.logger.debug(fixed_string.strip())
                    items = json.loads(fixed_string)
                except Exception as e:
                    self.logger.error(e)
                    return False, []

                return True, items

            return True, []

    def _verify_single_cmd_ret(self, cmd_dict, delay_poll_s=0.1):
        method = cmd_dict.get("method", None)
        args = cmd_dict.get("args", None)

        if method is None:
            return False, "method not specified"

        if args is None:
            return False, "args not specified"

        cmds = []
        c = str(cmd_dict)
        cmds.append("upyrpc_main.upyrpc.cmd({})".format(c))
        success, result = self.server_cmd(cmds, repl_enter=False, repl_exit=False)
        if not success:
            self.logger.error("{} {}".format(success, result))
            return success, result

        cmds = ["upyrpc_main.upyrpc.ret(method='{}')".format(method)]

        # it is assumed the command sent will post a return, with success set
        retry = 5
        succeeded = False
        while retry and not succeeded:
            time.sleep(delay_poll_s)
            success, result = self.server_cmd(cmds, repl_enter=False, repl_exit=False)
            self.logger.debug("{} {}".format(success, result))
            if success:
                for r in result:
                    if r.get("method", False) == "_debug":
                        self.logger.debug("PYBOARD DEBUG: {}".format(r["value"]))
                        retry += 1  # debug lines don't count against retrying
                    if r.get("method", False) == method:
                        succeeded = True
            else:
                return success, result

            retry -= 1

        if not succeeded:
            return False, "Failed to verify method {} was executed".format(method)

        if len(result) > 1:
            self.logger.error("More results than expected: {}".format(result))
            return False, "More results than expected, internal error"

        return result[0]["success"], result[0]

    # -------------------------------------------------------------------------------------------------
    # API (wrapper functions)
    # these are the important functions

    def start_server(self):
        """ Starts the Server on the target
        - this is the only time that REPL is entered, which will do a soft reset on the target and
          start the server

        :return:
        """
        cmds = ["import upyrpc_main"]
        success, result = self.server_cmd(cmds, repl_enter=True, repl_exit=False)
        self.logger.info("{} {}".format(success, result))
        return success, result

    def unique_id(self):
        c = {'method': 'unique_id', 'args': {}}
        return self._verify_single_cmd_ret(c)

    def version(self):
        c = {'method': 'version', 'args': {}}
        return self._verify_single_cmd_ret(c)

    def debug(self, enable=True):
        """ Set Server debug mode

        :param enable:
        :return:
        """
        c = {'method': 'debug', 'args': {"enable": enable}}
        return self._verify_single_cmd_ret(c)

    def get_server_method(self, method, all=False):
        """ Get return value message(s) from the server for a specific method
        - this function will remove the message(s) from the server queue

        :param method:
        :param all: set True for all the return messages
        :return: success, result
        """
        cmds = ["upyrpc_main.upyrpc.ret(method='{}', all={})".format(method, all)]
        retry = 5
        succeeded = False
        while retry and not succeeded:
            time.sleep(0.1)
            success, result = self.server_cmd(cmds, repl_enter=False, repl_exit=False)
            self.logger.debug("{} {}".format(success, result))
            if success:
                for r in result:
                    if r.get("method", False) == method:
                        succeeded = True
            else:
                return success, result

            retry -= 1

        if not succeeded:
            return False, "Failed to find method {}".format(method)

        return success, result

    def peek_server_method(self, method=None, all=False):
        """ Peek return message value(s from the server for a specific method
        - this function will NOT remove the message(s) from the server queue

        :param method:
        :param all: set True for all the return messages
        :return:
        """
        cmds = ["upyrpc_main.upyrpc.peek(method='{}', all='{}')".format(method, all)]
        retry = 5
        succeeded = False
        while retry and not succeeded:
            time.sleep(0.1)
            success, result = self.server_cmd(cmds, repl_enter=False, repl_exit=False)
            self.logger.debug("{} {}".format(success, result))
            if success:
                for r in result:
                    if r.get("method", False) == method:
                        succeeded = True
            else:
                return success, result

            retry -= 1

        if not succeeded:
            return False, "Failed to find method {}".format(method)

        return success, result

    def led(self, set):
        """ LED on/off
        :param set: [(#, True/False), ...], where #: 1=Red, 2=Yellow, 3=Green, 4=Blue
        :return:
        """
        if not isinstance(set, list):
            return False, "argument must be a list of tuples"
        c = {'method': 'led', 'args': {'set': set}}
        return self._verify_single_cmd_ret(c)

    def led_toggle(self, led, on_ms=500, off_ms=500, once=False):
        """ toggle and LED ON and then OFF
        - this is a blocking command

        :param led: # of LED, see self.LED_*
        :param on_ms: # of milliseconds to turn on LED
        :return:
        """
        c = {'method': 'led_toggle', 'args': {'led': led, 'on_ms': on_ms, 'off_ms': off_ms, 'once': once}}
        return self._verify_single_cmd_ret(c)

    def adc_read(self, pin, samples=1, samples_ms=1):
        """ Read an ADC pin
        - This is a BLOCKING function
        - result is raw ADC value, client needs to scale to VREF (3.3V)

        :param pin: pin name, X2, X3, etc
        :param samples: Number of samples to average over
        :param samples_ms: Delay between samples
        :return: success, result
        """
        c = {'method': 'adc_read', 'args': {'pin': pin, 'samples': samples, 'samples_ms': samples_ms}}
        return self._verify_single_cmd_ret(c)

    def adc_read_multi(self, pins, samples=100, freq=100):
        """ Read single or Multiple pins at Freq rate
        - NON-BLOCKING
        - the result is a list of samples
        - results are raw ADC values, client needs to scale to VREF (3.3V)

        :param pins: list of pins
        :param samples: # of samples to take
        :param freq: rate of taking samples
        :return: success, result
        """
        c = {'method': 'adc_read_multi', 'args': {'pins': pins, 'samples': samples, 'freq': freq}}
        return self._verify_single_cmd_ret(c)

    def init_gpio(self, name, pin, mode, pull):
        """ Init GPIO

        :param name:
        :param pin:
        :param mode: one of pyb.Pin.IN, Pin.OUT_PP, Pin.OUT_OD, ..
        :param pull: one of pyb.Pin.PULL_NONE, pyb.Pin.PULL_UP, pyb.Pin.PULL_DN
        :return:
        """
        c = {'method': 'init_gpio', 'args': {'name': name, 'pin': pin, 'mode': mode, 'pull': pull}}
        return self._verify_single_cmd_ret(c)

    def get_gpio(self, pin):
        """ Get GPIO
        :param pin:
        :return:
        """
        c = {'method': 'get_gpio', 'args': {'pin': pin}}
        return self._verify_single_cmd_ret(c)

    def set_gpio(self, name, value):
        """ Set GPIO
        :param name:
        :param value: True|False
        :return:
        """
        c = {'method': 'set_gpio', 'args': {'name': name, 'value': value}}
        return self._verify_single_cmd_ret(c)

    def reset(self):
        """ Reset the I2C devices to a known/default state

        :return:
        """
        c = {'method': 'reset', 'args': {}}
        return self._verify_single_cmd_ret(c)

    def pwm(self, name, pin, timer, channel, freq, duty_cycle, enable=True):
        """ Setup PWM

        :param name:
        :param pin: name of the pin, can be the same as name
        :param timer: timer number, see http://micropython.org/resources/pybv11-pinout.jpg
        :param channel: timer channel number
        :param freq:
        :param duty_cycle: default 50%
        :return:
        """
        c = {'method': 'pwm', 'args': {'name': name, 'pin': pin, 'timer': timer, "channel": channel,
                                       'freq': freq, 'duty_cycle': duty_cycle,
                                       "enable": enable}}
        return self._verify_single_cmd_ret(c)

    def long_running_example(self, delay_s):
        """ Example of Long Running RPC
        - _verify_single_cmd_ret attempts to get a return value, thinking the command will
          complete "right away".  In this example, it does complete right away, but the result is
          not final.  The immediate post is an indication that the task has been scheduled on the target.

        - in order to get the final result of the long running task, one needs to call
          get_server_method(), like so,



        :param delay_s:
        :return:
        """
        c = {'method': 'long_running_example', 'args': {'delay_s': delay_s}}
        return self._verify_single_cmd_ret(c)
