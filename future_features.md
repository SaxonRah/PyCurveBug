# Future Features
This list contains features inspired by other octopus curve tracers, test equipment software, and industry tools that could align well with the CurveBug.

Some features are more valuable to individual hobbyists/engineers, while others shine in professional/production environments. 
For example, a production facility might prioritize **_Go/No-Go Limit Testing_** as a supplement to bed-of-nails testing, whereas an individual user doing component analysis might find **_Cursor Measurements with Curve Comparison & Overlay_** more immediately useful.

Implementation timeline for these features is uncertain, but contributions are welcome! If a feature particularly interests you, please feel free to fork the project and submit a pull request.

---

## **_Measurement & Analysis_**
### Cursor Measurements
- Draggable crosshair cursors to measure specific voltage/current points
- Delta cursors (cursor A - cursor B) for differential measurements
- Display voltage, current, and resistance at cursor position
- Snap-to-curve functionality
### Data Export & Capture
- Save curves to CSV/JSON with metadata (date, settings, component ID)
- PNG/SVG screenshot export with annotations
- Session logging for batch testing
- Quick export button in UI
### Curve Comparison & Overlay
- "Hold" function to freeze a reference curve
- Database of components and traces
- Overlay multiple saved curves with different colors/transparency
- Side-by-side comparison mode
- Difference mode (show deviation from reference)
### Calibration Features
- Calibration wizard
- Zero offset correction
- Known-good reference comparison
- Self-test routine
---
## **_Enhanced Display_**
### Persistence/Phosphor Mode
- Simulate oscilloscope persistence (fading older traces)
- Configurable decay time
- Useful for seeing drift or instability
### Mouse Position Readout
- Real-time voltage/current display following mouse cursor
- Nearest point indicator on curves
- Distance from zero crossing
### Automatic Parameter Extraction
- Forward voltage (Vf) for diodes
- Breakdown voltage (Vbr) for zeners
- Beta/hFE for transistors
- On-resistance for MOSFETs
- Display extracted parameters in info panel
- Useful with an automatic database of components and traces
---
## **_Testing Features_**
### Go/No-Go Limit Testing
- Define tolerance bands/windows
- Visual pass/fail indicators
- Audible alerts for failures
- Test result statistics
### Component Database
- Library of reference curves for common components
- Component identification helper
- Auto-suggest based on curve shape
- User-customizable library
### Annotations & Labels
- Text labels on curves
- Mark interesting features (breakdown, knee voltage)
- Color-coded regions
- Save annotations with curves
### Automated Testing
- Test sequence scripting
- Batch mode with auto-advance
- CSV import for test schedules
- Generate test reports
---
## **_Usability Improvements_**
### Presets & Quick Actions
- Save/load view presets (zoom, pan, colors)
- Quick zoom presets (2x, 5x, 10x, fit)
- One-click component type templates
- Keyboard shortcuts for common measurements
### Enhanced Grid Options
- Logarithmic scales
- Fine/coarse grid toggle
- Graticule divisions customization
- Minor grid lines
### Statistics & Averaging
- Average multiple sweeps to reduce noise
- Min/max envelope display
- Standard deviation shading
- Running average mode
### Dual Monitor Support
- Detachable windows
- Plot window separate from controls
- Multi-plot layouts
