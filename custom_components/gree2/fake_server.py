from datetime import (datetime, timedelta)
import base64
import json
import socket
import sys
import threading
import logging
import time
from homeassistant.helpers.event import (
    async_track_time_interval )
from .ciper import (CIPER_KEY, ciperEncrypt, ciperDecrypt)

_LOGGER = logging.getLogger(__name__)


class FakeServer:
    def __init__(self, hass, ip, port, hostname):
        self.hass = hass
        self.ip = ip
        self.port = port
        self.hostname = hostname
        self.socket = socket.socket(
            family=socket.AF_INET, type=socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self._serving = True

        self.connMap = {}
        self.haMap = {}
        async_track_time_interval(
            self.hass, self.heart_beat, timedelta(seconds=60))

        self.start()

    def heart_beat(self, now):
        for key in self.haMap.keys():
            conn = self.haMap[key]
            _LOGGER.info('* Server send heart beat to conn: {}'.format(conn))
            conn.sendall(json.dumps({'t': 'hb'}).encode())

    def start(self):
        thread = threading.Thread(target=self.serve, args=())
        thread.daemon = True
        thread.start()

    def serve(self):
        self.socket.bind((self.ip, self.port))
        self.socket.listen()
        _LOGGER.info('* Server is running on (tcp) {}:{}, DNS A record: {}'.format(
            self.ip, self.port, self.hostname))

        while self._serving:
            conn, address = self.socket.accept()
            (host, port) = address
            _LOGGER.info(
                '* Server receive connect form {}:{}, connect: {}'.format(host, port, conn))
            # conn.setblocking(False)
            thread = threading.Thread(target=self.receive, args=(conn, host,))
            thread.daemon = True
            thread.start()

    def receive(self, conn, host):
        keep_alive = True
        while keep_alive:
            try:
                data = conn.recv(65535)
                if not data:
                    keep_alive = False
                _LOGGER.debug('conn recv data: {} from: {} conn addr: {}'.format(
                    data, host, conn.getpeername()))
                lines = data.splitlines()
                for message in lines:
                    self.process(message, conn)
            except BlockingIOError as e:
                time.sleep(0.5)
            except Exception as e:
                _LOGGER.info(
                    '* Connection Exception: {}'.format(e))
                keep_alive = False
        conn.close()
        if host in self.connMap.keys():
            self.connMap.pop(host)
        _LOGGER.debug('receive thread end keep_alive: {}'.format(keep_alive))

    def cmd_dis(self, msg, conn):
        pack = {'t': 'svr',
                'ip': self.ip,
                'ip2': self.ip,
                'Ip3': self.ip,
                'host': self.hostname,
                'udpPort': self.port,
                'tcpPort': self.port,
                'protocol': 'TCP',
                'datHost': self.hostname,
                'datHostPort': self.port}

        answer = {'t': 'pack',
                  'i': 1,
                  'uid': 0,
                  'cid': '',
                  'tcid': msg['mac'],
                  'pack': ciperEncrypt(pack)}
        _LOGGER.info(
            '    Discovery request pack: {} answer: {}'.format(pack, answer))
        conn.sendall(json.dumps(answer).encode())

    def cmd_devLogin(self, msg, conn):
        norm_arr = [8, 9, 14, 15, 2, 3, 10, 11, 4, 5, 0, 1]
        cid = ''.join([msg['mac'][c] for c in norm_arr])

        pack = {'t': 'loginRes',
                'r': 200,
                'cid': cid,
                'uid': 0}

        answer = {'t': 'pack',
                  'i': 1,
                  'uid': 0,
                  'cid': '',
                  'tcid': '',
                  'pack': ciperEncrypt(pack)}
        _LOGGER.info(
            '    DevLogin request answer: {} pack: {}'.format(answer, pack))
        conn.sendall(json.dumps(answer).encode())

    def cmd_tm(self, conn):
        time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        answer = {'t': 'tm',
                  'time': time}
        _LOGGER.info('    Tm request answer: {}'.format(answer))
        conn.sendall(json.dumps(answer).encode())

    def cmd_hb(self, conn):
        answer = {'t': 'hbok'}
        (host, _) = conn.getpeername()
        self.connMap[host] = conn
        _LOGGER.info('    Hb request answer: {}'.format(answer))
        conn.sendall(json.dumps(answer).encode())

    def cmd_pack(self, msg, conn):
        msg = ciperDecrypt(msg['pack'])
        self.process(msg, conn)

    def cmd_app_pack(self, msg, conn):
        _LOGGER.debug('    App pack received: {} host: {}'.format(msg, conn))
        (host, _) = conn.getpeername()
        if host in self.haMap.keys():
            msg = msg + b'\n'
            _LOGGER.debug(
                '    App pack: {} send to host: {}'.format(msg, conn))
            conn = self.haMap[host]
            conn.sendall(msg)

    def cmd_pas(self, msg, conn):
        _LOGGER.debug('    Pas request msg:{}'.format(msg))
        host = msg['host']
        if host in self.connMap.keys():
            self.haMap[host] = conn
            conn = self.connMap[host]
            req = msg['req']
            _LOGGER.debug('    Pas request, req:{} to {}'.format(req, host))
            conn.sendall(json.dumps(req).encode())
        else:
            _LOGGER.debug(
                'Connection from device host: {} is not ready'.format(host))
    
    def cmd_ret(self, conn):
        _LOGGER.info('    Ret request answer: {}'.format(conn))
        (host, _) = conn.getpeername()
        if host in self.haMap.keys():
            msg = {'t': 'ret'}
            conn = self.haMap[host]
            conn.sendall(json.dumps(msg).encode())

    def process(self, data, conn):
        try:
            msg = json.loads(data)
            _LOGGER.info('  Process: {}'.format(msg))
            cmd = msg['t']
            match cmd:
                case 'dis':
                    self.cmd_dis(msg, conn)
                case 'devLogin':
                    self.cmd_devLogin(msg, conn)
                case 'tm':
                    self.cmd_tm(conn)
                case 'hb':
                    self.cmd_hb(conn)
                case 'pack':
                    if msg['tcid'] == 'app':
                        self.cmd_app_pack(data, conn)
                    else:
                        self.cmd_pack(msg, conn)
                case 'pas':
                    self.cmd_pas(msg, conn)
                case 'ret':
                    self.cmd_ret(conn)

        except Exception as e:
            _LOGGER.info('* Exception: {} on message {}'.format(e, str(data)))
