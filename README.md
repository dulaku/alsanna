## ``alsanna``
``alsanna`` is a CLI-based intercepting proxy for TCP connections written in Python with few third-party dependencies. This project aims to meet slightly different needs than some existing solutions like [tcpprox](https://github.com/nccgroup/tcpprox). ``alsanna`` lets you monitor TCP connections and modify the TCP stream travelling in either direction before it reaches its destination.

Like its namesake, it is:
* Small, coming in at just a few hundred lines of code that can be hacked to support whatever you need your protocol to do
* Composed primarily of dark arts, in this case sockets programming and multiprocessing
* An intermediary between you and the Old Chaos that is the Internet

### Usage

``alsanna`` only supports Python 3.4 and above, but has no Python dependencies outside the standard library. Automatic leaf certificate signing depends on ``openssl`` being on your system path; it probably is, but if it isn't and you can't put it there, you'll have to generate your own certificate trusted by the client. Arguments are documented with ``argparse``, so you can get a full list by reading the top of the file or by running ``python alsanna.py -h``. I could copy and reformat them here, but I'm not going to.

``alsanna`` assumes "invisible" proxying - that is, it assumes the software it's proxying doesn't know it's being proxied. So you're responsible for configuring that software to send its traffic to the port you set ``alsanna`` to listen to, which you can often do by listening on the port the software expects and configuring your ``hosts`` file to point traffic for the hostnames the software uses to yourself instead of using DNS. You're also responsible for telling ``alsanna`` where to send traffic it receives.

``alsanna``'s default configuration assumes a patient client and an impatient server - it therefore waits to open a connection to a server until you have your first message to send. The connection should remain open thereafter until one end closes. This suits HTTP well as a demo protocol, but you may need to change the behavior.

The editor chosen by default is ``nano``, but you should choose one available on your system. I highly recommend using soft line wrapping for readability (``Esc``, ``$``). Avoid hard line wrapping (``Esc``, ``L``), which inserts newlines and will corrupt your data. If your modified file is corrupted or otherwise can't be read properly, the unmodified message will be sent. I have noticed graphical editors such as ``pluma`` and ``gedit`` do not work - ``alsanna`` will read back the unmodified contents of the file, and I have no earthly idea why.

The default configuration expects a certificate and private key, both in ``.pem`` format, at ``./tls_cert.pem`` and ``./tls_key.pem`` respectively. An easy way to get these is to run ``openssl req -nodes -new -x509 -keyout tls_key.pem -out tls_cert.pem`` in ``alsanna``'s directory. Getting your software to trust this certificate as a CA or TLS certificate is left as an exercise to the reader, but a good first stop would be installing them in your OS trust store.

``util_tls.py`` shouldn't need much hacking, but if you need to add information to your certificate to get your software to trust it, that'd be the place to do it.

Some screenshots:

![Nano](images/Nano.png)

![PassiveListening](images/Passive.png)

### Security Considerations
``alsanna`` uses an unspeakably lazy trick for editing TCP messages. Because it just drops them in a temporary file and then opens them in a text editor, this code is almost certainly vulnerable to race conditions. Since the contents of that file are later deserialized into a bytestring, those race conditions can possibly lead to code execution if someone can write to the files. I don't know, I haven't checked ast.literal_eval()'s implementation. Because ``alsanna`` probably has to run as ``root`` to bind well-known ports, that would be pretty bad. Exploitation and mitigation are both left as exercises to the reader.

A similar risk exists because we're running whatever your environment happens to think ``openssl`` is, again probably as ``root``. Seriously, don't run ``alsanna`` on hosts you don't trust.

``alsanna`` does absolutely no certificate verification. This makes testing easier, but it means you should trust your DNS servers and such.

### Change Log
* 2020-07-20 - Initial Release
* 2020-08-16 - Refactor for better error handling, (hopefully) easier hacking, and a default implementation that can handle the common case of an impatient server. Added ``read_size``, ``error_color`` arguments.
* 2020-10-04 - Add automatic generation of leaf TLS certificates, derived from the information sent by the client (if present). Also fixed a bug in ``alsanna``'s use of nonblocking SSLSockets which hadn't occurred in prior testing.

### Future Work
Support for DNS lookups so you don't need to supply a raw IP address if you don't want to.

I'd also like to add support for mTLS. This version only handles impersonating the server.

I tried to build in toggle keys for intercepting client and server messages separately, but couldn't get anything to work without breaking the editor. Revisiting this in the future would be a good idea.
