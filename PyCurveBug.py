#!/usr/bin/env python3
"""
PyCurveBug - Curve Viewer for vintageTEK CurveBug

REQUIRED:
    PySerial
    PyGame
    Numpy

Shows TWO I-V curves on the same plot:
    - DUT1 (CH1 - Black lead):  CH1 voltage vs current
    - DUT2 (CH2 - Red lead): CH2 voltage vs current

Features:
    1. Axes are INVERTED per manual: "graphs are reversed left-to-right and up-to-down"
       - Leftward = increasingly negative voltage
       - Upward = increasingly negative current
    2. Axis labels: Voltage (X-axis) vs Current (Y-axis) for I-V curves
    3. Data interpretation matches official CurveBug software
    4. Fixed scaling matches original C++ implementation by default
    5. Pan/Zoom navigation in fixed mode
    6. Settings feature
        - Responsive UI that adapts to almost any window size
        - Popup color picker for all colors
        - Configurable settings with persistence
"""

import pygame
import serial
import struct
import numpy as np
import sys
import time
import json
import os

# Default colors
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

# Fixed scale constants from original C++ code
ADC_MAX = 2800  # Maximum ADC range
ADC_ORIGIN = 2048  # Mid-scale ADC reference (12-bit center)
FLOOR_RATIO = 7.0 / 8.0  # Baseline at 7/8 down the screen

OUTPUT_DEBUG_TEXT = False

def debug_print(contents: str = None):
    if OUTPUT_DEBUG_TEXT:
        print(contents)

class ConfigManager:
    """Manages application configuration and settings"""

    DEFAULT_CONFIG = {
        'serial_port': 'COM3',
        'window_width': 1080,
        'window_height': 1080,
        'colors': {
            'background': [0, 0, 0],
            'dut1_trace': [50, 150, 255],
            'dut2_trace': [255, 50, 50],
            'dut1_dimmed': [25, 75, 128],
            'dut2_dimmed': [128, 25, 25],
            'grid_background': [30, 30, 30],
            'grid': [50, 50, 50],
            'crosshair': [255, 255, 50],
            'label': [200, 200, 200],
            'axis_title': [255, 255, 255],
            'border': [100, 100, 100],
            'dut_voltage': [50, 255, 150],
        },
        'keybinds': {
            'quit': 'q',
            'pause': 'p',
            'single_channel': 's',
            'auto_scale': 'a',
            'fit_window': 'f',
            'reset_view': 'r',
            'cycle_mode': 'space',
            'settings': 'f1',
        }
    }

    def __init__(self, config_file='curvebug_config.json'):
        self.config_file = config_file
        self.config = self.DEFAULT_CONFIG.copy()
        self.load_config()

    def load_config(self):
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    saved_config = json.load(f)
                    self._deep_update(self.config, saved_config)
                debug_print(f"Configuration loaded from {self.config_file}")
            except Exception as e:
                debug_print(f"Error loading config: {e}, using defaults")

    def save_config(self):
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            debug_print(f"Configuration saved to {self.config_file}")
            return True
        except Exception as e:
            debug_print(f"Error saving config: {e}")
            return False

    def _deep_update(self, base_dict, update_dict):
        """Recursively update nested dictionary"""
        for key, value in update_dict.items():
            if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
                self._deep_update(base_dict[key], value)
            else:
                base_dict[key] = value

    def get(self, *keys):
        """Get nested config value"""
        value = self.config
        for key in keys:
            value = value.get(key)
            if value is None:
                return None
        return value

    def set(self, value, *keys):
        """Set nested config value"""
        config = self.config
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        config[keys[-1]] = value


class Button:
    """Simple button widget"""

    def __init__(self, rect, text, color, text_color, font):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.color = color
        self.hover_color = tuple(min(c + 30, 255) for c in color)
        self.text_color = text_color
        self.font = font
        self.hovered = False

    def draw(self, screen):
        color = self.hover_color if self.hovered else self.color
        pygame.draw.rect(screen, color, self.rect)
        pygame.draw.rect(screen, self.text_color, self.rect, 2)

        text_surf = self.font.render(self.text, True, self.text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.rect.collidepoint(event.pos):
                return True
        return False


class InputBox:
    """Text input box"""

    def __init__(self, rect, text, font):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.active = False
        self.cursor_visible = True
        self.cursor_timer = 0

    def draw(self, screen):
        color = WHITE if self.active else GRAY
        pygame.draw.rect(screen, DARK_GRAY, self.rect)
        pygame.draw.rect(screen, color, self.rect, 2)

        text_surf = self.font.render(self.text, True, WHITE)
        screen.blit(text_surf, (self.rect.x + 5, self.rect.y + 5))

        # Cursor
        if self.active and self.cursor_visible:
            cursor_x = self.rect.x + 5 + text_surf.get_width()
            pygame.draw.line(screen, WHITE,
                             (cursor_x, self.rect.y + 5),
                             (cursor_x, self.rect.bottom - 5), 2)

    def update(self, dt):
        if self.active:
            self.cursor_timer += dt
            if self.cursor_timer > 0.5:
                self.cursor_visible = not self.cursor_visible
                self.cursor_timer = 0

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
            self.cursor_visible = True
            self.cursor_timer = 0

        elif event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_RETURN:
                self.active = False
                return True
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.unicode.isprintable():
                self.text += event.unicode

        return False


class ColorPickerDialog:
    """Popup color picker with RGB sliders"""

    def __init__(self, color, font, screen_width, screen_height):
        self.color = list(color)
        self.original_color = list(color)
        self.font = font
        self.active = False

        # Center the dialog
        self.width = 400
        self.height = 250
        self.x = (screen_width - self.width) // 2
        self.y = (screen_height - self.height) // 2

        self.slider_width = 250
        self.slider_height = 20
        self.dragging = -1

        # Buttons
        self.ok_button = Button(
            (self.x + self.width - 220, self.y + self.height - 60, 100, 40),
            'OK', GREEN, WHITE, font
        )
        self.cancel_button = Button(
            (self.x + self.width - 110, self.y + self.height - 60, 100, 40),
            'Cancel', RED, WHITE, font
        )

    def show(self, color):
        """Show the color picker with initial color"""
        self.color = list(color)
        self.original_color = list(color)
        self.active = True

    def hide(self):
        """Hide the color picker"""
        self.active = False

    def draw(self, screen):
        if not self.active:
            return

        # Semi-transparent overlay
        overlay = pygame.Surface((screen.get_width(), screen.get_height()))
        overlay.set_alpha(200)
        overlay.fill(BLACK)
        screen.blit(overlay, (0, 0))

        # Dialog background
        dialog_rect = pygame.Rect(self.x, self.y, self.width, self.height)
        pygame.draw.rect(screen, DARK_GRAY, dialog_rect)
        pygame.draw.rect(screen, WHITE, dialog_rect, 3)

        # Title
        title = self.font.render('Choose Color', True, WHITE)
        screen.blit(title, (self.x + 20, self.y + 15))

        # RGB sliders
        labels = ['Red:', 'Green:', 'Blue:']
        slider_start_y = self.y + 60

        for i, label in enumerate(labels):
            y_pos = slider_start_y + i * 45

            # Label
            text = self.font.render(label, True, WHITE)
            screen.blit(text, (self.x + 30, y_pos))

            # Slider background
            slider_rect = pygame.Rect(
                self.x + 100, y_pos,
                self.slider_width, self.slider_height
            )
            pygame.draw.rect(screen, MID_GRAY, slider_rect)
            pygame.draw.rect(screen, GRAY, slider_rect, 1)

            # Slider fill
            fill_width = int((self.color[i] / 255) * self.slider_width)
            fill_rect = pygame.Rect(self.x + 100, y_pos, fill_width, self.slider_height)
            slider_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
            pygame.draw.rect(screen, slider_colors[i], fill_rect)

            # Value text
            value_text = self.font.render(str(self.color[i]), True, WHITE)
            screen.blit(value_text, (self.x + 100 + self.slider_width + 10, y_pos))

        # Color preview
        preview_size = 80
        preview_rect = pygame.Rect(
            self.x + self.width - preview_size - 30,
            slider_start_y,
            preview_size, preview_size
        )
        pygame.draw.rect(screen, tuple(self.color), preview_rect)
        pygame.draw.rect(screen, WHITE, preview_rect, 2)

        # Preview label
        preview_label = self.font.render('Preview', True, LIGHT_GRAY)
        screen.blit(preview_label, (preview_rect.x, preview_rect.y - 25))

        # Buttons
        self.ok_button.draw(screen)
        self.cancel_button.draw(screen)

    def handle_event(self, event):
        """Returns: 'ok' if OK clicked, 'cancel' if cancelled, None otherwise"""
        if not self.active:
            return None

        # Button handling
        if self.ok_button.handle_event(event):
            self.hide()
            return 'ok'

        if self.cancel_button.handle_event(event):
            self.color = self.original_color.copy()
            self.hide()
            return 'cancel'

        # Slider handling
        slider_start_y = self.y + 60

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i in range(3):
                slider_rect = pygame.Rect(
                    self.x + 100, slider_start_y + i * 45,
                    self.slider_width, self.slider_height
                )
                if slider_rect.collidepoint(event.pos):
                    self.dragging = i
                    self._update_slider(i, event.pos[0])

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = -1

        elif event.type == pygame.MOUSEMOTION and self.dragging != -1:
            self._update_slider(self.dragging, event.pos[0])

        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.color = self.original_color.copy()
            self.hide()
            return 'cancel'

        return None

    def _update_slider(self, index, mouse_x):
        slider_x = self.x + 100
        relative_x = max(0, min(mouse_x - slider_x, self.slider_width))
        self.color[index] = int((relative_x / self.slider_width) * 255)


class ColorSwatch:
    """Clickable color swatch"""

    def __init__(self, rect, color, label, font):
        self.rect = pygame.Rect(rect)
        self.color = list(color)
        self.label = label
        self.font = font
        self.hovered = False

    def draw(self, screen):
        # Label
        label_surf = self.font.render(self.label, True, WHITE)
        screen.blit(label_surf, (self.rect.x, self.rect.y + 5))

        # Color box
        color_rect = pygame.Rect(self.rect.right - 100, self.rect.y, 100, 35)
        pygame.draw.rect(screen, tuple(self.color), color_rect)

        border_color = WHITE if self.hovered else GRAY
        pygame.draw.rect(screen, border_color, color_rect, 2)

        return color_rect

    def handle_event(self, event):
        color_rect = pygame.Rect(self.rect.right - 100, self.rect.y, 100, 35)

        if event.type == pygame.MOUSEMOTION:
            self.hovered = color_rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and color_rect.collidepoint(event.pos):
                return True
        return False

    def update_color(self, color):
        self.color = list(color)


class SettingsWindow:
    """Full-screen settings overlay with responsive layout"""

    def __init__(self, config_manager, screen_width, screen_height):
        self.config = config_manager
        self.screen_width = screen_width
        self.screen_height = screen_height

        self.font = pygame.font.Font(None, 28)
        self.title_font = pygame.font.Font(None, 48)
        self.small_font = pygame.font.Font(None, 20)

        self.active = False
        self.tab = 0  # 0=Display, 1=Colors, 2=Keybinds, 3=Serial

        self.color_picker = None
        self.editing_color = None  # Track which color is being edited

        self.display_settings_text = 'Display Settings'
        self.color_settings_text = 'Color Settings'
        self.keybinds_settings_text = 'Keyboard Shortcuts'
        self.serial_settings_text = 'Serial Port Configuration'
        self.active_settings_window = self.display_settings_text

        self._calculate_layout()
        self._init_widgets()

    def _calculate_layout(self):
        """Calculate layout for full-screen settings"""
        # Use entire screen
        self.width = self.screen_width
        self.height = self.screen_height

        # Calculate margins based on screen size
        self.margin_x = max(40, int(self.width * 0.05))
        self.margin_y = max(30, int(self.height * 0.05))

        # Content area
        self.content_x = self.margin_x
        self.content_y = 140  # Below title and tabs
        self.content_width = self.width - 2 * self.margin_x
        self.content_height = self.height - self.content_y - 100  # Space for bottom buttons

    def update_screen_size(self, width, height):
        """Update layout when screen is resized"""
        self.screen_width = width
        self.screen_height = height
        self._calculate_layout()
        self._init_widgets()

        # Update color picker position if it exists
        if self.color_picker:
            self.color_picker.x = (width - self.color_picker.width) // 2
            self.color_picker.y = (height - self.color_picker.height) // 2
            self.color_picker.ok_button.rect.x = self.color_picker.x + self.color_picker.width - 220
            self.color_picker.ok_button.rect.y = self.color_picker.y + self.color_picker.height - 60
            self.color_picker.cancel_button.rect.x = self.color_picker.x + self.color_picker.width - 110
            self.color_picker.cancel_button.rect.y = self.color_picker.y + self.color_picker.height - 60

    def _init_widgets(self):
        """Initialize UI widgets"""
        # Tab buttons - centered at top
        tab_width = max(120, min(180, (self.content_width - 60) // 4))
        tab_spacing = 15
        total_tab_width = 4 * tab_width + 3 * tab_spacing
        tab_start_x = (self.width - total_tab_width) // 2
        tab_y = 70

        self.tab_buttons = [
            Button((tab_start_x + i * (tab_width + tab_spacing), tab_y, tab_width, 45),
                   text, MID_GRAY, WHITE, self.font)
            for i, text in enumerate(['Display', 'Colors', 'Keybinds', 'Serial'])
        ]

        # Calculate column layout for better use of space
        col_width = min(400, self.content_width // 2 - 40)
        col1_x = self.content_x + 40
        col2_x = self.content_x + self.content_width // 2 + 20

        # Display settings
        self.width_input = InputBox(
            (col1_x + 180, self.content_y + 30, 150, 40),
            str(self.config.get('window_width')),
            self.font
        )
        self.height_input = InputBox(
            (col1_x + 180, self.content_y + 90, 150, 40),
            str(self.config.get('window_height')),
            self.font
        )

        # Color swatches - use two columns for better space usage
        self.color_swatches = {}
        color_configs = [
            ('background', 'Background'),
            ('dut1_trace', 'DUT1 Trace (Blue)'),
            ('dut2_trace', 'DUT2 Trace (Red)'),
            ('dut1_dimmed', 'DUT1 Dimmed'),
            ('dut2_dimmed', 'DUT2 Dimmed'),
            ('grid_background', 'Grid Background'),
            ('grid', 'Grid Lines'),
            ('crosshair', 'Crosshair'),
            ('label', 'Axis Labels'),
            ('axis_title', 'Axis Titles'),
            ('border', 'Border'),
            ('dut_voltage', 'DUT Voltage'),
        ]

        # Calculate rows per column
        items_per_col = (len(color_configs) + 1) // 2
        swatch_width = min(500, (self.content_width - 80) // 2)

        for i, (key, label) in enumerate(color_configs):
            color = self.config.get('colors', key)
            col = i // items_per_col
            row = i % items_per_col

            x = col1_x if col == 0 else col2_x
            y = self.content_y + 20 + row * 50

            swatch = ColorSwatch(
                (x, y, swatch_width, 40),
                color, label, self.font
            )
            self.color_swatches[key] = swatch

        # Keybind inputs - two columns
        self.keybind_inputs = {}
        self.keybind_labels = {
            'quit': 'Quit:',
            'pause': 'Pause:',
            'single_channel': 'Single Channel:',
            'auto_scale': 'Auto Scale:',
            'fit_window': 'Fit Window:',
            'reset_view': 'Reset View:',
            'cycle_mode': 'Cycle Mode:',
            'settings': 'Settings:',
        }

        keybind_names = list(self.config.get('keybinds').keys())
        items_per_col = (len(keybind_names) + 1) // 2

        for i, name in enumerate(keybind_names):
            col = i // items_per_col
            row = i % items_per_col

            x = col1_x if col == 0 else col2_x
            y = self.content_y + 20 + row * 60

            self.keybind_inputs[name] = InputBox(
                (x + 200, y, 120, 40),
                self.config.get('keybinds', name),
                self.font
            )

        # Serial port input
        self.serial_input = InputBox(
            (col1_x + 180, self.content_y + 30, min(400, self.content_width - 300), 40),
            self.config.get('serial_port'),
            self.font
        )

        # Bottom buttons - centered
        button_width = 140
        button_height = 50
        button_spacing = 20
        button_y = self.height - button_height - 30
        total_button_width = 2 * button_width + button_spacing
        button_start_x = (self.width - total_button_width) // 2

        self.save_button = Button(
            (button_start_x, button_y, button_width, button_height),
            'Save', GREEN, WHITE, self.font
        )
        self.cancel_button = Button(
            (button_start_x + button_width + button_spacing, button_y, button_width, button_height),
            'Cancel', RED, WHITE, self.font
        )

        # Create color picker
        self.color_picker = ColorPickerDialog(
            [0, 0, 0], self.font, self.screen_width, self.screen_height
        )

        self.scroll_offset = 0

    def show(self):
        """Show the settings window"""
        self.active = True

    def hide(self):
        """Hide the settings window"""
        self.active = False

    def draw(self, screen):
        if not self.active:
            return

        # Full screen dark background
        screen.fill(BLACK)

        # Title bar background
        title_bar_rect = pygame.Rect(0, 0, self.width, 60)
        pygame.draw.rect(screen, DARK_GRAY, title_bar_rect)
        pygame.draw.line(screen, GRAY, (0, 60), (self.width, 60), 2)

        # Title
        title = self.title_font.render(self.active_settings_window, True, WHITE)
        title_rect = title.get_rect(center=(self.width // 2, 30))
        screen.blit(title, title_rect)

        # Tab buttons
        for i, button in enumerate(self.tab_buttons):
            if i == self.tab:
                button.color = BLUE
            else:
                button.color = MID_GRAY
            button.draw(screen)

        # Draw content based on active tab
        if self.tab == 0:  # Display
            self.active_settings_window = self.display_settings_text
            self._draw_display_settings(screen)
        elif self.tab == 1:  # Colors
            self.active_settings_window = self.color_settings_text
            self._draw_color_settings(screen)
        elif self.tab == 2:  # Keybinds
            self.active_settings_window = self.keybinds_settings_text
            self._draw_keybind_settings(screen)
        elif self.tab == 3:  # Serial
            self.active_settings_window = self.serial_settings_text
            self._draw_serial_settings(screen)

        # Bottom buttons
        self.save_button.draw(screen)
        self.cancel_button.draw(screen)

        # Instructions at bottom
        instruction_text = "ESC to cancel  |  Click Save to apply changes"
        instruction_surf = self.small_font.render(instruction_text, True, LIGHT_GRAY)
        instruction_rect = instruction_surf.get_rect(center=(self.width // 2, self.height - 90))
        screen.blit(instruction_surf, instruction_rect)

        # Draw color picker on top of everything
        self.color_picker.draw(screen)

    def _draw_display_settings(self, screen):
        col1_x = self.content_x + 40
        y = self.content_y + 30

        label = self.font.render('Window Width:', True, WHITE)
        screen.blit(label, (col1_x, y + 10))
        self.width_input.draw(screen)

        label = self.font.render('Window Height:', True, WHITE)
        screen.blit(label, (col1_x, y + 70))
        self.height_input.draw(screen)

        # Info box
        info_y = y + 150
        info_rect = pygame.Rect(col1_x, info_y, self.content_width - 80, 80)
        pygame.draw.rect(screen, DARK_GRAY, info_rect)
        pygame.draw.rect(screen, YELLOW, info_rect, 2)

        info = self.font.render('Note: Window size changes require application restart', True, YELLOW)
        screen.blit(info, (col1_x + 20, info_y + 20))

        info2 = self.small_font.render('You can also resize the window by dragging the window edges', True, LIGHT_GRAY)
        screen.blit(info2, (col1_x + 20, info_y + 50))

    def _draw_color_settings(self, screen):

        # Draw all color swatches
        for swatch in self.color_swatches.values():
            swatch.draw(screen)

        # Instruction box at bottom of content
        info_y = self.content_y + self.content_height - 80
        info_rect = pygame.Rect(self.content_x + 40, info_y, self.content_width - 80, 60)
        pygame.draw.rect(screen, DARK_GRAY, info_rect)
        pygame.draw.rect(screen, BLUE, info_rect, 2)

        info = self.font.render('Click any color box to customize', True, LIGHT_GRAY)
        screen.blit(info, (self.content_x + 60, info_y + 18))

    def _draw_keybind_settings(self, screen):
        col1_x = self.content_x + 40
        col2_x = self.content_x + self.content_width // 2 + 20

        keybind_names = list(self.keybind_inputs.keys())
        items_per_col = (len(keybind_names) + 1) // 2

        for i, name in enumerate(keybind_names):
            col = i // items_per_col
            row = i % items_per_col

            x = col1_x if col == 0 else col2_x
            y = self.content_y + 20 + row * 60

            label_text = self.keybind_labels.get(name, name + ':')
            label = self.font.render(label_text, True, WHITE)
            screen.blit(label, (x, y + 8))

            if name in self.keybind_inputs:
                self.keybind_inputs[name].draw(screen)

        # Info box
        info_y = self.content_y + self.content_height - 100
        info_rect = pygame.Rect(self.content_x + 40, info_y, self.content_width - 80, 80)
        pygame.draw.rect(screen, DARK_GRAY, info_rect)
        pygame.draw.rect(screen, BLUE, info_rect, 2)

        info = self.font.render('Click a keybind box and type the new key', True, LIGHT_GRAY)
        screen.blit(info, (self.content_x + 60, info_y + 15))

        info2 = self.small_font.render('Supported: letters (a-z), space, f1-f12, escape', True, LIGHT_GRAY)
        screen.blit(info2, (self.content_x + 60, info_y + 48))

    def _draw_serial_settings(self, screen):
        col1_x = self.content_x + 40
        y = self.content_y + 30

        label = self.font.render('Serial Port:', True, WHITE)
        screen.blit(label, (col1_x, y + 10))
        self.serial_input.draw(screen)

        # Info boxes
        info_y = y + 100

        # Platform examples
        example_rect = pygame.Rect(col1_x, info_y, self.content_width - 80, 140)
        pygame.draw.rect(screen, DARK_GRAY, example_rect)
        pygame.draw.rect(screen, BLUE, example_rect, 2)

        example_title = self.font.render('Platform Examples:', True, WHITE)
        screen.blit(example_title, (col1_x + 20, info_y + 15))

        examples = [
            'Windows:  COM3, COM4, COM5, ...',
            'Linux:    /dev/ttyUSB0, /dev/ttyACM0',
            'macOS:    /dev/cu.usbserial, /dev/cu.usbmodem'
        ]

        for i, example in enumerate(examples):
            ex_surf = self.small_font.render(example, True, LIGHT_GRAY)
            screen.blit(ex_surf, (col1_x + 40, info_y + 55 + i * 25))

        # Connection status
        status_y = info_y + 160
        status_rect = pygame.Rect(col1_x, status_y, self.content_width - 80, 60)
        pygame.draw.rect(screen, DARK_GRAY, status_rect)
        pygame.draw.rect(screen, YELLOW, status_rect, 2)

        status = self.font.render('Note: Serial port changes require reconnection', True, YELLOW)
        screen.blit(status, (col1_x + 20, status_y + 18))

    def update(self, dt):
        """Update animations"""
        if not self.active:
            return

        # Update all input boxes
        self.width_input.update(dt)
        self.height_input.update(dt)
        for input_box in self.keybind_inputs.values():
            input_box.update(dt)
        self.serial_input.update(dt)

    def handle_event(self, event):
        """Handle events, returns True if settings were saved"""
        if not self.active:
            return False

        # Color picker gets first priority
        if self.color_picker.active:
            result = self.color_picker.handle_event(event)
            if result == 'ok' and self.editing_color:
                # Update the swatch with new color
                self.color_swatches[self.editing_color].update_color(self.color_picker.color)
                self.editing_color = None
            elif result == 'cancel':
                self.editing_color = None
            return False

        # Tab switching
        for i, button in enumerate(self.tab_buttons):
            if button.handle_event(event):
                self.tab = i
                return False

        # Save/Cancel buttons
        if self.save_button.handle_event(event):
            self._save_settings()
            self.hide()
            return True

        if self.cancel_button.handle_event(event):
            self.hide()
            return False

        # Tab-specific widgets
        if self.tab == 0:  # Display
            self.width_input.handle_event(event)
            self.height_input.handle_event(event)

        elif self.tab == 1:  # Colors
            for key, swatch in self.color_swatches.items():
                if swatch.handle_event(event):
                    # Open color picker for this color
                    self.editing_color = key
                    self.color_picker.show(swatch.color)
                    break

        elif self.tab == 2:  # Keybinds
            for input_box in self.keybind_inputs.values():
                input_box.handle_event(event)

        elif self.tab == 3:  # Serial
            self.serial_input.handle_event(event)

        # ESC to close
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if not self.color_picker.active:  # Don't close if color picker is open
                self.hide()

        return False

    def _save_settings(self):
        """Save all settings to config"""
        # Display
        try:
            self.config.set(int(self.width_input.text), 'window_width')
            self.config.set(int(self.height_input.text), 'window_height')
        except ValueError:
            pass

        # Colors
        for name, swatch in self.color_swatches.items():
            self.config.set(swatch.color, 'colors', name)

        # Keybinds
        for name, input_box in self.keybind_inputs.items():
            self.config.set(input_box.text.lower(), 'keybinds', name)

        # Serial
        self.config.set(self.serial_input.text, 'serial_port')

        # Save to file
        self.config.save_config()


class CurveTracerDual:
    def __init__(self):
        # Load configuration
        self.config = ConfigManager()

        pygame.init()
        pygame.display.set_caption("PyCurveBug - Curve Viewer for vintageTEK CurveBug")

        # Use configured window size, make resizable
        self.width = self.config.get('window_width')
        self.height = self.config.get('window_height')
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 28)
        self.small_font = pygame.font.Font(None, 20)
        self.serial = None

        # Get colors from config
        self._load_colors()

        # Data - per manual: 336 points per channel from 1008 total samples
        self.ch1_std = []
        self.ch2_std = []
        self.ch1_voltage_std = []
        self.ch2_voltage_std = []
        self.drive_voltage_std = []

        self.ch1_weak = []
        self.ch2_weak = []
        self.ch1_voltage_weak = []
        self.ch2_voltage_weak = []
        self.drive_voltage_weak = []

        self.ch1 = []
        self.ch2 = []
        self.ch1_voltage = []
        self.ch2_voltage = []
        self.drive_voltage = []

        self.frame_count = 0
        self.fps = 0

        self.alt_use_weak = False
        self.last_mode_was_weak = False

        # Control modes
        self.paused = False
        self.single_channel = False
        self.auto_scale = False
        self.excitation_mode = 0

        # Pan and Zoom
        self.zoom_level = 1.0
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0
        self.dragging = False
        self.drag_start_pos = None
        self.drag_start_offset = None

        # Settings window
        self.settings_window = SettingsWindow(self.config, self.width, self.height)

        # Settings button - positioned relative to window size
        self._update_settings_button_position()

    def auto_detect_port(self):
        """Try to auto-detect CurveBug on available ports"""
        import serial.tools.list_ports

        ports = [port.device for port in serial.tools.list_ports.comports()]

        for port in ports:
            try:
                test_serial = serial.Serial(port, 115200, timeout=1)
                time.sleep(0.1)
                test_serial.reset_input_buffer()
                test_serial.write(b'T')

                data = bytearray()
                start = time.time()
                while len(data) < 2016 and time.time() - start < 1.0:
                    if test_serial.in_waiting > 0:
                        data.extend(test_serial.read(min(test_serial.in_waiting, 2016 - len(data))))

                test_serial.close()

                if len(data) == 2016:
                    debug_print(f"Auto-detected CurveBug on {port}")
                    return port
            except:
                continue

        return None

    def _load_colors(self):
        """Load colors from config"""
        colors = self.config.get('colors')
        self.BACKGROUND_COLOR = tuple(colors['background'])
        self.DUT1_COLOR = tuple(colors['dut1_trace'])
        self.DUT2_COLOR = tuple(colors['dut2_trace'])
        self.DUT1_DIMMED = tuple(colors['dut1_dimmed'])
        self.DUT2_DIMMED = tuple(colors['dut2_dimmed'])
        self.GRID_BACKGROUND_COLOR = tuple(colors['grid_background'])
        self.GRID_COLOR = tuple(colors['grid'])
        self.CROSSHAIR_COLOR = tuple(colors['crosshair'])
        self.LABEL_COLOR = tuple(colors['label'])
        self.AXIS_TITLE_COLOR = tuple(colors['axis_title'])
        self.BORDER_COLOR = tuple(colors['border'])
        self.DUT_VOLTAGE_COLOR = tuple(colors['dut_voltage'])

    def _update_settings_button_position(self):
        """Update settings button position based on window size"""
        self.settings_button = Button(
            (self.width - 120, self.height - 50, 100, 35),
            'Settings', MID_GRAY, WHITE, self.font
        )

    def handle_resize(self, new_width, new_height):
        """Handle window resize event"""
        self.width = new_width
        self.height = new_height

        # Update settings window layout
        self.settings_window.update_screen_size(new_width, new_height)

        # Update settings button position
        self._update_settings_button_position()

        debug_print(f"Window resized to {new_width}x{new_height}")

    def connect(self):
        try:
            port = self.config.get('serial_port')
            self.serial = serial.Serial(port, 115200, timeout=1)
            time.sleep(0.1)
            self.serial.reset_input_buffer()
            debug_print(f"Connected to {port}")
            return True
        except Exception as e:
            debug_print(f"Connection to {self.config.get('serial_port')} failed: {e}")
            debug_print("Attempting auto-detection...")

            detected = self.auto_detect_port()
            if detected:
                try:
                    self.serial = serial.Serial(detected, 115200, timeout=1)
                    time.sleep(0.1)
                    self.serial.reset_input_buffer()
                    debug_print(f"Auto-connected to {detected}")
                    self.config.set(detected, 'serial_port')
                    self.config.save_config()
                    self.settings_window.serial_input.text = detected
                    return True
                except:
                    pass

            return False

    def get_key_from_config(self, action):
        """Get pygame key constant from config"""
        key_str = self.config.get('keybinds', action)
        if key_str == 'space':
            return pygame.K_SPACE
        elif key_str == 'f1':
            return pygame.K_F1
        elif key_str == 'escape':
            return pygame.K_ESCAPE
        else:
            return ord(key_str.lower())

    def acquire(self):
        """Acquire data from CurveBug"""
        # Allow app to run without connection
        if self.serial is None or not self.serial.is_open:
            return False
        try:
            if self.excitation_mode == 0:
                command = b'T'
                store_as_weak = False
            elif self.excitation_mode == 1:
                command = b'W'
                store_as_weak = True
            else:
                if self.alt_use_weak:
                    command = b'W'
                    store_as_weak = True
                else:
                    command = b'T'
                    store_as_weak = False
                self.alt_use_weak = not self.alt_use_weak

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

            values = []
            for i in range(0, len(data), 2):
                val = struct.unpack('<H', data[i:i + 2])[0]
                values.append(val & 0x0FFF)

            if len(values) != 1008:
                return False

            drive_voltage = values[0::3]
            ch1_raw = values[1::3]
            ch2_raw = values[2::3]

            ch1_current = [drive_voltage[i] - ch1_raw[i] for i in range(len(drive_voltage))]
            ch2_current = [drive_voltage[i] - ch2_raw[i] for i in range(len(drive_voltage))]

            if store_as_weak:
                self.ch1_voltage_weak = ch1_raw
                self.ch2_voltage_weak = ch2_raw
                self.ch1_weak = ch1_current
                self.ch2_weak = ch2_current
                self.drive_voltage_weak = drive_voltage
                self.last_mode_was_weak = True
            else:
                self.ch1_voltage_std = ch1_raw
                self.ch2_voltage_std = ch2_raw
                self.ch1_std = ch1_current
                self.ch2_std = ch2_current
                self.drive_voltage_std = drive_voltage
                self.last_mode_was_weak = False

            if store_as_weak:
                self.ch1_voltage = self.ch1_voltage_weak
                self.ch2_voltage = self.ch2_voltage_weak
                self.ch1 = self.ch1_weak
                self.ch2 = self.ch2_weak
                self.drive_voltage = self.drive_voltage_weak
            else:
                self.ch1_voltage = self.ch1_voltage_std
                self.ch2_voltage = self.ch2_voltage_std
                self.ch1 = self.ch1_std
                self.ch2 = self.ch2_std
                self.drive_voltage = self.drive_voltage_std

            return True

        except Exception as e:
            debug_print(f"Error: {e}")
            return False

    def fit_to_window(self):
        """Calculate zoom and pan to show all data"""
        if not self.ch1 or not self.ch2:
            return

        if self.excitation_mode == 2 and len(self.ch1_std) > 0 and len(self.ch1_weak) > 0:
            all_x = self.ch1_voltage_std + self.ch2_voltage_std + self.ch1_voltage_weak + self.ch2_voltage_weak
            all_y = self.ch1_std + self.ch2_std + self.ch1_weak + self.ch2_weak
        else:
            all_x = self.ch1_voltage + self.ch2_voltage
            all_y = self.ch1 + self.ch2

        data_x_min = min(all_x)
        data_x_max = max(all_x)
        data_y_min = min(all_y)
        data_y_max = max(all_y)

        x_margin = (data_x_max - data_x_min) * 0.2
        y_margin = (data_y_max - data_y_min) * 0.2
        data_x_min -= x_margin
        data_x_max += x_margin
        data_y_min -= y_margin
        data_y_max += y_margin

        data_x_range = data_x_max - data_x_min
        data_y_range = data_y_max - data_y_min

        base_x_min = 0
        base_x_max = ADC_MAX
        y_range = ADC_MAX - 700
        base_y_max = y_range / 8
        base_y_min = -y_range * 7 / 8

        base_x_range = base_x_max - base_x_min
        base_y_range = base_y_max - base_y_min

        zoom_x = base_x_range / data_x_range if data_x_range > 0 else 1.0
        zoom_y = base_y_range / data_y_range if data_y_range > 0 else 1.0

        self.zoom_level = min(zoom_x, zoom_y)

        if self.zoom_level > 1.0:
            self.zoom_level = 1.0

        data_x_center = (data_x_min + data_x_max) / 2
        data_y_center = (data_y_min + data_y_max) / 2

        base_x_center = (base_x_min + base_x_max) / 2
        base_y_center = (base_y_min + base_y_max) / 2

        self.pan_offset_x = data_x_center - base_x_center
        self.pan_offset_y = data_y_center - base_y_center

        debug_print(f"Fit to window: zoom={self.zoom_level:.3f}x, pan=({self.pan_offset_x:.0f}, {self.pan_offset_y:.0f})")

    def reset_view(self):
        """Reset zoom and pan to default"""
        self.zoom_level = 1.0
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0
        debug_print("View reset to default")

    def draw_trace(self, ch1_voltage, ch2_voltage, ch1_current, ch2_current,
                   color1, color2, rect, x_min, x_max, y_min, y_max, line_width=3):
        """Draw trace curves"""
        points1 = []
        for i in range(len(ch1_voltage)):
            x_norm = (ch1_voltage[i] - x_min) / (x_max - x_min) if x_max != x_min else 0.5
            y_norm = (ch1_current[i] - y_min) / (y_max - y_min) if y_max != y_min else 0.5

            px = int(rect.right - (x_norm * rect.width))
            py = int(rect.top + (y_norm * rect.height))
            points1.append((px, py))

        if len(points1) > 1:
            pygame.draw.lines(self.screen, color1, False, points1, line_width)

        if not self.single_channel:
            points2 = []
            for i in range(len(ch2_voltage)):
                x_norm = (ch2_voltage[i] - x_min) / (x_max - x_min) if x_max != x_min else 0.5
                y_norm = (ch2_current[i] - y_min) / (y_max - y_min) if y_max != y_min else 0.5

                px = int(rect.right - (x_norm * rect.width))
                py = int(rect.top + (y_norm * rect.height))
                points2.append((px, py))

            if len(points2) > 1:
                pygame.draw.lines(self.screen, color2, False, points2, line_width)

    def draw_dual_xy_plot(self, rect):
        """Draw I-V curves"""
        pygame.draw.rect(self.screen, self.GRID_BACKGROUND_COLOR, rect)

        title_text = "I-V Characteristics - Dual DUT Comparison"
        if self.auto_scale:
            title_text += " [AUTO-SCALE]"
        else:
            title_text += f" [FIXED SCALE] Zoom:{self.zoom_level:.2f}x"
        title = self.font.render(title_text, True, WHITE)
        title_rect = title.get_rect(center=(rect.centerx, rect.y - 30))
        self.screen.blit(title, title_rect)

        if not self.ch1 or not self.ch2 or not self.drive_voltage or len(self.drive_voltage) < 2:
            text = self.font.render("No Data", True, WHITE)
            text_rect = text.get_rect(center=rect.center)
            self.screen.blit(text, text_rect)
            pygame.draw.rect(self.screen, self.BORDER_COLOR, rect, 2)
            return

        # Calculate scale
        if self.auto_scale:
            if self.excitation_mode == 2 and len(self.ch1_std) > 0 and len(self.ch1_weak) > 0:
                x1_data_std = np.array(self.ch1_voltage_std)
                x2_data_std = np.array(self.ch2_voltage_std)
                y1_data_std = np.array(self.ch1_std)
                y2_data_std = np.array(self.ch2_std)

                x1_data_weak = np.array(self.ch1_voltage_weak)
                x2_data_weak = np.array(self.ch2_voltage_weak)
                y1_data_weak = np.array(self.ch1_weak)
                y2_data_weak = np.array(self.ch2_weak)

                x_min = min(x1_data_std.min(), x2_data_std.min(), x1_data_weak.min(), x2_data_weak.min())
                x_max = max(x1_data_std.max(), x2_data_std.max(), x1_data_weak.max(), x2_data_weak.max())
                y_min = min(y1_data_std.min(), y2_data_std.min(), y1_data_weak.min(), y2_data_weak.min())
                y_max = max(y1_data_std.max(), y2_data_std.max(), y1_data_weak.max(), y2_data_weak.max())
            else:
                x1_data = np.array(self.ch1_voltage)
                x2_data = np.array(self.ch2_voltage)
                y1_data = np.array(self.ch1)
                y2_data = np.array(self.ch2)

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

        else:
            # Fixed scale with pan/zoom
            base_x_min = 0
            base_x_max = ADC_MAX

            y_range = ADC_MAX - 700
            base_y_max = y_range / 8
            base_y_min = -y_range * 7 / 8

            x_range_visible = (base_x_max - base_x_min) / self.zoom_level
            y_range_visible = (base_y_max - base_y_min) / self.zoom_level

            x_center = (base_x_max + base_x_min) / 2 + self.pan_offset_x
            y_center = (base_y_max + base_y_min) / 2 + self.pan_offset_y

            x_min = x_center - x_range_visible / 2
            x_max = x_center + x_range_visible / 2
            y_min = y_center - y_range_visible / 2
            y_max = y_center + y_range_visible / 2

        # Grid
        for i in range(11):
            x = rect.x + (i * rect.width) // 10
            pygame.draw.line(self.screen, self.GRID_COLOR, (x, rect.y), (x, rect.bottom), 1)
            y = rect.y + (i * rect.height) // 10
            pygame.draw.line(self.screen, self.GRID_COLOR, (rect.x, y), (rect.right, y), 1)

        # Crosshairs
        zero_x_norm = (ADC_ORIGIN - x_min) / (x_max - x_min) if x_max != x_min else 0.5
        zero_y_norm = (0 - y_min) / (y_max - y_min) if y_max != y_min else 0.5

        if 0 <= zero_x_norm <= 1:
            zero_x_pos = int(rect.right - (zero_x_norm * rect.width))
            pygame.draw.line(self.screen, self.CROSSHAIR_COLOR, (zero_x_pos, rect.y), (zero_x_pos, rect.bottom), 2)

        if 0 <= zero_y_norm <= 1:
            zero_y_pos = int(rect.top + (zero_y_norm * rect.height))
            pygame.draw.line(self.screen, self.CROSSHAIR_COLOR, (rect.x, zero_y_pos), (rect.right, zero_y_pos), 2)

        # Draw traces
        if self.excitation_mode == 2 and len(self.ch1_std) > 0 and len(self.ch1_weak) > 0:
            if self.last_mode_was_weak:
                self.draw_trace(self.ch1_voltage_std, self.ch2_voltage_std,
                                self.ch1_std, self.ch2_std,
                                self.DUT1_DIMMED, self.DUT2_DIMMED,
                                rect, x_min, x_max, y_min, y_max, line_width=2)
                self.draw_trace(self.ch1_voltage_weak, self.ch2_voltage_weak,
                                self.ch1_weak, self.ch2_weak,
                                self.DUT1_COLOR, self.DUT2_COLOR,
                                rect, x_min, x_max, y_min, y_max, line_width=3)
            else:
                self.draw_trace(self.ch1_voltage_weak, self.ch2_voltage_weak,
                                self.ch1_weak, self.ch2_weak,
                                self.DUT1_DIMMED, self.DUT2_DIMMED,
                                rect, x_min, x_max, y_min, y_max, line_width=2)
                self.draw_trace(self.ch1_voltage_std, self.ch2_voltage_std,
                                self.ch1_std, self.ch2_std,
                                self.DUT1_COLOR, self.DUT2_COLOR,
                                rect, x_min, x_max, y_min, y_max, line_width=3)
        else:
            self.draw_trace(self.ch1_voltage, self.ch2_voltage,
                            self.ch1, self.ch2,
                            self.DUT1_COLOR, self.DUT2_COLOR,
                            rect, x_min, x_max, y_min, y_max, line_width=3)

        # Axis labels
        for i in [0, 5, 10]:
            x_val = x_min + (x_max - x_min) * (10 - i) / 10
            x_pos = rect.x + (i * rect.width) // 10
            label = self.small_font.render(f"{int(x_val)}", True, self.LABEL_COLOR)
            label_rect = label.get_rect(center=(x_pos, rect.bottom + 25))
            self.screen.blit(label, label_rect)

        for i in [0, 5, 10]:
            y_val = y_min + (y_max - y_min) * i / 10
            y_pos = rect.y + (i * rect.height) // 10
            label = self.small_font.render(f"{int(y_val)}", True, self.LABEL_COLOR)
            label_rect = label.get_rect(midright=(rect.x - 10, y_pos))
            self.screen.blit(label, label_rect)

        # Axis titles
        x_title = self.font.render("DUT Voltage", True, self.AXIS_TITLE_COLOR)
        x_title_rect = x_title.get_rect(center=(rect.centerx, rect.bottom + 50))
        self.screen.blit(x_title, x_title_rect)

        y_title = self.font.render("Current", True, self.AXIS_TITLE_COLOR)
        self.screen.blit(y_title, (rect.x - 80, rect.centery - 30))

        # Legend
        legend_x = rect.x + 20
        legend_y = rect.y + 20

        pygame.draw.line(self.screen, self.DUT1_COLOR,
                         (legend_x, legend_y), (legend_x + 40, legend_y), 4)
        dut1_text = self.font.render("DUT1 (CH1 - Black Lead)", True, self.DUT1_COLOR)
        self.screen.blit(dut1_text, (legend_x + 50, legend_y - 12))

        if not self.single_channel:
            pygame.draw.line(self.screen, self.DUT2_COLOR,
                             (legend_x, legend_y + 30), (legend_x + 40, legend_y + 30), 4)
            dut2_text = self.font.render("DUT2 (CH2 - Red Lead)", True, self.DUT2_COLOR)
            self.screen.blit(dut2_text, (legend_x + 50, legend_y + 18))

        pygame.draw.rect(self.screen, self.BORDER_COLOR, rect, 2)

        # Pause overlay
        if self.paused:
            overlay_font = pygame.font.Font(None, 72)
            pause_text = overlay_font.render("PAUSED", True, YELLOW)
            pause_rect = pause_text.get_rect(center=rect.center)
            s = pygame.Surface((pause_rect.width + 40, pause_rect.height + 20))
            s.set_alpha(200)
            s.fill(BLACK)
            self.screen.blit(s, (pause_rect.x - 20, pause_rect.y - 10))
            self.screen.blit(pause_text, pause_rect)

    def draw_info_panel(self):
        """Draw info panel"""
        info_y = self.height - 60

        if self.ch1 and self.ch2 and self.drive_voltage:
            info_lines = [
                f"CH1 (DUT1 Current - Black Lead): {min(self.ch1):.0f}-{max(self.ch1):.0f}  Mean: {int(np.mean(self.ch1))}  Points: {len(self.ch1)}",
                f"CH2 (DUT2 Current - Red Lead): {min(self.ch2):.0f}-{max(self.ch2):.0f}  Mean: {int(np.mean(self.ch2))}  Points: {len(self.ch2)}",
                f"DUT Voltages: V1={min(self.ch1_voltage):.0f}-{max(self.ch1_voltage):.0f}, V2={min(self.ch2_voltage):.0f}-{max(self.ch2_voltage):.0f}, Drive={min(self.drive_voltage):.0f}-{max(self.drive_voltage):.0f}"
            ]
            for i, line in enumerate(info_lines):
                color = [self.DUT1_COLOR, self.DUT2_COLOR, self.DUT_VOLTAGE_COLOR][i]
                text = self.small_font.render(line, True, color)
                self.screen.blit(text, (20, info_y + i * 22))

        # Status
        mode_names = ["4.7K(T)", "100K WEAK(W)", "ALT"]
        mode_str = mode_names[self.excitation_mode]

        if self.excitation_mode == 2 and len(self.ch1) > 0:
            if self.last_mode_was_weak:
                mode_str = "ALT[W-bright T-dim]"
            else:
                mode_str = "ALT[T-bright W-dim]"

        pause_str = " [PAUSED]" if self.paused else ""
        single_str = " [SINGLE CH]" if self.single_channel else ""
        scale_str = " [AUTO]" if self.auto_scale else " [FIXED]"
        status = f"Controls: SPACE=mode P=pause S=single A=auto F=fit R=reset F1=settings | Drag=pan Wheel=zoom"
        info = f"Frame: {self.frame_count}  |  FPS: {self.fps:.1f}  |  Mode: {mode_str}{pause_str}{single_str}{scale_str}"
        status_text = self.small_font.render(status, True, GRAY)
        info_text = self.small_font.render(info, True, GRAY)
        self.screen.blit(status_text, (20, 5))
        self.screen.blit(info_text, (20, 20))

        # Show connection status
        conn_status = "Connected" if (self.serial and self.serial.is_open) else "NOT CONNECTED"
        conn_color = GREEN if (self.serial and self.serial.is_open) else RED
        conn_text = self.small_font.render(f"Serial: {conn_status}", True, conn_color)
        self.screen.blit(conn_text, (self.width - 200, 5))

    def run(self):
        """Main loop"""
        running = True
        last_update = time.time()

        debug_print("\n" + "=" * 70)
        debug_print("Curve Tracer - Dual DUT Comparison")
        debug_print("=" * 70)
        debug_print("\nKeyboard Controls:")
        debug_print("  SPACEBAR - Cycle excitation mode")
        debug_print("  P        - Pause/Resume")
        debug_print("  S        - Single channel mode")
        debug_print("  A        - Toggle Auto-scale")
        debug_print("  F        - Fit to window")
        debug_print("  R        - Reset view")
        debug_print("  F1       - Settings menu")
        debug_print("  Q/ESC    - Quit")
        debug_print("\nMouse: Drag=pan, Wheel=zoom")
        debug_print("=" * 70 + "\n")

        while running:
            dt = self.clock.tick(20) / 1000.0

            for event in pygame.event.get():
                # Handle window resize
                if event.type == pygame.VIDEORESIZE:
                    self.handle_resize(event.w, event.h)
                    continue

                # Settings window gets priority
                if self.settings_window.handle_event(event):
                    self._load_colors()
                    continue

                # Settings button (only if settings not active)
                if not self.settings_window.active:
                    if self.settings_button.handle_event(event):
                        self.settings_window.show()
                        continue

                # Skip other input if settings active
                if self.settings_window.active:
                    continue

                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.KEYDOWN:
                    if event.key in [self.get_key_from_config('quit'), pygame.K_ESCAPE]:
                        running = False
                    elif event.key == self.get_key_from_config('cycle_mode'):
                        self.excitation_mode = (self.excitation_mode + 1) % 3
                        mode_names = ["4.7K Ohm (T)", "100K Ohm WEAK (W)", "Alternating (T+W)"]
                        debug_print(f"Excitation mode: {mode_names[self.excitation_mode]}")
                    elif event.key == self.get_key_from_config('pause'):
                        self.paused = not self.paused
                        debug_print(f"Paused: {self.paused}")
                    elif event.key == self.get_key_from_config('single_channel'):
                        self.single_channel = not self.single_channel
                        debug_print(f"Single channel: {self.single_channel}")
                    elif event.key == self.get_key_from_config('auto_scale'):
                        self.auto_scale = not self.auto_scale
                        debug_print(f"Auto scale: {self.auto_scale}")
                    elif event.key == self.get_key_from_config('fit_window'):
                        if not self.auto_scale:
                            self.fit_to_window()
                    elif event.key == self.get_key_from_config('reset_view'):
                        if not self.auto_scale:
                            self.reset_view()
                    elif event.key == self.get_key_from_config('settings'):
                        self.settings_window.show()

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if not self.auto_scale:
                        if event.button == 1:
                            self.dragging = True
                            self.drag_start_pos = event.pos
                            self.drag_start_offset = (self.pan_offset_x, self.pan_offset_y)
                        elif event.button == 4:
                            self.zoom_level *= 1.2
                        elif event.button == 5:
                            self.zoom_level /= 1.2
                            self.zoom_level = max(0.1, self.zoom_level)

                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
                        self.dragging = False

                elif event.type == pygame.MOUSEMOTION:
                    if self.dragging and not self.auto_scale:
                        dx = event.pos[0] - self.drag_start_pos[0]
                        dy = event.pos[1] - self.drag_start_pos[1]

                        plot_width = self.width - 200
                        plot_height = self.height - 200

                        x_range_visible = ADC_MAX / self.zoom_level
                        y_range_visible = (ADC_MAX - 700) / self.zoom_level

                        x_offset_change = -dx * x_range_visible / plot_width
                        y_offset_change = -dy * y_range_visible / plot_height

                        self.pan_offset_x = self.drag_start_offset[0] - x_offset_change
                        self.pan_offset_y = self.drag_start_offset[1] + y_offset_change

            # Update settings window
            self.settings_window.update(dt)

            # Acquire data
            if not self.paused and not self.settings_window.active and self.acquire():
                self.frame_count += 1

            # Calculate FPS
            current_time = time.time()
            if current_time - last_update > 0:
                self.fps = 1.0 / (current_time - last_update)
            last_update = current_time

            # Draw
            self.screen.fill(self.BACKGROUND_COLOR)

            # Only draw main UI if settings is not active
            if not self.settings_window.active:
                # Calculate plot area dynamically based on window size
                margin = min(150, self.width // 10)
                plot_rect = pygame.Rect(
                    margin,
                    80,
                    self.width - margin - 50,
                    self.height - 200
                )
                self.draw_dual_xy_plot(plot_rect)
                self.draw_info_panel()
                self.settings_button.draw(self.screen)

            # Draw settings window (full screen when active)
            self.settings_window.draw(self.screen)

            pygame.display.flip()

        if self.serial:
            self.serial.close()
        pygame.quit()
        debug_print("\nClosed")


def main():
    app = CurveTracerDual()
    app.connect()
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
