import serial.tools.list_ports
import time
import re
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QGridLayout, QPushButton, QLabel, QComboBox, 
                             QTextEdit, QLineEdit, QGroupBox, QRadioButton, 
                             QButtonGroup, QSlider, QSplitter, QMessageBox, 
                             QFrame, QApplication)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QTextCursor, QTextBlockFormat, QColor, QTextCharFormat
from src.core.serial_worker import SerialWorker
from src.core.macro_runner import MacroRunner
from src.ui.styles import DARK_THEME_QSS

class CNCWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DELTA X - ULTRA CONTROLLER")
        self.resize(1000, 700)
        self.setStyleSheet(DARK_THEME_QSS)
        self.toggle_mode_checked = True
        # State vars
        self.serial_worker = SerialWorker()
        self.macro_runner = MacroRunner()
        self.step_size = 1.0
        self.feed_rate = 1000

        # Signals - Serial
        self.serial_worker.data_received.connect(self.on_serial_data)
        self.serial_worker.error_occurred.connect(self.on_serial_error)
        self.serial_worker.connected_status.connect(self.on_connection_status_changed)
        
        # Signals - Macro
        self.macro_runner.command_to_send.connect(self.send_command)
        self.macro_runner.log_message.connect(self.log)
        self.macro_runner.current_line_changed.connect(self.highlight_current_line)
        self.macro_runner.finished.connect(self.on_macro_finished)
        
        # Connect Serial RX to Macro Runner for handshake
        self.serial_worker.data_received.connect(self.macro_runner.on_serial_rx)

        # Position Polling Timer
        self.timer_position = QTimer()
        self.timer_position.setInterval(200) # 200ms
        self.timer_position.timeout.connect(self.request_position)

        # UI Initialization
        self.init_ui()
        self.refresh_ports()

        
        # Set Default Step Size triggers logic, so do it AFTER UI init
        # Find the 1.0 button and check it
        if hasattr(self, 'step_btn_group'):
            for btn in self.step_btn_group.buttons():
                if btn.text() == "1":
                    btn.setChecked(True)
                    break

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main Layout: Left (Controls) | Right (Terminal/Macro)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # --- LEFT PANEL (Controls) ---
        # --- LEFT PANEL (Controls) ---
        left_panel = QWidget()
        left_main_layout = QHBoxLayout(left_panel) # Split into 2 columns
        left_main_layout.setContentsMargins(0, 0, 0, 0)
        left_main_layout.setSpacing(10)
        
        # COL 1 (Left)
        col1_widget = QWidget()
        col1_layout = QVBoxLayout(col1_widget)
        col1_layout.setContentsMargins(0, 0, 0, 0)
        
        col1_layout.addWidget(self.create_connection_group())
        col1_layout.addWidget(self.create_status_group())
        col1_layout.addWidget(self.create_position_group())
        col1_layout.addWidget(self.create_speed_group())
        col1_layout.addStretch() # Push up
        
        # COL 2 (Right)
        col2_widget = QWidget()
        col2_layout = QVBoxLayout(col2_widget)
        col2_layout.setContentsMargins(0, 0, 0, 0)
        
        col2_layout.addWidget(self.create_motion_params_group())
        col2_layout.addWidget(self.create_jog_group())
        col2_layout.addWidget(self.create_emg_group())
        col2_layout.addStretch() # Push up
        
        # Add cols to Left Main Layout
        left_main_layout.addWidget(col1_widget)
        left_main_layout.addWidget(col2_widget)

        # --- RIGHT PANEL (Terminal & Logic) ---
        right_panel = QWidget()

        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 1. Terminal Group
        right_layout.addWidget(self.create_terminal_group(), stretch=3)

        # 2. Macro Group
        right_layout.addWidget(self.create_macro_group(), stretch=2)

        # ADD TO SPLITTER OR LAYOUT directly
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1) # 50/50 split
        
        main_layout.addWidget(splitter)

    # ------------------------------------------------------------------------
    # UI COMPONENT CREATION
    # ------------------------------------------------------------------------
    def create_connection_group(self):
        group = QGroupBox("Connection")
        layout = QGridLayout()
        
        self.combo_ports = QComboBox()
        self.btn_refresh = QPushButton("R")
        self.btn_refresh.setFixedWidth(30)
        self.btn_refresh.clicked.connect(self.refresh_ports)
        
        self.combo_baud = QComboBox()
        self.combo_baud.addItems(["9600", "19200", "38400", "57600", "115200", "250000"])
        self.combo_baud.setCurrentText("115200")

        self.btn_connect = QPushButton("CONNECT")
        self.btn_connect.clicked.connect(self.toggle_connection)
        
        layout.addWidget(QLabel("Port:"), 0, 0)
        layout.addWidget(self.combo_ports, 0, 1)
        layout.addWidget(self.btn_refresh, 0, 2)
        
        layout.addWidget(QLabel("Baud:"), 1, 0)
        layout.addWidget(self.combo_baud, 1, 1, 1, 2)
        
        layout.addWidget(self.btn_connect, 2, 0, 1, 3)
        
        group.setLayout(layout)
        return group

    def create_status_group(self):
        group = QGroupBox("Status & Mode")
        layout = QHBoxLayout()
        
        self.lbl_status = QLabel("DISCONNECTED")
        self.lbl_status.setStyleSheet("color: #757575; font-weight: bold; font-size: 14px;")
        
        self.btn_mode = QPushButton("AUTO JOB")
        self.btn_mode.setStyleSheet("background-color: #00897b;")
        self.btn_mode.setCheckable(True)
        self.btn_mode.setChecked(True)
        # self.btn_mode.setDisabled(True) # Removed disable
        self.btn_mode.toggled.connect(self.toggle_mode)

        layout.addWidget(QLabel("State:"))
        layout.addWidget(self.lbl_status)
        layout.addStretch()
        layout.addWidget(self.btn_mode)
        
        group.setLayout(layout)
        return group

    def create_position_group(self):
        group = QGroupBox("Position (mm)")
        layout = QGridLayout()
        
        # Styles for position labels
        style_val = "font-size: 18px; font-weight: bold; color: #4db6ac;" # Teal color
        style_lbl = "font-size: 14px; font-weight: bold; color: #b0bec5;"

        self.lbl_pos_x = QLabel("0.000")
        self.lbl_pos_x.setStyleSheet(style_val)
        self.lbl_pos_x.setAlignment(Qt.AlignRight)
        
        self.lbl_pos_y = QLabel("0.000")
        self.lbl_pos_y.setStyleSheet(style_val)
        self.lbl_pos_y.setAlignment(Qt.AlignRight)
        
        self.lbl_pos_z = QLabel("0.000")
        self.lbl_pos_z.setStyleSheet(style_val)
        self.lbl_pos_z.setAlignment(Qt.AlignRight)

        # Labels
        layout.addWidget(QLabel("X:"), 0, 0)
        layout.addWidget(self.lbl_pos_x, 0, 1)
        
        layout.addWidget(QLabel("Y:"), 1, 0)
        layout.addWidget(self.lbl_pos_y, 1, 1)
        
        layout.addWidget(QLabel("Z:"), 2, 0)
        layout.addWidget(self.lbl_pos_z, 2, 1)

        group.setLayout(layout)
        return group

    def create_speed_group(self):
        group = QGroupBox("Speed Override")
        layout = QHBoxLayout() # Horizontal layout for buttons
        
        self.speed_btn_group = QButtonGroup()
        self.speed_btn_group.setExclusive(True)
        
        # 0%, 5%, 20%, 40%, 60%, 80%, 100%
        percentages = [0, 5, 20, 40, 60, 80, 100]
        
        for p in percentages:
            rbtn = QRadioButton(f"{p}%")
            if p == 5:
                rbtn.setChecked(True)
            
            # Connect
            rbtn.toggled.connect(lambda checked, val=p: self.on_speed_changed(val) if checked else None)
            
            layout.addWidget(rbtn)
            self.speed_btn_group.addButton(rbtn)
            
        group.setLayout(layout)
        return group

    def create_motion_params_group(self):
        # Motion Parameters Group (F, A, J, S, E)
        group = QGroupBox("Cài Đặt Chuyển Động (Motion Params)")
        layout = QGridLayout()
        layout.setSpacing(10)
        
        # Styles
        lbl_style = "font-weight: bold; font-size: 14px; color: #b0bec5;"
        val_style = "font-weight: bold; font-size: 14px; color: #ffd700;" # Gold
        
        # Labels map
        self.lbl_motion_vals = {}
        params = [
            ("F", "Tốc độ trục 5 (u/s)"), 
            ("A", "Gia tốc trục 5 (u/s²)"), 
            ("J", "Giật trục 5 (u/s³)"), 
            ("S", "Vận tốc đầu (u/s)"), 
            ("E", "Vận tốc cuối (u/s)")
        ]
        
        for i, (key, desc) in enumerate(params):
            l_key = QLabel(f"{key}:")
            l_key.setStyleSheet(lbl_style)
            l_key.setToolTip(desc)
            
            l_val = QLabel("---")
            l_val.setStyleSheet(val_style)
            l_val.setAlignment(Qt.AlignRight)
            self.lbl_motion_vals[key] = l_val
            
            layout.addWidget(l_key, i, 0)
            layout.addWidget(l_val, i, 1)
        
        # Button GET PARAMS
        self.btn_get_params = QPushButton("LẤY THÔNG SỐ (GET PARAMS)")
        self.btn_get_params.setCursor(Qt.PointingHandCursor)
        self.btn_get_params.setStyleSheet("""
            QPushButton {
                background-color: #5c6bc0;
                color: white;
                font-weight: bold;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton:hover { background-color: #7986cb; }
        """)
        self.btn_get_params.clicked.connect(self.request_motion_params)
        
        layout.addWidget(self.btn_get_params, 5, 0, 1, 2)
        
        group.setLayout(layout)
        return group

    def create_jog_group(self):
        group = QGroupBox("Jog Control")
        layout = QVBoxLayout()

        # Step Size Selection
        step_layout = QHBoxLayout()
        self.step_btn_group = QButtonGroup()
        
        steps = [0.01, 0.1, 1, 5, 10, 100, 200]
        for val in steps:
            rbtn = QRadioButton(str(val))
            # Connect toggle but DON'T set Checked=True here within loop to avoid early firing before UI is ready
            rbtn.toggled.connect(lambda checked, v=val: self.set_step(v) if checked else None)
            step_layout.addWidget(rbtn)
            self.step_btn_group.addButton(rbtn)
        
        layout.addLayout(step_layout)
        
        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #444;")
        layout.addWidget(line)

        # Jog Grid
        grid = QGridLayout()
        grid.setSpacing(10)
        
        btn_y_plus = QPushButton("Y+")
        btn_y_plus.setProperty("class", "jog-btn")
        btn_y_plus.clicked.connect(lambda: self.send_jog('Y', 1))
        
        btn_y_minus = QPushButton("Y-")
        btn_y_minus.setProperty("class", "jog-btn")
        btn_y_minus.clicked.connect(lambda: self.send_jog('Y', -1))

        btn_x_minus = QPushButton("X-")
        btn_x_minus.setProperty("class", "jog-btn")
        btn_x_minus.clicked.connect(lambda: self.send_jog('X', -1))
        
        btn_x_plus = QPushButton("X+")
        btn_x_plus.setProperty("class", "jog-btn")
        btn_x_plus.clicked.connect(lambda: self.send_jog('X', 1))

        btn_z_plus = QPushButton("Z+")
        btn_z_plus.setProperty("class", "jog-btn")
        btn_z_plus.clicked.connect(lambda: self.send_jog('Z', 1))
        
        btn_z_minus = QPushButton("Z-")
        btn_z_minus.setProperty("class", "jog-btn")
        btn_z_minus.clicked.connect(lambda: self.send_jog('Z', -1))

        btn_home = QPushButton("HOME (G28)")
        btn_home.setObjectName("btn_home")
        btn_home.clicked.connect(self.send_home)
        
        grid.addWidget(btn_y_plus, 0, 1)
        grid.addWidget(btn_z_plus, 0, 3)
        grid.addWidget(btn_x_minus, 1, 0)
        grid.addWidget(btn_home, 1, 1)
        grid.addWidget(btn_x_plus, 1, 2)
        grid.addWidget(btn_z_minus, 1, 3) 
        grid.addWidget(btn_y_minus, 2, 1)
        
        layout.addLayout(grid)
        group.setLayout(layout)
        return group

    def toggle_mode(self):
        if not self.btn_mode.isChecked():
            self.btn_mode.setText("MANUAL JOB")
            self.btn_mode.setStyleSheet("background-color: #34343d;")
            self.log("Switched to MANUAL MODE")
            
            # Send M84 and Start Polling
            self.send_command("M84 0A") 
            self.timer_position.start()
        else:
            self.btn_mode.setText("AUTO JOB")
            self.btn_mode.setStyleSheet("background-color: #00897b;") # Teal for Auto
            self.log("Switched to AUTO MODE")
            
            # Stop Polling
            self.timer_position.stop()

    # Removed create_speed_group as requested


    def create_emg_group(self):
        group = QGroupBox()
        group.setStyleSheet("border: none; background: transparent; margin-top: 10px;")
        layout = QHBoxLayout()
        layout.setSpacing(10)
        
        # Emergency Stop - Big Red Button
        self.btn_emg = QPushButton("EMERGENCY STOP")
        self.btn_emg.setObjectName("btn_emg")
        self.btn_emg.clicked.connect(self.send_emg)
        self.btn_emg.setCursor(Qt.PointingHandCursor)
        self.btn_emg.setFixedHeight(60)
        self.btn_emg.setStyleSheet("""
            QPushButton {
                background-color: #d32f2f;
                color: white;
                font-weight: bold;
                font-size: 16px;
                border: 2px solid #b71c1c;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #e53935;
            }
            QPushButton:pressed {
                background-color: #c62828;
            }
        """)
        
        # Reset Emergency - Distinct Style
        self.btn_reset = QPushButton("RESET EMERGENCY")
        self.btn_reset.setObjectName("btn_reset")
        self.btn_reset.clicked.connect(self.send_reset)
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setFixedHeight(60)
        self.btn_reset.setFixedWidth(180)
        self.btn_reset.setStyleSheet("""
            QPushButton {
                background-color: #f57f17;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #f9a825;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #fbc02d;
            }
            QPushButton:pressed {
                background-color: #f57f17;
            }
        """)
        
        layout.addWidget(self.btn_emg, stretch=1)
        layout.addWidget(self.btn_reset)
        
        group.setLayout(layout)
        return group

    def create_terminal_group(self):
        group = QGroupBox("Terminal & Signals")
        layout = QVBoxLayout()
        
        self.text_terminal = QTextEdit()
        self.text_terminal.setReadOnly(True)
        self.text_terminal.setStyleSheet("font-family: 'Consolas', 'Courier New'; font-size: 13px; color: #cfd8dc;")
        
        self.input_terminal = QLineEdit()
        self.input_terminal.setPlaceholderText("Type G-Code command here (e.g. G0 X10)...")
        self.input_terminal.returnPressed.connect(self.send_manual_command)
        
        layout.addWidget(self.text_terminal)
        layout.addWidget(self.input_terminal)
        
        group.setLayout(layout)
        return group

    def create_macro_group(self):
        group = QGroupBox("Macro Programming")
        layout = QVBoxLayout()
        
        self.text_macro = QTextEdit()
        self.text_macro.setPlaceholderText("Enter G-code program here...\\nG90\\nG0 X10 Y10\\n...")
        self.text_macro.setStyleSheet("font-family: 'Consolas'; color: #b2dfdb;")
        
        layout_btns = QHBoxLayout()
        self.btn_run_macro = QPushButton("RUN")
        self.btn_run_macro.setStyleSheet("background-color: #00897b;") 
        self.btn_run_macro.clicked.connect(self.run_macro)
        
        self.btn_debug_macro = QPushButton("DEBUG")
        self.btn_debug_macro.setStyleSheet("background-color: #f57f17;") # Orange
        self.btn_debug_macro.clicked.connect(self.start_debug)
        
        self.btn_step_macro = QPushButton("STEP")
        self.btn_step_macro.setStyleSheet("background-color: #0277bd;") # Blue
        self.btn_step_macro.clicked.connect(self.step_macro)
        self.btn_step_macro.setEnabled(False) # Start disabled

        self.btn_stop_macro = QPushButton("STOP")
        self.btn_stop_macro.setStyleSheet("background-color: #d32f2f;")
        self.btn_stop_macro.clicked.connect(self.stop_macro)

        layout_btns.addWidget(self.btn_run_macro)
        layout_btns.addWidget(self.btn_debug_macro)
        layout_btns.addWidget(self.btn_step_macro)
        layout_btns.addWidget(self.btn_stop_macro)

        btn_clear_macro = QPushButton("CLEAR")
        btn_clear_macro.clicked.connect(lambda: self.text_macro.clear())
        layout_btns.addWidget(btn_clear_macro)
        
        layout.addWidget(self.text_macro)
        layout.addLayout(layout_btns)
        
        group.setLayout(layout)
        return group

    # ------------------------------------------------------------------------
    # LOGIC
    # ------------------------------------------------------------------------
    def refresh_ports(self):
        self.combo_ports.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.combo_ports.addItem(port.device)

    def toggle_connection(self):
        if not self.serial_worker.is_running:
            port = self.combo_ports.currentText()
            baud = self.combo_baud.currentText()
            
            if not port:
                QMessageBox.warning(self, "No Port", "Please select a COM port.")
                return
                
            self.log(f"Connecting to {port} at {baud}...")
            self.serial_worker.connect_serial(port, int(baud))
        else:
            self.serial_worker.disconnect_serial()

    def on_connection_status_changed(self, connected):
        if connected:
            self.btn_connect.setText("DISCONNECT")
            self.btn_connect.setStyleSheet("background-color: #4caf50; color: white;")
            self.lbl_status.setText("CONNECTED")
            self.lbl_status.setStyleSheet("color: #4caf50; font-weight: bold;")
        else:
            self.btn_connect.setText("CONNECT")
            self.btn_connect.setStyleSheet("") 
            self.lbl_status.setText("DISCONNECTED")
            self.lbl_status.setStyleSheet("color: #d32f2f; font-weight: bold;")

    def on_serial_data(self, data):
        self.log(f"[RX] {data}")
        
        # Parse Position
        # Format provided by user: +30.4,-065.32,-300.00
        # Regex: Look for 3 comma-separated numbers (float)
        
        # 1. New CSV Format
        match_csv = re.search(r"([+-]?\d+(?:\.\d+)?),([+-]?\d+(?:\.\d+)?),([+-]?\d+(?:\.\d+)?)", data)
        if match_csv:
            try:
                x = float(match_csv.group(1))
                y = float(match_csv.group(2))
                z = float(match_csv.group(3))
                self.update_position_display(x, y, z)
            except ValueError:
                pass

        # 2. Keep Grbl Status Format just in case: MPos:0.000,0.000,0.000
        if "MPos:" in data or "WPos:" in data:
            match_grbl = re.search(r"(?:MPos|WPos):([-\d\.]+),([-\d\.]+),([-\d\.]+)", data)
            if match_grbl:
                try:
                    x = float(match_grbl.group(1))
                    y = float(match_grbl.group(2))
                    z = float(match_grbl.group(3))
                    self.update_position_display(x, y, z)
                except ValueError:
                    pass

        # 3. Parse Motion Parameters (M220 I0 response)
        # Looking for F, A, J, S, E values. 
        # Pattern assumption: F:1000 A:500 or F1000 A500
        # We'll use a generic finder for these keys.
        # Check if we have labels first (in case UI not initialized fully)
        if hasattr(self, 'lbl_motion_vals'):
            # Regex to find Key:Value or KeyValue
            # Matches F, A, J, S, E followed optionally by : then a number
            params = re.findall(r"([FAJSE])[:\s]*(\d+(?:\.\d+)?)", data, re.IGNORECASE)
            if params:
                for key, val in params:
                    u_key = key.upper()
                    if u_key in self.lbl_motion_vals:
                        self.lbl_motion_vals[u_key].setText(val)

    def on_serial_error(self, error):
        self.log(f"[ERROR] {error}")
        QMessageBox.critical(self, "Serial Error", str(error))

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        # SAFETY CHECK: Ensure text_terminal exists
        if not hasattr(self, 'text_terminal') or self.text_terminal is None:
            print(f"[{timestamp}] {message}") # Fallback to console
            return
            
        self.text_terminal.append(f"[{timestamp}] {message}")
        self.text_terminal.moveCursor(self.text_terminal.textCursor().End)

    def set_step(self, val):
        self.step_size = val
        self.log(f"Step size set to: {val} mm")

    # update_feed_label removed

    def send_command(self, cmd):
        if not self.serial_worker.is_running:
            self.log("[SYS] Not connected.")
            # For demonstration, log what would be sent even if not connected
            # self.log(f"(Mock) [TX] {cmd}") 
            return

        cmd = cmd.strip()
        self.log(f"[TX] {cmd}")
        self.serial_worker.write_data(cmd)

    def send_manual_command(self):
        cmd = self.input_terminal.text()
        if cmd:
            self.send_command(cmd)
            self.input_terminal.clear()

    def send_jog(self, axis, direction):
        # User requested: G90 move based on current UI position
        
        # 1. Get current position for the requested axis from UI
        current_val = 0.0
        try:
            if axis == 'X':
                text = self.lbl_pos_x.text()
            elif axis == 'Y':
                text = self.lbl_pos_y.text()
            elif axis == 'Z':
                text = self.lbl_pos_z.text()
            else:
                text = "0"
            
            # Remove any non-numeric chars except . and - and +
            # Actually float() handles whitespace, but let's be safe if "X: 10" is used (though it isn't here)
            current_val = float(text)
        except ValueError:
            current_val = 0.0
            
        # 2. Calculate Target
        dist = self.step_size * direction
        target = current_val + dist
        
        # 3. Send G90 Absolute Move
        # "VD ĐANG CLICK VÀO 1 THÌ GỬI LÀ G01 X..1."
        # We'll assume they mean target position.
        # Format: G90 G01 X<Target> F<Speed>
        cmd = f"G01 {axis}{target:.3f}"
        self.send_command(cmd)
        
    def send_home(self):
        # Auto-off Manual Mode requested
        if not self.btn_mode.isChecked():
             self.btn_mode.setChecked(True) # This will trigger toggle_mode -> stop timer
        self.send_command("G28")
        
    def send_emg(self):
        self.log("!!! EMERGENCY STOP !!!")
        if self.serial_worker.is_running:
            self.send_command("M600 A4 B5") 

    def send_reset(self):
        self.send_command("M502")

    def run_macro(self):
        script = self.text_macro.toPlainText()
        if not script:
            return
        if not script:
            return
        self.macro_runner.start_macro(script, is_debug=False)
        self.update_macro_ui_state(running=True, debug=False)

    def start_debug(self):
        script = self.text_macro.toPlainText()
        if not script:
            return
        self.macro_runner.start_macro(script, is_debug=True)
        self.update_macro_ui_state(running=True, debug=True)
        
    def step_macro(self):
        self.macro_runner.step()
        
    def stop_macro(self):
        self.macro_runner.stop_macro()
        # State update handled in on_macro_finished or here?
        # on_macro_finished is emitted by runner, so we rely on that.

    def on_macro_finished(self):
        self.log("Macro execution finished.")
        self.update_macro_ui_state(running=False, debug=False)
        
        # Clear highlight
        cursor = self.text_macro.textCursor()
        cursor.select(QTextCursor.Document)
        fmt = QTextCharFormat()
        cursor.setCharFormat(fmt) # Reset
        
    def update_macro_ui_state(self, running: bool, debug: bool):
        """
        Update button states based on execution status.
        """
        if running:
            self.btn_run_macro.setEnabled(False)
            self.btn_debug_macro.setEnabled(False)
            self.text_macro.setReadOnly(True)
            self.btn_stop_macro.setEnabled(True)
            if debug:
                self.btn_step_macro.setEnabled(True)
            else:
                self.btn_step_macro.setEnabled(False)
        else:
            self.btn_run_macro.setEnabled(True)
            self.btn_debug_macro.setEnabled(True)
            self.text_macro.setReadOnly(False)
            self.btn_stop_macro.setEnabled(False)
            self.btn_step_macro.setEnabled(False)
        
    def highlight_current_line(self, line_index):
        """
        Highlights the background of the current line in the macro editor 
        to act as a visual arrow/cursor.
        """
        # Reset formatting first
        cursor = self.text_macro.textCursor()
        cursor.select(QTextCursor.Document)
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#15151a")) # Default dark bg
        cursor.setCharFormat(fmt)
        
        # Highlight specific line
        doc = self.text_macro.document()
        block = doc.findBlockByNumber(line_index)
        
        if block.isValid():
            cursor.setPosition(block.position())
            cursor.select(QTextCursor.BlockUnderCursor)
            
            fmt.setBackground(QColor("#00695c")) # Teal Highlight
            cursor.setCharFormat(fmt)
            
            self.text_macro.setTextCursor(cursor)
            self.text_macro.ensureCursorVisible() 

    def on_speed_changed(self, val):
        # val is now percentage directly (20, 40, ..., 100)
        self.log(f"Speed Override: {val}%")
        
        # Update MacroRunner with speed override
        self.macro_runner.set_speed_override(val / 100.0)

    def request_motion_params(self):
        # User requested M220 I0 to get F, A, J, S, E params
        if self.serial_worker.is_running:
            self.send_command("M220 I0")
        else:
            self.log("Not connected!")

    def request_position(self):
        if self.serial_worker.is_running:
            # Send '?' for status report. 
            # Note: We use write_data directly or send_command? 
            # send_command logs every [TX], which might spam the log every 200ms.
            # So we might want to bypass log, OR just accept the spam. 
            # Let's bypass log for polling to keep it clean.
            self.serial_worker.write_data("Position")

    def update_position_display(self, x, y, z):
        # Sync to Macro Runner for #robot0.HOME_X/Y/Z variables
        self.macro_runner.update_machine_position(x, y, z)
        
        self.lbl_pos_x.setText(f"{x:.3f}")
        self.lbl_pos_y.setText(f"{y:.3f}")
        self.lbl_pos_z.setText(f"{z:.3f}") 
