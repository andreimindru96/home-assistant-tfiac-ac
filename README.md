# TFIAC Local for Home Assistant

Local replacement for the removed Home Assistant `tfiac` integration. It talks directly to the AC over UDP port `7777`, based on the protocol used by `pytfiac`.

## What this gives you

- Local control, no Intelligent AC cloud login required
- A custom `climate` platform you can copy into Home Assistant
- A small CLI so you can discover and test the unit before wiring it into HA

## Files to copy into Home Assistant

Copy the folder below into your HA config directory:

`custom_components/tfiac_local`

Final path in Home Assistant should look like:

`/config/custom_components/tfiac_local`

## YAML configuration

Add this to `configuration.yaml`:

```yaml
climate:
  - platform: tfiac_local
    host: 192.168.1.50
    name: Starlight AC
    temperature_unit: C
    protocol_temperature_unit: F
    timeout: 5

switch:
  - platform: tfiac_local
    host: 192.168.1.50
    name: Starlight AC
    timeout: 5
```

Notes:

- `host` is the IP address of the AC on your LAN.
- `temperature_unit` is what Home Assistant should show.
- `protocol_temperature_unit` is what the AC expects on the wire.
- Start with `protocol_temperature_unit: F`, because that matches the historical `pytfiac` code. If the setpoint behaves incorrectly, switch it to `C`.
- The `switch` entry exposes the binary options supported by the device. It uses
  the same host as the climate entry but does not need the temperature settings.

## Home Assistant option switches

The switch platform reads the device status during setup and creates only the
controls reported by that AC. Supported controls are:

- Display
- Eco mode
- Turbo mode (`Opt_super`)
- Health mode (`Opt_healthy`)
- Anti-mildew
- Clean mode (`CleannessEnable`)
- Beeper (`BeepEnable`)
- Sleep mode (`Opt_sleepMode`)

Sleep and Eco modes are mutually exclusive on these devices. Enabling either
switch automatically disables the other in the same command.

Restart Home Assistant after adding the `switch` configuration. The entities
will have names such as `switch.starlight_ac_beeper` and
`switch.starlight_ac_eco_mode`.

## Discover the device

From this repo:

```bash
python3 -m custom_components.tfiac_local.cli discover
```

If broadcast discovery does not find the device, check your router DHCP lease table or the Intelligent AC app to identify the AC IP.

## Read current status

```bash
python3 -m custom_components.tfiac_local.cli status --host 192.168.1.50
```

## Send a test command

```bash
python3 -m custom_components.tfiac_local.cli set \
  --host 192.168.1.50 \
  --power on \
  --hvac cool \
  --temperature 24 \
  --fan Auto \
  --swing Both \
  --display-unit C \
  --protocol-unit F
```

Binary device options can be changed independently or included with the other
settings:

```bash
python3 -m custom_components.tfiac_local.cli set \
  --host 192.168.1.50 \
  --display on \
  --eco off \
  --super off \
  --healthy on \
  --beep off \
  --sleep off
```

Every option accepts `on` or `off`. The raw names printed by `status` are also
accepted as aliases: `--Opt_display`, `--Opt_ECO`, `--Opt_super`,
`--Opt_healthy`, `--BeepEnable`, and `--Opt_sleepMode`. For example, both
`--beep off` and `--BeepEnable off` disable the beeper.

## Behavior notes

- HVAC mode mapping:
  - `cool` -> `cool`
  - `heat` -> `heat`
  - `dry` -> `dehumi`
  - `fan_only` -> `fan`
  - `auto` -> `selfFeel`
- Selecting a non-off HVAC mode or using turn-on starts the unit.
- Changing target temperature, fan mode, or swing mode preserves the current power state.
- Home Assistant shows setting changes optimistically, then normal polling verifies the device state.
- The protocol is local UDP/XML and does not need your Intelligent AC credentials.

## Source references

- `pytfiac`: https://github.com/fredrike/pytfiac
- Old protocol behavior inferred from `pytfiac.py`
