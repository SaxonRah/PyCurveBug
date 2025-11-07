# PyCurveBug
OpenSource CurveBug Software

![Untitled.png](/Untitled.png)

REQUIRED:
* PySerial
* PyGame
* Numpy

Shows TWO I-V curves on the same plot:
* BLUE DUT1 (CH0 - Black lead):  CH0 (current) vs CH2 (voltage)
* RED DUT2 (CH1 - Red lead): CH1 (current) vs CH2 (voltage)

Axes are INVERTED per manual: "graphs are reversed left-to-right and up-to-down"
* Leftward = increasingly negative voltage
* Upward = increasingly negative current

Keys:
* Pause: P
* Single Trace: S
* Change Modes (Standard, Weak, Alternating Excitation): SPACEBAR
