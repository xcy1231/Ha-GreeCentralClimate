#!/usr/bin/python
# Do basic imports
import importlib.util
import socket
import base64
import re
import sys

import threading
import asyncio
import logging
import binascii
import os.path
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
import homeassistant.util.dt as dt_util
from datetime import datetime, timedelta
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.event import async_call_later
from homeassistant.components.climate import (ClimateEntity, PLATFORM_SCHEMA)

from homeassistant.components.climate.const import (
    HVAC_MODE_OFF, HVAC_MODE_AUTO, HVAC_MODE_COOL, HVAC_MODE_DRY,
    HVAC_MODE_FAN_ONLY, HVAC_MODE_HEAT, SUPPORT_FAN_MODE,
    FAN_AUTO, FAN_LOW, FAN_MIDDLE, FAN_HIGH,
    SUPPORT_TARGET_TEMPERATURE, SUPPORT_SWING_MODE, SUPPORT_PRESET_MODE)

from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT, ATTR_TEMPERATURE, CONF_SCAN_INTERVAL,
    CONF_NAME, CONF_HOST, CONF_PORT, CONF_MAC, CONF_TIMEOUT, CONF_CUSTOMIZE, 
    STATE_ON, STATE_OFF, STATE_UNKNOWN, 
    TEMP_CELSIUS, PRECISION_WHOLE, PRECISION_TENTHS)

from homeassistant.helpers.event import (async_track_state_change)
from homeassistant.core import callback
from homeassistant.helpers.restore_state import RestoreEntity
from configparser import ConfigParser
from Crypto.Cipher import AES
try: import simplejson
except ImportError: import json as simplejson

REQUIREMENTS = ['pycryptodome']

_LOGGER = logging.getLogger(__name__)

SUPPORT_FLAGS = SUPPORT_TARGET_TEMPERATURE | SUPPORT_FAN_MODE

DEFAULT_NAME = 'Gree Climate'

BROADCAST_ADDRESS = '<broadcast>'
DEFAULT_PORT = 7000
DEFAULT_TARGET_TEMP_STEP = 1

# from the remote control and gree app
MIN_TEMP = 16
MAX_TEMP = 30

# fixed values in gree mode lists
HVAC_MODES = [HVAC_MODE_AUTO, HVAC_MODE_COOL, HVAC_MODE_DRY, HVAC_MODE_FAN_ONLY, HVAC_MODE_HEAT, HVAC_MODE_OFF]

FAN_MODES = [FAN_AUTO, FAN_LOW, 'medium-low', FAN_MIDDLE, 'medium-high', FAN_HIGH]

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    vol.Required(CONF_HOST, default=BROADCAST_ADDRESS): cv.string,
    vol.Optional(CONF_SCAN_INTERVAL, default=timedelta(seconds=30)): (
        vol.All(cv.time_period, cv.positive_timedelta)),
})

def Pad(s):
    aesBlockSize = 16
    return s + (aesBlockSize - len(s) % aesBlockSize) * chr(aesBlockSize - len(s) % aesBlockSize)     

def ciperEncrypt(data, key="a3K8Bx%2r8Y7#xDh"):
    # _LOGGER.info('Crypto encrypt key: {}'.format(key))
    cipher = AES.new(key.encode("utf8"), AES.MODE_ECB)
    jsonStr = simplejson.dumps(data).replace(' ', '')
    padStr = Pad(jsonStr)
    encryptStr = cipher.encrypt(padStr.encode("utf-8"))
    finalStr = base64.b64encode(encryptStr).decode('utf-8')
    # _LOGGER.info('Crypto encrypt str: {}'.format(finalStr))
    return finalStr

def ciperDecrypt(data, key="a3K8Bx%2r8Y7#xDh"):
    decodeData = base64.b64decode(data)
    cipher = AES.new(key.encode("utf8"), AES.MODE_ECB)
    decryptData = cipher.decrypt(decodeData).decode("utf-8")
    replacedData = decryptData.replace('\x0f', '').replace(decryptData[decryptData.rindex('}')+1:], '')
    return simplejson.loads(replacedData)

async def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    _LOGGER.info('Setting up Gree climate platform')
    name = config.get(CONF_NAME)
    ip_addr = config.get(CONF_HOST)
    
    scan_interval = config.get(CONF_SCAN_INTERVAL)

    bridge = GreeBridge(hass, ip_addr, scan_interval, async_add_devices)


class GreeBridge(object):
    def __init__(self, hass, host, scan_interval, async_add_devices):
        self.hass = hass
        self.async_add_devices = async_add_devices
        self._scan_interval = scan_interval
        self._host = host
        self._socket = None
        self._listening = False

        self._key = "a3K8Bx%2r8Y7#xDh"
        self.mid = None
        self.mac = None
        self.name = None
        self.subCnt = None
        self.uid = None
        self.devMap = {}

        self.start_listen()
        self.scan_broadcast()

    def start_listen(self):
        self._listening = True
        self.create_socket()
        self._thread = threading.Thread(target=self.socket_listen,args=())
        self._thread.daemon = True
        self._thread.start()

    def stop_listen(self):
        self._listening = False
        if self._socket is not None:
            _LOGGER.info('Closing socket')
            self._socket.close()
            self._socket = None

        self._thread.join()

    def create_socket(self):
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # self._socket.bind(('', DEFAULT_PORT))
        except:
            _LOGGER.error('creat socket error')

    def get_all_state(self, now):
        for climate in self.devMap.values():
            climate.syncStatus()

    def socket_listen(self):
        while self._listening:
            if self._socket is None:
                continue
            try:
                data, address = self._socket.recvfrom(65535)
            except ConnectionResetError:
                _LOGGER.debug("Connection reset by peer")
                self.creat_socket()
                continue

            except socket.timeout as e:
                self.get_all_state(dt_util.now())
                continue

            except OSError as e:
                if e.errno == 9:  # when socket close, errorno 9 will raise
                    _LOGGER.debug("OSError 9 raise, socket is closed")
                else:
                    _LOGGER.error("unknown error when recv", exc_info=e)
                continue

            _LOGGER.info('socket received from {}:{}'.format(address, data.decode('utf-8')))
            receivedJson = simplejson.loads(data)
            if self.uid == None:
                self.uid = receivedJson['uid']
            if 'pack' in receivedJson:
                pack = receivedJson['pack']
                jsonPack = ciperDecrypt(pack, self._key)
                _LOGGER.info('Server received pack {}'.format(jsonPack))
                if jsonPack['t'] == 'dev':
                    (host,_) = address
                    self._host = host
                    self.mid = jsonPack['mid']
                    self.mac = jsonPack['mac']
                    self.name = jsonPack['name']
                    self.subCnt = jsonPack['subCnt']
                    self.bind_device()
                elif jsonPack['t'] == 'bindOk':
                    self._key = jsonPack['key']
                    self.get_subdevices()
                elif jsonPack['t'] == 'subList':
                    devList = jsonPack['list']
                    _LOGGER.info('Scan Gree climate device list: {}'.format(devList))
                    for item in devList:
                        if not item['mac'] in self.devMap.keys():
                            self.devMap[item['mac']] = Gree2Climate(self.hass, item['name'] + item['mac'], item['mid'], item['mac'], self)
                    if len(self.devMap) < self.subCnt and jsonPack['i'] < self.subCnt:
                        self.get_subdevices(jsonPack['i'] + 1)
                    else :
                        subDevList = self.devMap.values()
                        _LOGGER.info('All Gree climate device: {} subCnt: {}'.format(subDevList, len(self.devMap) ))
                        self.async_add_devices(subDevList)
                        if len(self.devMap) == 0:
                            self.stop_listen()
                        else:
                            async_track_time_interval(self.hass, self.get_all_state, self._scan_interval)

                elif jsonPack['t'] == 'dat':
                    self.devMap[jsonPack['mac']].dealStatusPack(jsonPack)
                elif jsonPack['t'] == 'res':
                    self.devMap[jsonPack['mac']].dealResPack(jsonPack)

    def socket_send(self, reqData):
        _LOGGER.info('socket send data {} to {}'.format(reqData, self._host))
        self._socket.sendto(simplejson.dumps(reqData).encode('utf-8'), (self._host, DEFAULT_PORT))

    def socket_send_pack(self, message, i=0, uid=None):
        _LOGGER.info('socket send pack {} to {}'.format(message, self._host))
        if uid == None:
            uid = self.uid
        pack = ciperEncrypt(message, self._key)
        reqData = {
            'cid': 'app',
            'i': i,
            't': 'pack',
            'uid': uid,
            'pack': pack,
            'tcid': self.mac
        }
        self.socket_send(reqData)

    def scan_broadcast(self):
        _LOGGER.info('scan_broadcast')
        reqData = {"t": "scan"}
        self.socket_send(reqData)

    def bind_device(self):
        message = {
            'mac': self.mac,
            't': 'bind',
            'uid': 0
        }
        self.socket_send_pack(message, 1, 0)

    def get_subdevices(self, i=0):
        message = {
            't': "subDev",
            'mac': self.mac,
            'i': i,
        }
        self.socket_send_pack(message)

    async def socket_request(self, reqData):
        _LOGGER.info('Server request data {}'.format(reqData))
        self._socket.sendto(simplejson.dumps(reqData).encode('utf-8'), (self._host, DEFAULT_PORT))
        data, address = self._socket.recvfrom(65535)
        _LOGGER.info('Server received from {}:{}'.format(address, data.decode('utf-8')))
        receivedJson = simplejson.loads(data)
        if 'pack' in receivedJson:
            pack = receivedJson['pack']
            jsonPack = ciperDecrypt(pack, self._key)
            _LOGGER.info('Server received json {}'.format(jsonPack))
            return jsonPack

    async def pack_request(self, message, i=0):
        _LOGGER.info('Server request message {}'.format(message))
        pack = ciperEncrypt(message, self._key)
        reqData = {
            'cid': 'app',
            'i': i,
            't': 'pack',
            'uid': self.uid,
            'pack': pack
        }
        jsonPack = await self.socket_request(reqData)
        return jsonPack

class Gree2Climate(ClimateEntity):

    def __init__(self, hass, name, mid, mac, bridge):
        _LOGGER.info('Initialize the GREE climate device')
        self.hass = hass
        self.mac = mac

        self._available = False

        self._name = name
        self._mid = mid
        
        self._bridge = bridge

        self._unit_of_measurement = hass.config.units.temperature_unit

        self._target_temperature = 26
        self._current_temperature = 26
        self._target_temperature_step = DEFAULT_TARGET_TEMP_STEP
        self._hvac_mode = HVAC_MODE_OFF
        self._fan_mode = FAN_AUTO

        self._hvac_modes = HVAC_MODES
        self._fan_modes = FAN_MODES

        self._acOptions = {
            'Pow': 0,
            'Mod': str(self._hvac_mode.index(HVAC_MODE_OFF)),
            'WdSpd': 0,
            'SetTem': 26,
        }
    @property
    def should_poll(self):
        # Return the polling state.
        return False

    @property
    def available(self):
        # Return available of the climate device.
        return self._available

    @property
    def name(self):
        # Return the name of the climate device.
        return self._name

    @property
    def temperature_unit(self):
        # Return the unit of measurement.
        return self._unit_of_measurement

    @property
    def current_temperature(self):
        # Return the current temperature.
        return self._current_temperature

    @property
    def target_temperature(self):
        # Return the temperature we try to reach.
        return self._target_temperature

    @property
    def target_temperature_step(self):
        # Return the supported step of target temperature.
        return self._target_temperature_step

    @property
    def min_temp(self):
        # Return the minimum temperature.
        return MIN_TEMP
        
    @property
    def max_temp(self):
        # Return the maximum temperature.
        return MAX_TEMP

    @property
    def hvac_mode(self):
        # Return current operation mode ie. heat, cool, idle.
        return self._hvac_mode

    @property
    def hvac_modes(self):
        # Return the list of available operation modes.
        return self._hvac_modes

    @property
    def fan_mode(self):
        # Return the fan mode.
        return self._fan_mode

    @property
    def fan_modes(self):
        # Return the list of available fan modes.
        return self._fan_modes

    @property
    def supported_features(self):
        # Return the list of supported features.
        return SUPPORT_FLAGS        

    def set_temperature(self, **kwargs):
        _LOGGER.info('set_temperature(): ' + str(kwargs.get(ATTR_TEMPERATURE)))
        # Set new target temperatures.
        if kwargs.get(ATTR_TEMPERATURE) is not None:
            # do nothing if temperature is none
            if not (self._acOptions['Pow'] == 0):
                # do nothing if HVAC is switched off
                _LOGGER.info('syncState with SetTem=' + str(kwargs.get(ATTR_TEMPERATURE)))
                self.syncState({ 'SetTem': int(kwargs.get(ATTR_TEMPERATURE))})

    def set_fan_mode(self, fan):
        _LOGGER.info('set_fan_mode(): ' + str(fan))
        # Set the fan mode.
        if not (self._acOptions['Pow'] == 0):
            _LOGGER.info('Setting normal fan mode to ' + str(self._fan_modes.index(fan)))
            self.syncState({'WdSpd': str(self._fan_modes.index(fan))})

    def set_hvac_mode(self, hvac_mode):
        _LOGGER.info('set_hvac_mode(): ' + str(hvac_mode))
        # Set new operation mode.
        if (hvac_mode == HVAC_MODE_OFF):
            self.syncState({'Pow': 0})
        else:
            self.syncState({'Mod': self._hvac_modes.index(hvac_mode), 'Pow': 1})

    @asyncio.coroutine
    async def async_added_to_hass(self):
        _LOGGER.info('Gree climate device added to hass()')
        self.syncStatus()

    def syncStatus(self):
        cmds = ['Pow', 'Mod', 'SetTem', 'WdSpd', 'Air', 'Blo', 'Health', 'SwhSlp', 'SwingLfRig', 'Quiet', 'SvSt']
        message = {
            'cols': cmds,
            'mac': self.mac,
            't': 'status'
        }
        self._bridge.socket_send_pack(message)
    
    def dealStatusPack(self, statusPack):
        if statusPack is not None:
            self._available = True
            for i, val in enumerate(statusPack['cols']):
                self._acOptions[val] = statusPack['dat'][i]
            _LOGGER.info('Climate {} status: {}'.format(self._name, self._acOptions))
            self.UpdateHAStateToCurrentACState()
            async_call_later(self.hass, 1, self.async_schedule_update_ha_state)

    def dealResPack(self, resPack):
        if resPack is not None:
            for i, val in enumerate(resPack['opt']):
                self._acOptions[val] = resPack['val'][i]
            self.UpdateHAStateToCurrentACState()
            async_call_later(self.hass, 1, self.async_schedule_update_ha_state)

    def syncState(self, options):
        commands = []
        values = []
        for cmd in options.keys():
            commands.append(cmd)
            values.append(int(options[cmd]))
        message = {
            'opt': commands,
            'p': values,
            't': 'cmd',
            'sub': self.mac
        }
        self._bridge.socket_send_pack(message)

    def UpdateHATargetTemperature(self):
        # Sync set temperature to HA
        self._target_temperature = self._acOptions['SetTem']
        _LOGGER.info('{} HA target temp set according to HVAC state to: {}'.format(self._name ,str(self._acOptions['SetTem'])))

    def UpdateHAHvacMode(self):
        # Sync current HVAC operation mode to HA
        if (self._acOptions['Pow'] == 0):
            self._hvac_mode = HVAC_MODE_OFF
        else:
            self._hvac_mode = self._hvac_modes[self._acOptions['Mod']]
        _LOGGER.info('{} HA operation mode set according to HVAC state to: {}'.format(self._name, str(self._hvac_mode)))

    def UpdateHAFanMode(self):
        # Sync current HVAC Fan mode state to HA
        index = int(self._acOptions['WdSpd'])
        if index < len(self._fan_modes):
            self._fan_mode = self._fan_modes[int(self._acOptions['WdSpd'])]
            _LOGGER.info('{} HA fan mode set according to HVAC state to: {}'.format(self._name, str(self._fan_mode)))
        else:
            _LOGGER.info('{} HA fan mode set WdSpd to: {}'.format(self._name, str(self._acOptions['WdSpd'])))

    def UpdateHAStateToCurrentACState(self):
        self.UpdateHATargetTemperature()
        self.UpdateHAHvacMode()
        self.UpdateHAFanMode()