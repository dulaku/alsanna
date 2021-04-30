## ``alsanna``
``alsanna`` is a CLI-based intercepting proxy for TCP connections written in Python with few third-party dependencies. This project aims to meet slightly different needs than some existing solutions like [tcpprox](https://github.com/nccgroup/tcpprox). ``alsanna`` lets you monitor TCP connections and modify the TCP stream travelling in either direction before it reaches its destination.

Like its namesake, it is:
* Small, at less than a thousand lines of code and now modularized for easier modification
* Composed primarily of dark arts, in this case sockets programming, multiprocessing, multithreading, and signal handling
* An intermediary between you and the Old Chaos that is the Internet

### Usage

``alsanna`` only supports Python 3.4 and above, but has no Python dependencies outside the standard library. Automatic leaf certificate signing depends on ``openssl`` being on your system path; it probably is, but if it isn't and you can't put it there, you'll have to generate your own certificate trusted by the client. 

A core concept in ``alsanna`` is protocol "handlers", each of which is responsible for managing one, and only one, protocol. This spares you from needing to think about all the concurrency going on elsewhere in ``alsanna`` and makes encapsulation of protocols very straightforward.

Arguments are documented with ``argparse``, so you can get a full list by reading the top of the files or by running ``python alsanna.py -h``. I could copy and reformat them here, but I'm not going to. Note that you can get help for individual handlers and their arguments by including them, e.g. ``python alsanna.py --handlers tls rawbytes -h``. All arguments have defaults to demonstrate their use, even when you are more or less required to supply the argument to make ``alsanna`` do something useful. This is a feature, not a bug.

``alsanna`` assumes "invisible" proxying - that is, it assumes the software it's proxying doesn't know it's being proxied. So you're responsible for configuring that software to send its traffic to the port you set ``alsanna`` to listen to, which you can often do by listening on the port the software expects and configuring your ``hosts`` file to point traffic for the hostnames the software uses to yourself instead of using DNS. You're also responsible for telling ``alsanna`` where to send traffic it receives.

``alsanna`` assumes a patient client and an impatient server - it therefore waits to open a connection to a server until you have your first message to send. The connection should remain open thereafter until one end closes. Many servers close a TCP connection that doesn't send anything quickly, but if this is a problem for your protocol you may wish to examine the ``forward()`` and ``manage_connection()`` functions in ``alsanna.py``.

The editor chosen by default is ``nano``, but you should choose one available on your system. I highly recommend using soft line wrapping for readability (``Esc``, ``$``). Avoid hard line wrapping (``Esc``, ``L``), which inserts newlines and will corrupt your data when using the ``rawbytes`` handler. If your modified file is corrupted or otherwise can't be read properly, the unmodified message will be sent. I have noticed graphical editors such as ``pluma`` and ``gedit`` do not work - ``alsanna`` will read back the unmodified contents of the file, and I have no earthly idea why.

The default configuration expects a certificate and private key, both in ``.pem`` format, at ``./tls_cert.pem`` and ``./tls_key.pem`` respectively. An easy way to get these is to run ``openssl req -nodes -new -newkey rsa:4096 -x509 -keyout tls_key.pem -out tls_cert.pem`` in ``alsanna``'s directory. Getting your software to trust this certificate as a CA or TLS certificate is left as an exercise to the reader, but a good first stop would be installing them in your OS trust store.

Some screenshots:

![Nano](images/Nano.png)

![PassiveListening](images/Passive.png)

### Handlers

A handler is a Python module that follows a few specific rules. For the absolute bare minimum, take a look at ``handler_rawbytes.py``. For a thoroughly documented tutorial example, take a look at ``handler_prototype.py``. At a high level, a handler has two jobs:

* Modify the socket objects passed to it so that they produce readable messages for the next handler in the chain.
* For the last handler in a chain, format the message for viewing and modification by a user.

If a protocol basically serves as a transport for other protocols, as with TLS, you probably care more about the first. If you're just parsing things, you care a bit more about the second.

### Security Considerations
``alsanna`` uses an unspeakably lazy trick for editing TCP messages. Because it just drops them in a temporary file and then opens them in a text editor, this code is almost certainly vulnerable to race conditions. Since the contents of that file are later deserialized into a bytestring, those race conditions can possibly lead to code execution if someone can write to the files. I don't know, I haven't checked ast.literal_eval()'s implementation. Because ``alsanna`` probably has to run as ``root`` to bind well-known ports, that would be pretty bad. Exploitation and mitigation are both left as exercises to the reader.

A similar risk exists because we're running whatever your environment happens to think ``openssl`` is, again probably as ``root``. Seriously, don't run ``alsanna`` on hosts you don't trust.

``alsanna`` does absolutely no certificate verification. This makes testing easier, but it means you should trust your DNS servers and such.

### Change Log
* 2020-07-20 - Initial Release
* 2020-08-16 - Refactor for better error handling, (hopefully) easier hacking, and a default implementation that can handle the common case of an impatient server. Added ``read_size``, ``error_color`` arguments.
* 2020-10-04 - Add automatic generation of leaf TLS certificates, derived from the information sent by the client (if present). Also fixed a bug in ``alsanna``'s use of nonblocking SSLSockets which hadn't occurred in prior testing.
* 2021-04-29 - Tremendous refactor; all blocking sockets thanks to threading, UI now allows toggling interception for each direction, protocol handlers are now a clear concept (and TLS is just an example of one). Added more comments, fixed a couple bugs. Also, this release and future ones use the Apache v2.0 license, not the MIT license.

### Future Work
More protocol handlers!

Add support for a name resolution override, formatted like ``/etc/hosts``. Will allow multiplexing connections to different servers in one instance of ``alsanna`` provided the connections indicate what they're trying to connect to (e.g. SNI).

On back of above, add per-host args to the file, will allow different handlers for different situations.
