import argparse                                 # Args
import socket, select, ssl                      # Networking
import multiprocessing                          # Multiprocessing
import traceback, sys, os, tempfile, ast, time  # Misc

arg_parser = argparse.ArgumentParser()
arg_parser.add_argument(
    "--use_tls", type=bool, default=True,
    help="Whether or not to use TLS at all."
)
arg_parser.add_argument(
    "--cert", type=str, default="./tls_cert.pem",
    help="Path to a TLS certificate trusted by the software that produces your traffic."
)
arg_parser.add_argument(
    "--priv_key", type=str, default="./tls_key.pem",
    help="Path to the private key associated with the TLS certificate."
)
arg_parser.add_argument(
    "--listen_ip", type=str, default="127.0.0.1",
    help="IP address of a local interface to listen on."
)
arg_parser.add_argument(
    "--listen_port", type=int, default=443,
    help="TCP port to listen for incoming connections on."
)
arg_parser.add_argument(
    "--max_connections", type=int, default=5,
    help="Max number of simultaneous connections supported."
)
arg_parser.add_argument(
    "--server_ip", type=str, default="127.0.0.1",
    help="IP address of the server your traffic is ultimately bound for."
)
arg_parser.add_argument(
    "--server_port", type=int, default=443,
    help="TCP port on remote server to send traffic to; probably same as listen_port."
)
arg_parser.add_argument(
    "--client_color", type=int, default=13,
    help="8-bit color code for client-sent text."
)
arg_parser.add_argument(
    "--server_color", type=int, default=14,
    help="8-bit color code for server-sent text."
)
arg_parser.add_argument(
    "--editor", type=str, default="nano",
    help="Command to use for launching editor."
)
arg_parser.add_argument(
    "--intercept_client", type=bool, default=True,
    help="Whether to intercept client-sent data for editing."
)
arg_parser.add_argument(
    "--intercept_server", type=bool, default=False,
    help="Whether to intercept server-sent data for editing."
)
arg_parser.add_argument(
    "--edit_delay", type=int, default=1,
    help="Number of seconds to wait before sending edited messages."
)

args = arg_parser.parse_args()

# A dumb hack to get Python to ignore TLS certs
ssl._create_default_https_context = ssl._create_unverified_context

def process_messages(preprocessing_q):
    """
    Perform synchronous message processing steps, one message at a time. Lets us reason
    about our messages in order without giving up the ability to handle multiple
    connections.
    """
    postprocessing_queues = {}
    while True:
        connection_id, message = preprocessing_q.get()
        if connection_id == "Kill":
            while not postprocessing_queues[message].empty():
                postprocessing_queues[message].get()  # Discard bytes still in queue
            del postprocessing_queues[message]
            continue
        if connection_id not in postprocessing_queues.keys():  # Register new queue
            postprocessing_queues[connection_id] = message  # "message# is Queue object
            continue
        print(message)  # Print unmodified message
        end_of_colorcode = message.index('m')
        color = int(message[7:end_of_colorcode])
        start_of_bytes = message.index('b')
        message = message[start_of_bytes:-4]  # Trim color codes
        if (color == args.client_color and args.intercept_client) \
                or (color == args.server_color and args.intercept_server):
            with tempfile.NamedTemporaryFile(mode="w+") as tmpfile:
                tmpfile.write(message)
                tmpfile.flush()
                time.sleep(args.edit_delay)
                os.system(args.editor + " " + tmpfile.name)
                tmpfile.seek(0)
                message = ast.literal_eval(tmpfile.read())
        else:
            message = ast.literal_eval(message)
        postprocessing_queues[connection_id].put(message)

def forward(receive_sock, send_sock, preprocessing_q, postprocessing_q, connection_id, color_code):
    """
    Handles one direction of communication in a connection. Handles the guts of sockets
    programming, so _probably_ doesn't need to be changed often. For handling messages,
    see the process_messages function.
    """
    readable, writable, exception = select.select(
        [receive_sock],             # rlist
        [send_sock],                # wlist
        [receive_sock, send_sock],  # xlist
        60                          # timeout
    )
    if len(exception) > 0:
        print("Exception in socket(s): " + str(exception),
              file=sys.stderr)
        return True  # Something bad happened, close the sockets.

    if receive_sock in readable and send_sock in writable:
        data_string = receive_sock.recv(4096)
        if len(data_string) == 0:
            return True  # Signifies connection is closed on the remote end.
        data_string = "\033[38;5;" + str(color_code) + "m" + str(data_string)  # Add color
        data_string += "\033[0m" # Terminate color
        preprocessing_q.put((connection_id, data_string))
        data_string = postprocessing_q.get()  # Blocks until processed message available
        sent = 0
        while sent < len(data_string):
            sent += send_sock.send(data_string[sent:])
        return False  # Keep connection alive.
    else:
        return False  # Not in a state to read+write, wait till we are.

def handle_connections(listen_sock, preprocessing_q, connection_id):
    """
    Logic for keeping a half-duplex communication channel open between the client and
    server. If your protocol does things like have the server talk first, you'll want
    to edit that in here.
    """
    q_manager = multiprocessing.Manager()
    postprocessing_q = q_manager.Queue()
    preprocessing_q.put((connection_id, postprocessing_q))
    if args.use_tls:
        listen_tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        listen_tls_context.load_cert_chain(args.cert, args.priv_key)

        forward_tls_context = ssl.create_default_context()
        forward_tls_context.check_hostname = False

    try:
        if args.use_tls:
            listen_sock = listen_tls_context.wrap_socket(listen_sock,
                                                         server_side=True)
        listen_sock.setblocking(False)
        with listen_sock:
            f_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
            with f_sock:
                if args.use_tls:
                    forward_sock = forward_tls_context.wrap_socket(f_sock)
                else:
                    forward_sock = f_sock
                with forward_sock:
                    forward_sock.connect((args.server_ip, args.server_port))
                    forward_sock.setblocking(False)
                    while True:
                        # Listen to client software
                        client_done = forward(listen_sock,
                                              forward_sock,
                                              preprocessing_q,
                                              postprocessing_q,
                                              connection_id,
                                              args.client_color)

                        # Listen to server software
                        server_done = forward(forward_sock,
                                              listen_sock,
                                              preprocessing_q,
                                              postprocessing_q,
                                              connection_id,
                                              args.server_color)
                        if client_done or server_done:
                            break
    except:
        traceback.print_exc()
    finally:
        preprocessing_q.put(("Kill", connection_id))

if __name__ == '__main__':
    """
    Highest-level server logic. Sets up the synchronous message processor, accepts
    incoming connections, and spins up a subprocess for each one that comes in before
    handing off the new socket object for that connection. Chances are, this won't need
    to change often.
    """
    with multiprocessing.Manager() as queue_manager:
        preprocessing_queue = multiprocessing.Queue()

        message_processor = multiprocessing.Process(target=process_messages,
                                                    args=(preprocessing_queue,))
        message_processor.daemon = True
        message_processor.start()

        connection_id = 0
        connections = []

        l_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        l_sock.bind((args.listen_ip, args.listen_port))
        l_sock.listen(args.max_connections)
        with l_sock:
            try:
                while True:
                    listen_sock, addr = l_sock.accept()
                    connections.append(multiprocessing.Process(target=handle_connections,
                                                               args=(listen_sock,
                                                                     preprocessing_queue,
                                                                     connection_id)))
                    connection_id += 1
                    connections[-1].start()
            except:
                traceback.print_exc()
            finally:
                for connection in connections:
                    connection.terminate() # Manual cleanup since can't daemonize
