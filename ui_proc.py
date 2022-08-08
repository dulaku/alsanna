import signal, threading
import os
import traceback

def user_interface(display_q, args):
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

    # This is here so you know about it. SIGINT (so ctrl+c) and SIGTERM will,
    # instead of their normal behavior, repair the terminal and then kill
    # alsanna (with SIGKILL, so with no further cleanup).
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
                                              "stdin_lock": ui_utils.stdin_lock,
                                              "display_q": display_q},
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
            ui_utils.print_ui(message=("Failed to get message",
                                       traceback.format_exc()),
                              color=args.error_color)
            continue

        # Act on special messages
        if connection_id == "Err":
            ui_utils.print_ui(message=message, color=args.error_color)
            continue
        if connection_id == "Note":
            ui_utils.print_ui(message=message, color=args.notification_color)
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
            try:
                message = ui_utils.print_and_edit(message=message,
                                                  intercept=intercept,
                                                  color=color,
                                                  editor=args.editor)
            except:
                ui_utils.print_ui(message=("Error in printing/editing.",
                                           traceback.format_exc()),
                                  color=args.error_color)
                break

        finally:
            try:
                forwarding_queues[connection_id].put(message)
            except:
                pass  # If a subprocess died and its queue is gone, continue
