# Professional Dark Theme QSS

DARK_THEME_QSS = """
QMainWindow {
    background-color: #1e1e24;
    color: #e0e0e0;
}
QWidget {
    font-family: 'Segoe UI', 'Roboto', sans-serif;
    font-size: 14px;
    color: #e0e0e0;
}
QGroupBox {
    border: 1px solid #3a3a45;
    border-radius: 8px;
    margin-top: 1.2em;
    font-weight: bold;
    color: #00bcd4; /* Cyan accent */
    background-color: #25252b;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    left: 10px;
}
QPushButton {
    background-color: #34343d;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
    color: #ffffff;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #454552;
}
QPushButton:pressed {
    background-color: #00bcd4; /* Cyan */
    color: #121212;
}
QPushButton:disabled {
    background-color: #2a2a30;
    color: #555;
}
/* Special Buttons */
QPushButton#btn_emg {
    background-color: #d32f2f; /* Red */
    border-radius: 8px;
    font-size: 16px;
    padding: 15px;
}
QPushButton#btn_emg:hover {
    background-color: #b71c1c;
}
QPushButton#btn_emg:pressed {
    background-color: #ff5252;
}
QPushButton#btn_home {
    background-color: #1976d2; /* Blue */
}
QPushButton#btn_reset {
    background-color: #fbc02d; /* Yellow/Amber */
    color: #000;
}

/* Jog Buttons */
QPushButton.jog-btn {
    background-color: #2d2d36;
    border: 2px solid #3a3a45;
    border-radius: 5px;
    font-size: 16px;
}
QPushButton.jog-btn:pressed {
    background-color: #00bcd4;
    border-color: #00bcd4;
}

/* Inputs */
QLineEdit, QTextEdit, QComboBox {
    background-color: #15151a;
    border: 1px solid #3a3a45;
    border-radius: 4px;
    padding: 5px;
    color: #00e5ff; /* Bright Cyan text */
}
QLineEdit:focus, QTextEdit:focus {
    border: 1px solid #00bcd4;
}
QScrollBar:vertical {
    border: none;
    background: #1e1e24;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #444;
    border-radius: 5px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Radio Buttons */
QRadioButton {
    spacing: 5px;
}
QRadioButton::indicator {
    width: 18px;
    height: 18px;
}
QRadioButton::indicator:unchecked {
    image: none;
    background-color: #15151a;
    border: 2px solid #555;
    border-radius: 9px;
}
QRadioButton::indicator:checked {
    background-color: #00bcd4;
    border: 2px solid #00bcd4;
    border-radius: 9px;
}
"""
