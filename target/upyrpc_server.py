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
import time
import micropython

from upyrpc_queue import MicroPyQueue

micropython.alloc_emergency_exception_buf(100)
__DEBUG_FILE = "upyrpc_server"


class MicroPyServer(object):
    """ Async Worker MicroPython Server
    - runs in its own thread

    !! This is a base class and should not be used directly !!

    cmds: Are in this format: {"method": <class_method>, "args": {<args>}}

    ret: Are in this format: {"method": <class_method>, "value": { ...}}
    """
    def __init__(self, debug=False):
        self._cmd = MicroPyQueue()
        self._ret = MicroPyQueue()
        self._debug_flag = debug

    # ===================================================================================
    # Public API to send commands and get results from the MicroPy Server
    #
    def cmd(self, cmd):
        """ Send (Add) a command to the MicroPy Server command queue
        - commands are executed in the order they are received

        :param cmd: dict format {"method": <class_method>, "args": {<args>}}
        :return: success (True/False)
        """
        if not isinstance(cmd, dict):
            self._ret.put({"method": "cmd", "value": "cmd must be a dict", "success": False})
            return False

        if not cmd.get("method", False):
            self._ret.put({"method": "cmd", "value": "cmd dict must have method key", "success": False})
            return False

        if not getattr(self, cmd["method"], False):
            self._ret.put({"method": "cmd", "value": "'{}' invalid method".format(cmd["method"]), "success": False})
            return False

        self._cmd.put(cmd)
        return True

    def ret(self, method=None, all=False):
        """ return result(s) of command

        :param method: string, if specified, only results of that command are returned
        :param all: True, will return all commands, otherwise only ONE return result is retrieved
        :return: success (True|False)
        """
        _ret = self._ret.get(method, all)
        print(_ret)
        return True

    def peek(self, method=None, all=False):
        """ Peek at item(s) in the queue, does not remove item(s)

        :param method:
        :param all:
        :return: success (True|False)
        """
        ret = self._ret.peek(method, all)
        print(ret)
        return True

    def update(self, item_update):
        """ Update an item in queue, or append item if it doesn't exist

        :param item_update: dict format {"method": <class_method>, "args": {<args>}}
        :return: success (True|False)
        """
        return self._ret.update(item_update)

    # ===================================================================================
    # private

    def _run(self):
        # run on thread
        while True:
            item = self._cmd.get()
            if item:
                method = item[0]["method"]
                args = item[0]["args"]
                method = getattr(self, method, None)
                if method is not None:
                    method(args)
                    # methods should always be found because they are checked before being queued

            # allows other threads to run, but generally speaking there should be no other threads(?)
            time.sleep_ms(self.SERVER_CMD_SLEEP_MS)

    def _debug(self, msg, line=0, file=__DEBUG_FILE, name="unknown"):
        """ Add debug statement

        :param msg:
        :param line:
        :return:
        """
        if self._debug_flag:
            self._ret.put({"method": "_debug", "value": "{:15s}:{:10s}:{:4d}: {}".format(file, name, line, msg), "success": True})

