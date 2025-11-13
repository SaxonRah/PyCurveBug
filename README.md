# PyCurveBug - Python Curve Viewer for vintageTEK CurveBug

**A Python-based curve tracer viewer for the vintageTEK CurveBug hardware, providing real-time I-V characteristic visualization with dual DUT comparison capabilities.**

**Note**: *This is an independent Python reimplementation based on reverse engineering and the original CurveBug C++ source code. For the official Windows application, please refer to vintageTEK.*

### Main Application
![MainApp.png](/screenshots/MainApp.png)
### Settings Window
![AllSettings.png](/screenshots/AllSettings.png)

## Overview

PyCurveBug is a cross-platform alternative to the original Windows CurveBug software, featuring:
- Real-time dual-channel I-V curve display
- Multiple excitation modes (4.7K, 100K weak, alternating)
- Pan and zoom navigation with fixed scale mode
- Auto-scaling for dynamic range adjustment
- Inverted axes matching CurveBug manual specifications
- Persistent settings configuration file with in app editor.
- Runs without CurveBug and can AutoDetect CurveBug

## Requirements
### Hardware
- vintageTEK CurveBug device
- USB connection (appears as COM port)

### Built Binaries
- None as far as we know. Just download and run!

### Raw Python:
#### Software
- Python 3.7+
  - PySerial
  - PyGame
  - NumPy
- **PyInstaller** *[only needed if building OS native applications]*

## Installation

#### Binaries:
```bash
# Download latest Binary from the Releases page and Run!
```

#### Python:
```bash
# Install required packages
pip install pyserial pygame numpy

# Clone or download PyCurveBug.py
# It should auto-detect your CurveBug
```

## Configuration
The software natively supports persistent settings via configuration file and has editable settings in the application. It will also autodetect your CurveBug if connected on startup.

## Usage
- Just run the binary!
- Or if you prefer running the code yourself:
```bash
python PyCurveBug.py
```

## Features

### Display Modes

**Fixed Scale (Default)**
- Matches original C++ CurveBug behavior
- X-axis: 0-2800 ADC units
- Y-axis: Floor at 7/8 down (-1837 to +262 range)
- Origin crosshair at ADC 2048 (voltage) and 0 (current)
- Supports pan and zoom navigation

**Auto-Scale**
- Dynamically adjusts to fit data range
- Useful for viewing signals outside normal range

### Excitation Modes

1. **4.7K Ohm (T command)** - Standard mode
2. **100K Ohm Weak (W command)** - Weak excitation mode
3. **Alternating (T+W)** - Shows both measurements overlaid
   - Bright traces: Current measurement
   - Dimmed traces: Previous measurement

### Channel Configuration

- **CH0 (Drive)**: Common reference voltage sweep
- **CH1 (Blue - Black lead)**: DUT1 voltage and current
- **CH2 (Red - Red lead)**: DUT2 voltage and current

336 data points per channel (1008 total samples per acquisition)

## Controls

### Keyboard

| Key | Function |
|-----|----------|
| **SPACEBAR** | Cycle excitation mode (4.7K → 100K → Alternating) |
| **P** | Pause/Resume scanning |
| **S** | Single channel mode (show only black trace) |
| **A** | Toggle Auto-scale / Fixed scale |
| **F** | Fit to window (auto zoom/pan to show all data) |
| **R** | Reset view (1x zoom, centered) |
| **Q / ESC** | Quit |

### Mouse (Fixed Scale Mode)

| Action | Function |
|--------|----------|
| **Click + Drag** | Pan view |
| **Wheel Up** | Zoom in |
| **Wheel Down** | Zoom out |

## Display Information

### Top Status Bar
- Controls
- Frame count
- FPS (frames per second)
- Current excitation mode
- Pause/Single channel/Scale indicators
- Connection status (Serial: CONNECTED / Serial: NOT CONNECTED)

### Bottom Info Panel
- CH1/CH2 current ranges and statistics
- DUT voltage ranges
- Drive voltage range
- Number of data points
- Settings Button

### On-Screen Legend
- Blue line: DUT1 (Black lead)
- Red line: DUT2 (Red lead)
- Yellow crosshairs: Origin (voltage=2048, current=0)

## Axis Orientation

Per CurveBug manual: "graphs are reversed left-to-right and up-to-down"

- **X-axis (Horizontal)**: DUT Voltage - **Leftward = more negative voltage**
- **Y-axis (Vertical)**: Current - **Upward = more negative current**
- Both axes are inverted for proper I-V curve display

## Technical Details

### Data Acquisition
- Protocol: 2016 bytes per acquisition (1008 16-bit samples)
- Sample format: Little-endian, masked to 12-bit (0-4095)
- First sample contains sync flag (0x8000), masked during processing
- Interleaved format: CH0, CH1, CH2, CH0, CH1, CH2...

### Channel Mapping
```
Position 0: Drive/reference voltage (used for current calculation)
Position 1: DUT1 voltage (Black lead)
Position 2: DUT2 voltage (Red lead)

Current = Drive_voltage - DUT_voltage (proportional to actual current)
```

### Fixed Scale Parameters
```python
ADC_MAX = 2800              # Full scale ADC range
ADC_ORIGIN = 2048           # Voltage reference (12-bit midpoint)
Y_RANGE = 2100              # Current range span
FLOOR_RATIO = 7/8           # 87.5% down (optimized for forward bias)
```

## Troubleshooting

### Connection Issues
```
Error: Connection to COM3 failed
```
- Verify CurveBug is connected via USB
- It should now auto-detect your CurveBug, if not Check Device Manager (Windows) or `ls /dev/tty*` (Linux/Mac) for correct COM port
- Update `serial_port` in configuration json file
- Try different baud rates if needed (default: 115200)

### Data Acquisition Errors
```
Error: Expected 1008 values
```
- USB cable issue - try different cable
- Power cycle the CurveBug device
- Check for USB 2.0 compatibility

### Traces Off-Screen
- Press **'F'** to auto-fit data to window
- Press **'R'** to reset to default view
- Use mouse wheel to zoom out
- Try **'A'** to toggle auto-scale mode

### Performance Issues
- Lower window size in configuration
- Close other applications
- Check FPS in status bar (should be ~20 FPS)

## Comparison with Original Software

| Feature | Original C++     | PyCurveBug                        |
|---------|------------------|------------------------------|
| Fixed scale | Y                | Y                            |
| Auto-scale | X                | Y                            |
| Pan/Zoom | X                | Y                            |
| Alternating mode | Y                | Y                            |
| Single channel | Y                | Y                            |
| Pause | Y                | Y                            |
| Cross-platform | X (Windows only) | Y (Any OS where Python runs) |

## Development

### Project Structure
```
PyCurveBug.py          # Main application
├── Configuration      # Settings and constants
├── CurveTracerDual    # Main application class
├── Data acquisition   # Serial communication
├── Rendering          # PyGame drawing routines
└── Event handling     # Keyboard/mouse input
```

### Contributing
Improvements and bug reports welcome! Key areas:
- Additional device support
- Export/save functionality
- Measurement cursors
- Peak detection

---

## GitHub Build Action
- Building no longer requires individuals to provide builds for an OS.
  - sigurasg (Sigurður Ásgeirsson) has added a build action on GitHub for all the major OSes.

(See `/pyinstaller_builds/Build.md` if you wish to build yourself.)

---

## Credits

- **Original CurveBug**: Robert Puckette, 2024-2025
- **PyCurveBug Python Implementation**: Robert Valentine, 2025
- **GitHub Build Action**: Sigurður Ásgeirsson, 2025
- Based on initial USB reverse engineering and now original C++ source code analysis

## License

This software follows the same MIT licensing as the original CurveBug software. See COPYING.txt in the original distribution.

## Version History

### v1.1 (Current)
- Initial Python implementation
- Fixed scale with pan/zoom
- Auto-scale mode
- Dual DUT comparison
- Three excitation modes
- Corrected channel mapping from C++ source
- Proper axis inversion per manual
- Persistent configuration settings with in app editor
- Runs without CurveBug and can AutoDetect CurveBug
