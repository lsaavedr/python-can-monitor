#!/usr/bin/env python3

import argparse
import curses
import sys
import threading
import traceback
from collections import OrderedDict
from datetime import datetime
from operator import itemgetter

from .source_handler import (
    CandumpHandler,
    CanHandler,
    InvalidFrame,
    SerialBinHandler,
    SerialHandler,
)

should_redraw = threading.Event()
stop_reading = threading.Event()

can_messages = {}
Appereances = {}
can_messages_lock = threading.Lock()

thread_exception = None
msg_old = {}
msg_len = {}
TOTAL = 0
frame_ID = 0
frame_ID_old = 0
Date_DOC = datetime.now()
Date_DOC = datetime.timestamp(Date_DOC)


def reading_loop(source_handler, blacklist):
    global TOTAL
    global can_messages
    global Appereances
    """Background thread for reading."""
    try:
        while not stop_reading.is_set():
            try:
                now = datetime.now()
                timestamp = datetime.timestamp(now)
                frame_id, data = source_handler.get_message()
                # frame_ID = frame_id
                if frame_id in Appereances:
                    Appereances[frame_id] += 1
                    TOTAL = sum(Appereances.values())
                else:
                    Appereances[frame_id] = 1
                f = open(str(Date_DOC) + ".txt", "a")
                f.write(
                    str(timestamp)
                    + " "
                    + str(frame_id)
                    + " "
                    + " ".join("%02X" % byte for byte in data)
                    + "\n"
                )
                f.close()

            except InvalidFrame:
                continue
            except EOFError:
                break

            # if frame_id in blacklist:
            #    continue

            # Add the frame to the can_messages dict and tell the
            # main thread to refresh its content
            with can_messages_lock:
                can_messages[frame_id] = data
                should_redraw.set()

        stop_reading.wait()

    except Exception:
        if not stop_reading.is_set():
            # Only log exception if we were not going to stop the thread
            # When quitting, the main thread calls close() on the serial device
            # and read() may throw an exception. We don't want to display it as
            # we're stopping the script anyway
            global thread_exception
            thread_exception = sys.exc_info()


def init_window(stdscr):
    """Init a window filling the entire screen with a border around it."""
    stdscr.clear()
    stdscr.refresh()

    max_y, max_x = stdscr.getmaxyx()
    root_window = stdscr.derwin(max_y, max_x, 0, 0)

    root_window.box()

    return root_window


def format_data_hex(data, data_old):
    """Convert the bytes array to an hex representation."""
    dif = []

    # Bytes are separated by spaces.
    a = " ".join("%02X" % byte for byte in data)
    return a, dif


def format_data_ascii(data):
    """Try to make an ASCII representation of the bytes.

    Non printable characters are replaced by '?' except null character which
    is replaced by '.'.
    """
    msg_str = ""
    for byte in data:
        char = chr(byte)
        if char == "\0":
            msg_str = msg_str + "."
        elif ord(char) < 32 or ord(char) > 126:
            msg_str = msg_str + "?"
        else:
            msg_str = msg_str + char
    return msg_str


def main(stdscr, reading_thread):
    """Main function displaying the UI."""
    # Don't print typed character
    curses.noecho()
    curses.cbreak()
    curses.curs_set(0)  # set cursor state to invisible
    curses.start_color()
    curses.initscr()
    curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
    # curses.init_pair(1, 1, 0) # Turquoise Blue

    # Date_DOC = datetime.now()
    # Date_DOC = datetime.timestamp(Date_DOC)

    # Set getch() to non-blocking
    stdscr.nodelay(True)

    win = init_window(stdscr)
    global msg_old
    global Date_DOC
    global frame_ID
    global can_messages
    global Appereances
    while True:

        # should_redraw is set by the serial thread when new data is available
        if should_redraw.wait(
            timeout=0.5
        ):  # Timeout needed in order to react to user input
            max_y, max_x = win.getmaxyx()
            max_y = max_y
            column_width = 50
            id_column_start = 2
            bytes_column_start = 13
            text_column_start = 38

            # Compute row/column counts according to
            # the window size and borders
            row_start = 3
            lines_per_column = max_y - (1 + row_start) - 5
            num_columns = (max_x - 2) // column_width

            # Setting up column headers
            for i in range(0, num_columns):
                win.addstr(1, id_column_start + i * column_width, "ID")
                win.addstr(1, bytes_column_start + i * column_width, "Bytes")
                # win.addstr(1, text_column_start + i * column_width, 'Text')
                win.addstr(
                    1, text_column_start + i * column_width, "Ocurrences"
                )

            win.addstr(3, id_column_start, "Press 'q' to quit")

            row = (
                row_start + 2
            )  # The first column starts a bit lower to make space for
            # the 'press q to quit message'
            current_column = 0

            # Make sure we don't read the can_messages dict while it's being
            # written to in the reading thread
            with can_messages_lock:
                d = OrderedDict(
                    sorted(
                        Appereances.items(), key=itemgetter(1), reverse=True
                    )
                )
                # for frame_id in sorted(can_messages.keys()):
                for frame_id in d.keys():
                    if frame_id not in can_messages:
                        continue

                    msg = can_messages[frame_id]

                    # if (
                    #     frame_id in msg_len
                    #     and abs(len(msg) - msg_len[frame_id]) > 2
                    # ):
                    #  continue
                    # else:
                    #  msg_len[frame_id] = len(msg)

                    msg_bytes, change = format_data_hex(msg, msg_old)

                    # msg_str = format_data_ascii(msg)

                    # print frame ID in decimal and hex
                    win.addstr(
                        row,
                        id_column_start + current_column * column_width,
                        "          ",
                    )
                    win.addstr(
                        row,
                        id_column_start + current_column * column_width,
                        f"{frame_id:10x}",
                    )
                    # win.addstr(
                    #     row,
                    #     id_column_start + current_column * column_width,
                    #     '%X' % frame_id, curses.color_pair(1),
                    # )

                    # print frame bytes NOW COLORED WHILE CHANGING
                    # win.addstr(
                    #     row,
                    #     bytes_column_start + current_column * column_width,
                    #     msg_bytes.ljust(23)
                    # )
                    if frame_id not in msg_old:
                        win.addstr(
                            row,
                            bytes_column_start + current_column * column_width,
                            msg_bytes,
                        )
                    else:
                        win.addstr(
                            row,
                            bytes_column_start + current_column * column_width,
                            " " * 24,
                            curses.color_pair(1),
                        )
                        for i in range(min(len(msg), len(msg_old[frame_id]))):
                            if int(msg[i]) != int(msg_old[frame_id][i]):
                                win.addstr(
                                    row,
                                    bytes_column_start
                                    + current_column * column_width
                                    + i * 3,
                                    msg_bytes.split(" ")[i],
                                    curses.color_pair(2),
                                )
                            else:
                                win.addstr(
                                    row,
                                    bytes_column_start
                                    + current_column * column_width
                                    + i * 3,
                                    msg_bytes.split(" ")[i],
                                    curses.color_pair(1),
                                )

                    # print frame text NOW OCURRENCES
                    # win.addstr(
                    #     row,
                    #     text_column_start + current_column * column_width,
                    #     msg_str.ljust(8)
                    # )
                    if frame_id in Appereances:
                        win.addstr(
                            row,
                            text_column_start + current_column * column_width,
                            " " * 8,
                        )
                        win.addstr(
                            row,
                            text_column_start + current_column * column_width,
                            str(Appereances[frame_id]),
                        )

                    row = row + 1

                    if row >= lines_per_column + row_start:
                        # column full, switch to the next one
                        row = row_start
                        current_column = current_column + 1

                        if current_column >= num_columns:
                            break
                    NOW = datetime.now()
                    TIMESTAMP = datetime.timestamp(NOW)
                    win.addstr(
                        max_y - 2,
                        id_column_start,
                        "Timestamp:" + str(TIMESTAMP),
                    )
                    win.addstr(
                        max_y - 2,
                        max_x - 40,
                        "Message Amount:"
                        + str(sum(Appereances.values()))
                        + " "
                        + str(TOTAL),
                    )
                    msg_old[frame_id] = msg

            win.refresh()

            should_redraw.clear()

        c = stdscr.getch()
        if c == ord("q") or not reading_thread.is_alive():
            break
        elif c == curses.KEY_RESIZE:
            win = init_window(stdscr)
            should_redraw.set()


def parse_ints(string_list):
    int_set = set()
    for line in string_list:
        try:
            int_set.add(int(line, 0))
        except ValueError:
            continue
    return int_set


def run():
    parser = argparse.ArgumentParser(
        description="Process CAN data from a serial device or from a file."
    )
    parser.add_argument("serial_device", type=str, nargs="?")
    parser.add_argument(
        "baud_rate",
        type=int,
        default=115200,
        nargs="?",
        help="Serial baud rate in bps (default: 115200)",
    )
    parser.add_argument(
        "--bin-mode",
        metavar="BINARY_SERIAL_MODE",
        help="Binary Serial Mode",
        action="store_true",
    )
    parser.add_argument(
        "-f",
        "--candump-file",
        metavar="CANDUMP_FILE",
        help="File (of 'candump' format) to read from",
    )
    parser.add_argument(
        "-s",
        "--candump-speed",
        type=float,
        metavar="CANDUMP_SPEED",
        help="Speed scale of file read",
    )

    parser.add_argument(
        "--blacklist",
        "-b",
        nargs="+",
        metavar="BLACKLIST",
        help="Ids that must be ignored",
    )
    parser.add_argument(
        "--blacklist-file",
        "-bf",
        metavar="BLACKLIST_FILE",
        help="File containing ids that must be ignored",
    )
    parser.add_argument(
        "-c",
        "--can-interface",
        type=str,
        metavar="CAN_INTERFACE",
        help="Can Interface",
    )

    args = parser.parse_args()

    # checks arguments
    if (
        not args.serial_device
        and not args.candump_file
        and not args.can_interface
    ):
        print("Please specify serial device or file name or can interface")
        print()
        parser.print_help()
        return
    if args.serial_device and args.candump_file:
        print("You cannot specify a serial device AND a file name")
        print()
        parser.print_help()
        return
    if args.serial_device and args.can_interface:
        print("You cannot specify a serial device AND a can interface")
        print()
        parser.print_help()
        return
    if args.candump_file and args.can_interface:
        print("You cannot specify a file name AND a can interface")
        print()
        parser.print_help()
        return

    # --blacklist-file prevails over --blacklist
    if args.blacklist_file:
        with open(args.blacklist_file) as f_obj:
            blacklist = parse_ints(f_obj)
    elif args.blacklist:
        blacklist = parse_ints(args.blacklist)
    else:
        blacklist = set()

    if args.serial_device:
        if args.bin_mode:
            source_handler = SerialBinHandler(
                args.serial_device, baudrate=args.baud_rate
            )
        else:
            source_handler = SerialHandler(
                args.serial_device, baudrate=args.baud_rate
            )

    elif args.candump_file:
        source_handler = CandumpHandler(args.candump_file, args.candump_speed)
    elif args.can_interface:
        source_handler = CanHandler(args.can_interface)

    reading_thread = None

    try:
        # If reading from a serial device, it will be opened with
        # timeout=0 (non-blocking read())
        source_handler.open()

        # Start the reading background thread
        reading_thread = threading.Thread(
            target=reading_loop,
            args=(
                source_handler,
                blacklist,
            ),
        )
        reading_thread.start()

        # Make sure to draw the UI the first time even if no data has been read
        should_redraw.set()

        # Start the main loop
        curses.wrapper(main, reading_thread)
    finally:
        # Cleanly stop reading thread before exiting
        if reading_thread:
            stop_reading.set()

            if source_handler:
                source_handler.close()

            reading_thread.join()

            # If the thread returned an exception, print it
            if thread_exception:
                traceback.print_exception(*thread_exception)
                sys.stderr.flush()


if __name__ == "__main__":
    run()
