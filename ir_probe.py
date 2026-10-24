"""Troubleshooting probe for the double IR distance sensor (pins 34/35). Reads only; with --xd it also
turns the firmware's IR module on (robot sits and head-tracks) and off again at the end.

  .venv/bin/python ir_probe.py 10 [--xd]   stream readings for 10 s
  .venv/bin/python ir_probe.py --guided [--no-xd]   step through set distances (sends XD unless --no-xd), then summary
"""
import statistics
import sys
import time

import serial

PORT = "/dev/cu.wchusbserial5A4B0722411"  # macOS example; change for your machine
STEPS = [("no ball (keep it 60 cm+ away or hidden)", None), ("30 cm", 30), ("20 cm", 20),
         ("10 cm", 10), ("5 cm", 5), ("no ball again", None)]
SETTLE_S, SAMPLE_S = 4, 4

ser = serial.Serial(PORT, 115200, timeout=0.05)
time.sleep(0.5)
ser.reset_input_buffer()


def read(pin):
    ser.write(bytes([82, 97, pin, 126]))
    t, buf = time.monotonic(), b""
    while time.monotonic() - t < 1.5 and not buf.rstrip().endswith(b"R"):
        buf += ser.read(256)
    s = buf.decode("ISO-8859-1")
    return int(s.split("=")[1].split()[0]) if "=" in s else None


def module(on):
    ser.write(b"XD\n" if on else b"Xd\n")
    time.sleep(3 if on else 1)
    ser.reset_input_buffer()
    print(f"Sent {'XD (sensor module on)' if on else 'Xd (sensor module off)'}", flush=True)


def guided(xd=True):
    if xd:
        module(True)
    else:
        print("Sensor module NOT turned on (--no-xd)", flush=True)
    print("Hold the ball straight in front of Bittle's face (the sensor), measured from the sensor.\n"
          "Keep it STILL at each distance. Bittle's head may turn to follow it; that's fine.\n", flush=True)
    results = []
    for label, _ in STEPS:
        print(f">>> Move the ball to: {label}", flush=True)
        for n in range(SETTLE_S, 0, -1):
            print(f"    starting in {n}...", flush=True)
            time.sleep(1)
        a, b = [], []
        end = time.monotonic() + SAMPLE_S
        while time.monotonic() < end:
            a.append(read(34)), b.append(read(35))
        a, b = [x for x in a if x is not None], [x for x in b if x is not None]
        row = (label, len(a), statistics.median(a), min(a), max(a), statistics.median(b), min(b), max(b))
        results.append(row)
        print(f"    done: pin34 median {row[2]:.0f} (range {row[3]}-{row[4]}), "
              f"pin35 median {row[5]:.0f} (range {row[6]}-{row[7]})\n", flush=True)
    if xd:
        module(False)
    print("\nSUMMARY (raw ADC, 0-4095)")
    print(f"{'ball position':42} {'n':>3}  {'pin34 med':>9} {'min-max':>11}  {'pin35 med':>9} {'min-max':>11}")
    for label, n, ma, lo_a, hi_a, mb, lo_b, hi_b in results:
        print(f"{label:42} {n:>3}  {ma:>9.0f} {f'{lo_a}-{hi_a}':>11}  {mb:>9.0f} {f'{lo_b}-{hi_b}':>11}")


def stream(secs, xd):
    if xd:
        module(True)
    start = time.monotonic()
    while True:
        t = time.monotonic() - start
        print(f"{t:5.1f}s  pin34={read(34)}  pin35={read(35)}", flush=True)
        if t > secs:
            break
        time.sleep(0.3)
    if xd:
        module(False)


try:
    if "--guided" in sys.argv:
        guided(xd="--no-xd" not in sys.argv)
    else:
        stream(float(next((a for a in sys.argv[1:] if not a.startswith("--")), 10)), "--xd" in sys.argv)
finally:
    ser.close()
