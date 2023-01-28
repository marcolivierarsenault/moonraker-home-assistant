"""Sample SYNC moonraker Client."""
import logging

from moonrakerpy import MoonrakerPrinter

TIMEOUT = 10


_LOGGER = logging.getLogger(__name__)

PRINTER_OBJECT = [
    "webhooks",
    "extruder",
    "heater_bed",
    "print_stats",
    "display_status",
    "filament_switch_sensor",
]


class MoonrakerApiClient:
    """Moonraker communication API"""

    def __init__(self, url: str) -> None:
        """Sample API Client."""
        self._url = url

    def connect_client(self) -> None:
        """Connect moonraker"""
        self._moonraker_client = MoonrakerPrinter(self._url)
        # self._moonraker_client = await hass.async_add_executor_job(
        #    MoonrakerPrinter(self._url)
        # )

    def get_data(self) -> dict:
        """Get data from the API."""
        return self._printer_status()

    def _printer_status(self) -> dict:
        """Get information from the API."""
        try:
            printer_status = {}
            for printer_obj in PRINTER_OBJECT:
                printer_status[printer_obj] = self._moonraker_client.query_status(
                    printer_obj
                )
            return printer_status

        except Exception as exception:  # pylint: disable=broad-except
            _LOGGER.error("Something really wrong happened! - %s", exception)
