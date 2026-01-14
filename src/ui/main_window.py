import serial.tools.list_ports
import time
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
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 1. Connection Group
        left_layout.addWidget(self.create_connection_group())
        
        # 2. Control Mode & Status
        left_layout.addWidget(self.create_status_group())

        # 3. Jog Controls
        left_layout.addWidget(self.create_jog_group())

        # 4. Feed Rate (Removed)
        # left_layout.addWidget(self.create_speed_group())
        
        # Spacer
        left_layout.addStretch()
        
        # 5. Emergency Controls
        left_layout.addWidget(self.create_emg_group())

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
        
        self.btn_mode = QPushButton("MANUAL JOB")
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

    def toggle_mode(self, checked):
        if checked:
            self.btn_mode.setText("MANUAL JOB")
            self.btn_mode.setStyleSheet("background-color: #34343d;")
            self.log("Switched to MANUAL MODE")
        else:
            self.btn_mode.setText("AUTO JOB")
            self.btn_mode.setStyleSheet("background-color: #00897b;") # Teal for Auto
            self.log("Switched to AUTO MODE")

    # Removed create_speed_group as requested


    def create_emg_group(self):
        group = QGroupBox()
        group.setStyleSheet("border: none; background: transparent;")
        layout = QHBoxLayout()
        
        self.btn_emg = QPushButton("EMERGENCY STOP")
        self.btn_emg.setObjectName("btn_emg")
        self.btn_emg.clicked.connect(self.send_emg)
        
        self.btn_reset = QPushButton("RESET ALARM")
        self.btn_reset.setObjectName("btn_reset")
        self.btn_reset.clicked.connect(self.send_reset)
        self.btn_reset.setFixedWidth(120)
        self.btn_reset.setFixedHeight(50)
        
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
        btn_run_macro = QPushButton("RUN MACRO")
        btn_run_macro.setStyleSheet("background-color: #00897b;") 
        btn_run_macro.clicked.connect(self.run_macro)
        
        btn_stop_macro = QPushButton("STOP")
        btn_stop_macro.setStyleSheet("background-color: #d32f2f;")
        btn_stop_macro.clicked.connect(self.stop_macro)

        btn_clear_macro = QPushButton("CLEAR")
        btn_clear_macro.clicked.connect(lambda: self.text_macro.clear())
        
        layout_btns.addWidget(btn_run_macro)
        layout_btns.addWidget(btn_stop_macro)
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
        dist = self.step_size * direction
        cmd = f"G91 G0 {axis}{dist:.3f} F{self.feed_rate}"
        self.send_command(cmd)
        
    def send_home(self):
        self.send_command("G28")
        
    def send_emg(self):
        self.log("!!! EMERGENCY STOP !!!")
        if self.serial_worker.is_running:
            self.serial_worker.write_data('\\x18') 
            self.send_command("M112") 

    def send_reset(self):
        self.send_command("$X")
        self.send_command("M999")

    def run_macro(self):
        script = self.text_macro.toPlainText()
        if not script:
            return
        self.macro_runner.start_macro(script)
        
    def stop_macro(self):
        self.macro_runner.stop_macro()

    def on_macro_finished(self):
        self.log("Macro execution finished.")
        # Clear highlight
        cursor = self.text_macro.textCursor()
        cursor.select(QTextCursor.Document)
        fmt = QTextCharFormat()
        cursor.setCharFormat(fmt) # Reset
        
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
            
            # center view on line
            self.text_macro.setTextCursor(cursor)
            self.text_macro.ensureCursorVisible() 
