import argparse, ast

# Simplest handler. Does even less than the prototype because it doesn't need to
# demo custom socket-like objects. Leaves sockets unchanged and just converts
# between bytes and strings.

class Handler:
    def __init__(self, arg_parser, final):
        self.retry_errors = []
        self.arg_parser = argparse.ArgumentParser(parents=[arg_parser], 
                                                  add_help=final,
                                                  allow_abbrev=False)
        self.args, self.remaining_args = self.arg_parser.parse_known_args()

    def setup_listener(self, listen_sock, cnxn_locals=None):
        return listen_sock

    def setup_sender(self, send_sock, cnxn_locals=None):
        return send_sock

    def bytes_to_message(self, bytes):
        return str(bytes)

    def message_to_bytes(self, message):
        return ast.literal_eval(message)
