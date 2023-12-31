# pylint: disable=too-many-lines
# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=invalid-name
# pylint: disable=protected-access
# pylint: disable=line-too-long

from unittest.mock import patch
import pytest

from lennoxs30api.s30api_async import lennox_system

from custom_components.lennoxs30 import Manager
from custom_components.lennoxs30.const import LENNOX_DOMAIN
from custom_components.lennoxs30.switch import S30ZoningSwitch

from tests.conftest import (
    conf_test_exception_handling,
    conftest_base_entity_availability,
    conf_test_switch_info_async_turn_off,
    conf_test_switch_info_async_turn_on,
)


@pytest.mark.asyncio
async def test_zoning_switch_subscription(hass, manager: Manager):
    system: lennox_system = manager.api.system_list[0]
    c = S30ZoningSwitch(hass, manager, system)
    await c.async_added_to_hass()

    with patch.object(c, "schedule_update_ha_state") as update_callback:
        update_set = {"centralMode": not system.centralMode}
        system.attr_updater(update_set, "centralMode", "centralMode")
        system.executeOnUpdateCallbacks()
        assert update_callback.call_count == 1

    conftest_base_entity_availability(manager, system, c)


@pytest.mark.asyncio
async def test_zoning_switch(hass, manager: Manager, caplog):
    system: lennox_system = manager.api.system_list[0]
    c = S30ZoningSwitch(hass, manager, system)

    assert c.unique_id == (system.unique_id + "_SW_ZE").replace("-", "")
    assert c.name == system.name + "_zoning_enable"
    assert len(c.extra_state_attributes) == 0
    assert c.update() is True
    assert c.should_poll is False

    identifiers = c.device_info["identifiers"]
    for x in identifiers:
        assert x[0] == LENNOX_DOMAIN
        assert x[1] == system.unique_id

    system.centralMode = False
    assert c.is_on is True

    system.centralMode = True
    assert c.is_on is False

    with patch.object(system, "centralMode_off") as centralMode:
        await c.async_turn_on()
        assert centralMode.call_count == 1

    await conf_test_exception_handling(system, "centralMode_off", c, c.async_turn_on)

    with patch.object(system, "centralMode_on") as centralMode:
        await c.async_turn_off()
        assert centralMode.call_count == 1

    await conf_test_exception_handling(system, "centralMode_on", c, c.async_turn_off)
    await conf_test_switch_info_async_turn_off(system, "centralMode_on", c, caplog)
    await conf_test_switch_info_async_turn_on(system, "centralMode_off", c, caplog)
