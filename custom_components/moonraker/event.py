"""Event platform for Moonraker print lifecycle events."""

from homeassistant.components.event import EventEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_PRINT_EVENT
from .entity import BaseMoonrakerEntity

EVENT_TYPES = (
    "print_started",
    "print_resumed",
    "print_paused",
    "print_completed",
    "print_cancelled",
    "print_error",
)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the print lifecycle event entity."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MoonrakerPrintEvent(coordinator, entry)])


class MoonrakerPrintEvent(BaseMoonrakerEntity, EventEntity):
    """Entity emitting events on print state transitions."""

    _attr_event_types = list(EVENT_TYPES)
    _attr_icon = "mdi:printer-3d-nozzle-outline"

    def __init__(self, coordinator, entry) -> None:
        """Initialize the event entity."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_print_events"
        self._attr_name = "Print Events"
        self._attr_has_entity_name = True
        self._entry_id = entry.entry_id

    async def async_added_to_hass(self) -> None:
        """Subscribe to analyzer lifecycle dispatches."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_PRINT_EVENT}_{self._entry_id}",
                self._handle_print_event,
            )
        )

    @callback
    def _handle_print_event(self, payload: dict) -> None:
        """Fire the corresponding event entity event."""
        event_type = payload.get("type")
        if event_type not in self._attr_event_types:
            return
        self._trigger_event(event_type, {"filename": payload.get("filename") or ""})
        self.async_write_ha_state()
