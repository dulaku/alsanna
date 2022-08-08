import os
import traceback
import socket
import threading, multiprocessing

def manage_connections(listen_sock, display_q, connection_id, args):
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

    with sockets["client"]["sock"]:  # TODO: Consider moving this inside forward() like its sibling
        try:
            for handler in args.handlers:
                sockets["client"]["sock"] = handler.setup_client_facing(
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
                                                 "cnxn_locals": cnxn_locals,
                                                 "args": args},
                                         daemon=True)
        s_to_c_thread = threading.Thread(target=forward,
                                         kwargs={"sockets": sockets,
                                                 "listen": "server",
                                                 "send": "client",
                                                 "display_q": display_q,
                                                 "result_q": s_result_q,
                                                 "cnxn_locals": cnxn_locals,
                                                 "args": args},
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


def forward(sockets, listen, send, display_q, result_q, cnxn_locals, args):
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
    while True:
        msg_obj = None
        if os.getppid() == 1: # If orphaned, clean up toys and die
            cleanup(sockets, listen, send)
            return
        try:
            msg_obj = sockets[listen]["sock"].recv(args.read_size)
            if msg_obj is None:
                return

            readable, unprintable_state = args.handlers[-1].obj_to_printable(msg_obj)
            display_q.put((cnxn_locals['cnxn_id']+listen, readable))
            readable = result_q.get()  # Blocks until message available
            msg_obj = args.handlers[-1].printable_to_obj(readable, unprintable_state)
            # Set up socket to talk to server, typically on first iteration
            # If server talks first, this needs to change
            if listen == "client" and sockets["server"]["sock"] is None:
                sockets["server"]["sock"] = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
                try:
                    for handler in args.handlers:
                        sockets["server"]["sock"] = handler.setup_server_facing(
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
                if msg_obj is not None:  # We got a message but had an error after
                    sockets[send]["sock"].send(msg_obj)
            except:
                display_q.put(("Err", ("Error sending data.",
                                        traceback.format_exc())
                              ))
                cleanup(sockets, listen, send)
                return


def cleanup(sockets, listen, send):
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
