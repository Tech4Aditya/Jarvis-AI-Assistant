import sys
import threading

from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import QObject, pyqtSlot

from brain import ask_ai
from actions import perform_action
from voice import speak


class Backend(QObject):

    def __init__(self, view):
        super().__init__()
        self.view = view

    @pyqtSlot(str)
    def process(self, cmd):

        def run():
            result = perform_action(cmd)

            if result:
                response = result
            else:
                response = ask_ai(cmd)

            # send response to UI
            self.view.page().runJavaScript(
                f"addMessage(`{response}`, 'jarvis')"
            )

            speak(response)

        threading.Thread(target=run, daemon=True).start()


def start_ui():
    app = QApplication(sys.argv)

    view = QWebEngineView()
    view.setWindowTitle("JARVIS")
    view.setGeometry(200, 100, 1000, 800)

    channel = QWebChannel()
    backend = Backend(view)

    channel.registerObject("backend", backend)
    view.page().setWebChannel(channel)

    with open("ui.html", "r", encoding="utf-8") as f:
        html = f.read()

    view.setHtml(html)

    view.show()
    sys.exit(app.exec())