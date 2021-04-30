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
    def __init__(self, arg_parser, remaining_args, final):

        # It's common to have a situation where your underlying transport has
        # some data but not enough to actually construct a valid message for
        # whatever is next in the pipeline. For instance, a TLS socket can have
        # recv()'d data on the underlying TCP socket, but it might not be enough
        # to construct any plaintext bytes. This list should contain exceptions
        # that are raised in these situations by send() or recv(), which just
        # indicate that we need to keep retrying until we get something.
        self.retry_errors = [PrototypeWantWriteError]

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

    def setup_listener(self, listen_sock, cnxn_locals):
        """
        Do anything you need to as part of setting up a listener for your protocol.
        This is called before any bytes are received over listen_sock.
    
        listen_sock is some type of socket. It is guaranteed to have a send(), 
        recv(), connect(), and close() method, might or might not have any of 
        a socket's other methods. This is whatever type of socket your protocol 
        uses for transport, so it may be a plain TCP socket, a TLS-wrapped 
        sslsocket, and so on.
    
        cnxn_locals is a dictionary containing any information that needs to be
        communicated between different handlers and yours, or with alsanna.
    
        This should return the socket which will be used as the transport for the
        next protocol in the chain (if any) or which contains the data you are
        studying.
        """
        return HandlerSock(listen_sock)

    def setup_sender(self, send_sock, cnxn_locals):
        """
        Do anything you need to as part of setting up the connection from alsanna
        to the remote server for your protocol. This is called before any bytes are
        sent over send_sock.

        send_sock is some type of socket. The same guarantees apply as for
        listen_sock in setup_listener(), for the same reasons.

        cnxn_locals is a dictionary containing any information that needs to be
        communicated between different handlers and yours, or with alsanna.

        This should return the socket which will be used as the transport for the
        next protocol in the chain (if any) or which contains the data you are
        studying.
        """
        return HandlerSock(send_sock)

    def bytes_to_message(self, bytes):
        """
        Convert a sequence of bytes into a human-readable format. This will be
        called only for the last handler in a chain. It is recommended that you use
        logic in a custom Socket class in order to parse message boundaries, so that
        bytes is exactly one complete message in your protocol.

        bytes is a Python bytes object returned by your protocol's socket's recv()
        method.
        """
        return str(bytes)

    def message_to_bytes(self, message):
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

    def close():
        self.sock.close()

    def send(self, bytes):
        sent = 0
        self.send_buf += bytes
        if len(self.send_buf) < 64:  # Not enough data to proceed, retry
            raise PrototypeWantWriteError
        while len(self.send_buf) >= 64:  # Send everything we can
            self.sock.send(self.send_buf[:64])
            self.send_buf = self.send_buf[64:]
            sent += 64
        return sent + len(self.send_buf) # Number of bytes consumed from input

    def recv(self, num_bytes):
        while len(self.recv_buf) < 64: # Read until we get enough to work with
            self.recv_buf += self.sock.recv(num_bytes)
        recvd = self.recv_buf[:64]
        self.recv_buf = self.recv_buf[64:]
        return recvd

# It's recommended to create your own error classes to make debugging easier
class PrototypeWantWriteError(Exception):
    pass
