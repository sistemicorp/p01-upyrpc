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

This CLI provides a linux CLI interface to the MicroPyBoard "server".
"""
import sys
import time
import logging
import argparse

from UPYRPC import UPYRPC
from target.upyrpc_const import *

VERSION = "0.2.0"

# Command Line Interface...
# FIXME: this is horribly done...

def parse_args():
    epilog = """
    Usage examples:
       python3 UPYRPC_cli.py --port /dev/ttyACM0 adc --100
       python3 UPYRPC_cli.py --port /dev/ttyACM0 adc --all      
    """
    parser = argparse.ArgumentParser(description='UPYRPC_cli',
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=epilog)

    parser.add_argument("-p", '--port', dest='port', default=None, type=str,
                        action='store', help='Active serial port')
    parser.add_argument("-a", '--all', dest='all_funcs', default=0, action='store_true', help='run all tests')

    parser.add_argument("-v", '--verbose', dest='verbose', default=0, action='count', help='Increase verbosity')
    parser.add_argument("-d", '--debug', dest='debug', default=False, action='store_true', help='Enable debug prints on pyboard')
    parser.add_argument("--version", dest="show_version", action='store_true', help='Show version and exit')

    subp = parser.add_subparsers(dest="_cmd", help='commands')
    led_toggle_parser = subp.add_parser('led_toggle')
    led_toggle_parser.add_argument('-a', "--all", dest="all", action='store_true', help='run all tests sequentially', default=False, required=False)
    led_toggle_parser.add_argument('--100', dest="t100", action='store_true', help='toggle led using server.cmd', default=False, required=False)
    led_toggle_parser.add_argument('--101', dest="t101", action='store_true', help='toggle led using wrapper API', default=False, required=False)
    led_toggle_parser.add_argument('--102', dest="t102", action='store_true', help='toggle led using wrapper API only once', default=False, required=False)

    adc_parser = subp.add_parser('adc')
    adc_parser.add_argument('-a', "--all", dest="all", action='store_true', help='run all tests sequentially', default=False, required=False)
    adc_parser.add_argument('--100', dest="t100", action='store_true', help='adc_read', default=False, required=False)
    adc_parser.add_argument('--200', dest="t200", action='store_true', help='adc_read_multi', default=False, required=False)

    pwm_parser = subp.add_parser('pwm')
    pwm_parser.add_argument('-a', "--all", dest="all", action='store_true', help='run all tests sequentially', default=False, required=False)
    pwm_parser.add_argument('--100', dest="t100", action='store_true', help='PWM on Y1', default=False, required=False)

    misc_parser = subp.add_parser('misc')
    misc_parser.add_argument('-a', "--all", dest="all", action='store_true', help='run all tests sequentially', default=False, required=False)
    misc_parser.add_argument('--100', dest="t100", action='store_true', help='unique id', default=False, required=False)
    misc_parser.add_argument('--200', dest="t200", action='store_true', help='pyboard server version and uname', default=False, required=False)
    misc_parser.add_argument('--300', dest="t300", action='store_true', help='reset', default=False, required=False)
    misc_parser.add_argument('--400', dest="t400", action='store_true', help='long running example', default=False, required=False)
    misc_parser.add_argument('--500', dest="t500", action='store_true', help='Init GPIO Y1 PP', default=False, required=False)
    misc_parser.add_argument('--501', dest="t501", action='store_true', help='Init GPIO X12 Input Pull-UP', default=False, required=False)

    args = parser.parse_args()

    if args.show_version:
        logging.info("Version {}".format(VERSION))
        sys.exit(0)

    if not args.port:
        parser.error("--port is required")

    return args


def test_led_toggle(args, pyb):
    did_something = False
    _all = False
    if args._cmd == "led_toggle": _all = args.all
    all = args.all_funcs or _all
    _success = True
    logging.info("test_led_toggle:")

    if all or args.t100:
        # This is an example of how to execute non-blocking, long running async task
        # using the server.cmd({}) interface
        did_something = True
        logging.info("T100: Toggle Red LED with raw commands...")

        cmds = ["upyb_server_01.server.cmd({{'method': 'led_toggle', 'args': {{ 'led': {} }} }})".format(pyb.LED_RED)]

        success, result = pyb.server_cmd(cmds, repl_enter=False, repl_exit=False)
        logging.info("{} {}".format(success, result))

        cmds = ["upyb_server_01.server.ret(method='led_toggle')"]

        retry = 5
        succeeded = False
        while retry and not succeeded:
            time.sleep(0.5)
            success, result = pyb.server_cmd(cmds, repl_enter=False, repl_exit=False)
            logging.info("{} {}".format(success, result))
            if success:
                for r in result:
                    if r.get("method", False) == 'led_toggle' and r.get("value", False) == True:
                        succeeded = True
            retry -= 1

        if _success and not success: _success = False

        cmds = ["upyb_server_01.server.cmd({{'method': 'led_toggle', 'args': {{ 'led': {}, 'on_ms': 0 }} }})".format(pyb.LED_RED)]

        success, result = pyb.server_cmd(cmds, repl_enter=False, repl_exit=False)
        logging.info("{} {}".format(success, result))

    if all or args.t101:
        did_something = True
        logging.info("T101: Toggle Red LED with wrapper API...")

        success, result = pyb.led_toggle(2, 200)
        logging.info("{} {}".format(success, result))
        if _success and not success: _success = False

        time.sleep(5)  # let the led toggle for a bit

        success, result = pyb.led_toggle(2, 0)
        logging.info("{} {}".format(success, result))
        if _success and not success: _success = False

    if all or args.t102:
        did_something = True
        logging.info("T102: Toggle Orange LED with wrapper API for 1.5 sec ON")

        success, result = pyb.led_toggle(3, 1500, once=True)
        logging.info("{} {}".format(success, result))
        if _success and not success: _success = False

    if did_something: return _success
    else: logging.error("No Tests were specified")
    return False


def test_adc(args, pyb):
    did_something = False
    _all = False
    if args._cmd == "adc": _all = args.all
    all = args.all_funcs or _all
    _success = True
    logging.info("test_adc:")

    if all or args.t100:
        did_something = True
        logging.info("T100: Reading ADC...")
        success, result = pyb.adc_read("VREF")
        logging.info("{} {}".format(success, result))

        if _success and not success: _success = False

    if all or args.t200:
        did_something = True

        logging.info("T200: Reading (multi) ADC...")
        success, result = pyb.adc_read_multi(pins=["X19", "X20"])
        logging.info("{} {}".format(success, result))
        success, result = pyb.get_server_method("adc_read_multi_results")
        logging.info("{} {}".format(success, result))

        if _success and not success: _success = False

    if did_something: return _success
    else: logging.error("No Tests were specified")
    return False


def test_pwm(args, pyb):
    did_something = False
    _all = False
    if args._cmd == "pwm": _all = args.all
    all = args.all_funcs or _all
    _success = True
    logging.info("test_pwm:")

    if all or args.t100:
        did_something = True
        logging.info("T100: PWM on Y1")
        success, result = pyb.init_gpio("foo", "Y1", PYB_PIN_OUT_PP, PYB_PIN_PULLNONE)
        logging.info("{} {}".format(success, result))
        if _success and not success:
            _success = False
            logging.error("failed")

        success, result = pyb.pwm("foo", "foo", 8, 1, 1000, 50)
        logging.info("{} {}".format(success, result))

        if _success and not success: _success = False

    if did_something: return _success
    else: logging.error("No Tests were specified")
    return False


def test_misc(args, pyb):
    did_something = False
    _all = False
    if args._cmd == "adc": _all = args.all
    all = args.all_funcs or _all
    _success = True
    logging.info("test_misc:")

    if all or args.t100:
        did_something = True
        logging.info("T100: Reading unique id...")
        success, result = pyb.unique_id()
        logging.info("{} {}".format(success, result))

        if _success and not success: _success = False

    if all or args.t200:
        did_something = True
        logging.info("T200: Reading version and uname...")
        success, result = pyb.version()
        logging.info("{} {}".format(success, result))

        if _success and not success: _success = False

    if all or args.t300:
        did_something = True
        logging.info("T300: Resetting...")
        success, result = pyb.reset()
        logging.info("{} {}".format(success, result))

        if _success and not success: _success = False

    if all or args.t400:
        did_something = True
        logging.info("T400: Long Running Example...")
        success, result = pyb.long_running_example(5)
        logging.info("{} {}".format(success, result))

        if success:
            done = False
            while not done:
                time.sleep(1)  # poll the target for completion
                success, result = pyb.get_server_method("long_running_example")
                logging.info("Polling long_running_example: {} {}".format(success, result))
                if success and result[0].get("value", {}).get("value", False) == "completed":
                    done = True

        if _success and not success: _success = False

    if all or args.t500:
        did_something = True
        logging.info("T500: init GPIO Y1...")
        success, result = pyb.init_gpio("foo", "Y1", PYB_PIN_OUT_PP, PYB_PIN_PULLNONE)
        logging.info("{} {}".format(success, result))

        if _success and not success: _success = False

    if all or args.t501:
        did_something = True
        logging.info("T501: init GPIO X12...")
        success, result = pyb.init_gpio("X12", "X12", PYB_PIN_IN, PYB_PIN_PULLUP)
        logging.info("{} {}".format(success, result))

        if _success and not success: _success = False

    if did_something: return _success
    else: logging.error("No Tests were specified")
    return False


if __name__ == '__main__':
    args = parse_args()
    all_funcs = args.all_funcs

    pyb = None
    if args.verbose == 0:
        logging.basicConfig(level=logging.INFO, format='%(filename)20s %(levelname)6s %(lineno)4s %(message)s')
    else:
        logging.basicConfig(level=logging.DEBUG, format='%(filename)20s %(levelname)6s %(lineno)4s %(message)s')

    pyb = UPYRPC(args.port, loggerIn=logging)

    success, result = pyb.start_server()
    if not success:
        logging.error("Unable to start server")
        pyb.close()
        exit(1)

    if args.debug:
        logging.info("Debug: enabling...")
        success, result = pyb.debug()
        logging.info("{} {}".format(success, result))
        if not success:
            logging.error("Failed to set debug mode")
            pyb.close()
            exit(1)

    if args._cmd == 'led_toggle' or all_funcs:
        success = test_led_toggle(args, pyb)
        if not success:
            logging.error("Failed testing led_toggle")
            pyb.close()
            exit(1)

    if args._cmd == "adc" or all_funcs:
        success = test_adc(args, pyb)
        if not success:
            logging.error("Failed testing adc")
            pyb.close()
            exit(1)

    if args._cmd == "pwm" or all_funcs:
        success = test_pwm(args, pyb)
        if not success:
            logging.error("Failed testing adc")
            pyb.close()
            exit(1)

    if args._cmd == "misc" or all_funcs:
        success = test_misc(args, pyb)
        if not success:
            logging.error("Failed testing misc")
            pyb.close()
            exit(1)

    logging.info("all tests passed")
    pyb.close()

