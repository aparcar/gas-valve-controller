# import the pyserial module
import serial
import ncd.ncd_industrial_relay as ncd
import time
import yaml
from pathlib import Path
import sys


def die(msg):
    print(f"Error: {msg}")
    quit(1)


if len(sys.argv) > 1:
    config_file = sys.argv[1]
else:
    config_file = "config.yml"

config_path = Path(config_file)

if not config_path.is_file():
    die(f"Couldn't not find configuration file: {config_file}")

cfg = yaml.safe_load(config_path.read_text())


def set_sv(connection, port: int, state: int):
    if state == 1:
        connection["controller"].turn_on_relay_by_index(port)
    elif state == 0:
        connection["controller"].turn_off_relay_by_index(port)
    else:
        die(f"SV only support state 0 (off) and 1 (on), got {state}")


def set_mpv(connection, state: int):
    connection["serial"].write(bytes(f"GO{state}\r", "utf-8"))


def set_state(device: str, port: int, state: int):
    if device not in cfg["devices"].keys():
        die(f"Unknown device: {device}")

    if device.startswith("sv"):
        set_sv(cfg["devices"][device], port, state)
    elif device.startswith("mpv"):
        set_mpv(cfg["devices"][device], state)
    else:
        die(f"Device name must start with 'sv' or 'mpv': {device}")


for name, connection in cfg["devices"].items():
    print(f"Setup device {name}")
    connection["serial"] = serial.Serial(
        connection["port"], baudrate=connection["baud"], bytesize=8, stopbits=1
    )
    if name.startswith("sv"):
        connection["controller"] = ncd.Relay_Controller(
            connection["serial"]
        )

    for port, state in connection["init"].items():
        print(f"{name}: Set port {port} to state {state}")
        set_state(name, port, state)

    time.sleep(1)

cfg["sequence"].sort()

length_minutes = cfg["sequence"][-1].split(",")[0]
step_count = len(cfg["sequence"])

print(f"Total sequence length is {length_minutes} minutes")

while True:
    print("Start sequence from beginning")
    time_passed = 0.0
    for number, step in enumerate(cfg["sequence"]):
        delay, device, port, state = step.split(",")
        time_to_wait = float(delay) * 60 - time_passed
        print(
            f"[{number}/{step_count}]: Set {device}#{port} to {state} in {time_to_wait} seconds"
        )
        time.sleep(time_to_wait)
        time_passed += time_to_wait
        set_state(device, int(port), int(state))
