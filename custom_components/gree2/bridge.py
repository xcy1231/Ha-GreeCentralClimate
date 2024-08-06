import threading
import socket
import json
import logging
import time

from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import (
    async_track_time_interval, async_call_later)
from .ciper import (CIPER_KEY, ciperEncrypt, ciperDecrypt)

from .device import Gree2Climate

_LOGGER = logging.getLogger(__name__)

BROADCAST_ADDRESS = '<broadcast>'
DEFAULT_PORT = 7000
RSET_COUNT = 4


class GreeBridge(object):
    def __init__(self, hass, host, scan_interval, temp_sensor, temp_step, async_add_devices):
        self.hass = hass
        self.async_add_devices = async_add_devices
        self.scan_interval = scan_interval
        self.temp_sensor = temp_sensor
        self.temp_step = temp_step
        self.conf_host = host
        self.host = host
        self.device_socket = None
        self.fake_socket = None
        self.reset_count = 0
        self.fc_unready = True

        self.key = CIPER_KEY
        self.mac = None
        self.name = None

        self.subCnt = None
        self.devMap = {}

        self.start_device_listen()
        self.start_fake_listen()

        key = 'gree2.devices'
        if host != BROADCAST_ADDRESS:
            key = key + '.' + host
        self.store = Store(hass, 1, key)

        async_call_later(self.hass, 0, self.store_load)
        async_track_time_interval(
            self.hass, self.start_track, self.scan_interval)

    async def store_load(self, now):
        dic = await self.store.async_load()
        if dic is not None:
            self.mac = dic['mac']
            self.key = dic['key']
            self.host = dic['host']
            for item_mac in dic['sub']:
                self.devMap[item_mac] = Gree2Climate(self.hass, 'GREE Climate_' +
                                                     item_mac, item_mac, self, self.temp_sensor.get(item_mac), self.temp_step)
            self.async_add_devices(self.devMap.values())
            _LOGGER.debug('Load stored dic: {} path:{} devMap:{}'.format(
                dic, self.store.path, self.devMap))
        else:
            self.scan_broadcast()

    def start_track(self, now):
        if len(self.devMap) > 0:
            self.get_all_state(None)
        else:
            self.scan_broadcast()

    def start_device_listen(self):
        thread = threading.Thread(target=self.device_listen, args=())
        thread.daemon = True
        thread.start()

    def device_listen(self):
        while True:
            if self.device_socket is None:
                try:
                    self.device_socket = socket.socket(
                        socket.AF_INET, socket.SOCK_DGRAM)
                    self.device_socket.setsockopt(
                        socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    self.device_socket.settimeout(30)
                except:
                    _LOGGER.debug('creat device socket error')
                    self.device_socket.close()
                    self.device_socket = None
                    time.sleep(0.5)
                    continue
            try:
                data, address = self.device_socket.recvfrom(65535)
            except Exception as e:
                _LOGGER.debug(
                    'Device socket received error: {}'.format(str(e)))
                if self.fake_socket is None:
                    self.reset()
                continue
            (host, _) = address
            self.host = host
            lines = data.splitlines()
            for message in lines:
                self.process(message)

    def start_fake_listen(self):
        thread = threading.Thread(target=self.fake_listen, args=())
        thread.daemon = True
        thread.start()

    def fake_listen(self):
        while True:
            if self.fake_socket is None:
                self.fc_unready = True
                fake_socket = None
                try:
                    fake_socket = socket.socket(
                        socket.AF_INET, socket.SOCK_STREAM)
                    fake_socket.settimeout(60)
                    fake_socket.connect(('dis.gree.com', 1812))
                except:
                    _LOGGER.debug('connect fake server error')
                    fake_socket.close()
                    fake_socket = None
                    time.sleep(60)
                    continue
                self.fake_socket = fake_socket
            try:
                self.fake_socket.settimeout(60)
                data, _ = self.fake_socket.recvfrom(65535)
            except (ConnectionResetError, BrokenPipeError) as e:
                _LOGGER.error('Fake socket received ConnectionResetError or BrokenPipeError: {}'.format(str(e)))
                self.fake_socket = None
                continue
            except Exception as e:
                _LOGGER.debug('Fake socket received error: {}'.format(str(e)))
                self.reset()
                continue
            self.fc_unready = False
            lines = data.splitlines()
            for message in lines:
                self.process(message)

    def reset(self):
        _LOGGER.debug(
            'Socket timeout reset count :{}'.format(self.reset_count))
        if self.reset_count < RSET_COUNT:
            self.reset_count = self.reset_count + 1
        else:
            self.scan_broadcast()

    def process(self, data):
        try:
            msg = json.loads(data)
            _LOGGER.info('  process data: {} msg: {}'.format(data, msg))
            cmd = msg['t']
            match cmd:
                case 'hb':
                    self.cmd_hb()
                case 'pack':
                    self.cmd_pack(msg['pack'])
                case 'dev':
                    self.cmd_dev(msg)
                case 'bindOk':
                    self.cmd_bind(msg)
                case 'subList':
                    self.cmd_sub(msg)
                case 'dat':
                    self.cmd_dat(msg)
                case 'res':
                    self.cmd_res(msg)
        except Exception as e:
            _LOGGER.info(
                '* Exception: {} on message {}'.format(e, str(data)))

    def scan_broadcast(self):
        _LOGGER.info('scan_broadcast')
        reqData = {"t": "scan"}
        self.key = CIPER_KEY
        _LOGGER.debug('device socket send data {} to {}'.format(
            reqData, self.conf_host))
        self.device_socket.sendto(json.dumps(reqData).encode(
            'utf-8'), (self.conf_host, DEFAULT_PORT))

    def cmd_hb(self):
        answer = {'t': 'hbok'}
        self.fake_socket.sendall(json.dumps(answer).encode())

    def cmd_pack(self, pack):
        self.reset_count = 0
        msg = ciperDecrypt(pack, self.key)
        self.process(msg)

    def cmd_dev(self, msg):
        self.mac = msg['mac']
        self.name = msg['name']
        self.subCnt = msg['subCnt']
        self.bind_device()

    def bind_device(self):
        _LOGGER.info('bind_device')
        message = {
            'mac': self.mac,
            't': 'bind',
            'uid': 0
        }
        self.socket_send(self.pack_message(message, 1))

    def cmd_bind(self, msg):
        self.key = msg['key']
        _LOGGER.info('cmd_bind ok: {}'.format(self.key))
        if len(self.devMap) > 0:
            self.get_all_state(None)
            self.store.async_delay_save(self.data_to_save, 0)
        else:
            self.get_subdevices()

    def get_subdevices(self, i=0):
        _LOGGER.info('get_subdevices')
        message = {
            't': "subDev",
            'mac': self.mac,
            'i': i,
        }
        self.socket_send(self.pack_message(message))

    def cmd_sub(self, msg):
        devList = msg['list']
        for item in devList:
            item_mac = item['mac']
            if not item_mac in self.devMap.keys():
                self.devMap[item_mac] = Gree2Climate(self.hass, 'GREE Climate_' +
                                                     item_mac, item_mac, self, self.temp_sensor.get(item_mac), self.temp_step)
        if len(self.devMap) < self.subCnt and msg['i'] < self.subCnt:
            self.get_subdevices(msg['i'] + 1)
        else:
            if len(self.devMap) == 0:
                self.stop_listen()
            else:
                self.store.async_delay_save(self.data_to_save, 0)
                self.async_add_devices(self.devMap.values())

    def data_to_save(self):
        return {
            'mac': self.mac,
            'host': self.host,
            'key': self.key,
            'sub': list(self.devMap.keys())
        }

    def cmd_dat(self, msg):
        self.devMap[msg['mac']].dealStatusPack(msg)

    def cmd_res(self, msg):
        self.devMap[msg['mac']].dealResPack(msg)

    def socket_send(self, reqData):
        _LOGGER.debug(
            'device socket send data {} to {}'.format(reqData, self.host))
        self.device_socket.sendto(json.dumps(reqData).encode(
            'utf-8'), (self.host, DEFAULT_PORT))

    def pack_message(self, message, i=0):
        pack = ciperEncrypt(message, self.key)
        return {
            'cid': 'app',
            't': 'pack',
            'uid': 0,
            'i': i,
            'pack': pack,
            'tcid': self.mac
        }

    def get_all_state(self, now):
        i = 0
        for climate in self.devMap.values():
            async_call_later(self.hass, i, climate.syncStatus)
            i = i + 2

    def sync_status(self, data):
        msg = self.pack_message(data)
        _LOGGER.debug('cmd send status data: {}'.format(data))
        if self.fake_socket is not None:
            _LOGGER.debug('cmd send status to fake server self.host: {}'.format(self.host))
            try:
                self.fake_socket.sendall((json.dumps({
                    't': 'pas',
                    'host': self.host,
                    'req': msg
                }) + '\n').encode('utf-8'))
            except BrokenPipeError as e:
                _LOGGER.error(
                    'Exception BrokenPipeError {} when send status to fake server'.format(e))
                self.fake_socket = None
            except Exception as e:
                _LOGGER.debug(
                    'Exception {} when send status to fake server'.format(e))
        if self.fc_unready == True and self.reset_count < RSET_COUNT:
            _LOGGER.debug('cmd send status directly')
            self.socket_send(msg)
