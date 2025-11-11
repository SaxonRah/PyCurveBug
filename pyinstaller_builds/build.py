#!/usr/bin/env python3
"""
Build script for PyCurveBug using PyInstaller
Supports Windows, Linux, and macOS builds
"""

import os
import sys
import platform
import subprocess
import shutil
import argparse
from pathlib import Path


class BuildConfig:
    """Configuration for building PyCurveBug"""

    APP_NAME = "PyCurveBug"
    VERSION = "1.0.0"
    AUTHOR = "Robert Valentine"

    # Source files
    MAIN_SCRIPT = "PyCurveBug.py"
    CONFIG_FILE = "curvebug_config.json"

    # Build directories
    BUILD_DIR = "build"
    DIST_DIR = "dist"

    # Platform-specific settings
    PLATFORM_SETTINGS = {
        'Windows': {
            'icon': 'icon.ico',
            'extension': '.exe',
            'separator': ';',
            'console': False,
        },
        'Linux': {
            'icon': 'icon.png',
            'extension': '',
            'separator': ':',
            'console': False,
        },
        'Darwin': {  # macOS
            'icon': 'icon.icns',
            'extension': '.app',
            'separator': ':',
            'console': False,
            'bundle_identifier': 'com.communityTEK.pycurvebug',
        }
    }


def get_platform():
    """Detect the current platform"""
    system = platform.system()
    if system == 'Windows':
        return 'Windows'
    elif system == 'Linux':
        return 'Linux'
    elif system == 'Darwin':
        return 'Darwin'
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


def clean_build_dirs():
    """Remove previous build artifacts"""
    dirs_to_clean = [BuildConfig.BUILD_DIR, BuildConfig.DIST_DIR, '__pycache__']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            print(f"Cleaning {dir_name}...")
            shutil.rmtree(dir_name)

    # Remove spec file if it exists
    spec_file = f"{BuildConfig.APP_NAME}.spec"
    if os.path.exists(spec_file):
        os.remove(spec_file)
        print(f"Removed {spec_file}")


def check_dependencies():
    """Check if required packages are installed"""
    required_imports = {
        'pygame': 'pygame',
        'serial': 'pyserial',
        'numpy': 'numpy',
        'PyInstaller': 'pyinstaller'
    }

    missing_packages = []

    for import_name, package_name in required_imports.items():
        try:
            __import__(import_name)
            print(f"  YES - {package_name} ({import_name})")
        except ImportError:
            missing_packages.append(package_name)
            print(f"  NO - {package_name} ({import_name})")

    if missing_packages:
        print("\nError: Missing required packages:")
        for package in missing_packages:
            print(f"  - {package}")
        print("\nInstall them using:")
        print(f"  pip install {' '.join(missing_packages)}")
        return False

    return True


def find_icon(platform_name, custom_icon=None):
    """Find and validate icon file"""
    if custom_icon:
        if os.path.exists(custom_icon):
            print(f"  Yes, using custom icon: {custom_icon}")
            return custom_icon
        else:
            print(f"  No custom icon not found: {custom_icon}")

    # Try default icon for platform
    default_icon = BuildConfig.PLATFORM_SETTINGS[platform_name]['icon']
    if os.path.exists(default_icon):
        print(f"  Using default icon: {default_icon}")
        return default_icon

    print(f"  No icon file found (optional)")
    print(f"    Expected: {default_icon}")
    if platform_name == 'Windows':
        print("    Tip: Create an .ico file or use online converter")
    elif platform_name == 'Darwin':
        print("    Tip: Create an .icns file using 'iconutil' on macOS")

    return None


def create_spec_file(platform_name, icon_path=None):
    """Create a .spec file for PyInstaller"""
    settings = BuildConfig.PLATFORM_SETTINGS[platform_name]

    # Format icon path for spec file
    icon_line = f"icon='{icon_path}'" if icon_path else "icon=None"

    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['{BuildConfig.MAIN_SCRIPT}'],
    pathex=[],
    binaries=[],
    datas=[
        ('{BuildConfig.CONFIG_FILE}', '.'),
    ],
    hiddenimports=[
        'pygame',
        'serial',
        'serial.tools',
        'serial.tools.list_ports',
        'numpy',
        'numpy.core',
        'numpy.core._multiarray_umath',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
'''

    # Platform-specific EXE configuration
    if platform_name == 'Darwin':  # macOS
        spec_content += f'''
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='{BuildConfig.APP_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console={settings['console']},
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    {icon_line},
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='{BuildConfig.APP_NAME}',
)

app = BUNDLE(
    coll,
    name='{BuildConfig.APP_NAME}.app',
    {icon_line},
    bundle_identifier='{settings.get('bundle_identifier', 'com.example.pycurvebug')}',
    version='{BuildConfig.VERSION}',
)
'''
    else:  # Windows and Linux
        spec_content += f'''
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='{BuildConfig.APP_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console={settings['console']},
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    {icon_line},
)
'''

    spec_file = f"{BuildConfig.APP_NAME}.spec"
    with open(spec_file, 'w') as f:
        f.write(spec_content)

    print(f"Created {spec_file}")
    return spec_file


def build_executable(spec_file):
    """Build the executable using PyInstaller"""
    print(f"\nBuilding {BuildConfig.APP_NAME}...")
    print("This may take a few minutes...\n")

    cmd = [
        'pyinstaller',
        '--clean',
        '--noconfirm',
        spec_file
    ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print("Build failed!")
        print(e.stdout)
        print(e.stderr)
        return False


def create_distribution_package(platform_name):
    """Create a distribution package"""
    settings = BuildConfig.PLATFORM_SETTINGS[platform_name]

    # Create distribution directory
    dist_name = f"{BuildConfig.APP_NAME}-{BuildConfig.VERSION}-{platform_name}"
    dist_path = Path(BuildConfig.DIST_DIR) / dist_name

    if dist_path.exists():
        shutil.rmtree(dist_path)
    dist_path.mkdir(parents=True)

    # Copy executable
    if platform_name == 'Darwin':
        src = Path(BuildConfig.DIST_DIR) / f"{BuildConfig.APP_NAME}.app"
        if src.exists():
            shutil.copytree(src, dist_path / f"{BuildConfig.APP_NAME}.app")
    else:
        exe_name = f"{BuildConfig.APP_NAME}{settings['extension']}"
        src = Path(BuildConfig.DIST_DIR) / exe_name
        if src.exists():
            shutil.copy2(src, dist_path / exe_name)

    # Copy config file
    if os.path.exists(BuildConfig.CONFIG_FILE):
        shutil.copy2(BuildConfig.CONFIG_FILE, dist_path / BuildConfig.CONFIG_FILE)

    # Create README
    readme_content = f"""# {BuildConfig.APP_NAME} v{BuildConfig.VERSION}

## Installation

Simply extract this archive and run the executable.

## Configuration

The application uses `{BuildConfig.CONFIG_FILE}` for configuration.
You can modify this file to change:
- Serial port settings
- Window size
- Colors
- Keyboard shortcuts

## Usage

1. Connect your vintageTEK CurveBug device
2. Run {BuildConfig.APP_NAME}
3. Press F1 to open settings if needed
4. Use keyboard shortcuts for control:
   - SPACE: Cycle excitation mode
   - P: Pause/Resume
   - S: Single channel mode
   - A: Toggle auto-scale
   - F: Fit to window
   - R: Reset view
   - F1: Settings
   - Q/ESC: Quit

## Platform: {platform_name}

Built on: {platform.platform()}
Python version: {sys.version}
"""

    with open(dist_path / "README.txt", 'w') as f:
        f.write(readme_content)

    print(f"\nDistribution package created: {dist_path}")

    # Create archive
    archive_name = f"{dist_name}"
    if platform_name == 'Windows':
        archive_format = 'zip'
    else:
        archive_format = 'gztar'

    print(f"Creating archive: {archive_name}.{archive_format}")
    shutil.make_archive(
        str(Path(BuildConfig.DIST_DIR) / archive_name),
        archive_format,
        BuildConfig.DIST_DIR,
        dist_name
    )

    return dist_path


def main():
    """Main build process"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Build PyCurveBug executable')
    parser.add_argument('--icon', type=str,
                        help='Path to custom icon file (.ico for Windows, .icns for macOS, .png for Linux)')
    parser.add_argument('--console', action='store_true', help='Show console window (useful for debugging)')
    args = parser.parse_args()

    print("=" * 80)
    print(f"Building {BuildConfig.APP_NAME} v{BuildConfig.VERSION}")
    print("=" * 80)

    # Check if source file exists
    if not os.path.exists(BuildConfig.MAIN_SCRIPT):
        print(f"Error: {BuildConfig.MAIN_SCRIPT} not found!")
        return 1

    # Check dependencies
    print("\nChecking dependencies...")
    if not check_dependencies():
        return 1
    print("\nAll dependencies installed.")

    # Detect platform
    platform_name = get_platform()
    print(f"\nBuilding for: {platform_name}")

    # Override console setting if requested
    if args.console:
        BuildConfig.PLATFORM_SETTINGS[platform_name]['console'] = True
        print("Console window enabled for debugging")

    # Find icon
    print("\nLooking for icon file...")
    icon_path = find_icon(platform_name, args.icon)

    # Clean previous builds
    print("\nCleaning previous builds...")
    clean_build_dirs()

    # Create spec file
    print("\nCreating PyInstaller spec file...")
    spec_file = create_spec_file(platform_name, icon_path)

    # Build executable
    if not build_executable(spec_file):
        print("\nBuild failed!")
        return 1

    # Create distribution package
    print("\nCreating distribution package...")
    dist_path = create_distribution_package(platform_name)

    print("\n" + "=" * 80)
    print("Build completed successfully!")
    print("=" * 80)
    print(f"\nExecutable location: {BuildConfig.DIST_DIR}")
    print(f"Distribution package: {dist_path}")

    if icon_path:
        print(f"Icon applied: {icon_path}")
    else:
        print("\nNote: No icon was applied. To add an icon:")
        if platform_name == 'Windows':
            print("  1. Create or download an .ico file")
            print("  2. Save it as 'icon.ico' in this directory, or")
            print("  3. Run: python build.py --icon=path/to/your/icon.ico")
        elif platform_name == 'Darwin':
            print("  1. Create an .icns file")
            print("  2. Save it as 'icon.icns' in this directory, or")
            print("  3. Run: python build.py --icon=path/to/your/icon.icns")
        else:
            print("  1. Create or download a .png file")
            print("  2. Save it as 'icon.png' in this directory, or")
            print("  3. Run: python build.py --icon=path/to/your/icon.png")

    return 0


if __name__ == "__main__":
    sys.exit(main())