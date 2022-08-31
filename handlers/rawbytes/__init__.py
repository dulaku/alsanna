import argparse, ast

# Simplest possible handler.

class Handler:
    def __init__(self, arg_parser, final):
        self.retry_errors = []
        self.arg_parser = argparse.ArgumentParser(parents=[arg_parser], 
                                                  add_help=final,
                                                  allow_abbrev=False)
        self.args, self.remaining_args = self.arg_parser.parse_known_args()

    def setup_client_facing(self, listen_sock, cnxn_locals=None):
        return RawSocket(listen_sock)

    def setup_server_facing(self, send_sock, cnxn_locals=None):
        return RawSocket(send_sock)

    def obj_to_printable(self, bytes):
        return str(bytes), None # Return no unprintable features of the message

    def printable_to_obj(self, message, unprintable_state):
        return ast.literal_eval(message)

class RawSocket():
    def __init__(self, sock):
        self.sock = sock  # Underlying transport

    def connect(self, target_tuple):
        self.sock.connect(target_tuple)

    def close(self):
        self.sock.close()

    def send(self, bytestr):
        sent = 0
        while sent < len(bytestr):
            try:
                sent += self.sock.send(bytestr)
            except ConnectionResetError:
                return sent

        return sent  # Unused by alsanna

    def recv(self, num_bytes):
        try:
            recvd = self.sock.recv(num_bytes)
        except ConnectionResetError:  # Socket is closed here, give up
            return None
        if len(recvd) == 0:  # Socket is closed here, too
            return None
        return recvd
