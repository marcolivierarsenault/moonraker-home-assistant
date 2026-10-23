"""Update platform for Moonraker-managed components."""

from __future__ import annotations

from homeassistant.components.update import (
    UpdateEntity,
    UpdateEntityFeature,
)

from .const import DOMAIN, METHODS
from .entity import BaseMoonrakerEntity


async def async_setup_entry(hass, entry, async_add_entities):
    """Set update entities from the machine update status."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    machine_update = (coordinator.data or {}).get("machine_update")
    if not isinstance(machine_update, dict):
        machine_update = await coordinator.async_fetch_data(
            METHODS.MACHINE_UPDATE_STATUS
        )
    version_info = (machine_update or {}).get("version_info")
    if not isinstance(version_info, dict):
        return
    entities = []
    for component, info in version_info.items():
        if component == "system" or not isinstance(info, dict):
            continue
        if "version" not in info or "remote_version" not in info:
            continue
        entities.append(MoonrakerUpdate(coordinator, entry, component, info))
    async_add_entities(entities)


class MoonrakerUpdate(BaseMoonrakerEntity, UpdateEntity):
    """Update entity for one Moonraker-tracked component."""

    _attr_icon = "mdi:update"

    def __init__(self, coordinator, entry, component: str, info: dict) -> None:
        """Initialize the update entity for a component."""
        super().__init__(coordinator, entry)
        self._component = component
        self._info = info
        self._attr_unique_id = f"{entry.entry_id}_update_{component}"
        self._attr_name = f"{component.title()} Update"
        self._attr_has_entity_name = True
        client_type = str(info.get("client_type") or "")
        if client_type in ("web", "web_beta") or component in ("mainsail", "fluidd"):
            self._attr_supported_features = UpdateEntityFeature.INSTALL
        else:
            self._attr_supported_features = UpdateEntityFeature(0)
        self._update_attributes()

    def _update_attributes(self) -> None:
        """Refresh installed/latest versions from coordinator data."""
        info = (
            ((self.coordinator.data or {}).get("machine_update") or {}).get(
                "version_info"
            )
            or {}
        ).get(self._component) or self._info
        self._attr_installed_version = info.get("version")
        self._attr_latest_version = info.get("remote_version") or info.get("version")

    @property
    def extra_state_attributes(self):
        """Expose component metadata for dashboards."""
        info = (
            ((self.coordinator.data or {}).get("machine_update") or {}).get(
                "version_info"
            )
            or {}
        ).get(self._component) or self._info
        return {
            "component": self._component,
            "client_type": info.get("client_type"),
            "channel": info.get("channel"),
            "commits_behind": len(info.get("commits_behind") or []),
        }

    def _handle_coordinator_update(self) -> None:
        """Refresh versions when the coordinator updates."""
        self._update_attributes()
        self.async_write_ha_state()

    async def async_install(self, version=None, backup=False, **kwargs):
        """Install the latest update for a web client component."""
        await self.coordinator.async_send_data(
            METHODS.MACHINE_UPDATE_CLIENT_UPGRADE, {"name": self._component}
        )
        await self.coordinator.async_request_refresh()
