import sys
import time
from pathlib import Path

import ncd.ncd_industrial_relay as ncd
import serial
import yaml
from gpiozero import OutputDevice
from influxdb import InfluxDBClient


state_mapping = {
    0: 0,
    1: 1,
    "0": 0,
    "1": 1,
    "A": 0,
    "B": 1,
    "on": 0,
    "off": 1,
}

states = {}


def die(msg):
    print(f"Error: {msg}")
    sys.exit(1)


if len(sys.argv) > 1:
    config_file = sys.argv[1]
else:
    config_file = "config.yml"

config_path = Path(config_file)

if not config_path.is_file():
    die(f"Couldn't not find configuration file: {config_file}")

cfg = yaml.safe_load(config_path.read_text())

if cfg["influxdb"]["enabled"]:
    print("Connecting to InfluxDB")
    client = InfluxDBClient(
        cfg["influxdb"]["address"],
        cfg["influxdb"]["port"],
        cfg["influxdb"]["username"],
        cfg["influxdb"]["password"],
        cfg["influxdb"]["database"],
    )
else:
    print("InfluxDB connection disabled")


def init_serial(connection):
    connection["serial"] = serial.Serial(
        connection["port"], baudrate=connection["baud"], bytesize=8, stopbits=1
    )


def init_sv(connection):
    init_serial(connection)
    connection["controller"] = ncd.Relay_Controller(connection["serial"])


def init_gpio(connection):
    cfg_gpio = cfg["devices"].get("gpio", {})
    cfg_gpio["ports"] = {}
    for port, state in cfg_gpio.get("init", {}).items():
        if state:
            cfg_gpio["ports"][port] = OutputDevice(cfg_gpio["mapping"][port])


def set_gpio(connection, port: int, state):
    print(f"{port}: {state}")
    if state == 1:
        if port not in connection["ports"]:
            connection["ports"][port] = OutputDevice(connection["mapping"][port])
    elif state == 0:
        if port in connection["ports"]:
            connection["ports"].pop(port).close()
    else:
        die(f"GPIO only support state 0 (off) and 1 (on), got {state}")


def set_sv(connection, port: int, state):
    port = connection["mapping"][port]
    if state == 1:
        connection["controller"].turn_on_relay_by_index(port)
    elif state == 0:
        connection["controller"].turn_off_relay_by_index(port)
    else:
        die(f"SV only support state 0 (off) and 1 (on), got {state}")


def set_mpv(connection, state):
    connection["serial"].write(bytes(f"GO{state}\r", "utf-8"))


def set_state(device: str, port: int, state):
    state = state_mapping.get(state, state)
    states[f"{device}_{port}"] = state


    if device not in cfg["devices"].keys():
        die(f"Unknown device: {device}")

    if device.startswith("sv"):
        set_sv(cfg["devices"][device], port, state)
    elif device.startswith("mpv"):
        set_mpv(cfg["devices"][device], state)
    elif device.startswith("gpio"):
        set_gpio(cfg["devices"][device], port, state)

    if cfg["influxdb"]["enabled"]:
        client.write_points(
            [{"measurement": "valve_state", "fields": {f"{device}_{port}": int(state)}}]
        )


for name, connection in cfg["devices"].items():
    if not connection["enabled"]:
        print(f"Skipping device {name} (disabled)")
        continue

    print(f"Setup device {name}")
    if name.startswith("gpio"):
        init_gpio(connection)
    elif name.startswith("sv"):
        init_sv(connection)
    elif name.startswith("mpv"):
        init_serial(connection)
    else:
        die(f"Unkown device type: {name}. Pleaes use 'gpio', 'sv' or 'mpv'")

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
        delay, device, port, state = step.strip().split(",")
        time_to_wait = float(delay) * 60 - time_passed
        print(
            f"[{number}/{step_count}]: "
            f"Set {device}#{port} to {state} in {time_to_wait} seconds"
        )
        time.sleep(time_to_wait)
        time_passed += time_to_wait
        set_state(device, int(port), state)
