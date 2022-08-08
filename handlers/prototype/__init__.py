# A simple handler which demonstrates the "official" paradigm for handlers.
# Contains every attribute that alsanna.py expects, documented to tell you
# what they do. 

# cnxn_locals is a dictionary of variables used when handlers need
# to communicate with each other or alsanna. It contains the following key:
#     "cnxn_id": A numeric ID for the connection. Useful for debugging.
#                Used by alsanna's core module, guaranteed available.
# More may be added as handlers are added that need to share information, and
# this documentation will be updated as this happens.

import argparse, ast

class Handler:
    def __init__(self, arg_parser, final):
        # Each handler builds its own arg_parser that inherits from the handlers
        # before it, and from alsanna's global arg_parser. The upside is it's
        # easy to get help for just the handlers you're using, the downside is
        # you have to be aware of the flags used by all the handlers you use in
        # order to avoid collisions. You _must_ set self.arg_parser, self.args,
        # and self.remaining_args, and you almost always want to do it as shown
        # here.
        self.arg_parser = argparse.ArgumentParser(parents=[arg_parser], 
                                                  add_help=final,
                                                  allow_abbrev=False)

        ##########################################
        # Any handler-specific arguments go here.#
        ##########################################

        self.args, self.remaining_args = self.arg_parser.parse_known_args()

        #############################################
        # Anything else you do on startup goes here.#
        #############################################

    def setup_client_facing(self, listen_sock, cnxn_locals):
        """
        Do anything you need to as part of setting up the client-facing socket.
        This is called before any bytes are received over listen_sock.
    
        listen_sock is some type of socket. It is guaranteed to have a send(), 
        recv(), connect(), and close() method, might or might not have any of 
        a socket's other methods. This is a standard Python socket if this is the first
        handler, or the socket created by the previous handler otherwise.
    
        cnxn_locals is a dictionary containing any information that needs to be
        communicated between different handlers and yours, or with alsanna.
    
        This should return a socket that speaks your protocol (recv() returns objects
        representing messages, and send() turns those objects into whatever the
        underlying socket understands).
        """
        return HandlerSock(listen_sock)

    def setup_server_facing(self, send_sock, cnxn_locals):
        """
        Do anything you need to as part of setting up the connection from alsanna
        to the remote server for your protocol. This is called before any bytes are
        sent over send_sock.

        send_sock is some type of socket, just as for listen_sock in
        setup_client_facing().

        cnxn_locals is a dictionary containing any information that needs to be
        communicated between different handlers and yours, or with alsanna.

        This should return a socket that speaks your protocol (recv() returns objects
        representing messages, and send() turns those objects into whatever the
        underlying socket understands).
        """
        return HandlerSock(send_sock)

    def obj_to_printable(self, py_obj):
        """
        Convert a sequence of bytes into a human-readable format. This will be
        called only for the last handler in a chain. It is recommended that you use
        logic in a custom Socket class in order to parse message boundaries, so that
        bytes is exactly one complete message in your protocol.

        bytes is a Python bytes object returned by your protocol's socket's recv()
        method.
        """
        return str(py_obj)

    def printable_to_obj(self, message):
        """
        Convert a human-readable message back into a bytestring to be forwarded to
        the server. This should invert whatever happened in bytes_to_message(). If
        this fails, the original bytestring that was supplied to bytes_to_message()
        will be sent instead. This, too, is called only by the last handler in a
        chain.
        """
        return ast.literal_eval(message)


class HandlerSock():
    """
    A socket for some hypothetical protocol which sends fixed-length, 64 byte
    messages. The contents are arbitrary bytes, with no special meaning.
    """
    def __init__(self, sock):
        self.sock = sock  # Underlying transport
        self.send_buf = b''  # Store unsent bytes
        self.recv_buf = b''  # Store unread bytes

    def connect(self, target_tuple):
        self.sock.connect(target_tuple)

    def close(self):
        self.sock.close()

    def send(self, bytes):
        sent = 0
        self.send_buf += bytes
        while len(self.send_buf) >= 64:  # Send everything we can
            self.sock.send(self.send_buf[:64])
            self.send_buf = self.send_buf[64:]
            sent += 64

    # Your socket should accept a num_bytes in its recv(), but can ignore it if it
    # doesn't make sense, for instance if you don't read from a socket that recv()s
    # bytestrings.
    def recv(self, num_bytes):
        while len(self.recv_buf) < 64: # Read until we get enough to work with
            self.recv_buf += self.sock.recv(num_bytes)
        recvd = self.recv_buf[:64]
        self.recv_buf = self.recv_buf[64:]
        return recvd

# Make your own exceptions for errors in your protocol that you know how to identify,
# it will make your life easier debugging. We don't actually use this one though.
class PrototypeMysteryError(Exception):
    pass
