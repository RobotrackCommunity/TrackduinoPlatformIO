# Trackduino for PlatformIO converter

Convert board existing from installation of RoboTrack IDE to PlatformIO board

## Navigation

- [Usage](#usage)
  - [Excluded Libraries](#excluded-libraries)
- [Versions table](#versions-table)
- [Disclaimer](#disclaimer)

## Usage

```bash
python3 convert.py -p "path/to/robotrackIde" 
```

System requirements:

- Python: 3.8+
- OS: Any (Linux and MacOS request `wine` for self-test, or skip it by `-s` argument.)
- RoboTrack IDE (installed or just program folder)

### Excluded Libraries

| Library Name                | Reason                                                                          |
|-----------------------------|---------------------------------------------------------------------------------|
| RobotrackIoTClient          | [Issue #1](https://github.com/RobotrackCommunity/TrackduinoPlatformIO/issues/1) |
| Adafruit_Circuit_Playground | Fully broken for Trackduino                                                     |
| Robot_Control               | Fully broken for Trackduino                                                     |
| Esplora                     | Fully broken for Trackduino                                                     |
| GSM                         | Fully broken for Trackduino                                                     |
| Servo                       | Fully broken for Trackduino                                                     |
| Firmata                     | Fully broken for Trackduino                                                     |

## Versions table

| RoboTrack IDE version | Test result      |
|-----------------------|------------------|
| 2.4.4                 | *Will be tested* |
| 2.4.0                 | *Will be tested* |
| 2.2.9                 | *Will be tested* |

### Disclaimer

*This project and its creator are not associated with Brain Development LLC.*
