# Raspberry Pi 5 to DRI0042 Wiring

This wiring matches the backend GPIO controller used when `ROBOT_ENABLED=true` and `ROBOT_CONTROLLER=gpio`.

## Bench Layout

```text
Raspberry Pi 5                         DRI0042 drivers                         DC motors
left side                              middle                                  right side

Pin 11 GPIO17 -- green  ------------>  Driver 1 IN1
Pin 13 GPIO27 -- yellow ------------>  Driver 1 IN2        Driver 1 M+ -----> Left motor terminal 1
Pin 12 GPIO18 -- blue   ------------>  Driver 1 PWM        Driver 1 M- -----> Left motor terminal 2
Pin 1  3.3V   -- orange ------------>  Driver 1 VCC
Pin 6  GND    -- black  ------------>  Driver 1 GND

Pin 15 GPIO22 -- green  ------------>  Driver 2 IN1
Pin 16 GPIO23 -- yellow ------------>  Driver 2 IN2        Driver 2 M+ -----> Right motor terminal 1
Pin 32 GPIO12 -- blue   ------------>  Driver 2 PWM        Driver 2 M- -----> Right motor terminal 2
Pin 17 3.3V   -- orange ------------>  Driver 2 VCC
Pin 20 GND    -- black  ------------>  Driver 2 GND

Pin 29 GPIO5  -- green  ------------>  Driver 3 IN1
Pin 31 GPIO6  -- yellow ------------>  Driver 3 IN2        Driver 3 M+ -----> Brush motor terminal 1
Pin 33 GPIO13 -- blue   ------------>  Driver 3 PWM        Driver 3 M- -----> Brush motor terminal 2
Pin 1  3.3V   -- orange ------------>  Driver 3 VCC
Pin 30 GND    -- black  ------------>  Driver 3 GND

12 V LiFePO4 battery + -- red ------>  Driver 1 VIN
12 V LiFePO4 battery + -- red ------>  Driver 2 VIN
12 V LiFePO4 battery + -- red ------>  Driver 3 VIN

12 V LiFePO4 battery - -- black ---->  Driver 1 GND
12 V LiFePO4 battery - -- black ---->  Driver 2 GND
12 V LiFePO4 battery - -- black ---->  Driver 3 GND
12 V LiFePO4 battery - -- black ---->  Raspberry Pi GND
```

## Wire Color Key

| Color | Signal |
| --- | --- |
| Red | 12 V battery motor power |
| Black | Common ground |
| Blue | PWM speed signal |
| Green | IN1 direction signal |
| Yellow | IN2 direction signal |
| Orange | 3.3 V logic power |

## Driver Map

| Motor | Driver | IN1 | IN2 | PWM | Logic VCC | Ground | Runtime PWM |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Left movement | Driver 1 | Pi pin 11 / GPIO17 | Pi pin 13 / GPIO27 | Pi pin 12 / GPIO18 | Pi pin 1 / 3.3V | Pi pin 6 / GND | 20% |
| Right movement | Driver 2 | Pi pin 15 / GPIO22 | Pi pin 16 / GPIO23 | Pi pin 32 / GPIO12 | Pi pin 17 / 3.3V | Pi pin 20 / GND | 20% |
| Brush | Driver 3 | Pi pin 29 / GPIO5 | Pi pin 31 / GPIO6 | Pi pin 33 / GPIO13 | Pi pin 1 or 17 / 3.3V | Pi pin 30 / GND | 100% |

## Backend GPIO Settings

The backend GPIO controller uses BCM GPIO numbers, not physical pin numbers:

```bash
ROBOT_CONTROLLER=gpio
ROBOT_DRIVE_SPEED=0.15
ROBOT_BRUSH_SPEED=1.00
ROBOT_PWM_FREQUENCY_HZ=1000
ROBOT_BRUSH_LEAD_SECONDS=2.0
```

Cleaning timing:

1. Brush motor starts at 100% PWM.
2. Backend waits `ROBOT_BRUSH_LEAD_SECONDS`, currently 2 seconds.
3. Left and right movement motors start at 20% PWM while the brush stays at 100%.
4. At the end of the timed panel pass, all motors stop.
5. The next timed panel pass repeats the same 2-second brush lead before movement.

All grounds must be tied together: Raspberry Pi GND, battery negative, Driver 1 GND, Driver 2 GND, and Driver 3 GND.

Power the Raspberry Pi from its own USB-C supply or a proper 5 V regulator. Do not connect the 12 V battery directly to the Raspberry Pi 5 V or 3.3 V pins.
