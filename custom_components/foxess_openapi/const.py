"""Constants for the FoxESS Cloud Open API integration."""
from __future__ import annotations

DOMAIN = "foxess_openapi"

CONF_API_KEY = "api_key"
CONF_DEVICE_SN = "device_sn"
CONF_REALTIME_INTERVAL = "realtime_interval"  # minutes
CONF_SETTINGS_INTERVAL = "settings_interval"  # minutes

DEFAULT_BASE_URL = "https://www.foxesscloud.com"
DEFAULT_REALTIME_INTERVAL = 5   # 288 calls/day
DEFAULT_SETTINGS_INTERVAL = 30  # 3 endpoints x 48 = 144 calls/day
MIN_REALTIME_INTERVAL = 2

# Documented rate limits (Open API doc, "Access frequency limit"):
#   1440 calls/day per inverter, query endpoints max 1/s each,
#   update endpoints max 1 every 2 s each.
QUERY_SPACING_S = 1.1
UPDATE_SPACING_S = 2.1

# Endpoints (paths are also used in the signature)
PATH_DEVICE_LIST = "/op/v0/device/list"
PATH_DEVICE_DETAIL = "/op/v1/device/detail"
PATH_REAL_QUERY = "/op/v1/device/real/query"
PATH_SOC_GET = "/op/v0/device/battery/soc/get"
PATH_SOC_SET = "/op/v0/device/battery/soc/set"
PATH_SETTING_GET = "/op/v0/device/setting/get"
PATH_SETTING_SET = "/op/v0/device/setting/set"
PATH_SCHED_FLAG_GET = "/op/v1/device/scheduler/get/flag"
PATH_SCHED_FLAG_SET = "/op/v1/device/scheduler/set/flag"
PATH_SCHED_GET = "/op/v1/device/scheduler/get"
PATH_SCHED_SET = "/op/v1/device/scheduler/enable"
PATH_ACCESS_COUNT = "/op/v0/user/getAccessCount"

WORK_MODES = [
    "SelfUse", "Feedin", "Backup", "ForceCharge", "ForceDischarge",
    "ForceCharge(BAT)", "ForceDischarge(BAT)",  # reported by scheduler/get enumList on this inverter
]
FORCE_CHARGE_MODES = ("ForceCharge", "ForceCharge(BAT)")
GROUP_KEYS = ("enable", "startHour", "startMinute", "endHour", "endMinute",
              "workMode", "minSocOnGrid", "fdSoc", "fdPwr", "maxSoc")

SETTING_KEYS = [
    "ExportLimit", "MinSoc", "MinSocOnGrid", "MaxSoc", "GridCode", "WorkMode",
    "ActivePowerLimit", "ExportLimitPower", "EpsOutPut", "MaxSetChargeCurrent",
    "MaxSetDischargeCurrent", "ECOMode", "Meter1Enable", "Meter2Enable",
    "SysSwitch", "GroundProtection", "LowPowerMode",
]

RUNNING_STATE = {
    160: "self-test", 161: "waiting", 162: "checking", 163: "on-grid",
    164: "off-grid", 165: "fault", 166: "permanent-fault", 167: "standby",
    168: "upgrading", 169: "fct", 170: "illegal",
}

# Error codes documented in "Common error solutions"
ERRNO_MISSING_HEADERS = 40256
ERRNO_BAD_BODY = 40257
ERRNO_TOO_FREQUENT = 40400
