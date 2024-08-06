#!/usr/bin/python
# Do basic imports

import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from datetime import timedelta
from homeassistant.components.climate import PLATFORM_SCHEMA

from homeassistant.const import (CONF_SCAN_INTERVAL, CONF_HOST)

from .bridge import GreeBridge
from .fake_server import FakeServer

REQUIREMENTS = ['pycryptodome']

_LOGGER = logging.getLogger(__name__)

CONF_FAKE_SERVER = 'fake_server'
CONF_TEMP_SENSOR = 'temp_sensor'
CONF_TEMP_STEP = 'temp_step'

DEFAULT_NAME = 'Gree Climate'
BROADCAST_ADDRESS = '<broadcast>'
DEFAULT_TARGET_TEMP_STEP = 1

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST, default=BROADCAST_ADDRESS): cv.string,
    vol.Optional(CONF_FAKE_SERVER, default=''): cv.string,
    vol.Optional(CONF_SCAN_INTERVAL, default=timedelta(seconds=30)): (
        vol.All(cv.time_period, cv.positive_timedelta)),
    vol.Optional(CONF_TEMP_SENSOR, default={}): {cv.string: cv.entity_id},
    vol.Optional(CONF_TEMP_STEP, default=DEFAULT_TARGET_TEMP_STEP): cv.small_float,
})


async def async_setup_platform(hass, config, async_add_devices, discovery_info=None):
    _LOGGER.info('Setting up Gree climate platform')
    host = config.get(CONF_HOST)
    fake_server = config.get(CONF_FAKE_SERVER)
    scan_interval = config.get(CONF_SCAN_INTERVAL)
    temp_sensor = config.get(CONF_TEMP_SENSOR)
    temp_step = config.get(CONF_TEMP_STEP)
    if fake_server != '':
        server = FakeServer(hass, fake_server, 1812, 'dis.gree.com')
    bridge = GreeBridge(hass, host, scan_interval,
                        temp_sensor, temp_step, async_add_devices)
