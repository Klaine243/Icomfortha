"""Tests the reset smart hub button"""
# pylint: disable=line-too-long
# pylint: disable=missing-function-docstring
# pylint: disable=protected-access
# pylint: disable=invalid-name

from unittest.mock import patch
import pytest

from homeassistant.exceptions import HomeAssistantError

from lennoxs30api.s30api_async import lennox_system

from custom_components.lennoxs30 import Manager
from custom_components.lennoxs30.const import LENNOX_DOMAIN
from custom_components.lennoxs30.button import ResetSmartHubButton

from tests.conftest import (
    conf_test_button_info_async_press,
    conf_test_exception_handling,
    conftest_base_entity_availability,
)


@pytest.mark.asyncio
async def test_button_reset_smarthub_unique_id(hass, manager: Manager):
    system: lennox_system = manager.api.system_list[0]
    button = ResetSmartHubButton(hass, manager, system)
    assert button.unique_id == f"{system.unique_id}_RESET_SMART_HUB".replace("-", "")


@pytest.mark.asyncio
async def test_button_reset_smarthub_name(hass, manager: Manager):
    system: lennox_system = manager.api.system_list[0]
    button = ResetSmartHubButton(hass, manager, system)
    assert button.name == "South Moetown_reset_smarthub"


@pytest.mark.asyncio
async def test_button_reset_smarthub_subscription(hass, manager: Manager):
    system: lennox_system = manager.api.system_list[0]
    button = ResetSmartHubButton(hass, manager, system)
    await button.async_added_to_hass()
    conftest_base_entity_availability(manager, system, button)


@pytest.mark.asyncio
async def test_button_reset_smarthub_async_press(hass, manager_mz: Manager, caplog):
    manager = manager_mz
    system: lennox_system = manager.api.system_list[0]
    button = ResetSmartHubButton(hass, manager, system)

    manager.parameter_safety_turn_off(system.sysId)
    with patch.object(system, "reset_smart_controller") as reset_smart_controller:
        await button.async_press()
        assert reset_smart_controller.call_count == 1
        assert len(reset_smart_controller.await_args[0]) == 0

    manager.parameter_safety_turn_on(system.sysId)

    with patch.object(system, "reset_smart_controller") as reset_smart_controller:
        ex: HomeAssistantError = None
        try:
            await button.async_press()
        except HomeAssistantError as e:
            ex = e
        assert ex is not None
        assert reset_smart_controller.call_count == 0
        s = str(ex)
        assert "Unable to reset controller" in s
        assert button._myname in s
        assert "safety switch is on" in s

    manager.parameter_safety_turn_off(system.sysId)
    await conf_test_exception_handling(system, "reset_smart_controller", button, button.async_press)
    await conf_test_button_info_async_press(system, "reset_smart_controller", button, caplog)


@pytest.mark.asyncio
async def test_button_reset_smarthub_device_info(hass, manager: Manager):
    system: lennox_system = manager.api.system_list[0]
    await manager.create_devices()
    button = ResetSmartHubButton(hass, manager, system)

    identifiers = button.device_info["identifiers"]
    for ids in identifiers:
        assert ids[0] == LENNOX_DOMAIN
        assert ids[1] == system.unique_id


def test_button_reset_smarthub_entity_category(hass, manager: Manager):
    system: lennox_system = manager.api.system_list[0]
    button = ResetSmartHubButton(hass, manager, system)
    assert button.entity_category == "diagnostic"
