# p01-upyrpc

An RPC framework for MicroPython.  I couldn't find one so I made this.  It is not based
on standard RPC frameworks because I am not familiar with any.

Only tested on PyBoard v1.1 running `pybv11-thread-20190730-v1.11-182-g7c15e50eb.dfu`.

The server RPC can be blocking or non-blocking.

## Installation

1. Install requirements.txt via pip3.

2. Copy all the files in `./target` onto the PyBoard using `rshell` or `ampy`.

```
$ ampy --port /dev/ttyACM0 put target/upyrpc_const.py
$ ampy --port /dev/ttyACM0 put target/upyrpc_server.py
$ ampy --port /dev/ttyACM0 put target/upyrpc_queue.py
$ ampy --port /dev/ttyACM0 put target/upyrpc_main.py
```

3. Test it via the command line interface,
```
$ python3 UPYRPC_cli.py --port /dev/ttyACM0 misc --200
           UPYRPC.py   INFO  190 True []
       UPYRPC_cli.py   INFO  227 test_misc:
       UPYRPC_cli.py   INFO  239 T200: Reading version and uname...
       UPYRPC_cli.py   INFO  241 True {'success': True, 'value': {'uname': {'machine': 'PYBv1.1 with STM32F405RG', 'nodename': 'pyboard', 'version': 'v1.11-182-g7c15e50eb on 2019-07-30', 'release': '1.11.0', 'sysname': 'pyboard'}, 'version': '0.2'}, 'method': 'version'}
       UPYRPC_cli.py   INFO  329 all tests passed

$ python3 UPYRPC_cli.py --port /dev/ttyACM0 adc --100
           UPYRPC.py   INFO  190 True []
       UPYRPC_cli.py   INFO  168 test_adc:
       UPYRPC_cli.py   INFO  172 T100: Reading ADC...
       UPYRPC_cli.py   INFO  174 True {'success': True, 'value': {'value': 1.20315, 'samples': 1}, 'method': 'adc_read'}
       UPYRPC_cli.py   INFO  329 all tests passed
```

## Usage

Have a look at `UPYRPC_cli.py` code.

The code pattern looks like this,

```
    port = "/dev/ttyACM0"
    pyb = UPYRPC(port)
    success, result = pyb.start_server()
    # check for success, and error handle...

    success, result = pyb.version()
    logging.info("{} {}".format(success, result))

    # ... any other commands...

    pyb.close()
```

### How It Works

On the PC side, `UPYRPC.py` has the class *UPYRPC* which constructs the commands.  These look like,

```
    def led_toggle(self, led, on_ms=500, off_ms=500, once=False):
        """ toggle and LED ON and then OFF
        - this is a blocking command

        :param led: # of LED, see self.LED_*
        :param on_ms: # of milliseconds to turn on LED
        :return:
        """
        c = {'method': 'led_toggle', 'args': {'led': led, 'on_ms': on_ms, 'off_ms': off_ms, 'once': once}}
        return self._verify_single_cmd_ret(c)
```
This pattern is used for most commands that will return right away with a result.

For commands that perform long running tasks on the target, you will need to poll the target with a pattern like this,
```
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
```

Example testing the `long_running_example` with the CLI,
```
$ python3 UPYRPC_cli.py --port /dev/ttyACM0 misc --400
           UPYRPC.py   INFO  190 True []
       UPYRPC_cli.py   INFO  228 test_misc:
       UPYRPC_cli.py   INFO  256 T400: Long Running Example...
       UPYRPC_cli.py   INFO  258 True {'success': True, 'value': {'value': 'scheduled'}, 'method': 'long_running_example'}
       UPYRPC_cli.py   INFO  265 Polling long_running_example: False Failed to find method long_running_example
       UPYRPC_cli.py   INFO  265 Polling long_running_example: False Failed to find method long_running_example
       UPYRPC_cli.py   INFO  265 Polling long_running_example: False Failed to find method long_running_example
       UPYRPC_cli.py   INFO  265 Polling long_running_example: True [{'success': True, 'value': {'value': 'completed'}, 'method': 'long_running_example'}]
       UPYRPC_cli.py   INFO  347 all tests passed

```
You may also try adding the `-v` flag to the CLI command above to see all that is going on.

### Extending

Extending (adding methods to RPC to) involves three steps,

1) Create the method in `upyroc_main.py:uPyRPC()`.  Follow the other methods for signature.
Don't forget to put something in the return queue before your method ends.

2) Create a PC side "wrapper" for the new method in `UPYRPC.py:UPYRPC()`. Document the API here.
So as much argument checking here as possible.  The server should not have to validate arguments,
although the code currently does some now.

3) Update `UPYRPOC_cli.py` to test your new method.

## Debugging

Debugging is difficult.  Here are some suggestions.

1. If you extend the functionality, its very helpful to keep the CLI up to date, and test your
extensions with this tool, outside of any other development you are doing.

2. There are debug prints available on the MicroPython side, they look like this,

```
        self._debug("testing message", 164, __DEBUG_FILE, "version")  # note line number is manually set
```
You can see this line in `upyrpc_main.py` line 164.  And if you run the cli with verbosity set, you will 
see this debug line printed,

```
$ python3 UPYRPC_cli.py --port /dev/ttyACM0 -v misc --200
           UPYRPC.py  DEBUG   82 /dev/ttyACM0 cmd: import upyrpc_main
           UPYRPC.py   INFO  190 True []
       UPYRPC_cli.py   INFO  227 test_misc:
       UPYRPC_cli.py   INFO  239 T200: Reading version and uname...
           UPYRPC.py  DEBUG   82 /dev/ttyACM0 cmd: upyrpc_main.upyrpc.cmd({'method': 'version', 'args': {}})
           UPYRPC.py  DEBUG   82 /dev/ttyACM0 cmd: upyrpc_main.upyrpc.ret(method='version')
           UPYRPC.py  DEBUG  119 [{"success": true, "value": "upyrpc_main    :version   : 180: testing message", "method": "_debug"}]
           UPYRPC.py  DEBUG  155 True [{'success': True, 'value': 'upyrpc_main    :version   : 180: testing message', 'method': '_debug'}]
           UPYRPC.py  DEBUG  159 PYBOARD DEBUG: upyrpc_main    :version   : 164: testing message
           UPYRPC.py  DEBUG   82 /dev/ttyACM0 cmd: upyrpc_main.upyrpc.ret(method='version')
           UPYRPC.py  DEBUG  119 [{"success": true, "value": {"uname": {"machine": "PYBv1.1 with STM32F405RG", "nodename": "pyboard", "version": "v1.11-182-g7c15e50eb on 2019-07-30", "release": "1.11.0", "sysname": "pyboard"}, "version": "0.2"}, "method": "version"}]
           UPYRPC.py  DEBUG  155 True [{'success': True, 'value': {'uname': {'machine': 'PYBv1.1 with STM32F405RG', 'nodename': 'pyboard', 'version': 'v1.11-182-g7c15e50eb on 2019-07-30', 'release': '1.11.0', 'sysname': 'pyboard'}, 'version': '0.2'}, 'method': 'version'}]
       UPYRPC_cli.py   INFO  241 True {'success': True, 'value': {'uname': {'machine': 'PYBv1.1 with STM32F405RG', 'nodename': 'pyboard', 'version': 'v1.11-182-g7c15e50eb on 2019-07-30', 'release': '1.11.0', 'sysname': 'pyboard'}, 'version': '0.2'}, 'method': 'version'}
       UPYRPC_cli.py   INFO  329 all tests passed

``` 
As you will notice, the line numbers on the MicroPython side need to be manually entered... one day this could be
automated with a script.

3. Test with the REPL.  This is the only way you will find out if there is a syntax error in your code - so basically that
means you SHOULD do this FIRST before trying the CLI.  Here is a typical session,

```
$ rshell
Connecting to /dev/ttyACM0 (buffer-size 512)...
Trying to connect to REPL  connected
Testing if sys.stdin.buffer exists ... Y
Retrieving root directories ... /flash/
Setting time ... Oct 25, 2019 15:39:48
Evaluating board_name ... pyboard
Retrieving time epoch ... Jan 01, 2000
Welcome to rshell. Use Control-D (or the exit command) to exit rshell.
/home/martin/sistemi/git/p01-upyrpc> repl
Entering REPL. Use Control-X to exit.
>
MicroPython v1.11-182-g7c15e50eb on 2019-07-30; PYBv1.1 with STM32F405RG
Type "help()" for more information.
>>> 
>>> import upyrpc_main
>>> upyrpc_main.upyrpc.cmd({'method': 'version', 'args': {}})
True
>>> upyrpc_main.upyrpc.ret(method='version')
[{'success': True, 'value': 'upyrpc_main    :version   : 180: testing message', 'method': '_debug'}]
True
>>> upyrpc_main.upyrpc.ret(method='version')
[{'success': True, 'value': {'uname': {'machine': 'PYBv1.1 with STM32F405RG', 'nodename': 'pyboard', 'version': 'v1.11-182-g7c15e50eb on 2019-07-30', 'release': '1.11.0', 'sysname': 'pyboard'}, 'version': '0.2'}, 'method': 'version'}]
True
>>> upyrpc_main.upyrpc.ret(method='version')
[]
True
>>>
```
In step 2 above, with verbosity set, you can see the commands being sent to the server.  Copy and paste
those commands in the REPL for debugging.

---
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
