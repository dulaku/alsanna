import argparse                               # Args
import socket                                 # Networking
import multiprocessing                        # Concurrency
import traceback, time, importlib             # Misc
import ui_proc, cnxn_proc

arg_parser = argparse.ArgumentParser(allow_abbrev=False, add_help=False, conflict_handler='resolve') # Options needed for argparser shenanigans later
arg_parser.add_argument(
    "--handlers", type=str, nargs="+", default=["tls", "rawbytes"],
    help="Protocol and message handlers which should be used. Each may specify "
         "its own additional arguments. Order matters - handlers should be "
         "provided in the order in which protocols are encapsulated. For "
         "instance, the default of 'tls rawbytes' applies the tls handler "
         "first, then the rawbytes handler to the results. This is what you want "
         "when you're looking at raw bytes encapsulated in TLS."
)
arg_parser.add_argument(
    "--listen_ip", type=str, default="127.0.0.1",
    help="IP address of a local interface to listen on."
)
arg_parser.add_argument(
    "--listen_port", type=int, default=3125,
    help="TCP port to listen for incoming connections on."
)
arg_parser.add_argument(
    "--server_ip", type=str, default="127.0.0.1",
    help="The IP address of the server where traffic will be forwarded."
)
arg_parser.add_argument(
    "--server_port", type=int, default=3125,
    help="TCP port on remote server to send traffic to; probably same as "
         "listen_port."
)
arg_parser.add_argument(
    "--max_connections", type=int, default=5,
    help="Max number of simultaneous connections supported."
)
arg_parser.add_argument(
    "--read_size", type=int, default=4096,
    help="Number of bytes read from wire before forwarding."
)
arg_parser.add_argument(
    "--pass_client", action="store_true",
    help="If this is supplied, then by default alsanna will not intercept client "
         "traffic for editing."
)
arg_parser.add_argument(
    "--intercept_server", action="store_true",
    help="If this is supplied, then by default alsanna will intercept server "
         "traffic for editing."
)
arg_parser.add_argument(
    "--intercept_client_keypress", type=str, default='c',
    help="The key which, when pressed, toggles interception of client traffic "
         "for editing. Case sensitive."
)
arg_parser.add_argument(
    "--intercept_server_keypress", type=str, default='s',
    help="The key which, when pressed, toggles interception of server traffic "
         "for editing. Case sensitive."
)
arg_parser.add_argument(
    "--editor", type=str, default="nano",
    help="Command to use for launching editor. Trivial command injection."
)
arg_parser.add_argument(
    "--client_color", type=int, default=13,
    help="8-bit color code for client-sent messages."
)
arg_parser.add_argument(
    "--server_color", type=int, default=14,
    help="8-bit color code for server-sent messages."
)
arg_parser.add_argument(
    "--error_color", type=int, default=9,
    help="8-bit color code for error messages from alsanna."
)
arg_parser.add_argument(
    "--notification_color", type=int, default=11,
    help="8-bit color code for non-error notifications from alsanna."
)

# Build argument list dynamically so you only see help for options that matter.
args, remaining_args = arg_parser.parse_known_args()
for i in range(len(args.handlers)):
    final = True if i == len(args.handlers)-1 else False  # Is this the last one?
    handler_module = importlib.import_module('handlers.' + args.handlers[i])
    args.handlers[i] = handler_module.Handler(arg_parser, final)
    arg_parser = args.handlers[i].arg_parser
handlers = args.handlers  # Save the list of modules
args = args.handlers[-1].args # The final handler finished building the real arg_parser
args.handlers = handlers  # Replace the list of strings with a list of modules


def main():
    """
    Highest-level server logic. Sets up the synchronous message processor, sets 
    up connections, and spins up a subprocess to handle each connection.
    """
    display_q = multiprocessing.Queue()

    message_processor = multiprocessing.Process(target=ui_proc.user_interface,
                                                kwargs={"display_q": display_q,
                                                        "args": args})
    message_processor.daemon = True
    message_processor.start()

    connection_id = 0
    connections = {}

    l_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)

    # Allow socket to be reused quickly after quitting.
    l_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    l_sock.bind((args.listen_ip, args.listen_port))
    l_sock.listen(args.max_connections)
    with l_sock:
        while True:
            try:
                listen_sock, addr = l_sock.accept()

                connections[connection_id] = multiprocessing.Process(
                    target=cnxn_proc.manage_connections,
                    args=(listen_sock,
                          display_q,
                          connection_id,
                          args))
                connections[connection_id].start()
                connection_id += 1
            except:
                display_q.put(("Err", ("Parent process dying, exiting alsanna.\n",
                                       traceback.format_exc())
                                ))
                time.sleep(1)  # Give processor time to print the stack trace.
                break

if __name__ == '__main__':
    main()
