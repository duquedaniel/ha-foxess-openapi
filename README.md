# FoxESS Cloud Open API for Home Assistant

Custom integration that reads and **controls** a FoxESS hybrid inverter through the official
[FoxESS Cloud Open API](https://www.foxesscloud.com/i18n/en/OpenApiDocument.html).

> **Disclaimer:** this project is not endorsed by, affiliated with, maintained, authorized or
> sponsored by FoxESS. Use at your own risk; it writes settings to your inverter.

Tested on one FoxESS hybrid inverter with one battery. Other models may expose different
variables or scheduler options.

## Features
- 34 sensors from `/op/v1/device/real/query` (PV, load, grid import/export, battery SoC/power,
  energy totals for the Energy dashboard), plus running state, schedule and remaining API calls.
- Numbers: battery min SoC (off-grid / on-grid).
- Switch: scheduler master switch.
- Services:
  - `foxess_openapi.force_charge` – writes a ForceCharge window **and keeps the other enabled
    groups** (e.g. a 00:00-23:59 SelfUse base), trimming them around the window so no periods
    overlap. `replace_all: true` overwrites everything.
  - `foxess_openapi.set_schedule` – raw scheduler groups (V1 format, overwrites). Overlapping
    periods are rejected.
  - `foxess_openapi.disable_scheduler`, `set_min_soc`, `set_setting`,
    `get_setting` (returns data), `get_schedule` (returns data).

## Installation
### HACS (custom repository)
1. HACS → Integrations → ⋮ → Custom repositories → add `https://github.com/duquedaniel/ha-foxess-openapi` (type: Integration).
2. Install **FoxESS Cloud Open API** and restart Home Assistant.

### Manual
Copy `custom_components/foxess_openapi` to `/config/custom_components/` and restart.

## Setup
Settings → Devices & services → Add integration → **FoxESS Cloud Open API**, paste the API key
(foxesscloud.com → avatar → User Profile → API Management) and pick the inverter.

FoxESS allows 1440 API calls per inverter per day. Defaults: real-time every 5 min (288/day) and
settings/scheduler every 30 min (4 × 48 = 192/day); change in the integration options.

## Example: partial grid charge before an off-peak period ends
```yaml
# 05:55 - charge to 35 % at 1.5 kW, finishing at 07:59
- action: foxess_openapi.force_charge
  data:
    start_time: "06:43:00"
    end_time: "07:59:00"
    target_soc: 35
    power: 1500
    min_soc_on_grid: 10
# 08:01 - keep only the SelfUse base
- action: foxess_openapi.set_schedule
  data:
    groups:
      - {startHour: 0, startMinute: 0, endHour: 23, endMinute: 59, workMode: SelfUse,
         minSocOnGrid: 10, fdSoc: 10, fdPwr: 0, maxSoc: 100}
```

## Notes
- Scheduler periods must not overlap. The FoxESS app refuses overlapping periods, and in
  v0.1.1 a ForceCharge window written on top of a 00:00-23:59 SelfUse group did not run on a
  real inverter.
  Since v0.1.2 `force_charge` splits the other groups around the window (e.g. SelfUse
  00:00-06:42, ForceCharge 06:43-07:59, SelfUse 08:00-23:59).
- API host is `https://www.foxesscloud.com`.
- Signature: the doc table uses `url\r\ntoken\r\ntimestamp`; the official Python sample uses literal
  backslashes. The client tries the sample's form first and switches automatically if rejected.
- Uses Scheduler **V1** endpoints. `ForceCharge(BAT)` / `ForceDischarge(BAT)` are accepted when the
  inverter reports them.

## License
MIT
