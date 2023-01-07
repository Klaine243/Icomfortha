"""Support for Lennoxs30 outdoor temperature sensor"""
# pylint: disable=logging-not-lazy
# pylint: disable=logging-fstring-interpolation
# pylint: disable=global-statement
# pylint: disable=broad-except
# pylint: disable=unused-argument
# pylint: disable=line-too-long
# pylint: disable=invalid-name
import logging
from typing import Any

from homeassistant.const import (
    PERCENTAGE,
    POWER_WATT,
    TEMP_CELSIUS,
    TEMP_FAHRENHEIT,
    FREQUENCY_HERTZ,
    ELECTRIC_CURRENT_AMPERE,
    ELECTRIC_POTENTIAL_VOLT,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.components.sensor import (
    SensorStateClass,
    SensorEntity,
    SensorDeviceClass,
)

from lennoxs30api import (
    lennox_system,
    lennox_zone,
    lennox_equipment,
    lennox_equipment_diagnostic,
    LENNOX_BAD_STATUS,
    LENNOX_STATUS_NOT_EXIST,
)


from .base_entity import S30BaseEntityMixin
from .const import (
    MANAGER,
    UNIQUE_ID_SUFFIX_ACTIVE_ALERTS_SENSOR,
    UNIQUE_ID_SUFFIX_ALERT_SENSOR,
    UNIQUE_ID_SUFFIX_DIAG_SENSOR,
)
from .helpers import helper_create_system_unique_id, helper_get_equipment_device_info, lennox_uom_to_ha_uom

from . import Manager

_LOGGER = logging.getLogger(__name__)

DOMAIN = "lennoxs30"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> bool:
    """Setup the home assistant entities"""
    sensor_list = []
    manager: Manager = hass.data[DOMAIN][entry.unique_id][MANAGER]
    for system in manager.api.system_list:
        if system.outdoorTemperatureStatus != LENNOX_STATUS_NOT_EXIST:
            _LOGGER.info(f"Create S30OutdoorTempSensor system [{system.sysId}]")
            sensor = S30OutdoorTempSensor(hass, manager, system)
            sensor_list.append(sensor)
        else:
            _LOGGER.info(f"Not creating S30OutdoorTempSensor system [{system.sysId}] - sensor does not exist")

        if manager.create_inverter_power:
            _LOGGER.info(f"Create S30InverterPowerSensor system [{system.sysId}]")
            if system.diagLevel != 2:
                _LOGGER.warning(
                    f"Power Inverter Sensor requires S30 to be in diagLevel 2, currently in [{system.diagLevel}]"
                )
            if system.internetStatus or system.relayServerConnected:
                _LOGGER.warning(
                    f"To prevent S30 instability - Power Inverter Sensor requires S30 to be isolated from internet - internetStatus [{system.internetStatus}] relayServerConnected [{system.relayServerConnected}] - https://github.com/PeteRager/lennoxs30/blob/master/docs/diagnostics.md"
                )
            power_sensor = S30InverterPowerSensor(hass, manager, system)
            sensor_list.append(power_sensor)

        if manager.create_diagnostic_sensors:
            _LOGGER.info(f"Create Diagnostic Sensors system [{system.sysId}]")
            if system.diagLevel != 2:
                _LOGGER.warning(f"Diagnostics requires S30 to be in diagLevel 2, currently in [{system.diagLevel}]")
            if system.internetStatus or system.relayServerConnected:
                _LOGGER.warning(
                    f"To prevent S30 instability - diagnostics requires S30 to be isolated from internet - internetStatus [{system.internetStatus}] relayServerConnected [{system.relayServerConnected}] - https://github.com/PeteRager/lennoxs30/blob/master/docs/diagnostics.md"
                )
            for _, eq in system.equipment.items():
                equip: lennox_equipment = eq
                if equip.equipment_id != 0:
                    for _, diagnostic in equip.diagnostics.items():
                        if diagnostic.valid:
                            _LOGGER.info(
                                f"Create Diagsensor system [{system.sysId}] eid [{equip.equipment_id}] did [{diagnostic.diagnostic_id}] name [{diagnostic.name}]"
                            )
                            diagsensor = S30DiagSensor(hass, manager, system, equip, diagnostic)
                            sensor_list.append(diagsensor)

        if manager.create_sensors:
            for zone in system.zone_list:
                if zone.is_zone_active():
                    _LOGGER.info(f"Create S30TempSensor sensor system [{system.sysId}] zone [{zone.id}]")
                    sensor_list.append(S30TempSensor(hass, manager, system, zone))
                    _LOGGER.info(f"Create S30HumSensor sensor system [{system.sysId}] zone [{zone.id}]")
                    sensor_list.append(S30HumiditySensor(hass, manager, system, zone))

        if manager.create_alert_sensors:
            sensor_list.append(S30AlertSensor(hass, manager, system))
            sensor_list.append(S30ActiveAlertsList(hass, manager, system))

    if len(sensor_list) != 0:
        async_add_entities(sensor_list, True)
        _LOGGER.debug(f"sensor:async_setup_platform exit - created [{len(sensor_list)}] entitites")
        return True
    else:
        _LOGGER.info("sensor:async_setup_platform exit - no sensors found")
        return False


class S30DiagSensor(S30BaseEntityMixin, SensorEntity):
    """Diagnostic Data Sensor"""

    def __init__(
        self,
        hass,
        manager: Manager,
        system: lennox_system,
        equipment: lennox_equipment,
        diagnostic: lennox_equipment_diagnostic,
    ):
        super().__init__(manager, system)
        self._hass = hass
        self._equipment: lennox_equipment = equipment
        self._diagnostic: lennox_equipment_diagnostic = diagnostic

        suffix = str(self._equipment.equipment_id)
        if self._equipment.equipment_id == 1:
            suffix = "ou"
        elif self._equipment.equipment_id == 2:
            suffix = "iu"
        self._myname = f"{self._system.name}_{suffix}_{self._diagnostic.name}".replace(" ", "_")
        _LOGGER.debug(f"Create S30DiagSensor myname [{self._myname}]")

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug(f"async_added_to_hass S30DiagSensor myname [{self._myname}]")
        self._system.registerOnUpdateCallbackDiag(
            self.update_callback,
            [f"{self._equipment.equipment_id}_{self._diagnostic.diagnostic_id}"],
        )
        self._system.registerOnUpdateCallback(self.system_update_callback, ["diagLevel"])
        await super().async_added_to_hass()

    def update_callback(self, eid_did, newval):
        """Callback to execute on data change"""
        _LOGGER.debug(f"update_callback S30DiagSSensor myname [{self._myname}] value {newval}")
        self.schedule_update_ha_state()

    def system_update_callback(self):
        """Callback to execute on system data change"""
        _LOGGER.debug(f"system_update_callback S30DiagSSensor myname [{self._myname}]")
        self.schedule_update_ha_state()

    @property
    def available(self) -> bool:
        if self._diagnostic.value == "waiting...":
            return False
        if self._system.diagLevel not in (1, 2):
            return False
        return super().available

    @property
    def native_value(self):
        """Return native value of the sensor."""
        if self._diagnostic.value == "waiting...":
            return None
        return self._diagnostic.value

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {}

    @property
    def unique_id(self) -> str:
        # HA fails with dashes in IDs
        return (
            f"{self._system.unique_id}_{UNIQUE_ID_SUFFIX_DIAG_SENSOR}_{self._equipment.equipment_id}_{self._diagnostic.name}"
        ).replace("-", "")

    @property
    def name(self):
        return self._myname

    @property
    def native_unit_of_measurement(self):
        return lennox_uom_to_ha_uom(self._diagnostic.unit)

    @property
    def device_class(self):
        uom = self.native_unit_of_measurement
        if uom == TEMP_FAHRENHEIT:
            return SensorDeviceClass.TEMPERATURE
        elif uom == TEMP_CELSIUS:
            return SensorDeviceClass.TEMPERATURE
        elif uom == ELECTRIC_POTENTIAL_VOLT:
            return SensorDeviceClass.VOLTAGE
        elif uom == ELECTRIC_CURRENT_AMPERE:
            return SensorDeviceClass.CURRENT
        elif uom == FREQUENCY_HERTZ:
            return SensorDeviceClass.FREQUENCY
        return None

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        equip_device_map = self._manager.system_equip_device_map.get(self._system.sysId)
        if equip_device_map is not None:
            device = equip_device_map.get(self._equipment.equipment_id)
            if device is not None:
                return {
                    "identifiers": {(DOMAIN, device.unique_name)},
                }
            _LOGGER.warning(
                f"Unable to find equipment in device map [{self._equipment.equipment_id}] [{self._equipment.equipment_name}] [{self._equipment.equipment_type_name}] [{self._equipment.equipType}], please raise an issue and post a message log"
            )
        else:
            _LOGGER.error(
                f"No equipment device map found for sysId [{self._system.sysId}] equipment [{self._equipment.equipment_id}] [{self._equipment.equipment_name}] [{self._equipment.equipment_type_name}] [{self._equipment.equipType}], please raise an issue and post a message log"
            )
        return {
            "identifiers": {(DOMAIN, self._system.unique_id)},
        }

    @property
    def entity_category(self):
        return EntityCategory.DIAGNOSTIC


class S30OutdoorTempSensor(S30BaseEntityMixin, SensorEntity):
    """Class for Lennox S30 thermostat."""

    def __init__(self, hass: HomeAssistant, manager: Manager, system: lennox_system):
        super().__init__(manager, system)
        self._hass = hass
        self._myname = self._system.name + "_outdoor_temperature"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug(f"async_added_to_hass S30OutdoorTempSensor myname [{self._myname}]")
        self._system.registerOnUpdateCallback(
            self.update_callback,
            ["outdoorTemperature", "outdoorTemperatureC", "outdoorTemperatureStatus"],
        )
        await super().async_added_to_hass()

    def update_callback(self):
        """Callback to execute on data change"""
        _LOGGER.debug(f"update_callback S30OutdoorTempSensor myname [{self._myname}]")
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        # HA fails with dashes in IDs
        return (self._system.unique_id + "_OT").replace("-", "")

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {}

    @property
    def name(self):
        return self._myname

    @property
    def available(self):
        if self._system.outdoorTemperatureStatus in LENNOX_BAD_STATUS:
            return False
        return super().available

    @property
    def native_value(self):
        if self._system.outdoorTemperatureStatus in LENNOX_BAD_STATUS:
            _LOGGER.warning(
                f"S30OutdoorTempSensor [{self._myname}] has bad data quality [{self._system.outdoorTemperatureStatus}] returning None"
            )
            return None
        if self._manager.is_metric is False:
            return self._system.outdoorTemperature
        return self._system.outdoorTemperatureC

    @property
    def native_unit_of_measurement(self):
        if self._manager.is_metric is False:
            return TEMP_FAHRENHEIT
        return TEMP_CELSIUS

    @property
    def device_class(self):
        return SensorDeviceClass.TEMPERATURE

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._system.unique_id + "_ou")},
        }


class S30TempSensor(S30BaseEntityMixin, SensorEntity):
    """Class for Lennox S30 thermostat temperature."""

    def __init__(
        self,
        hass: HomeAssistant,
        manager: Manager,
        system: lennox_system,
        zone: lennox_zone,
    ):
        super().__init__(manager, system)
        self._hass = hass
        self._zone = zone
        self._myname = self._zone.system.name + "_" + self._zone.name + "_temperature"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug(f"async_added_to_hass S30TempSensor myname [{self._myname}]")
        self._zone.registerOnUpdateCallback(self.update_callback, ["temperature", "temperatureC"])
        await super().async_added_to_hass()

    def update_callback(self):
        """Callback to execute on data change"""
        _LOGGER.debug(f"update_callback S30TempSensor myname [{self._myname}]")
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        # HA fails with dashes in IDs
        return (self._zone.system.unique_id + "_" + str(self._zone.id)).replace("-", "") + "_T"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {}

    @property
    def available(self):
        if self._zone.temperatureStatus in LENNOX_BAD_STATUS:
            return False
        return super().available

    @property
    def name(self):
        return self._myname

    @property
    def native_value(self):
        if self._zone.temperatureStatus in LENNOX_BAD_STATUS:
            _LOGGER.warning(
                f"S30TempSensor [{self._myname}] has bad data quality [{self._zone.temperatureStatus}] returning None"
            )
            return None
        if self._manager.is_metric is False:
            return self._zone.getTemperature()
        return self._zone.getTemperatureC()

    @property
    def native_unit_of_measurement(self):
        if self._manager.is_metric is False:
            return TEMP_FAHRENHEIT
        return TEMP_CELSIUS

    @property
    def device_class(self):
        return SensorDeviceClass.TEMPERATURE

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._zone.unique_id)},
        }


class S30HumiditySensor(S30BaseEntityMixin, SensorEntity):
    """Class for Lennox S30 thermostat temperature."""

    def __init__(
        self,
        hass: HomeAssistant,
        manager: Manager,
        system: lennox_system,
        zone: lennox_zone,
    ):
        super().__init__(manager, system)
        self._hass = hass
        self._zone = zone
        self._myname = self._zone.system.name + "_" + self._zone.name + "_humidity"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug(f"async_added_to_hass S30TempSensor myname [{self._myname}]")
        self._zone.registerOnUpdateCallback(self.update_callback, ["humidity"])
        await super().async_added_to_hass()

    def update_callback(self):
        """Callback to execute on data change"""
        _LOGGER.debug(f"update_callback S30HumiditySensor myname [{self._myname}]")
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        # HA fails with dashes in IDs
        return (self._zone.system.unique_id + "_" + str(self._zone.id)).replace("-", "") + "_H"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {}

    @property
    def name(self):
        return self._myname

    @property
    def available(self):
        if self._zone.humidityStatus in LENNOX_BAD_STATUS:
            return False
        return super().available

    @property
    def native_value(self):
        if self._zone.humidityStatus in LENNOX_BAD_STATUS:
            _LOGGER.warning(
                f"S30HumiditySensor [{self._myname}] has bad data quality [{self._zone.humidityStatus}] returning None"
            )
            return None
        return self._zone.getHumidity()

    @property
    def native_unit_of_measurement(self):
        return PERCENTAGE

    @property
    def device_class(self):
        return SensorDeviceClass.HUMIDITY

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._zone.unique_id)},
        }


class S30InverterPowerSensor(S30BaseEntityMixin, SensorEntity):
    """Class for Lennox S30 inverter power."""

    def __init__(self, hass: HomeAssistant, manager: Manager, system: lennox_system):
        super().__init__(manager, system)
        self._hass = hass
        self._myname = self._system.name + "_inverter_energy"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug(f"async_added_to_hass S30TempSensor myname [{self._myname}]")
        self._system.registerOnUpdateCallback(
            self.update_callback,
            ["diagInverterInputVoltage", "diagInverterInputCurrent"],
        )
        self._system.registerOnUpdateCallback(self.system_update_callback, ["diagLevel"])
        await super().async_added_to_hass()

    def system_update_callback(self):
        """Callback to execute on data change"""
        _LOGGER.debug(f"system_update_callback S30InverterPowerSensor myname [{self._myname}]")
        self.schedule_update_ha_state()

    def update_callback(self):
        """Callback to execute on data change"""
        _LOGGER.debug(f"update_callback S30InverterPowerSensor [{self._myname}]")
        self.schedule_update_ha_state()

    @property
    def available(self) -> bool:
        if self._system.diagLevel not in (1, 2):
            return False
        return super().available

    @property
    def unique_id(self) -> str:
        # HA fails with dashes in IDs
        return (self._system.unique_id + "_IE").replace("-", "")

    @property
    def name(self):
        return self._myname

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {}

    @property
    def native_value(self):
        if self._system.diagInverterInputVoltage is None or self._system.diagInverterInputCurrent is None:
            _LOGGER.debug(f"Values are None for diagnostic sensors  [{self._myname}]")
            return None
        if (
            self._system.diagInverterInputVoltage == "waiting..."
            or self._system.diagInverterInputCurrent == "waiting..."
        ):
            _LOGGER.debug(f"System is waiting for values for diagnostic sensors  [{self._myname}]")
            return None
        try:
            return int(float(self._system.diagInverterInputVoltage) * float(self._system.diagInverterInputCurrent))
        except ValueError as e:
            _LOGGER.warning(
                f"state myname [{self._myname}] diagInverterInputVoltage [{self._system.diagInverterInputVoltage}] diagInverterInputCurrent [{self._system.diagInverterInputCurrent}] failed: {e}"
            )
        return None

    @property
    def native_unit_of_measurement(self):
        return POWER_WATT

    @property
    def device_class(self):
        return SensorDeviceClass.POWER

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        return {
            "identifiers": {(DOMAIN, self._system.unique_id + "_ou")},
        }


class S30AlertSensor(S30BaseEntityMixin, SensorEntity):
    """Class for Lennox S30 thermostat temperature."""

    def __init__(
        self,
        hass: HomeAssistant,
        manager: Manager,
        system: lennox_system,
    ):
        super().__init__(manager, system)
        self._hass = hass
        self._myname = self._system.name + "_alert"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug(f"async_added_to_hass S30AlertSensor myname [{self._myname}]")
        self._system.registerOnUpdateCallback(self.update_callback, ["alert"])
        await super().async_added_to_hass()

    def update_callback(self):
        """Callback to execute on data change"""
        _LOGGER.debug(f"update_callback S30AlertSensor myname [{self._myname}]")
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        return helper_create_system_unique_id(self._system, UNIQUE_ID_SUFFIX_ALERT_SENSOR)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {}

    @property
    def name(self):
        return self._myname

    @property
    def native_value(self):
        return self._system.alert

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return helper_get_equipment_device_info(self._manager, self._system, 0)


class S30ActiveAlertsList(S30BaseEntityMixin, SensorEntity):
    """Class for Lennox S30 thermostat temperature."""

    def __init__(
        self,
        hass: HomeAssistant,
        manager: Manager,
        system: lennox_system,
    ):
        super().__init__(manager, system)
        self._hass = hass
        self._myname = self._system.name + "_active_alerts"

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        _LOGGER.debug(f"async_added_to_hass S30ActiveAlertList myname [{self._myname}]")
        self._system.registerOnUpdateCallback(
            self.update_callback,
            [
                "active_alerts",
                "alerts_num_cleared",
                "alerts_num_active",
                "alerts_last_cleared_id",
                "alerts_num_in_active_array",
            ],
        )
        await super().async_added_to_hass()

    def update_callback(self):
        """Callback to execute on data change"""
        _LOGGER.debug(f"update_callback S30ActiveAlertList myname [{self._myname}]")
        self.schedule_update_ha_state()

    @property
    def unique_id(self) -> str:
        return helper_create_system_unique_id(self._system, UNIQUE_ID_SUFFIX_ACTIVE_ALERTS_SENSOR)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs: dict[str, Any] = {}
        attrs["alert_list"] = self._system.active_alerts
        val = self._system.alerts_num_cleared
        attrs["alerts_num_cleared"] = 0 if val is None else val
        val = self._system.alerts_last_cleared_id
        attrs["alerts_last_cleared_id"] = 0 if val is None else val
        val = self._system.alerts_num_in_active_array
        attrs["alerts_num_in_active_array"] = 0 if val is None else val
        return attrs

    @property
    def name(self):
        return self._myname

    @property
    def native_value(self):
        if (val := self._system.alerts_num_active) is None:
            return 0
        return val

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return helper_get_equipment_device_info(self._manager, self._system, 0)
