"""python -m opencat_gemma "walk forward then sit"  — request -> Gemma -> allowlist -> robot."""
import argparse
import getpass
import shlex
import sys
import time

from .ble import MultipleRobotsError, find_ble_robot
from .contract import ROBOTS, load
from .gemma import MODEL, ask, parse
from .links import SerialLink, WsLink, detect_ws_robot, find_robot, open_serial, rename_robot, robot_name, wifi_ip, wifi_setup
from .runner import STOP, TURN_SECONDS, plan, run

# How to run this tool again, for hints: the interpreter actually running (it has our packages), quoted for the shell.
RUN = f"{shlex.quote(sys.executable)} -m opencat_gemma"


def handle(contract, text, link, args):
    """One request: Gemma -> check -> robot (or just print, with --dry-run). Returns an error message, or None."""
    t = time.time()
    out = ask(contract, text, model=args.model)
    commands, err = parse(contract, out)
    print(f"Gemma ({time.time() - t:.1f}s): {text!r} -> {out}")
    if err:
        return f"Rejected: {err}"
    if args.dry_run:
        shown = [c + (f" (then {STOP} after {args.turn_seconds}s)" if timed else "") for c, _, timed in plan(contract, commands)]
        print("would send: " + (", ".join(shown) or "nothing"))
        return None
    try:
        run(contract, commands, link, turn_seconds=args.turn_seconds)
    except ValueError as e:  # raised before anything is sent, e.g. XO over Bluetooth
        return f"Refused: {e}"
    return None


def chat(contract, robot, link, args):
    print(f"Chatting with {robot}. Ctrl+C stops a move; Ctrl+D (or Ctrl+C here) quits.")
    while True:
        try:
            text = input(f"{robot.capitalize()}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not text:
            continue
        try:
            err = handle(contract, text, link, args)
        except KeyboardInterrupt:
            err = "interrupted"  # run() already reported whether the STOP reached the robot
        except (TimeoutError, RuntimeError, OSError) as e:
            err = f"error: {e}"
        if err:
            print(f"  {err}")


def open_link(args):
    """USB (auto-detect or --port) or Bluetooth link for the setup commands."""
    if args.port:
        return SerialLink(open_serial(args.port))
    if args.bluetooth:
        return (find_ble_robot(name=args.name) if args.name else find_ble_robot())[0]
    return find_robot()[0]


def main(argv=None):
    try:
        _main(argv)
    except MultipleRobotsError as e:
        sys.exit(str(e))


def _main(argv=None):
    p = argparse.ArgumentParser(prog="python -m opencat_gemma", description=__doc__)
    p.add_argument("request", nargs="?", help="omit to chat interactively")
    p.add_argument("--robot", choices=ROBOTS, help="default: detected over USB/Bluetooth/--ws; bittle for --dry-run")
    p.add_argument("--port", help="USB serial device (default: auto-detect)")
    p.add_argument("--bluetooth", action="store_true", help="find the robot over Bluetooth LE (no pairing needed)")
    p.add_argument("--name", metavar="NAME", help="with --bluetooth: the robot's Bluetooth name, with or without _BLE, e.g. Quaddle03")
    p.add_argument("--robot-name", nargs="?", const=True, metavar="NEW",
                   help="print the robot's Bluetooth name (over USB, --port or --bluetooth); with NEW, rename it")
    p.add_argument("--wifi-ip", action="store_true", help="print the IP of a robot already on Wi-Fi (over USB or --bluetooth)")
    p.add_argument("--wifi-setup", action="store_true", help="join the robot to Wi-Fi (over USB or --bluetooth), then print its ws:// URL")
    p.add_argument("--ws", metavar="URL", help="use WebSocket, e.g. ws://192.168.1.50:81")
    p.add_argument("--model", default=MODEL, help="Ollama model (default: %(default)s)")
    p.add_argument("--turn-seconds", type=float, default=TURN_SECONDS, help="how long turns run (default: %(default)s)")
    p.add_argument("--dry-run", action="store_true", help="show what would be sent; don't touch the robot")
    args = p.parse_args(argv)
    if args.name and not args.bluetooth:
        p.error("--name selects a robot over Bluetooth; add --bluetooth")

    if args.robot_name:
        link = open_link(args)
        try:
            if args.robot_name is True:
                name = robot_name(link)
            else:
                rename_robot(link, args.robot_name)
        finally:
            link.close()
        if args.robot_name is True:
            print(f"Your robot's Bluetooth name: {name}_BLE")
            print(f"Connect with: {RUN} --bluetooth --name {name}")
        else:
            print(f"Renamed to {args.robot_name}. Switch the robot off and on, then connect with --bluetooth --name {args.robot_name}")
        return

    if args.wifi_ip:
        link = open_link(args)
        try:
            ip = wifi_ip(link)
        finally:
            link.close()
        if ip is None:
            sys.exit("The robot is not on Wi-Fi yet. Run --wifi-setup first.")
        print(f"Robot IP address: {ip}")
        print(f"Connect with: {RUN} --ws ws://{ip}:81")
        return

    if args.wifi_setup:
        link = open_link(args)
        try:
            print("The robot can only join 2.4 GHz Wi-Fi (not 5 GHz).")
            ssid = input("Wi-Fi name (SSID): ").strip()
            password = getpass.getpass("Wi-Fi password (not shown): ")
            print("Joining Wi-Fi; this can take up to ~40 s. On success the robot reboots to start its web server.")
            ip = wifi_setup(link, ssid, password)
        finally:
            link.close()
        print("Robot is on Wi-Fi.")
        print(f"Robot IP address: {ip}")
        print(f"Connect with: {RUN} --ws ws://{ip}:81")
        return

    link = None
    if args.dry_run or args.port or (args.ws and args.robot):
        robot = args.robot or "bittle"
    elif args.ws:
        robot = None  # detected below, once the WebSocket is open
    else:
        if args.bluetooth:
            link, robot = find_ble_robot(name=args.name) if args.name else find_ble_robot()
        else:
            link, robot = find_robot()
    try:
        if not args.dry_run and link is None:
            link = WsLink(args.ws) if args.ws else SerialLink(open_serial(args.port))
        if robot is None:
            robot = detect_ws_robot(link)
            if robot is None:
                robot = "bittle"
                print("Warning: the robot did not report its model over Wi-Fi; assuming bittle (use --robot to set it).")
        contract = load(robot)
        if args.request:
            err = handle(contract, args.request, link, args)
            if err:
                sys.exit(err)
        else:
            chat(contract, robot, link, args)
    finally:
        if link:
            link.close()


if __name__ == "__main__":
    main()
