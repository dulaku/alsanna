## ``alsanna``
``alsanna`` is a CLI-based intercepting proxy for TCP connections written in Python with few third-party dependencies. This project aims to meet slightly different needs than some existing solutions like [tcpprox](https://github.com/nccgroup/tcpprox). ``alsanna`` lets you monitor TCP connections and modify the TCP stream travelling in either direction before it reaches its destination.

Like its namesake, it is:
* Small; core files are about 100 lines of commented code each
* Composed primarily of dark arts, in this case sockets programming, multiprocessing, multithreading, and signal handling
* An intermediary between you and the Old Chaos that is the Internet

### Usage

``alsanna``'s core supports Python 3.4 and above, but has no Python dependencies outside the standard library. Handlers can have additional dependencies. 

Handlers in ``alsanna`` are modules which are each responsible for managing one, and only one, protocol. Handlers decode data into a form you can edit in a text editor, then try to reassemble that code back into valid messages for your protocol. This design is meant to make encapsulation of protocols relatively straightforward, because you can compose handlers into a chain - data read off the wire is handled, then potentially handed to another handler, and so on. As a developer, you only need to know what types of objects the handler before yours will be supplying and how to reconstruct those objects after editing.

Arguments are documented with ``argparse``, so you can get a full list by reading the top of the files or by running ``python alsanna.py -h``. Help is only returned for ``alsanna`` core components, located in the root directory of the repository, and handlers that were actually included in the command, e.g. ``python alsanna.py --handlers tls rawbytes -h``. All arguments have defaults to demonstrate their use, even when you are more or less required to supply the argument to make ``alsanna`` do something useful.

``alsanna`` assumes "invisible" proxying - that is, it assumes the software it's proxying doesn't know it's being proxied. So you're responsible for configuring that software to send its traffic to the port you set ``alsanna`` to listen to. A good place to start is setting ``--listen_port`` to the port the software expects and configuring your ``hosts`` file to point traffic to yourself instead of using DNS. You're also responsible for telling ``alsanna`` where to send traffic it receives using ``--server_ip`` and ``--server_port``.

``alsanna`` assumes a patient client and an impatient server - it therefore waits to open a connection to a server until you have your first message to send. The connection should remain open thereafter until one end closes. Many servers close a TCP connection that doesn't send anything quickly, but if this is a problem for your protocol you may wish to examine the ``forward()`` and ``manage_connection()`` functions in ``cnxn_proc.py``.

The editor chosen by default is ``nano``, but you should choose one available on your system. I highly recommend using soft line wrapping for readability (``Esc``, ``$``). Avoid hard line wrapping (``Esc``, ``L``), which inserts newlines and will corrupt your data when using the ``rawbytes`` handler. If your modified file is corrupted or otherwise can't be read properly, the unmodified message will be sent. I have noticed graphical editors such as ``pluma`` and ``gedit`` do not work - ``alsanna`` will read back the unmodified contents of the file, and I have no earthly idea why.


Some screenshots:

![Nano](images/Nano.png)

![PassiveListening](images/Passive.png)

### Handlers

A handler is a Python module that follows a few specific rules. For the absolute bare minimum, take a look at ``handlers/rawbytes.py``. For a thoroughly documented tutorial example, take a look at ``handlers/prototype``. At a high level, a handler has two jobs:

* Modify the socket objects passed to it so that they produce readable messages for the next handler in the chain. This will usually mean making a new object that implements ``send()``, ``recv()``, ``connect()``, and ``close()``, and using that as a wrapper.
* For the last handler in a chain, format the message for viewing and modification by a user.

The socket object you create for your handler need not return ``bytes`` objects - it can return any kind of object, but it should represent one complete message if your protocol has semantics for message boundaries.

Handlers can import other handlers, in cases where strict encapsulation isn't actually applicable. For instance, STARTTLS commands in a protocol mean that it can start in plaintext and transition to an encrypted state. There's no sensible place to put the ``tls`` handler in the handler chain, but you can import it into your protocol's handler and use it to suit the protocol's semantics instead, without needing to duplicate the code. You will, however, need to be aware that the underlying sockets are shared between threads moving data in each direction, and you will therefore likely need to use locks or a similar mechanism to prevent ambiguity between your protocol's data and the imported handler's. For example, when you import ``tls`` you will need to ensure that TLS negotiation occurs atomically on the socket, so that TLS negotiation messages are not interpreted as protocol traffic and protocol traffic is not injected into TLS negotiation.

#### Handler Details

This section provides information on individual handlers. The trivial handler ``rawbytes`` and the example ``prototype`` are omitted.

##### LDAP

Depends on:

* [Impacket](https://github.com/SecureAuthCorp/impacket)
* [pyasn1](https://github.com/etingof/pyasn1)

This handler parses a subset of LDAP - enough to lay the groundwork for elements not already included. Currently covered are the messages needed to perform some simple queries, plus STARTTLS. TLS arguments won't be used unless STARTTLS actually occurs.

You will most likely want to use the ``--tls_server_name`` argument to specify the domain being queried if you need to use TLS, regardless of which of STARTTLS or LDAPS is being used. I have not observed SNI from actual LDAP clients negotiating TLS, so ``alsanna`` can't deduce the right domain name to use in generating a leaf certificate just from reading client requests.

##### TLS

This handler applies TLS to the connection using Python's built-in tools.

Automatic leaf certificate signing depends on ``openssl`` being on your system path; it probably is, but if it isn't and you can't put it there, you'll have to generate your own certificate trusted by the client. 

Getting your software to trust the certificates you supply is left as an exercise to the reader, but a good first stop would be installing them in your OS trust store. You can find the ones generated by default in ``handlers/tls/certs`` if you don't supply your own.

### Security Considerations
``alsanna`` uses an unspeakably lazy trick for editing TCP messages. Because it just drops them in a temporary file and then opens them in a text editor, this code is almost certainly vulnerable to race conditions. Since the contents of that file are later deserialized into a bytestring, those race conditions can possibly lead to code execution if someone can write to the files. Because ``alsanna`` probably has to run as ``root`` to bind well-known ports, that would be pretty bad. Exploitation and mitigation are both left as exercises to the reader.

A similar risk exists for the TLS handler because we're running whatever your environment happens to think ``openssl`` is, again probably as ``root`` - and with arguments controlled by the client software, though not in a shell. Don't run ``alsanna`` on hosts you don't trust or can't afford to lose.

``alsanna`` does absolutely no certificate verification. This makes testing easier, but it means you should trust your DNS servers and such.

### Change Log
* 2022-08-07 - Another big refactor; introduced a more sensible directory hierarchy, did a better job of separating protocol semantics from ``alsanna``'s core operation, improved naming conventions, squashed several bugs, and added an LDAP handler.
* 2021-04-29 - Tremendous refactor; all blocking sockets thanks to threading, UI now allows toggling interception for each direction, protocol handlers are now a clear concept (and TLS is just an example of one). Added more comments, fixed a couple bugs. Also, this release and future ones use the Apache v2.0 license, not the MIT license.
* 2020-10-04 - Add automatic generation of leaf TLS certificates, derived from the information sent by the client (if present). Also fixed a bug in ``alsanna``'s use of nonblocking SSLSockets which hadn't occurred in prior testing.
* 2020-08-16 - Refactor for better error handling, (hopefully) easier hacking, and a default implementation that can handle the common case of an impatient server. Added ``read_size``, ``error_color`` arguments.
* 2020-07-20 - Initial Release

### Future Work
More protocol handlers!

Add support for dynamic target resolution.

Add support for distinguishing arguments supplied for user-specified handlers vs implied handlers imported by other handlers such as TLS for LDAP's STARTTLS implementation.

Add support for a name resolution override, formatted like ``/etc/hosts``. Will allow multiplexing connections to different servers in one instance of ``alsanna`` provided the connections indicate what they're trying to connect to (e.g. SNI).

On back of above, add per-host args to the file, will allow different handlers for different situations.
