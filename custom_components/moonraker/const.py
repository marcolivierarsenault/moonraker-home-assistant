"""Constants for Moonraker."""

from enum import Enum

from homeassistant.const import Platform

# Base component constants
DOMAIN = "moonraker"
DOMAIN_DATA = f"{DOMAIN}_data"
VERSION = "1.13.4"
MANIFACTURER = "@marcolivierarsenault"

# Platforms
PLATFORMS = [
    Platform.SENSOR,
    Platform.CAMERA,
    Platform.BUTTON,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.LIGHT,
    Platform.SELECT,
    Platform.UPDATE,
    Platform.EVENT,
]

CONF_API_KEY = "api_key"
CONF_URL = "url"
CONF_PORT = "port"
CONF_TLS = "tls"
CONF_PRINTER_NAME = "printer_name"
CONF_OPTION_CAMERA_STREAM = "camera_stream_url"
CONF_OPTION_CAMERA_SNAPSHOT = "camera_snapshot_url"
CONF_OPTION_POLLING_RATE = "polling_rate"
DEFAULT_POLLING_RATE = 40
MIN_POLLING_RATE = 7
PRINTING_POLLING_RATE = 40 / 3
PUSH_UPDATE_INTERVAL = 5
SLOW_UPDATE_CYCLES = 4
QUEUE_META_JOB_LIMIT = 8
NOTIFY_STATUS_UPDATE = "notify_status_update"
NOTIFY_KLIPPY_DISCONNECTED = "notify_klippy_disconnected"
NOTIFY_KLIPPY_SHUTDOWN = "notify_klippy_shutdown"
NOTIFY_KLIPPY_READY = "notify_klippy_ready"
NOTIFY_GCODE_RESPONSE = "notify_gcode_response"
CONF_OPTION_QUIET_UNREACHABLE = "quiet_unreachable_devices"
CONF_OPTION_CAMERA_PORT = "camera_port"
CONF_OPTION_THUMBNAIL_PORT = "thumbnail_port"
CONF_OPTION_POWER_SENSOR = "power_sensor"
CONF_OPTION_MAX_FLOW = "max_flow_mm3"
CONF_OPTION_ENERGY_RATE = "energy_rate"
DEFAULT_MAX_FLOW_MM3 = 15.0
CONF_OPTION_NOTIFY_SERVICE = "notify_service"
CONF_OPTION_POWER_SWITCH = "power_switch_entity"
CONF_OPTION_POWER_OFF_DELAY = "power_off_delay_min"
CONF_OPTION_POWER_OFF_MAX_TEMP = "power_off_max_temp"
CONF_OPTION_AMBIENT_SENSOR = "ambient_sensor"
CONF_OPTION_HUMIDITY_SENSOR = "humidity_sensor"
CONF_OPTION_AI_TASK_ENTITY = "ai_task_entity"
CONF_OPTION_VISION_CAMERA = "vision_camera"
CONF_OPTION_PANEL_ROLE = "panel_role"
DEFAULT_POWER_OFF_DELAY_MIN = 15.0
DEFAULT_POWER_OFF_MAX_TEMP = 50.0
SIGNAL_PRINT_EVENT = "moonraker_print_event"
SIGNAL_PRINTCAST = "moonraker_printcast"

# API dict keys
DEVICE_TYPE = "device_type"
HOSTNAME = "hostname"
OBJ = "objects"

# API timeout
TIMEOUT = 10

# CONNECTION DATA
DEFAULT_PORT = 7125


class METHODS(Enum):
    """API methods."""

    HOST_RESTART = "machine.reboot"
    HOST_SHUTDOWN = "machine.shutdown"
    MACHINE_DEVICE_POWER_DEVICES = "machine.device_power.devices"
    MACHINE_DEVICE_POWER_GET_DEVICE = "machine.device_power.get_device"
    MACHINE_DEVICE_POWER_POST_DEVICE = "machine.device_power.post_device"
    MACHINE_SERVICES_START = "machine.services.start"
    MACHINE_SERVICES_STOP = "machine.services.stop"
    MACHINE_SERVICES_RESTART = "machine.services.restart"
    MACHINE_UPDATE_REFRESH = "machine.update.refresh"
    MACHINE_UPDATE_STATUS = "machine.update.status"
    MACHINE_UPDATE_CLIENT_UPGRADE = "machine.update.client.upgrade"
    MACHINE_SYSTEM_INFO = "machine.system_info"
    PRINTER_EMERGENCY_STOP = "printer.emergency_stop"
    PRINTER_INFO = "printer.info"
    PRINTER_PRINT_START = "printer.print.start"
    PRINTER_GCODE_HELP = "printer.gcode.help"
    PRINTER_GCODE_SCRIPT = "printer.gcode.script"
    PRINTER_OBJECTS_LIST = "printer.objects.list"
    PRINTER_OBJECTS_QUERY = "printer.objects.query"
    PRINTER_OBJECTS_SUBSCRIBE = "printer.objects.subscribe"
    PRINTER_PRINT_CANCEL = "printer.print.cancel"
    PRINTER_PRINT_PAUSE = "printer.print.pause"
    PRINTER_PRINT_RESUME = "printer.print.resume"
    PRINTER_FIRMWARE_RESTART = "printer.firmware_restart"
    SERVER_FILES_LIST = "server.files.list"
    SERVER_FILES_METADATA = "server.files.metadata"
    SERVER_FILES_DELETE_FILE = "server.files.delete_file"
    SERVER_GCODE_STORE = "server.gcode_store"
    SERVER_HISTORY_TOTALS = "server.history.totals"
    SERVER_HISTORY_RESET_TOTALS = "server.history.reset_totals"
    SERVER_JOB_QUEUE_STATUS = "server.job_queue.status"
    SERVER_JOB_QUEUE_START = "server.job_queue.start"
    SERVER_JOB_QUEUE_PAUSE = "server.job_queue.pause"
    SERVER_JOB_QUEUE_POST_JOB = "server.job_queue.post_job"
    SERVER_JOB_QUEUE_DELETE_JOB = "server.job_queue.delete_job"
    SERVER_JOB_QUEUE_JUMP = "server.job_queue.jump"
    SERVER_INFO = "server.info"
    SERVER_RESTART = "server.restart"
    SERVER_WEBCAMS_LIST = "server.webcams.list"
    SERVER_SPOOLMAN_ID = "server.spoolman.status"
    SERVER_SPOOLMAN_PROXY = "server.spoolman.proxy"


class ExtendedEnum(Enum):
    """Extended Enum class."""

    @classmethod
    def list(cls):
        """Return a list of all enum values."""
        return [c.value for c in cls]


class PRINTSTATES(ExtendedEnum):
    """Printer state."""

    STANDBY = "standby"
    PRINTING = "printing"
    PAUSED = "paused"
    COMPLETE = "complete"
    CANCELLED = "cancelled"
    ERROR = "error"


class PRINTERSTATES(ExtendedEnum):
    """Printer state."""

    READY = "ready"
    STARTUP = "startup"
    SHUTDOWN = "shutdown"
    ERROR = "error"
