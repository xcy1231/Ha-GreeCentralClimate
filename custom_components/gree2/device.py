import logging

from homeassistant.core import callback
from homeassistant.components.climate import ClimateEntity
from homeassistant.helpers.event import async_track_state_change

from homeassistant.components.climate.const import (
    HVAC_MODE_OFF, HVAC_MODE_AUTO, HVAC_MODE_COOL, HVAC_MODE_DRY,
    HVAC_MODE_FAN_ONLY, HVAC_MODE_HEAT, SUPPORT_FAN_MODE,
    FAN_AUTO, FAN_LOW, FAN_MIDDLE, FAN_HIGH,
    PRESET_NONE, PRESET_SLEEP,
    SUPPORT_TARGET_TEMPERATURE, SUPPORT_PRESET_MODE)

from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT, ATTR_TEMPERATURE, CONF_SCAN_INTERVAL,
    CONF_NAME, CONF_HOST, CONF_PORT, CONF_MAC, CONF_TIMEOUT, CONF_CUSTOMIZE,
    STATE_ON, STATE_OFF, STATE_UNKNOWN,
    TEMP_CELSIUS, PRECISION_WHOLE, PRECISION_TENTHS)

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 7000

# from the remote control and gree app
MIN_TEMP = 16
MAX_TEMP = 30

# fixed values in gree mode lists
HVAC_MODES = [HVAC_MODE_AUTO, HVAC_MODE_COOL, HVAC_MODE_DRY,
              HVAC_MODE_FAN_ONLY, HVAC_MODE_HEAT, HVAC_MODE_OFF]
FAN_MODES = [FAN_AUTO, FAN_LOW, 'medium-low',
             FAN_MIDDLE, 'medium-high', FAN_HIGH]
PRESET_MODES = [PRESET_NONE, PRESET_SLEEP]

SUPPORT_FLAGS = SUPPORT_TARGET_TEMPERATURE | SUPPORT_FAN_MODE | SUPPORT_PRESET_MODE


class Gree2Climate(ClimateEntity):

    def __init__(self, hass, name, mac, bridge, temp_sensor, temp_step):
        _LOGGER.info('Initialize the GREE climate device')
        self.hass = hass
        self.mac = mac

        self._unique_id = 'com.gree2.' + mac

        self._available = False

        self._name = name

        self._bridge = bridge

        self._unit_of_measurement = hass.config.units.temperature_unit

        self._target_temperature = 26
        self._current_temperature = 26
        self._target_temperature_step = temp_step
        self._hvac_mode = HVAC_MODE_OFF
        self._fan_mode = FAN_AUTO
        self._preset_mode = PRESET_NONE

        self._hvac_modes = HVAC_MODES
        self._fan_modes = FAN_MODES
        self._preset_modes = PRESET_MODES

        self._temp_sensor = temp_sensor
        if temp_sensor:
            async_track_state_change(
                hass, temp_sensor, self._async_temp_sensor_changed)
            temp_state = hass.states.get(temp_sensor)
            if temp_state:
                self._async_update_current_temp(temp_state)

        self._acOptions = {
            'Pow': 0,
            'Mod': str(self._hvac_mode.index(HVAC_MODE_OFF)),
            'WdSpd': 0,
            'SetTem': 26,
            'SwhSlp': 0,
        }

    @property
    def should_poll(self):
        # Return the polling state.
        return False

    @property
    def unique_id(self) -> str:
        # Return a unique ID.
        return self._unique_id

    @property
    def available(self):
        # Return available of the climate device.
        return self._available

    @property
    def hidden(self):
        # Return hidden of the climate device.
        return not self._available

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
    def preset_mode(self):
        # Return the preset mode.
        if self._acOptions['SwhSlp'] != 0:
            return PRESET_SLEEP
        return PRESET_NONE

    @property
    def preset_modes(self):
        # Return the list of available preset modes.
        return self._preset_modes

    @property
    def supported_features(self):
        # Return the list of supported features.
        return SUPPORT_FLAGS

    def turn_on(self):
        _LOGGER.info('turn_on(): ')
        # Turn on.
        self.SyncState({'Pow': 1})

    def turn_off(self):
        _LOGGER.info('turn_off(): ')
        # Turn on.
        self.SyncState({'Pow': 0})

    def set_temperature(self, **kwargs):
        _LOGGER.info('set_temperature(): ' + str(kwargs.get(ATTR_TEMPERATURE)))
        # Set new target temperatures.
        if kwargs.get(ATTR_TEMPERATURE) is not None:
            # do nothing if temperature is none
            if not (self._acOptions['Pow'] == 0):
                # do nothing if HVAC is switched off
                _LOGGER.info('syncState with SetTem=' +
                             str(kwargs.get(ATTR_TEMPERATURE)))
                tem, decimal = str(kwargs.get(ATTR_TEMPERATURE)).split('.')
                self.syncState({'SetTem': int(tem), 'Add0.1': int(decimal)})

    def set_fan_mode(self, fan):
        _LOGGER.info('set_fan_mode(): ' + str(fan))
        # Set the fan mode.
        if not (self._acOptions['Pow'] == 0):
            _LOGGER.info('Setting normal fan mode to ' +
                         str(self._fan_modes.index(fan)))
            self.syncState({'WdSpd': str(self._fan_modes.index(fan))})

    def set_hvac_mode(self, hvac_mode):
        _LOGGER.info('set_hvac_mode(): ' + str(hvac_mode))
        # Set new operation mode.
        if (hvac_mode == HVAC_MODE_OFF):
            self.syncState({'Pow': 0})
        else:
            self.syncState(
                {'Mod': self._hvac_modes.index(hvac_mode), 'Pow': 1})

    def set_preset_mode(self, preset_mode):
        _LOGGER.info('set_preset_mode(): ' + str(preset_mode))
        # Set the fan mode.
        if self._acOptions['Pow'] == 0:
            return

        if preset_mode == PRESET_SLEEP:
            _LOGGER.info('Setting SwhSlp mode to 1')
            self.syncState({'SwhSlp': 1, 'Quiet': 1})
            return

        self.syncState({'SwhSlp': 0, 'Quiet': 0})

    async def async_added_to_hass(self):
        _LOGGER.info('Gree climate device added to hass()')
        self.syncStatus()

    def syncStatus(self, now=None):
        cmds = ['Pow', 'Mod', 'SetTem', 'WdSpd', 'Air', 'Blo',
                'Health', 'SwhSlp', 'SwingLfRig', 'Quiet', 'SvSt', 'Add0.1']
        message = {
            'cols': cmds,
            'mac': self.mac,
            't': 'status'
        }
        self._bridge.sync_status(message)

    def dealStatusPack(self, statusPack):
        if statusPack is not None:
            self._available = True
            for i, val in enumerate(statusPack['cols']):
                self._acOptions[val] = statusPack['dat'][i]
            _LOGGER.info('Climate {} status: {}'.format(
                self._name, self._acOptions))
            self.UpdateHAStateToCurrentACState()
            self.async_write_ha_state()

    def dealResPack(self, resPack):
        if resPack is not None:
            for i, val in enumerate(resPack['opt']):
                self._acOptions[val] = resPack['val'][i]
            self.UpdateHAStateToCurrentACState()
            self.async_write_ha_state()

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
        self._bridge.sync_status(message)

    def UpdateHATargetTemperature(self):
        # Sync set temperature to HA
        tem = int(self._acOptions['SetTem'])
        if 'Add0.1' in self._acOptions:
            decimal = self._acOptions['Add0.1']
            if decimal:
                tem = tem + int(decimal) * 0.1
        self._target_temperature = tem
        _LOGGER.info('{} HA target temp set according to HVAC state to: {}'.format(
            self._name, str(tem)))

    def UpdateHAHvacMode(self):
        # Sync current HVAC operation mode to HA
        if (self._acOptions['Pow'] == 0):
            self._hvac_mode = HVAC_MODE_OFF
        else:
            self._hvac_mode = self._hvac_modes[self._acOptions['Mod']]
        _LOGGER.info('{} HA operation mode set according to HVAC state to: {}'.format(
            self._name, str(self._hvac_mode)))

    def UpdateHAFanMode(self):
        # Sync current HVAC Fan mode state to HA
        index = int(self._acOptions['WdSpd'])
        if index < len(self._fan_modes):
            self._fan_mode = self._fan_modes[int(self._acOptions['WdSpd'])]
            _LOGGER.info('{} HA fan mode set according to HVAC state to: {}'.format(
                self._name, str(self._fan_mode)))
        else:
            _LOGGER.info('{} HA fan mode set WdSpd to: {}'.format(
                self._name, str(self._acOptions['WdSpd'])))

    def UpdateHAStateToCurrentACState(self):
        self.UpdateHATargetTemperature()
        self.UpdateHAHvacMode()
        self.UpdateHAFanMode()

    @callback
    def _async_update_current_temp(self, state):
        try:
            float(state.state)
            pass
        except ValueError:
            return
        """Update thermostat with latest state from sensor."""
        try:
            self._current_temperature = self.hass.config.units.temperature(
                float(state.state), self._unit_of_measurement)
        except ValueError as ex:
            _LOGGER.error('Unable to update from sensor: %s', ex)

    async def _async_temp_sensor_changed(self, entity_id, old_state, new_state):
        _LOGGER.info('temp_sensor state changed |' + str(entity_id) +
                     '|' + str(old_state) + '|' + str(new_state))
        if new_state is None:
            return
        self._async_update_current_temp(new_state)
        self.async_write_ha_state()
