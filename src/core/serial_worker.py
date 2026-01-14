import serial
from PyQt5.QtCore import QThread, pyqtSignal

class SerialWorker(QThread):
    data_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    connected_status = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.serial_port = None
        self.port_name = ""
        self.baud_rate = 115200
        self.is_running = False

    def connect_serial(self, port, baud):
        self.port_name = port
        self.baud_rate = baud
        self.start() # Start the thread's run method

    def disconnect_serial(self):
        self.is_running = False
        if self.serial_port:
            try:
                self.serial_port.close()
            except:
                pass
        self.connected_status.emit(False)

    def run(self):
        try:
            self.serial_port = serial.Serial(self.port_name, self.baud_rate, timeout=0.1)
            self.is_running = True
            self.connected_status.emit(True)
            
            while self.is_running and self.serial_port.is_open:
                if self.serial_port.in_waiting > 0:
                    try:
                        line = self.serial_port.readline().decode('utf-8').strip()
                        if line:
                            self.data_received.emit(line)
                    except UnicodeDecodeError:
                        pass # Ignore decode errors
                else:
                    self.msleep(10) # Prevent CPU hogging
                    
        except serial.SerialException as e:
            self.error_occurred.emit(str(e))
            self.connected_status.emit(False)
        except Exception as e:
            self.error_occurred.emit(f"Unexpected Error: {e}")
            self.connected_status.emit(False)

    def write_data(self, data):
        if self.serial_port and self.serial_port.is_open:
            try:
                if not data.endswith('\n'):
                    data += '\n'
                self.serial_port.write(data.encode('utf-8'))
                return True
            except Exception as e:
                self.error_occurred.emit(f"Write Error: {e}")
        return False
