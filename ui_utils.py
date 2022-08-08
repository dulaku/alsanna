import fcntl, termios
import signal
import threading, subprocess
import copy
import os, sys
import tempfile
import time

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
    disable_toggles()  # Turn off keystroke toggles for editing
    print(colorful)  # Print received message

    # Open the message in an editor if required
    if intercept:
        with tempfile.NamedTemporaryFile(mode="w+") as tmpfile:
            tmpfile.write(str(message))
            tmpfile.flush()
            subprocess.call([editor, tmpfile.name])
            tmpfile.seek(0)
            message = tmpfile.read()

    enable_toggles()
    return message

def handle_toggles(ui_locals, stdin_lock, stdin, display_q):
    while True:
        try:
            with stdin_lock:
                c = stdin.read(1)
                time.sleep(1/1000000) # Sleep a bit to reduce CPU stress; can't use blocking stdin because we need the lock :(
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

                display_q.put(("Note", "Currently intercepting messages from "
                                       + ", ".join([host for host in hosts])))
        except IOError:
            pass

################################################################################
# Utility functions for printing and setting terminal flags
################################################################################

def print_ui(message, color):
    try:
        disable_toggles()
        if type(message) is tuple:
            message = message[0] + "\n" + indent(message[1]) + "\n"
        print("\033[38;5;" + str(color) + "m" + message + "\033[0m", file=sys.stderr)
    finally:
        enable_toggles()


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
    while termios.tcgetattr(stdin.fileno())[3] != new_attrs[3]:
        termios.tcsetattr(stdin.fileno(), termios.TCSAFLUSH, new_attrs)

    # Set stdin to nonblocking so the thread never blocks waiting for input
    new_flags = copy.deepcopy(stdin_flags)
    new_flags = new_flags | os.O_NONBLOCK
    while fcntl.fcntl(stdin.fileno(), fcntl.F_GETFL) != new_flags:
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
    while termios.tcgetattr(stdin.fileno())[3] != stdin_attrs[3]:
        termios.tcsetattr(stdin.fileno(), termios.TCSAFLUSH, stdin_attrs)
    while fcntl.fcntl(stdin.fileno(), fcntl.F_GETFL) != stdin_flags:
        fcntl.fcntl(stdin.fileno(), fcntl.F_SETFL, stdin_flags)
    # Deliberately do not release the lock - this stops handle_toggles()
    # from acquiring the lock, and therefore from reading anything, until
    # after we finish editing requests.

def abort(*args):
    disable_toggles()
    # Die without raising confusing error messages for alsanna internals.
    pid = os.getpid()
    os.kill(pid, signal.SIGKILL)

