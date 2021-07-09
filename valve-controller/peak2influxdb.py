import json
import sys
import threading
import time
from pathlib import Path

import serial
import yaml
from influxdb import InfluxDBClient, SeriesHelper


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

states_file = Path(cfg["states_file"])

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


print("Start peak2influxdb")

while True:
    with serial.Serial("/dev/analyzer", 9600) as ser:
        if states_file.exists():
            states = yaml.safe_load(states_file.read_text())
        else:
            states = {}

        try:
            values = ser.read_until(b"\x03").decode("utf-8").split(",")
            measurement_date = values[1]
            measurement_time = values[2]
            h2 = values[6]
            co = values[9]
            print(f"H2: {h2}, CO: {co}")

            if cfg["influxdb"]["enabled"]:
                BasicSeriesHelper(node="sws-1", h2=int(h2), co=int(co), **states)

            states_string = ",".join(f"{k},{v}" for k, v in states.items())

            with open(cfg["data_file"], "a") as data_file:
                data_file.write(
                    f"{measurement_date},{measurement_time},{h2},{co},{states_string}\n"
                )

        except Exception as e:
            print(e)
