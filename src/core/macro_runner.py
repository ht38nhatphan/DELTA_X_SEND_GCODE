from PyQt5.QtCore import QObject, pyqtSignal, QTimer

class MacroRunner(QObject):
    """
    Handles step-by-step execution of G-code macros with 'ok' handshake.
    Supports N-line numbers and GOTO commands.
    """
    command_to_send = pyqtSignal(str)
    log_message = pyqtSignal(str)
    current_line_changed = pyqtSignal(int) # Emits the 0-based index of the line being executed
    finished = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.lines = []
        self.line_map = {} # Maps N-number to 'lines' list index
        self.current_index = 0
        self.is_running = False
        self.waiting_for_ok = False
        
        # Watchdog to prevent hanging forever if 'ok' is missed
        self.watchdog = QTimer()
        self.watchdog.setSingleShot(True)
        self.watchdog.timeout.connect(self.on_watchdog_timeout)
        self.watchdog_timeout_ms = 5000 # 5 seconds timeout

    def parse_script(self, script_text):
        """Pre-process script to find line numbers and clean content."""
        self.lines = script_text.split('\n')
        self.line_map = {}
        
        for idx, line in enumerate(self.lines):
            line = line.strip().upper()
            # Check for N number at start (e.g. "N10 G1...")
            parts = line.split()
            if parts and parts[0].startswith('N'):
                try:
                    # Extract number from N10 -> 10
                    n_val = int(parts[0][1:])
                    self.line_map[n_val] = idx
                except ValueError:
                    pass

    def start_macro(self, script_text):
        if self.is_running:
            return
            
        self.parse_script(script_text)
        if not self.lines:
            self.log_message.emit("Macro is empty.")
            return
            
        self.is_running = True
        self.current_index = 0
        self.waiting_for_ok = False
        self.log_message.emit("--- MACRO STARTED ---")
        
        self.run_current_line()

    def stop_macro(self):
        self.is_running = False
        self.watchdog.stop()
        self.log_message.emit("--- MACRO STOPPED ---")
        self.finished.emit()

    def run_current_line(self):
        if not self.is_running:
            return
            
        if self.current_index >= len(self.lines):
            self.stop_macro()
            return
            
        line_content = self.lines[self.current_index].strip()
        
        # Visual Update
        self.current_line_changed.emit(self.current_index)
        
        # Skip empty lines or comments
        if not line_content or line_content.startswith(';') or line_content.startswith('('):
            self.current_index += 1
            # Recurse immediately (use QTimer to avoid deep recursion recursion stack overflow)
            QTimer.singleShot(0, self.run_current_line)
            return

        # Check specifically for GOTO logic LOCALLY before sending anything
        # User Syntax: "N5 GOTO 15" or just "GOTO 15"
        # We need to parse parts again
        parts = line_content.upper().split()
        
        # Handle "N5 GOTO 15" -> parts=["N5", "GOTO", "15"]
        # Handle "GOTO 15" -> parts=["GOTO", "15"]
        
        goto_target = None
        
        if "GOTO" in parts:
            try:
                goto_idx = parts.index("GOTO")
                if goto_idx + 1 < len(parts):
                    goto_target = int(parts[goto_idx + 1])
            except ValueError:
                self.log_message.emit(f"Error parsing GOTO target in: {line_content}")
                self.stop_macro()
                return

        if goto_target is not None:
            # Execute GOTO
            if goto_target in self.line_map:
                self.log_message.emit(f"Executing: {line_content} -> Jumping to N{goto_target}")
                self.current_index = self.line_map[goto_target]
                # Small delay to let UI show the jump before executing next
                QTimer.singleShot(100, self.run_current_line) 
            else:
                self.log_message.emit(f"GOTO Error: Label N{goto_target} not found!")
                self.stop_macro()
            return

        # Determine pure command (strip N number if present, though controllers usually ignore it, 
        # it is cleaner to send raw G-code if the controller is strict, but standard G-code accepts N.
        # We will send the full line as is.)
        
        self.waiting_for_ok = True
        self.command_to_send.emit(line_content)
        self.watchdog.start(self.watchdog_timeout_ms)

    def on_serial_rx(self, message):
        """
        Called when new data comes from serial.
        We look for 'ok' to proceed.
        """
        print(message)
        if not self.is_running or not self.waiting_for_ok:
            return
        
        # Check for 'ok'
        if "ok" in message.lower():
            self.waiting_for_ok = False
            self.watchdog.stop()
            
            # Prepare next step
            self.current_index += 1
            # Add a tiny delay to allow UI to breathe
            QTimer.singleShot(50, self.run_current_line)

    def on_watchdog_timeout(self):
        if self.is_running and self.waiting_for_ok:
            self.log_message.emit("Timeout requesting 'ok' response. Stopping macro.")
            self.stop_macro()
