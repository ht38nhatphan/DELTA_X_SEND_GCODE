# DELTA X - ULTRA CONTROLLER

**Version**: 1.0.0
**Language**: Python (PyQt5)
**Author**: Nhat Phan

## Introduction
**DELTA X CONTROLLER** is a professional CNC/Delta X Robot control software, built on the Python and Qt5 platform. The software provides a modern Dark Mode interface, powerful Serial connectivity, and a smart Macro system.

## Key Features

### 1. User Interface (UI)
- **Dark Mode**: Professional dark interface, reducing eye strain during long operations.
- **Responsive**: Flexible and intuitive layout.

### 2. Control
- **Jogging**: Control X, Y, Z axes with flexible step sizes (0.01mm to 200mm).
- **Manual/Auto Mode**: Flexibly switch between manual and automatic modes.
- **Safety**: Integrated Emergency Stop (EMG) and Reset Alarm (M999) buttons.

### 3. Advanced Macro System
Smart G-code runner with superior features:
- **Handshake (Question-Answer)**: Ensures each command is executed (`ok` response) before sending the next one.
- **GOTO & Line Numbers**: Supports `GOTO` jump commands and `N` line numbering.
- **Visual Feedback**: Real-time highlighting of the running command line (Visual indicator).

**Macro Example:**
```gcode
N0 G28         ; Home
N5 GOTO 15     ; Jump over line 10
N10 G01 X100   ; This command will be skipped
N15 M03        ; Turn on Spindle
```

## Installation & Running

### Requirements
- Python 3.10+
- Conda (recommended)

### Install Libraries
```bash
pip install PyQt5 pyserial
```

### Run Software
```bash
python main.py
```

## Project Structure
```
DELTA_X/
├── main.py                # Main entry file
├── src/
│   ├── core/
│   │   ├── serial_worker.py  # Multi-threaded Serial processing
│   │   └── macro_runner.py   # Smart Macro processor
│   └── ui/
│       ├── main_window.py    # Main interface
│       └── styles.py         # Dark Theme (QSS)
└── README.md
```

python -m PyInstaller --onefile --noconsole main.py
pyinstaller app.spec