import fcntl, termios, signal, threading, copy, os, tempfile, subprocess

# This gets executed just by importing the module, which is convenient for
# ensuring it only runs once and gets the initial state of things, but might be
# unexpected if you're expecting alsanna to be a proper python module.
stdin_lock = threading.RLock()
stdin = open(0)

# Store the original settings of stdin for use whenever we restore them
stdin_attrs = termios.tcgetattr(stdin.fileno())
stdin_flags = fcntl.fcntl(stdin.fileno(), fcntl.F_GETFL)

###############################################################################
# print_and_edit() and handle_toggles() are the functions you're likeliest to
# edit, if you want to modify what alsanna does with messages or you want to
# add or modify what different keystrokes do.
###############################################################################
def print_and_edit(message, intercept, color, editor):
    colorful = "\033[38;5;" + str(color) + "m" + message + "\033[0m"
    print(colorful)  # Print received message

    # Open the message in an editor if required
    if intercept:
        with tempfile.NamedTemporaryFile(mode="w+") as tmpfile:
            tmpfile.write(str(message))
            tmpfile.flush()
            subprocess.run([editor, tmpfile.name])
            tmpfile.seek(0)
            message = tmpfile.read()
    return message

def handle_toggles(ui_locals, stdin_lock, stdin):
    while True:
        try:
            with stdin_lock:
                c = stdin.read(1)

            if c:
                if c == ui_locals["intercept"]["i_c_key"]:
                    with ui_locals["intercept"]["lock"]:
                        ui_locals["intercept"]["client"] = not ui_locals["intercept"]["client"]
                elif c == ui_locals["intercept"]["i_s_key"]:
                    with ui_locals["intercept"]["lock"]:
                        ui_locals["intercept"]["server"] = not ui_locals["intercept"]["server"]
                hosts = []
                if ui_locals["intercept"]["client"]:
                    hosts.append("client")
                if ui_locals["intercept"]["server"]:
                    hosts.append("server")
                print(format_notification("Currently intercepting messages from "
                      + ", ".join([host for host in hosts])))
        except IOError: pass

################################################################################
# print_and_edit() and handle_toggles() are above this line.
################################################################################

# Text formatting
def format_error(message):
    if type(message) is tuple:
        message = message[0] + "\n" + indent(message[1]) + "\n"
    return "\033[38;5;" + str(error_color) + "m" + message + "\033[0m"
def format_notification(message):
    return "\033[38;5;" + str(notification_color) + "m" + message + "\033[0m"
def indent(string):
    lines = string.split("\n")
    for line_num in range(len(lines)):
        lines[line_num] = "\t" + lines[line_num]
    return "\n".join(lines)

# Utility functions for catching keystrokes. You shouldn't need to mess with
# these to handle protocols.
def enable_toggles():
    # Disable canonical mode and echo
    new_attrs = copy.deepcopy(stdin_attrs)
    new_attrs[3] = new_attrs[3] & ~termios.ICANON & ~termios.ECHO
    termios.tcsetattr(stdin.fileno(), termios.TCSANOW, new_attrs)

    # Set stdin to nonblocking so the thread never blocks waiting for input
    new_flags = copy.deepcopy(stdin_flags)
    new_flags = new_flags | os.O_NONBLOCK
    fcntl.fcntl(stdin.fileno(), fcntl.F_SETFL, new_flags)
    # The lock might have been acquired once or twice, so just keep releasing
    # until we're sure it's free.
    while True:
        try:
            stdin_lock.release()
        except RuntimeError:
            break

def disable_toggles():
    stdin_lock.acquire()
    termios.tcsetattr(stdin.fileno(), termios.TCSAFLUSH, stdin_attrs)
    fcntl.fcntl(stdin.fileno(), fcntl.F_SETFL, stdin_flags)
    # Deliberately do not release the lock - this stops handle_toggles()
    # from acquiring the lock, and therefore from reading anything, until
    # after we finish editing requests.

def abort(*args):
    disable_toggles()
    # Die without raising confusing error messages.
    pid = os.getpid()
    os.kill(pid, signal.SIGKILL)

