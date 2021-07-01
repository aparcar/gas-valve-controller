#!/usr/bin/env python

import sys
import time
from pathlib import Path

import ncd.ncd_industrial_relay as ncd
import serial
import yaml
from influxdb import InfluxDBClient, SeriesHelper
import json
import threading


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

print("Starting...")


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

print(f"Loaded config from {config_file}")

if "state_file" in cfg:
    state_file = Path(cfg["state_file"])

if cfg["influxdb"]["enabled"]:
    print("Connecting to InfluxDB")
    client = InfluxDBClient(
        cfg["influxdb"]["address"],
        cfg["influxdb"]["port"],
        cfg["influxdb"]["username"],
        cfg["influxdb"]["password"],
        cfg["influxdb"]["database"],
    )

    class BasicSeriesHelper(SeriesHelper):
        class Meta:
            client = client
            series_name = "events.stats.basic"
            fields = ["h2", "co"]
            tags = ["node"]
            bulk_size = 1
            autocommit = True

    def peak2influxdb():
        while True:
            with serial.Serial("/dev/ttyUSB0", 9600) as ser:
                try:
                    values = ser.read_until(b"\x03").decode("utf-8").split(",")
                    h2 = values[6]
                    co = values[9]
                    print(f"H2: {h2}, CO: {co}")

                    BasicSeriesHelper(
                        node="sws-1",
                        h2=int(h2),
                        co=int(co),
                    )
                except Exception as e:
                    print(e)

    print("Start peak2influxdb thread")
    threading.Thread(target=peak2influxdb).start()
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
    for port, state in cfg_gpio.get("init", {}).items():
        gpio = cfg_gpio["mapping"][port]
        print(gpio)
        if Path(f"/sys/class/gpio/gpio{gpio}").is_dir():
            Path("/sys/class/gpio/unexport").write_text(str(gpio))

        if state:
            Path("/sys/class/gpio/export").write_text(str(gpio))
            Path(f"/sys/class/gpio/gpio{gpio}/direction").write_text("out")


def set_gpio(connection, port: int, state):
    print(f"{port}: {state}")
    gpio = connection["mapping"][port]
    if state == 1:
        if not Path(f"/sys/class/gpio/gpio{gpio}/").is_dir():
            Path("/sys/class/gpio/export").write_text(str(gpio))

        Path(f"/sys/class/gpio/gpio{gpio}/direction").write_text("out")
    elif state == 0:
        if Path(f"/sys/class/gpio/gpio{gpio}/").is_dir():
            Path("/sys/class/gpio/unexport").write_text(str(gpio))
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

    if state_file:
        state_file.write_text(json.dumps(states, sort_keys=True, indent=4))

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


print("Enter infinite valve loop")
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
