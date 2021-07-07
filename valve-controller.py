#!/usr/bin/python -u

import json
import sys
import threading
import time
from pathlib import Path

import serial
import yaml
from influxdb import InfluxDBClient, SeriesHelper

import ncd.ncd_industrial_relay as ncd

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
just_init = False
manual_step = None

print("Starting...")


def die(msg):
    print(f"Error: {msg}")
    sys.exit(1)

if len(sys.argv) > 1:
    config_file = sys.argv[1]
else:
    config_file = "config.yml"

if len(sys.argv) > 2:
    if "init" == sys.argv[2]:
        print("Just reset to init state and quit")
        just_init = True
    elif "manual" == sys.argv[2]:
        manual_step = sys.argv[3]

config_path = Path(config_file)

if not config_path.is_file():
    die(f"Couldn't not find configuration file: {config_file}")

cfg = yaml.safe_load(config_path.read_text())

print(f"Loaded config from {config_file}")

if "states_file" in cfg:
    states_file = Path(cfg["states_file"])
    if states_file.exists():
        states = yaml.safe_load(states_file.read_text())
else:
    states_file = None

if "step_file" in cfg:
    step_file = Path(cfg["step_file"])
else:
    step_file = None

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


else:
    client = None
    print("InfluxDB connection disabled")


def peak2influxdb():
    while True:
        with serial.Serial("/dev/analyzer", 9600) as ser:
            try:
                values = ser.read_until(b"\x03").decode("utf-8").split(",")
                measurement_date = values[1]
                measurement_time = values[2]
                h2 = values[6]
                co = values[9]
                print(f"H2: {h2}, CO: {co}")

                if cfg["influxdb"]["enabled"]:
                    BasicSeriesHelper(
                        node="sws-1",
                        h2=int(h2),
                        co=int(co),
                    )

                states_string = ",".join(f"{k},{v}" for k, v in states.items())

                with open(cfg["data_file"], "a") as data_file:
                    data_file.write(
                        f"{measurement_date},{measurement_time},{h2},{co},{states_string}\n"
                    )

            except Exception as e:
                print(e)


if cfg.get("enable_peak2influxdb"):
    print("Start peak2influxdb thread")
    threading.Thread(target=peak2influxdb).start()


def init_serial(connection):
    connection["serial"] = serial.Serial(
        connection["port"], baudrate=connection["baud"], bytesize=8, stopbits=1
    )


def init_sv(connection):
    init_serial(connection)
    connection["controller"] = ncd.Relay_Controller(connection["serial"])


def init_gpio(connection):
    pass


# cfg_gpio = cfg["devices"].get("gpio", {})
# for port, state in cfg_gpio.get("init", {}).items():
#    gpio = cfg_gpio["mapping"][port]
#    if Path(f"/sys/class/gpio/gpio{gpio}").is_dir():
#        Path("/sys/class/gpio/unexport").write_text(str(gpio))

#    if state:
#        Path("/sys/class/gpio/export").write_text(str(gpio))
#        Path(f"/sys/class/gpio/gpio{gpio}/direction").write_text("out")


def set_gpio(connection, port: int, state):
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

    if states_file:
        states_file.write_text(json.dumps(states, sort_keys=True, indent=4))

    if client:
        try:
            client.write_points(
                [
                    {
                        "measurement": "valve_state",
                        "fields": {f"{device}_{port}": int(state)},
                    }
                ]
            )
        except Exception as e:
            print(e)


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

    # don't set init state if step file exists
    if step_file.exists() or manual_step:
        print("Skip init state since step file exists or maual step")
    else:
        for port, state in connection["init"].items():
            print(f"{name}: Set port {port} to state {state}")
            set_state(name, port, state)

    time.sleep(0.1)

if just_init:
    sys.exit(0)

if manual_step:
    device, port, state = manual_step.strip().split(",")
    set_state(device, int(port), state)
    sys.exit(0)

# make sure the sequence is sorted correctly
cfg["sequence"].sort()

# find total sequence length and step count
length_minutes = cfg["sequence"][-1].split(",")[0]
step_count = len(cfg["sequence"])

print(f"Total sequence length is {length_minutes} minutes")

time_passed = 0.0
sequence_step = 0
if step_file.exists():
    sequence_step, time_passed = step_file.read_text().strip().split(",")
    sequence_step = int(sequence_step)
    time_passed = float(time_passed)
    if sequence_step > step_count:
        die(
            "Read sequence step {sequence_step} is higher than total step count {step_count}"
        )

print("Start sequence")
while True:
    for number, step in enumerate(cfg["sequence"][sequence_step:]):
        delay, device, port, state = step.strip().split(",")
        time_to_wait = float(delay) * 60 - time_passed
        print(
            f"[{number + sequence_step + 1}/{step_count}]: "
            f"Set {device}#{port} to {state} in {time_to_wait} seconds"
        )

        if cfg.get("manual_mode"):
            input("Press enter to continue (manual mode enalbed)")
        else:
            time.sleep(time_to_wait)

        time_passed += time_to_wait
        set_state(device, int(port), state)

        if step_file:
            step_file.write_text(f"{number + sequence_step},{time_passed}")

    if not cfg.get("sequence_loop", True):
        print("No repeat of sequence since sequence_loop is disabled")
        break

    sequence_step = 0
    time_passed = 0.0
