"""Select platform for Moonraker integration."""

from homeassistant.components.select import SelectEntity

from .const import DOMAIN, METHODS, SLOW_UPDATE_CYCLES
from .entity import BaseMoonrakerEntity
from custom_components.moonraker.__init__ import _normalize_file_list


async def _files_updater(coordinator):
    """Fetch the printer's stored gcode files."""
    files = await coordinator.async_fetch_data(
        METHODS.SERVER_FILES_LIST, {"root": "gcodes"}, quiet=True
    )
    return {"file_list": _normalize_file_list(files)}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the moonraker select platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.add_data_updater(_files_updater, every=SLOW_UPDATE_CYCLES)
    await coordinator.async_refresh_files()
    async_add_entities([MoonrakerFileSelect(coordinator, entry)])


class MoonrakerFileSelect(BaseMoonrakerEntity, SelectEntity):
    """Select entity that chooses a stored gcode file for printing."""

    _attr_has_entity_name = True
    _attr_name = "Print File"
    _attr_icon = "mdi:file-code-outline"

    def __init__(self, coordinator, entry) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, entry)
        self.coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_print_file"

    @property
    def options(self) -> list[str]:
        """Return the stored gcode filenames."""
        file_list = (self.coordinator.data or {}).get("file_list") or {}
        files = file_list.get("files") if isinstance(file_list, dict) else file_list
        if not isinstance(files, list):
            return []
        return sorted(
            file["path"]
            for file in files
            if isinstance(file, dict) and file.get("path")
        )

    @property
    def current_option(self) -> str | None:
        """Return the currently selected filename."""
        return self.coordinator.selected_file

    async def async_select_option(self, option: str) -> None:
        """Store the selected file without starting a print."""
        if option not in self.options:
            return
        self.coordinator.selected_file = option
        self.async_write_ha_state()
