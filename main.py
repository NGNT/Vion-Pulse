import sys
from PyQt6.QtWidgets import QApplication, QSplashScreen
from PyQt6.QtGui import QPixmap
from gui.main_window_old import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Splash screen
    try:
        pixmap = QPixmap("img/splash.png")
        splash = QSplashScreen(pixmap)
        splash.show()
    except Exception as e:
        print(f"Could not load splash screen: {e}")
        splash = None

    window = MainWindow()
    window.show()
    
    if splash:
        splash.finish(window)
        
    sys.exit(app.exec())
