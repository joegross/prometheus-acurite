#!/usr/bin/env python

import argparse
import json
import logging
import shlex
import subprocess
import time
from collections import defaultdict
from prometheus_client import Gauge, start_http_server

logger = logging.getLogger(__name__)

LISTEN_PORT = 8005
LOOP_SLEEP_TIME = 5
METRIC_TTL = 10 * 60
# CMD = 'ssh pivac "/usr/local/bin/rtl_433 -q -F json -C customary -R 40 -R 41"'
# CMD = 'ssh pivac "/usr/local/bin/rtl_433 -q -F json -C customary -R 40"'
# CMD = '/usr/local/bin/rtl_433 -q -F json -C customary -R 40'
CMD = '/usr/local/bin/rtl_433 -q -F json -C customary -R 40 -R 41'

MODEL_MAP = {
    'Acurite tower sensor': '40',
    'Acurite 986 Sensor': '41',
}


class sensor_server(object):
    def __init__(self, listen_port, sleep=LOOP_SLEEP_TIME, cmd=CMD):
        self.sleep = sleep
        self.last_seen = defaultdict(lambda: 0)
        start_http_server(listen_port)
        self.acurite_temp = Gauge(
            'acurite_temp', 'acurite temperature in DegF', ['id', 'model'])
        # self.acurite_temp = Gauge(
        #     'acurite_temp', 'acurite temperature in DegF').set_function(lambda: self.show_temp())
        self.acurite_hum = Gauge(
            'acurite_hum', 'acurite humidity in %RH', ['id', 'model'])
        self.acurite_battery_low = Gauge(
            'acurite_battery_low', 'acurite battery_low', ['id', 'model'])
        self.acurite_last_seen = Gauge(
            'acurite_last_seen', 'acurite last_seen', ['id', 'model'])
        self.process = subprocess.Popen(
            shlex.split(CMD), stdout=subprocess.PIPE)

    def expire_sensors(self):
        for sensor_id in list(self.last_seen.keys()):
            age = time.time() - self.last_seen[sensor_id]
            if age > METRIC_TTL:
                logging.info('removing stale sensor: %s age: %s',
                             sensor_id, age)
                self.acurite_temp.remove(sensor_id)
                self.acurite_hum.remove(sensor_id)
                self.acurite_battery_low.remove(sensor_id)
                self.acurite_last_seen.remove(sensor_id)
                del self.last_seen[sensor_id]

    def serve_forever(self):
        # TODO: Redo with poll() so we can expire the last sensor
        while True:
            data = json.loads(self.process.stdout.readline())
            # Acurite 986 Sensor uses "battery=OK" instead of "battery_low=0"
            if data.get('battery'):
                battery = data.get('battery')
                if battery == "OK":
                    data['battery_low'] = 0
                else:
                    data['battery_low'] = 1
            logging.debug(data)
            # print(self.metrics)

            sensor_id = data.get('id')
            model = MODEL_MAP.get(data.get('model'))
            self.acurite_temp.labels(id=sensor_id, model=model).set(
                data.get('temperature_F'))
            if data.get('humidity'):
                self.acurite_hum.labels(id=sensor_id, model=model).set(
                    data.get('humidity'))
            self.acurite_battery_low.labels(
                id=sensor_id, model=model).set(data.get('battery_low'))
            now = time.time()
            self.acurite_last_seen.labels(id=sensor_id, model=model).set(now)
            self.last_seen[sensor_id] = now
            self.expire_sensors()

        logging.debug("sleeping %s...", self.sleep)
        time.sleep(self.sleep)


def init_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(name)-18s %(levelname)-8s %(message)s'
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('-p', '--listen_port', type=int,
                        default=LISTEN_PORT, help='listen port')
    args = parser.parse_args()
    if args.verbose:
        init_logging(logging.DEBUG)
    else:
        init_logging(logging.INFO)
    sensor_server(args.listen_port).serve_forever()
