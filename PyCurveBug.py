#!/usr/bin/env python3
"""
CurveBug Tracer - Dual DUT Comparison

REQUIRED:
PySerial
PyGame
Numpy

Shows TWO I-V curves on the same plot:
- DUT1 (CH0 - Black lead):  CH0 (current) vs CH2 (voltage)
- DUT2 (CH1 - Red lead): CH1 (current) vs CH2 (voltage)

1. Axes are INVERTED per manual: "graphs are reversed left-to-right and up-to-down"
   - Leftward = increasingly negative voltage
   - Upward = increasingly negative current
2. Axis labels: Voltage (X-axis) vs Current (Y-axis) for I-V curves
3. Data interpretation matches official CurveBug software
"""

import pygame
import serial
import struct
import numpy as np
import sys
import time

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
LIGHT_GRAY = (200, 200, 200)
GRAY = (100, 100, 100)
MID_GRAY = (50, 50, 50)
DARK_GRAY = (30, 30, 30)
RED = (255, 50, 50)
BLUE = (50, 150, 255)
GREEN = (50, 255, 150)
YELLOW = (255, 255, 50)
ORANGE = (255, 150, 50)

# CONFIGURATION HERE

SERIAL_COM_PORT = 'COM3'
WINDOW_HEIGHT_SIZE = 1080
WINDOW_WIDTH_SIZE = 1080

DUT1_CH0_BLACK_LEAD = BLUE
DUT2_CH1_RED_LEAD = RED

# Dimmed versions for alternating mode (older trace)
DUT1_CH0_DIMMED = (25, 75, 128)  # Dark blue
DUT2_CH1_DIMMED = (128, 25, 25)  # Dark red

BACKGROUND_COLOR = BLACK
GRID_BACKGROUND_COLOR = DARK_GRAY
GRID_COLOR = MID_GRAY
CROSSHAIR_COLOR = YELLOW

LABEL_COLOR = LIGHT_GRAY
AXIS_TITLE_COLOR = WHITE
BORDER_COLOR = GRAY
DUT_VOLTAGE_COLOR = GREEN


# CONFIGURATION HERE


class CurveTracerDual:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("PyBUG a Curve Viewer for VintageTek CurveBug")
        self.width = WINDOW_WIDTH_SIZE
        self.height = WINDOW_HEIGHT_SIZE
        self.screen = pygame.display.set_mode((self.width, self.height))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 28)
        self.small_font = pygame.font.Font(None, 20)
        self.serial = None

        # Data - per manual: 336 points per channel from 1008 total samples
        # Standard mode (T command - 4.7K)
        self.ch0_std = []  # DUT1 current (computed)
        self.ch1_std = []  # DUT2 current (computed)
        self.ch2_std = []  # Drive voltage (reference)
        self.ch0_voltage_std = []  # DUT1 voltage (for X-axis)
        self.ch1_voltage_std = []  # DUT2 voltage (for X-axis)

        # Weak mode (W command - 100K)
        self.ch0_weak = []  # DUT1 current (computed)
        self.ch1_weak = []  # DUT2 current (computed)
        self.ch2_weak = []  # Drive voltage (reference)
        self.ch0_voltage_weak = []  # DUT1 voltage (for X-axis)
        self.ch1_voltage_weak = []  # DUT2 voltage (for X-axis)

        # Pointers to current active datasets
        self.ch0 = []
        self.ch1 = []
        self.ch2 = []
        self.ch0_voltage = []
        self.ch1_voltage = []

        self.frame_count = 0
        self.fps = 0

        # Alternating mode state
        self.alt_use_weak = False  # For alternating mode: False=T, True=W
        self.last_mode_was_weak = False  # Track what was captured last

        # Control modes
        self.paused = False
        self.single_channel = False  # S key - show only black trace
        self.excitation_mode = 0  # 0=4.7k(T), 1=100k weak(W), 2=alternating(T+W)

    def connect(self):
        try:
            self.serial = serial.Serial(SERIAL_COM_PORT, 115200, timeout=1)
            time.sleep(0.1)
            self.serial.reset_input_buffer()
            print(f"Connected to {SERIAL_COM_PORT}")
            return True
        except Exception as e:
            print(f"Connection to {SERIAL_COM_PORT} failed: {e}")
            return False

    def acquire(self):
        """
        Acquire 3-channel data
        Per manual: 2016 bytes total (1008 16-bit samples masked to 12-bit)
        Format: Sync word + 335 groups of (CH0, CH1, CH2) = 1 + 1005 = 1006 values
        Skip first value (sync), take next 1005 values as 335 groups of 3

        Modes:
        0 = Standard (T command, 4.7K)
        1 = Weak (W command, 100K)
        2 = Alternating (T and W, switching each frame)
        """
        try:
            # Determine command based on mode
            if self.excitation_mode == 0:
                # Standard mode - always T
                command = b'T'
                store_as_weak = False
            elif self.excitation_mode == 1:
                # Weak mode - always W
                command = b'W'
                store_as_weak = True
            else:
                # Alternating mode - switch between T and W
                if self.alt_use_weak:
                    command = b'W'
                    store_as_weak = True
                else:
                    command = b'T'
                    store_as_weak = False
                # Toggle for next acquisition
                self.alt_use_weak = not self.alt_use_weak

            # Send command and acquire data
            self.serial.reset_input_buffer()
            self.serial.write(command)

            data = bytearray()
            start = time.time()
            while len(data) < 2016:
                if time.time() - start > 0.5:
                    break
                if self.serial.in_waiting > 0:
                    data.extend(self.serial.read(min(self.serial.in_waiting, 2016 - len(data))))

            if len(data) != 2016:
                return False

            # Decode little-endian 16-bit values, but MASK to 12-bit per manual
            values = []
            for i in range(0, len(data), 2):
                val = struct.unpack('<H', data[i:i + 2])[0]
                values.append(val & 0x0FFF)  # Mask to 12 bits (0-4095)

            # Skip sync word (first value), take complete groups of 3
            # Per manual: 336 points per channel
            values = values[1:1006]  # 335 groups x 3 = 1005 values

            # Extract interleaved channels: CH0, CH1, CH2, CH0, CH1, CH2, ...
            ch0_raw = values[0::3]  # DUT1 voltage measurement (Black lead)
            ch1_raw = values[1::3]  # DUT2 voltage measurement (Red lead)
            ch2_raw = values[2::3]  # Drive voltage sweep

            # Compute actual current: I = (V_drive - V_dut) / R_sense
            ch0_current = [ch2_raw[i] - ch0_raw[i] for i in range(len(ch2_raw))]
            ch1_current = [ch2_raw[i] - ch1_raw[i] for i in range(len(ch2_raw))]

            # Store in appropriate dataset
            if store_as_weak:
                self.ch0_voltage_weak = ch0_raw
                self.ch1_voltage_weak = ch1_raw
                self.ch0_weak = ch0_current
                self.ch1_weak = ch1_current
                self.ch2_weak = ch2_raw
                self.last_mode_was_weak = True
            else:
                self.ch0_voltage_std = ch0_raw
                self.ch1_voltage_std = ch1_raw
                self.ch0_std = ch0_current
                self.ch1_std = ch1_current
                self.ch2_std = ch2_raw
                self.last_mode_was_weak = False

            # Point current data to most recent acquisition
            if store_as_weak:
                self.ch0_voltage = self.ch0_voltage_weak
                self.ch1_voltage = self.ch1_voltage_weak
                self.ch0 = self.ch0_weak
                self.ch1 = self.ch1_weak
                self.ch2 = self.ch2_weak
            else:
                self.ch0_voltage = self.ch0_voltage_std
                self.ch1_voltage = self.ch1_voltage_std
                self.ch0 = self.ch0_std
                self.ch1 = self.ch1_std
                self.ch2 = self.ch2_std

            return True

        except Exception as e:
            print(f"Error: {e}")
            return False

    def draw_trace(self, ch0_voltage, ch1_voltage, ch0_current, ch1_current,
                   color1, color2, rect, x_min, x_max, y_min, y_max, line_width=3):
        """Helper function to draw a single trace (DUT1 and optionally DUT2)"""
        # DUT1 (Blue/Dark Blue)
        points1 = []
        for i in range(len(ch0_voltage)):
            x_norm = (ch0_voltage[i] - x_min) / (x_max - x_min)
            y_norm = (ch0_current[i] - y_min) / (y_max - y_min)
            # INVERTED per manual: right-to-left X, top-to-bottom Y
            px = int(rect.right - (x_norm * rect.width))
            py = int(rect.top + (y_norm * rect.height))
            points1.append((px, py))

        if len(points1) > 1:
            pygame.draw.lines(self.screen, color1, False, points1, line_width)

        # DUT2 (Red/Dark Red) - only if NOT in single channel mode
        if not self.single_channel:
            points2 = []
            for i in range(len(ch1_voltage)):
                x_norm = (ch1_voltage[i] - x_min) / (x_max - x_min)
                y_norm = (ch1_current[i] - y_min) / (y_max - y_min)
                # INVERTED per manual
                px = int(rect.right - (x_norm * rect.width))
                py = int(rect.top + (y_norm * rect.height))
                points2.append((px, py))

            if len(points2) > 1:
                pygame.draw.lines(self.screen, color2, False, points2, line_width)

    def draw_dual_xy_plot(self, rect):
        """
        Draw I-V curves - Current (X) vs Voltage (Y) with inversions

        Manual: "graphs are reversed left-to-right and up-to-down"
        - Leftward = increasingly negative current
        - Upward = increasingly negative voltage

        Plot: Current (CH0/CH1) on X, Voltage (CH2) on Y, BOTH AXES INVERTED
        """
        pygame.draw.rect(self.screen, GRID_BACKGROUND_COLOR, rect)

        title = self.font.render("I-V Characteristics - Dual DUT Comparison", True, WHITE)
        title_rect = title.get_rect(center=(rect.centerx, rect.y - 30))
        self.screen.blit(title, title_rect)

        if not self.ch0 or not self.ch1 or not self.ch2 or len(self.ch2) < 2:
            text = self.font.render("No Data", True, WHITE)
            text_rect = text.get_rect(center=rect.center)
            self.screen.blit(text, text_rect)
            pygame.draw.rect(self.screen, BORDER_COLOR, rect, 2)
            return

        # For I-V curves: DUT Voltage (X) vs Current (Y)
        # In alternating mode, include both std and weak data for range calculation
        if self.excitation_mode == 2 and len(self.ch0_std) > 0 and len(self.ch0_weak) > 0:
            # Alternating mode - calculate ranges from both datasets
            x1_data_std = np.array(self.ch0_voltage_std)
            x2_data_std = np.array(self.ch1_voltage_std)
            y1_data_std = np.array(self.ch0_std)
            y2_data_std = np.array(self.ch1_std)

            x1_data_weak = np.array(self.ch0_voltage_weak)
            x2_data_weak = np.array(self.ch1_voltage_weak)
            y1_data_weak = np.array(self.ch0_weak)
            y2_data_weak = np.array(self.ch1_weak)

            # Combine all for range calculation
            x_min = min(x1_data_std.min(), x2_data_std.min(), x1_data_weak.min(), x2_data_weak.min())
            x_max = max(x1_data_std.max(), x2_data_std.max(), x1_data_weak.max(), x2_data_weak.max())
            y_min = min(y1_data_std.min(), y2_data_std.min(), y1_data_weak.min(), y2_data_weak.min())
            y_max = max(y1_data_std.max(), y2_data_std.max(), y1_data_weak.max(), y2_data_weak.max())
        else:
            # Normal mode - use current data
            x1_data = np.array(self.ch0_voltage)
            x2_data = np.array(self.ch1_voltage)
            y1_data = np.array(self.ch0)
            y2_data = np.array(self.ch1)

            x_min = min(x1_data.min(), x2_data.min())
            x_max = max(x1_data.max(), x2_data.max())
            y_min = min(y1_data.min(), y2_data.min())
            y_max = max(y1_data.max(), y2_data.max())

        x_margin = (x_max - x_min) * 0.1 if x_max > x_min else 100
        x_min -= x_margin
        x_max += x_margin

        y_margin = (y_max - y_min) * 0.1 if y_max > y_min else 100
        y_min -= y_margin
        y_max += y_margin

        if x_max == x_min:
            x_max = x_min + 1
        if y_max == y_min:
            y_max = y_min + 1

        # Grid
        for i in range(11):
            x = rect.x + (i * rect.width) // 10
            pygame.draw.line(self.screen, GRID_COLOR, (x, rect.y), (x, rect.bottom), 1)
            y = rect.y + (i * rect.height) // 10
            pygame.draw.line(self.screen, GRID_COLOR, (rect.x, y), (rect.right, y), 1)

        # Crosshairs at origin
        zero_x_norm = (0 - x_min) / (x_max - x_min) if x_min < 0 < x_max else 0.5
        zero_y_norm = (0 - y_min) / (y_max - y_min) if y_min < 0 < y_max else 0.5

        # INVERTED per manual
        zero_x_pos = int(rect.right - (zero_x_norm * rect.width))
        zero_y_pos = int(rect.top + (zero_y_norm * rect.height))

        pygame.draw.line(self.screen, CROSSHAIR_COLOR, (zero_x_pos, rect.y), (zero_x_pos, rect.bottom), 2)
        pygame.draw.line(self.screen, CROSSHAIR_COLOR, (rect.x, zero_y_pos), (rect.right, zero_y_pos), 2)

        # Draw traces based on mode
        if self.excitation_mode == 2 and len(self.ch0_std) > 0 and len(self.ch0_weak) > 0:
            # Alternating mode - draw both traces
            # Draw the older trace first (dimmed, in background)
            if self.last_mode_was_weak:
                # Just captured weak, so std is older - draw std dimmed
                self.draw_trace(self.ch0_voltage_std, self.ch1_voltage_std,
                                self.ch0_std, self.ch1_std,
                                DUT1_CH0_DIMMED, DUT2_CH1_DIMMED,
                                rect, x_min, x_max, y_min, y_max, line_width=2)
                # Draw weak trace bright (current)
                self.draw_trace(self.ch0_voltage_weak, self.ch1_voltage_weak,
                                self.ch0_weak, self.ch1_weak,
                                DUT1_CH0_BLACK_LEAD, DUT2_CH1_RED_LEAD,
                                rect, x_min, x_max, y_min, y_max, line_width=3)
            else:
                # Just captured std, so weak is older - draw weak dimmed
                self.draw_trace(self.ch0_voltage_weak, self.ch1_voltage_weak,
                                self.ch0_weak, self.ch1_weak,
                                DUT1_CH0_DIMMED, DUT2_CH1_DIMMED,
                                rect, x_min, x_max, y_min, y_max, line_width=2)
                # Draw std trace bright (current)
                self.draw_trace(self.ch0_voltage_std, self.ch1_voltage_std,
                                self.ch0_std, self.ch1_std,
                                DUT1_CH0_BLACK_LEAD, DUT2_CH1_RED_LEAD,
                                rect, x_min, x_max, y_min, y_max, line_width=3)
        else:
            # Normal mode - draw current trace only
            self.draw_trace(self.ch0_voltage, self.ch1_voltage,
                            self.ch0, self.ch1,
                            DUT1_CH0_BLACK_LEAD, DUT2_CH1_RED_LEAD,
                            rect, x_min, x_max, y_min, y_max, line_width=3)

        # Axis labels - INVERTED per manual

        # X-axis (voltage) - INVERTED: right to left
        for i in [0, 5, 10]:
            x_val = x_min + (x_max - x_min) * (10 - i) / 10  # Reversed
            x_pos = rect.x + (i * rect.width) // 10
            label = self.small_font.render(f"{int(x_val)}", True, LABEL_COLOR)
            label_rect = label.get_rect(center=(x_pos, rect.bottom + 25))
            self.screen.blit(label, label_rect)

        # Y-axis (current) - INVERTED: top to bottom
        for i in [0, 5, 10]:
            y_val = y_min + (y_max - y_min) * i / 10
            y_pos = rect.y + (i * rect.height) // 10
            label = self.small_font.render(f"{int(y_val)}", True, LABEL_COLOR)
            label_rect = label.get_rect(midright=(rect.x - 10, y_pos))
            self.screen.blit(label, label_rect)

        # Axis titles
        x_title = self.font.render("DUT Voltage", True, AXIS_TITLE_COLOR)
        x_title_rect = x_title.get_rect(center=(rect.centerx, rect.bottom + 50))
        self.screen.blit(x_title, x_title_rect)

        y_title = self.font.render("Current", True, AXIS_TITLE_COLOR)
        self.screen.blit(y_title, (rect.x - 80, rect.centery - 30))

        # Legend
        legend_x = rect.x + 20
        legend_y = rect.y + 20

        # DUT1 legend (BLUE) - always shown
        pygame.draw.line(self.screen, DUT1_CH0_BLACK_LEAD,
                         (legend_x, legend_y), (legend_x + 40, legend_y), 4)
        dut1_text = self.font.render("DUT1 (CH0 - Black Lead)", True, DUT1_CH0_BLACK_LEAD)
        self.screen.blit(dut1_text, (legend_x + 50, legend_y - 12))

        # DUT2 legend (RED) - only if not in single channel mode
        if not self.single_channel:
            pygame.draw.line(self.screen, DUT2_CH1_RED_LEAD,
                             (legend_x, legend_y + 30), (legend_x + 40, legend_y + 30), 4)
            dut2_text = self.font.render("DUT2 (CH1 - Red Lead)", True, DUT2_CH1_RED_LEAD)
            self.screen.blit(dut2_text, (legend_x + 50, legend_y + 18))

        # Border
        pygame.draw.rect(self.screen, BORDER_COLOR, rect, 2)

        # Pause indicator overlay
        if self.paused:
            overlay_font = pygame.font.Font(None, 72)
            pause_text = overlay_font.render("PAUSED", True, YELLOW)
            pause_rect = pause_text.get_rect(center=rect.center)
            # Semi-transparent background
            s = pygame.Surface((pause_rect.width + 40, pause_rect.height + 20))
            s.set_alpha(200)
            s.fill(BLACK)
            self.screen.blit(s, (pause_rect.x - 20, pause_rect.y - 10))
            self.screen.blit(pause_text, pause_rect)

    def draw_info_panel(self):
        """Draw info panel at bottom"""
        info_y = self.height - 60

        # Channel ranges
        if self.ch0 and self.ch1 and self.ch2:
            info_lines = [
                f"CH0 (DUT1 Current - Black Lead): {min(self.ch0):.0f}-{max(self.ch0):.0f}  Mean: {int(np.mean(self.ch0))}",
                f"CH1 (DUT2 Current - Red Lead): {min(self.ch1):.0f}-{max(self.ch1):.0f}  Mean: {int(np.mean(self.ch1))}",
                f"DUT Voltages: V1={min(self.ch0_voltage):.0f}-{max(self.ch0_voltage):.0f}, V2={min(self.ch1_voltage):.0f}-{max(self.ch1_voltage):.0f}"
            ]
            for i, line in enumerate(info_lines):
                color = [DUT1_CH0_BLACK_LEAD, DUT2_CH1_RED_LEAD, DUT_VOLTAGE_COLOR][i]
                text = self.small_font.render(line, True, color)
                self.screen.blit(text, (20, info_y + i * 22))

        # Status
        mode_names = ["4.7K(T)", "100K WEAK(W)", "ALT"]
        mode_str = mode_names[self.excitation_mode]

        # In alternating mode, show which was captured last
        if self.excitation_mode == 2 and len(self.ch0) > 0:
            if self.last_mode_was_weak:
                mode_str = "ALT[W-bright T-dim]"
            else:
                mode_str = "ALT[T-bright W-dim]"

        pause_str = " [PAUSED]" if self.paused else ""
        single_str = " [SINGLE CH]" if self.single_channel else ""

        status = f"Frame: {self.frame_count}  |  FPS: {self.fps:.1f}  |  Mode: {mode_str}{pause_str}{single_str}  |  SPACE=mode P=pause S=single Q=quit"
        text = self.small_font.render(status, True, GRAY)
        self.screen.blit(text, (20, 15))

    def run(self):
        """Main loop"""
        running = True
        last_update = time.time()

        print("\n" + "=" * 70)
        print("Curve Tracer - Dual DUT Comparison")
        print("=" * 70)
        print("\nChannel Configuration:")
        print("  CH0 (Blue):  DUT1 Current (Black lead)")
        print("  CH1 (Red):   DUT2 Current (Red lead)")
        print("  CH2 (Green): Voltage Sweep (X-axis)")
        print("\nDisplay (Per CurveBug Manual):")
        print("  - Axes INVERTED: Leftward = more negative V, Upward = more negative I")
        print("  - DUT Voltage (X-axis) vs Current (Y-axis)")
        print("  - Blue curve = DUT1 characteristic (Black lead)")
        print("  - Red curve = DUT2 characteristic (Red lead)")
        print("\nKeyboard Controls:")
        print("  SPACEBAR - Cycle excitation: 4.7K ohm, 100K ohm (WEAK), Alternating")
        print("  P        - Pause/Resume scanning")
        print("  S        - Single channel mode (Black trace only)")
        print("  Q/ESC    - Quit")
        print("=" * 70 + "\n")

        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in [pygame.K_q, pygame.K_ESCAPE]:
                        running = False
                    elif event.key == pygame.K_SPACE:
                        # Cycle excitation mode: 4.7k -> 100k (weak) -> alternating
                        self.excitation_mode = (self.excitation_mode + 1) % 3
                        mode_names = ["4.7K Ohm (T)", "100K Ohm WEAK (W)", "Alternating (T+W)"]
                        print(f"Excitation mode: {mode_names[self.excitation_mode]}")
                    elif event.key == pygame.K_p:
                        # Toggle pause (local only)
                        self.paused = not self.paused
                        print(f"Paused: {self.paused}")
                    elif event.key == pygame.K_s:
                        # Toggle single channel mode (local only)
                        self.single_channel = not self.single_channel
                        print(f"Single channel (black only): {self.single_channel}")

            # Acquire data (skip if paused)
            if not self.paused and self.acquire():
                self.frame_count += 1

                # Debug first frame
                if self.frame_count == 1:
                    print(f"\nFirst acquisition:")
                    print(
                        f"  CH0 (DUT1 - Black): {len(self.ch0)} samples, range {min(self.ch0):.0f}-{max(self.ch0):.0f}")
                    print(f"  CH1 (DUT2 - Red): {len(self.ch1)} samples, range {min(self.ch1):.0f}-{max(self.ch1):.0f}")
                    print(f"  CH2 (Voltage): {len(self.ch2)} samples, range {min(self.ch2):.0f}-{max(self.ch2):.0f}")
                    print()

            # Calculate FPS
            current_time = time.time()
            if current_time - last_update > 0:
                self.fps = 1.0 / (current_time - last_update)
            last_update = current_time

            # Draw
            self.screen.fill(BACKGROUND_COLOR)

            # Large X-Y plot in center
            plot_rect = pygame.Rect(150, 80, self.width - 200, self.height - 200)
            self.draw_dual_xy_plot(plot_rect)

            # Info panel
            self.draw_info_panel()

            pygame.display.flip()
            self.clock.tick(20)

        if self.serial:
            self.serial.close()
        pygame.quit()
        print("\nClosed")


def main():
    app = CurveTracerDual()
    if app.connect():
        app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
