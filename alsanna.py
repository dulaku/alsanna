import argparse                                 # Args
import socket, select, ssl                      # Networking
import multiprocessing, subprocess, signal      # Multiprocessing and signals
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
    "--read_size", type=int, default=4096,
    help="Number of bytes read from wire before forwarding."
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
    "--error_color", type=int, default=9,
    help="8-bit color code for error messages from alsanna."
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

def format_error(error_message):
    return "\033[38;5;" + str(args.error_color) + "m" + error_message + "\033[0m"

def process_messages(preprocessing_q):
    """
    Perform synchronous message processing steps, one message at a time. Lets us reason
    about our messages in order without giving up the ability to handle multiple
    connections.
    """
    postprocessing_queues = {}
    while True:
        # Die if orphaned
        if os.getppid() == 1:
            return

        # Get a message
        try:
            connection_id, message = preprocessing_q.get()
        except:
            print(format_error("Failed to get message\n" + traceback.format_exc()),
                  file=sys.stderr)
            continue

        # Act on special messages
        if connection_id == "Err":
            print(format_error(message), file=sys.stderr)
            continue
        if connection_id == "Kill":
            del postprocessing_queues[message]  # Destroy reference to a now-dead queue.
            continue
        if connection_id not in postprocessing_queues.keys():  # Register new queue
            postprocessing_queues[connection_id] = message  # "message# is Queue object
            continue

        # Colorize text
        if connection_id[-1] == "c":
            color = args.client_color
        elif connection_id[-1] == "s":
            color = args.server_color
        else:
            color = 8  # If this ever gets used something's gone wrong.

        colorful = "\033[38;5;" + str(color) + "m" + message + "\033[0m"
        print(colorful)  # Print received message

        # Open the message in an editor if required
        try:
            if (connection_id[-1] == "c" and args.intercept_client) \
                    or (connection_id[-1] == "s" and args.intercept_server):
                with tempfile.NamedTemporaryFile(mode="w+") as tmpfile:
                    tmpfile.write(message)
                    tmpfile.flush()
                    time.sleep(args.edit_delay)
                    subprocess.run([args.editor, tmpfile.name])
                    tmpfile.seek(0)
                    message = tmpfile.read()
        except:
            print(
                format_error("Error reading message from disk.\n"
                             + traceback.format_exc()),
                file=sys.stderr
            )

        # Send the last-good message version (original if the modification failed)
        finally:
            try:
                postprocessing_queues[connection_id].put(message)
            except:
                pass  # If a subprocess died and its queue is gone, just continue

def forward(receive_sock, send_sock, processing_q, result_q, connection_id):
    """
    Handles one direction of communication in a connection. For processing messages
    in order, see the process_messages() function. This implementation assumes the
    server is finicky and will close the connection if a message is not promptly sent
    after connection - to allow you editing time, we therefore wait to open
    the TCP connection until after editing. Assumes the client is patient.
    """
    return_sock = False
    # If we haven't opened the forwarding connection yet, send_sock is None. So we have
    # to write our select() call to avoid passing None to it. This never gets called
    # with receive_sock as None so we don't worry about it.
    readable, writable, exception = select.select(
        [receive_sock],                                                          # rlist
        [send_sock] if send_sock is not None else [],                            # wlist
        [receive_sock, send_sock] if send_sock is not None else [receive_sock],  # xlist
        0  # timeout disabled - don't block
    )

    if len(exception) > 0:
        processing_q.put(("Err", "Exception in socket(s): " + str(exception)))
        return True  # Something bad happened, close the sockets.

    if receive_sock in readable and (send_sock in writable or send_sock is None):
        data_bytes = receive_sock.recv(args.read_size)
        if len(data_bytes) == 0:  # Signifies connection is closed on the remote end.
            return True
        data_string = str(data_bytes)

        processing_q.put((connection_id, data_string))
        try:
            data_string = result_q.get()  # Blocks until processed message available

            if send_sock is None:  # We need to open a connection
                try:
                    return_sock = True
                    send_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
                    if args.use_tls:
                        f_tls_context = ssl.create_default_context()
                        f_tls_context.check_hostname = False
                        send_sock = f_tls_context.wrap_socket(send_sock)
                    send_sock.connect((args.server_ip, args.server_port))
                    send_sock.setblocking(False)
                except:
                    processing_q.put(("Err", "Error setting up forwarder.\n"
                                             + traceback.format_exc()))
                    return True  # Can't send data without this, so give up.

            try:
                data_bytes = ast.literal_eval(data_string)  # Convert from string to bytes
            except:
                processing_q.put(("Err", "Error parsing processed message.\n"
                                         + traceback.format_exc()))
        finally:
            try:
                sent = 0
                while sent < len(data_bytes):
                    sent += send_sock.send(data_bytes[sent:])
            except:
                processing_q.put(("Err", "Error forwarding message to destination.\n"
                                         + traceback.format_exc()))
                send_sock.close()  # Might need to do this here if it failed immediately
                return True  # Probably want to give up if sending failed somehow.
    if return_sock:  # Disgusting overloading of return value type
        return send_sock
    else:
        return False  # Keep connection alive.


def manage_connections(listen_sock, processing_q, connection_id):
    """
    Handle logic required to set up and maintain connections. The ability to hack this
    is the main selling point of alsanna - for instance if you need to send a plaintext
    message from the server to the client prior to TLS negotiation, you can do it here.

    So that we can have all the protocol logic in one place, we handle both directions
    of traffic here. A more specialized proxy might benefit in modularity from having
    a child process for each direction and using blocking sockets for each.

    The forward() method handles setting up the socket we use to forward data to the
    server. This is ugly as heck, but handles the common case where the server kills
    your connection if you take too long editing something.
    """

    ###########################################################
    # Initialize queues and set up TLS on listener if need be #
    ###########################################################

    q_manager = multiprocessing.Manager()
    c_result_q = q_manager.Queue()
    processing_q.put((str(connection_id) + "c", c_result_q))
    s_result_q = q_manager.Queue()
    processing_q.put((str(connection_id) + "s", s_result_q))

    with listen_sock:
        forward_sock = None
        if args.use_tls:
            try:
                l_tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                l_tls_context.load_cert_chain(args.cert, args.priv_key)
                listen_sock = l_tls_context.wrap_socket(listen_sock,
                                                        server_side=True)
                listen_sock.setblocking(False)
            except:
                processing_q.put(("Err", "Error setting up TLS listener.\n"
                                         + traceback.format_exc()))
                return

        ############################################################################
        # Shuffle bytes back and forth, setting up forwarder on first sent message #
        ############################################################################
        client_done, server_done = False, False
        try:
            # We check forward_sock to handle the situation where we never update
            # server_done because we errored out trying to send from client to server
            while not client_done and (not server_done or forward_sock is None):
                # Die if orphaned
                if os.getppid() == 1:
                    return
                # Send try to forward data in each direction
                if not client_done:
                    try:
                        client_done = forward(listen_sock, forward_sock,
                                              processing_q, c_result_q,
                                              str(connection_id) + "c")
                        if isinstance(client_done, ssl.SSLSocket):
                            forward_sock = client_done
                            client_done = False
                    except:
                        processing_q.put(("Err", "Error forwarding data to server.\n"
                                          + traceback.format_exc()))
                        break
                if not server_done and forward_sock is not None:
                    try:
                        server_done = forward(forward_sock, listen_sock,
                                              processing_q, s_result_q,
                                              str(connection_id) + "s")
                    except:
                        processing_q.put(("Err", "Error forwarding data to client.\n"
                                          + traceback.format_exc()))
                        break
        finally:  # No context manager because it's None sometimes; manual cleanup
            if forward_sock is not None:
                forward_sock.close()


def main():
    """
    Highest-level server logic. Sets up the synchronous message processor, sets up
    connections, and spins up a subprocess to handle each connection.
    """
    processing_q = multiprocessing.Queue()

    message_processor = multiprocessing.Process(target=process_messages,
                                                args=(processing_q,))
    message_processor.daemon = True
    message_processor.start()

    connection_id = 0
    connections = {}

    l_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    l_sock.bind((args.listen_ip, args.listen_port))
    l_sock.listen(args.max_connections)
    with l_sock:
        while True:
            try:
                listen_sock, addr = l_sock.accept()

                connections[connection_id] = multiprocessing.Process(
                    target=manage_connections,
                    args=(listen_sock,
                          processing_q,
                          connection_id))
                connections[connection_id].start()
                connection_id += 1
            except KeyboardInterrupt:
                break
            except:
                processing_q.put(("Err", "Something terrible happened. Exiting.\n"
                                         + traceback.format_exc()))
                break


if __name__ == '__main__':
    main()
