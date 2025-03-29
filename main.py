# main.py (Updated Entry Point - No changes needed from previous version)
import sys
from PyQt6.QtWidgets import QApplication, QMessageBox  # Added QMessageBox
import logging
import os  # Import os for path joining
# --- Import configuration ---
import config  # Needed for APP_DIR

# --- Import the main window ---
try:
    from annotator_window import AnnotatorWindow
except ImportError as e:
    print(f"[CRITICAL] Failed to import AnnotatorWindow: {e}")
    try:
        app = QApplication(sys.argv)
        QMessageBox.critical(
            None, "Startup Error", f"Failed to import main window components:\n{e}\n\nApplication cannot start.")
    except Exception as qt_err:
        print(f"[CRITICAL] Cannot start QApplication: {qt_err}")
    sys.exit(1)

if __name__ == "__main__":
    # --- Setup Logging ---
    log_path = "app_debug.log"
    log_dir_set = False
    log_handlers = [logging.StreamHandler()]
    try:
        if config.APP_DIR:
            os.makedirs(config.APP_DIR, exist_ok=True)
            log_path = os.path.join(config.APP_DIR, "app_debug.log")
            log_handlers.append(logging.FileHandler(log_path, mode='w'))
            log_dir_set = True
        else:
            print("[WARN] config.APP_DIR not defined, logging to current directory.")
            try:
                log_handlers.append(logging.FileHandler(log_path, mode='w'))
                log_dir_set = True
            except Exception as current_dir_log_e:
                print(
                    f"[ERROR] Failed log setup in current dir: {current_dir_log_e}")
    except Exception as log_e:
        print(f"[ERROR] Failed file log setup using config: {log_e}")
        try:
            log_handlers.append(logging.FileHandler(log_path, mode='w'))
            log_dir_set = True
        except Exception as current_dir_log_e:
            print(
                f"[ERROR] Failed log setup in current dir: {current_dir_log_e}")

    logging.basicConfig(
        level=logging.DEBUG, format="%(asctime)s - %(name)s [%(threadName)s] - %(levelname)s - %(message)s", handlers=log_handlers, force=True)
    logger = logging.getLogger(__name__)
    logger.info(
        f"Logging initialized. Log path configured: {log_path if log_dir_set else 'Console Only'}")
    # --- End Logging Setup ---

    # --- Run Application ---
    try:
        app = QApplication(sys.argv)
        window = AnnotatorWindow()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        logger.critical(
            "Unhandled exception during application execution:", exc_info=True)
        try:
            QMessageBox.critical(
                None, "Fatal Error", f"An unhandled error occurred:\n{e}\n\nApplication will exit. Check logs.")
        except Exception as msg_box_err:
            logger.error(
                f"Could not display final error msg box: {msg_box_err}")
        sys.exit(1)
