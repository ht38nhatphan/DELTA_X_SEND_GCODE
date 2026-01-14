import sys
from PyQt5.QtWidgets import QApplication
from src.ui.main_window import CNCWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = CNCWindow()
    window.show()
    
    sys.exit(app.exec_())
