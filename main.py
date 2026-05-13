import sys

from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow

__version__ = "0.1.0"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Android PSS Memory Monitor")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
