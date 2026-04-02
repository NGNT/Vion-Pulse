import sys
import logging
from PyQt6.QtWidgets import QApplication, QSplashScreen
from PyQt6.QtGui import QPixmap
from gui.main_window import MainWindow

if __name__ == "__main__":
    LOG_FILE = "converter.log"
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[
                            logging.FileHandler(LOG_FILE),
                            logging.StreamHandler()
                        ])

    logging.info("Application started.")
    app = QApplication(sys.argv)

    splash = None
    try:
        pixmap = QPixmap("img/splash.png")
        if pixmap.isNull():
            raise FileNotFoundError("Splash image not found or could not be loaded.")
        splash = QSplashScreen(pixmap)
        splash.show()
        app.processEvents()
        logging.info("Splash screen displayed.")
    except Exception as e:
        logging.error(f"Could not load splash screen: {e}")

    window = MainWindow()
    window.show()

    if splash:
        splash.finish(window)

    sys.exit(app.exec())
