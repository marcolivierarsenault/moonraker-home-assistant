"""Support for Moonraker camera."""

from __future__ import annotations

import asyncio
from http import HTTPStatus
import logging
import posixpath
from urllib.parse import quote

from homeassistant.components.camera import Camera
from homeassistant.components.mjpeg.camera import MjpegCamera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import (
    CONF_API_KEY,
    CONF_TLS,
    CONF_URL,
    CONF_OPTION_CAMERA_STREAM,
    CONF_OPTION_CAMERA_SNAPSHOT,
    CONF_OPTION_CAMERA_PORT,
    CONF_OPTION_THUMBNAIL_PORT,
    DOMAIN,
    METHODS,
    PRINTSTATES,
    THUMBNAIL_EXTENSIONS,
)

_LOGGER = logging.getLogger(__name__)
DEFAULT_PORT = 80
SNAPSHOT_TIMEOUT = 10

# Moonraker webcam services whose stream_url serves an MJPEG stream
MJPEG_SERVICES = {"mjpegstreamer", "mjpegstreamer-adaptive", "uv4l-mjpeg"}

hardcoded_camera = {
    "name": "webcam",
    "location": "printer",
    "service": "mjpegstreamer-adaptive",
    "target_fps": "15",
    "stream_url": "/webcam/?action=stream",
    "snapshot_url": "/webcam/?action=snapshot",
    "flip_horizontal": False,
    "flip_vertical": False,
    "rotation": 0,
    "source": "database",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the available Moonraker camera."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    camera_cnt = 0

    try:
        if (
            config_entry.options.get(CONF_OPTION_CAMERA_STREAM) is not None
            and config_entry.options.get(CONF_OPTION_CAMERA_STREAM) != ""
        ):
            hardcoded_camera["stream_url"] = config_entry.options.get(
                CONF_OPTION_CAMERA_STREAM
            )
            hardcoded_camera["snapshot_url"] = config_entry.options.get(
                CONF_OPTION_CAMERA_SNAPSHOT
            )
            async_add_entities(
                [MoonrakerCamera(config_entry, coordinator, hardcoded_camera, 100)]
            )
            camera_cnt += 1
        else:
            cameras = await coordinator.async_fetch_data(METHODS.SERVER_WEBCAMS_LIST)
            session = async_get_clientsession(hass, verify_ssl=False)
            for camera_id, camera in enumerate(cameras["webcams"]):
                if _is_mjpeg_camera(camera):
                    entity = MoonrakerCamera(
                        config_entry, coordinator, camera, camera_id
                    )
                else:
                    entity = MoonrakerSnapshotCamera(
                        config_entry, coordinator, camera, camera_id, session
                    )
                async_add_entities([entity])
                camera_cnt += 1
    except Exception:
        _LOGGER.info("Could not add any cameras from the API list")

    if camera_cnt == 0:
        _LOGGER.info("No Camera in the list, trying hardcoded")
        async_add_entities(
            [MoonrakerCamera(config_entry, coordinator, hardcoded_camera, 0)]
        )

    async_add_entities(
        [
            PreviewCamera(
                config_entry,
                coordinator,
                async_get_clientsession(hass, verify_ssl=False),
            )
        ]
    )


def _is_mjpeg_camera(camera) -> bool:
    """Return True if the webcam provides an MJPEG stream."""
    if not camera.get("stream_url"):
        return False
    service = camera.get("service")
    return service is None or service in MJPEG_SERVICES


def _camera_url(config_entry, path) -> str:
    """Return the full URL of a webcam path."""
    if path.startswith("http"):
        return path
    port = config_entry.options.get(CONF_OPTION_CAMERA_PORT)
    if port is None or port == "":
        port = DEFAULT_PORT
    scheme = "https" if config_entry.data.get(CONF_TLS) else "http"
    return f"{scheme}://{config_entry.data.get(CONF_URL)}:{port}{path}"


class MoonrakerCamera(MjpegCamera):
    """Representation of an Moonraker Camera Stream."""

    def __init__(self, config_entry, coordinator, camera, camera_id) -> None:
        """Initialize as a subclass of MjpegCamera."""

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)}
        )
        if (
            config_entry.options.get(CONF_OPTION_CAMERA_PORT) is not None
            and config_entry.options.get(CONF_OPTION_CAMERA_PORT) != ""
        ):
            self.port = config_entry.options.get(CONF_OPTION_CAMERA_PORT)
        else:
            self.port = DEFAULT_PORT

        if camera["stream_url"].startswith("http"):
            self.url = ""
        else:
            self.url = f"http://{config_entry.data.get(CONF_URL)}:{self.port}"

        _LOGGER.info(f"Connecting to camera: {self.url}{camera['stream_url']}")

        super().__init__(
            device_info=self._attr_device_info,
            mjpeg_url=f"{self.url}{camera['stream_url']}",
            name=f"{coordinator.api_device_name} {camera['name']}",
            still_image_url=f"{self.url}{camera['snapshot_url']}",
            unique_id=f"{config_entry.entry_id}_{camera['name']}_{camera_id}",
        )


class MoonrakerSnapshotCamera(Camera):
    """Moonraker webcam without an MJPEG stream, served from its snapshot URL."""

    def __init__(self, config_entry, coordinator, camera, camera_id, session) -> None:
        """Initialize the snapshot camera."""

        super().__init__()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)}
        )
        self._attr_name = f"{coordinator.api_device_name} {camera['name']}"
        self._attr_unique_id = f"{config_entry.entry_id}_{camera['name']}_{camera_id}"
        self._session = session
        snapshot_url = camera.get("snapshot_url")
        self._snapshot_url = (
            _camera_url(config_entry, snapshot_url) if snapshot_url else None
        )
        # Only send the API key to the printer itself, not to absolute URLs
        api_key = config_entry.data.get(CONF_API_KEY)
        self._headers = (
            {"X-Api-Key": api_key}
            if api_key and snapshot_url and not snapshot_url.startswith("http")
            else None
        )
        _LOGGER.info(
            f"Connecting to {camera.get('service')} camera via snapshots: "
            f"{self._snapshot_url}"
        )

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return the current snapshot."""
        del width, height
        if self._snapshot_url is None:
            return None
        async with asyncio.timeout(SNAPSHOT_TIMEOUT):
            response = await self._session.get(
                self._snapshot_url, headers=self._headers
            )
            response.raise_for_status()
            return await response.read()


class PreviewCamera(Camera):
    """Representation of the gcode thumnail."""

    _attr_is_streaming = False

    def __init__(self, config_entry, coordinator, session) -> None:
        """Initialize as a subclass of Camera for the Thumbnail Preview."""

        super().__init__()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)}
        )
        self.url = config_entry.data.get(CONF_URL)
        self._scheme = "https" if config_entry.data.get(CONF_TLS) else "http"
        api_key = config_entry.data.get(CONF_API_KEY)
        self._headers = {"X-Api-Key": api_key} if api_key else None
        self.coordinator = coordinator
        self._attr_name = f"{coordinator.api_device_name} Thumbnail"
        self._attr_unique_id = f"{config_entry.entry_id}_thumbnail"
        self._session = session
        self._current_pic = None
        self._current_path = ""

        if (
            config_entry.options.get(CONF_OPTION_THUMBNAIL_PORT) is not None
            and config_entry.options.get(CONF_OPTION_THUMBNAIL_PORT) != ""
        ):
            self.port = config_entry.options.get(CONF_OPTION_THUMBNAIL_PORT)
        else:
            self.port = DEFAULT_PORT

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return current camera image."""
        _LOGGER.debug("Trying to get thumbnail ")
        state = (
            self.coordinator.data.get("status", {}).get("print_stats", {}).get("state")
        )
        if state != PRINTSTATES.PRINTING.value:
            _LOGGER.debug("Not printing, no thumbnail")
            return None

        del width, height

        new_path = self.coordinator.data["thumbnails_path"]

        _LOGGER.debug(f"Thumbnail new_path: {new_path}")
        if self._current_path == new_path and self._current_pic is not None:
            _LOGGER.debug("no change in thumbnail, returning cached")
            return self._current_pic

        if new_path == "" or new_path is None:
            self._current_pic = None
            self._current_path = ""
            _LOGGER.debug("Empty path, no thumbnail")
            return None

        pic = await self._async_fetch_thumbnail(new_path)
        if pic == HTTPStatus.NOT_FOUND:
            pic = await self._async_fetch_thumbnail_from_folder(new_path)
        if pic is None or isinstance(pic, int):
            # Do not cache a failed fetch, so the next request tries again
            self._current_pic = None
            self._current_path = ""
            return None

        self._current_path = new_path
        self._current_pic = pic

        return self._current_pic

    async def _async_fetch_thumbnail(self, path: str) -> bytes | int:
        """Fetch a thumbnail file, returning the HTTP status if it fails."""
        url = (
            f"{self._scheme}://{self.url}:{self.port}/server/files/gcodes/{quote(path)}"
        )
        _LOGGER.debug(f"Fetching new thumbnail: {url}")
        response = await self._session.get(url, headers=self._headers)
        if response.status != 200:
            _LOGGER.debug(f"Thumbnail request returned HTTP {response.status}: {url}")
            response.release()
            return response.status
        return await response.read()

    async def _async_fetch_thumbnail_from_folder(self, path: str) -> bytes | int | None:
        """Use the image in a per-file thumbnail folder when metadata names a missing file.

        Some firmware (for example QIDI's for ``.gcode.3mf`` files) stores the
        thumbnail as ``.thumbs/<file>/plate_<n>.png`` but always reports
        ``plate_1.png`` in the file metadata.
        """
        thumb_dir = posixpath.dirname(path)
        if posixpath.basename(posixpath.dirname(thumb_dir)) != ".thumbs":
            # A shared .thumbs folder holds the images of every file
            return None

        try:
            listing = await self.coordinator.async_fetch_data(
                METHODS.SERVER_FILES_GET_DIRECTORY,
                {"path": f"gcodes/{thumb_dir}", "extended": False},
                quiet=True,
            )
        except UpdateFailed:
            _LOGGER.debug(f"Could not list thumbnail folder {thumb_dir}")
            return None

        files = listing.get("files") if isinstance(listing, dict) else None
        images = [
            item
            for item in files or []
            if isinstance(item, dict)
            and str(item.get("filename", "")).lower().endswith(THUMBNAIL_EXTENSIONS)
        ]
        # A stale listing may still name the file that just failed.
        images = [
            item
            for item in images
            if posixpath.join(thumb_dir, item["filename"]) != path
        ]
        if not images:
            return None

        best = max(images, key=_thumbnail_size)
        best_path = posixpath.join(thumb_dir, best["filename"])
        _LOGGER.debug(f"Thumbnail {path} is missing, using {best_path}")
        return await self._async_fetch_thumbnail(best_path)


def _thumbnail_size(item: dict) -> float:
    """Return a listed file's size, treating unknown sizes as the smallest."""
    try:
        return float(item.get("size"))
    except (TypeError, ValueError):
        return -1.0
