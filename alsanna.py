import argparse                               # Args
import socket, ssl                            # Networking
import multiprocessing, threading, signal     # Concurrency
import traceback, sys, os, time, importlib    # Misc

arg_parser = argparse.ArgumentParser(allow_abbrev=False, add_help=False) # Options needed for argparser shenanigans later
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
    handler_module = importlib.import_module("handler_"+args.handlers[i])
    args.handlers[i] = handler_module.Handler(arg_parser, remaining_args, final)
    arg_parser = args.handlers[i].arg_parser
    remaining_args = args.handlers[i].remaining_args
args = args.handlers[-1].args # The final handler finished building the real arg_parser

def user_interface(display_q):
    """
    Define the process that runs the user interface. This process will:
        * Monitor for keystrokes that signal a change to alsanna's behavior
        * Print messages and, if needed, open an editor for tampering with them
        * Return messages back to their originating connections
        * Print status information such as error messages
    Putting all this in a single process eliminates the worst concurrency
    headaches we might otherwise run into.

    display_q is the queue which all other processes will use to communicate
    with this process.
    """
    import ui_utils
    ui_utils.error_color = args.error_color
    ui_utils.notification_color = args.notification_color

    # This is here so you know about it. SIGINT (so ctrl+c) and SIGTERM will,
    # instead of their normal behavior, repair the terminal and then kill 
    # alsanna (with SIGKILL, so with no further cleanup.
    signal.signal(signal.SIGINT, ui_utils.abort)
    signal.signal(signal.SIGTERM, ui_utils.abort)

    # This is also here so you know about it. There is a separate thread running
    # that checks for keystrokes and updates the intercept dict as needed.
    ui_locals = {}
    ui_locals["intercept"] = {"client": not args.pass_client,
                              "server": args.intercept_server,
                              "i_c_key": args.intercept_client_keypress,
                              "i_s_key": args.intercept_server_keypress,
                              "lock": threading.Lock()}
    toggle_catcher = threading.Thread(target=ui_utils.handle_toggles, 
                                      kwargs={"ui_locals": ui_locals,
                                              "stdin": ui_utils.stdin, 
                                              "stdin_lock": ui_utils.stdin_lock},
                                      daemon=True)
    ui_utils.enable_toggles()
    toggle_catcher.start()

    forwarding_queues = {}
    while True:
        # If orphaned, reset terminal and die
        if os.getppid() == 1:
            ui_utils.disable_toggles()
            return
     
        # Get a message
        try:
            connection_id, message = display_q.get()
        except:
            print(ui_utils.format_error(("Failed to get message", 
                                         traceback.format_exc())),
                  file=sys.stderr)
            continue

        # Act on special messages
        if connection_id == "Err":
            print(ui_utils.format_error(message), file=sys.stderr)
            continue
        if connection_id == "Kill":
            del forwarding_queues[message]  # Destroy reference to dead queue.
            continue
        if connection_id not in forwarding_queues.keys():  # Register new queue
            forwarding_queues[connection_id] = message  # "message" is Queue object
            continue
        
        # Colorize text and choose whether to intercept for editing
        with ui_locals["intercept"]["lock"]:
            if connection_id[-6:] == "client":
                intercept = ui_locals["intercept"]["client"]
                color = args.client_color
            elif connection_id[-6:] == "server":
                intercept = ui_locals["intercept"]["server"]
                color = args.server_color
            else:  # If this ever happens it's a bug
                intercept = False
                color = 8

        try:
            ui_utils.disable_toggles() # Turn off keystroke toggles for editing
            try:
                message = ui_utils.print_and_edit(message=message, 
                                                  intercept=intercept, 
                                                  color=color, 
                                                  editor=args.editor)
            except:
                print(
                    ui_utils.format_error(("Error in printing/editing.", 
                                           traceback.format_exc())),
                    file=sys.stderr
                )
                break
            ui_utils.enable_toggles()

        finally:
            try:
                forwarding_queues[connection_id].put(message)
            except:
                pass  # If a subprocess died and its queue is gone, continue

def cleanup(sockets):
    """
    Ensures the sockets for listening and sending are both closed.
    """
    try:
        sockets[listen]["sock"].close()
    except:
        pass
    try:
        sockets[send]["sock"].close()
    except:
        pass

def forward(sockets, listen, send, display_q, result_q, cnxn_locals):
    """
    Forwards a TCP stream in one direction, from listen to send.

    sockets is a dictionary containing sockets and related data structures; see
    manage_connection()

    listen is the host which will be sending data in this direction, either 
    "client" or "server". The host alsanna listens to.

    send is the host which will be receiving data in this direction, either
    "client" or "server". The host alsanna sends to.

    display_q is the global queue the user interface reads from.

    result_q is the queue which this direction of travel reads from when
    forwarding a message. the user interface process puts messages on this queue.

    cnxn_locals is a dictionary which holds any state that needs to be shared
    across different handlers or by alsanna itself.
    """
    ignored_sock_errors = []
    for handler in args.handlers:
        ignored_sock_errors += handler.retry_errors
    ignored_sock_errors = tuple(ignored_sock_errors)
    while True:
        if os.getppid() == 1: # If orphaned, clean up toys and die
            cleanup(sockets)
            break
        try:
            try:
                data_bytes = sockets[listen]["sock"].recv(args.read_size)
            except ignored_sock_errors:
                continue 
            if len(data_bytes) == 0:
                break

            readable = args.handlers[-1].bytes_to_message(data_bytes)
            display_q.put((cnxn_locals['cnxn_id']+listen, readable))
            readable = result_q.get() # Blocks until message available
            data_bytes = args.handlers[-1].message_to_bytes(readable)

            # Set up socket to talk to server, typically on first iteration 
            if listen == "client" and sockets["server"]["sock"] is None:
                sockets["server"]["sock"] = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
                try:
                    for handler in args.handlers:
                        sockets["server"]["sock"] = handler.setup_sender(
                            send_sock=sockets["server"]["sock"],
                            cnxn_locals=cnxn_locals
                        )
                    sockets["server"]["sock"].connect((args.server_ip, 
                                                       args.server_port))
                    sockets["server"]["connected"].set()
                except:
                    display_q.put(("Err", ("Error setting up listener.",
                                           traceback.format_exc())
                                    ))
                    return
        except:
            display_q.put(("Err", ("Error in forwarder.",
                                   traceback.format_exc())
                            ))
            return
        finally:
            try:
                sent = 0
                while sent < len(data_bytes):
                    try:
                        sent += sockets[send]["sock"].send(data_bytes[sent:])
                    except ignored_sock_errors:
                        continue
            except:
                display_q.put(("Err", ("Error sending data.",
                                        traceback.format_exc())
                                ))
                cleanup(sockets)
                return

def manage_connections(listen_sock, display_q, connection_id):
    """
    Manage a single TCP connection. Sets up shared resources and a thread for
    each direction of communication.

    listen_sock is the "client" socket spun off from our server upon receiving
    a connection.

    display_q is the global queue the user interface reads from.

    connection_id is a numeric id incremented for each connection we receive.
    """

    # Keep track of anything needed for maintaining state.
    cnxn_locals = {'cnxn_id': str(connection_id)}

    q_manager = multiprocessing.Manager()
    c_result_q = q_manager.Queue()
    display_q.put((cnxn_locals['cnxn_id'] + "client", c_result_q))
    s_result_q = q_manager.Queue()
    display_q.put((cnxn_locals['cnxn_id'] + "server", s_result_q))

    sockets = {"client": {"sock": listen_sock},
               "server": {"sock": None,
                          "connected": threading.Event()}}

    with sockets["client"]["sock"]:
        try:
            for handler in args.handlers:
                sockets["client"]["sock"] = handler.setup_listener(
                    listen_sock=sockets["client"]["sock"], 
                    cnxn_locals=cnxn_locals
                )
        except:
            display_q.put(("Err", ("Error setting up listener.",
                                   traceback.format_exc())
                            ))
            return

        c_to_s_thread = threading.Thread(target=forward,
                                         kwargs={"sockets": sockets,
                                                 "listen": "client",
                                                 "send": "server",
                                                 "display_q": display_q,
                                                 "result_q": c_result_q,
                                                 "cnxn_locals": cnxn_locals},
                                         daemon=True)
        s_to_c_thread = threading.Thread(target=forward,
                                         kwargs={"sockets": sockets,
                                                 "listen": "server",
                                                 "send": "client",
                                                 "display_q": display_q,
                                                 "result_q": s_result_q,
                                                 "cnxn_locals": cnxn_locals},
                                         daemon=True)

        try:
            c_to_s_thread.start()
            sockets["server"]["connected"].wait() # Wait for connection to server
            s_to_c_thread.start()                 # Only now begin server->client
            c_to_s_thread.join()
            s_to_c_thread.join()
        except:
            display_q.put(("Err", ("Forwarder " + cnxn_locals["cnxn_id"] + "dying.",
                                   traceback.format_exc())
                            ))
            display_q.put(("Kill", cnxn_locals['cnxn_id'] + "client"))
            display_q.put(("Kill", cnxn_locals['cnxn_id'] + "server"))
        return

def main():
    """
    Highest-level server logic. Sets up the synchronous message processor, sets 
    up connections, and spins up a subprocess to handle each connection.
    """
    display_q = multiprocessing.Queue()

    message_processor = multiprocessing.Process(target=user_interface,
                                                kwargs={"display_q": display_q})
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
                    target=manage_connections,
                    args=(listen_sock,
                          display_q,
                          connection_id))
                connections[connection_id].start()
                connection_id += 1
            except:
                display_q.put(("Err", ("Parent process dying, exiting alsanna.\n",
                                       traceback.format_exc())
                                ))
                time.sleep(1) # Give processor time to print the stack trace.
                break

if __name__ == '__main__':
    main()
