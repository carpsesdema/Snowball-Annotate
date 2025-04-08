import sys
import os
import logging
import requests # Ensure 'requests' library is installed (pip install requests)
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QInputDialog

# --- Import configuration ---
import config  # Needed for APP_DIR

# --- Import the main window ---
try:
    from annotator_window import AnnotatorWindow
except ImportError as e:
    # If main window fails, show error before trying license check
    app_init = QApplication.instance() # Check if app exists
    if not app_init:
        app_init = QApplication(sys.argv) # Create if not
    QMessageBox.critical(None, "Startup Error", f"Failed to import main window components:\n{e}\n\nApplication cannot start.")
    sys.exit(1)
except Exception as general_e:
     # Catch other potential import errors
    app_init = QApplication.instance()
    if not app_init:
        app_init = QApplication(sys.argv)
    QMessageBox.critical(None, "Startup Error", f"An unexpected error occurred during startup:\n{general_e}\n\nApplication cannot start.")
    sys.exit(1)


# --- Backend License Verification ---

# !!! IMPORTANT: Replace this placeholder with your actual deployed backend URL !!!
BACKEND_VERIFY_URL = "https://snowball-license-backend-frsu.vercel.app/api/verify-license"


def verify_license_with_backend():
    """Prompts user if needed and verifies key against the secure backend."""

    # --- Simple check for local activation flag ---
    # This avoids prompting every single time. It's not secure storage,
    # but assumes the *initial* check via backend was secure.
    activation_flag_file = os.path.join(config.APP_DIR, ".snowball_activated")
    try:
        if os.path.exists(activation_flag_file):
             # Check if file is recent enough or has specific content if needed
             # For simplicity, just check existence
             logging.info("Local activation flag found. Skipping prompt.")
             return True # Assume valid if flag exists
    except Exception as e:
        logging.warning(f"Could not check for activation flag: {e}")

    # --- Prompt user if flag doesn't exist or check failed ---
    key, ok = QInputDialog.getText(None, "Activate Snowball Annotation", "Please enter your license key:")

    if ok and key:
        key = key.strip() # Remove leading/trailing whitespace
        if not key:
            # User entered only whitespace
            QMessageBox.warning(None, "License Required", "Please enter a valid license key.")
            return verify_license_with_backend() # Re-prompt

        logging.info(f"Attempting verification for key ending in ...{key[-4:]}")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor) # Show busy cursor

        try:
            headers = {'Content-Type': 'application/json'}
            payload = {'licenseKey': key}

            # --- Make the call to YOUR backend ---
            # Increased timeout for potentially slow cold starts on serverless
            response = requests.post(BACKEND_VERIFY_URL, headers=headers, json=payload, timeout=25)

            response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)

            data = response.json()
            if data.get("valid") is True:
                # --- Success! ---
                logging.info("License verified successfully via backend.")
                QApplication.restoreOverrideCursor() # Restore cursor
                QMessageBox.information(None, "Activated", "Thank you! License verified successfully.")

                # --- Store simple activation flag ---
                try:
                    os.makedirs(config.APP_DIR, exist_ok=True) # Ensure directory exists
                    with open(activation_flag_file, "w") as f: f.write("true")
                    logging.info(f"Stored activation flag at {activation_flag_file}")
                except Exception as e_flag:
                    logging.error(f"Failed to store activation flag: {e_flag}")
                    # Non-critical error, app can still proceed

                return True
            else:
                # Backend said the key was invalid
                error_msg = data.get("error", "Invalid license key reported by server.")
                logging.warning(f"Backend reported invalid key: {error_msg}")
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(None, "Invalid Key", f"{error_msg}")
                sys.exit(1)

        except requests.exceptions.HTTPError as e:
             # Handle specific HTTP errors (4xx, 5xx)
             logging.error(f"HTTP Error during license verification: {e.response.status_code} - {e.response.text}")
             QApplication.restoreOverrideCursor()
             # Try to get a more specific message from response if possible
             try:
                 error_data = e.response.json()
                 error_detail = error_data.get("error", e.response.reason)
             except:
                 error_detail = e.response.reason
             QMessageBox.critical(None, "Activation Error", f"Could not verify license. Server responded with: {e.response.status_code} {error_detail}. Please try again later or contact support.")
             sys.exit(1)
        except requests.exceptions.Timeout:
             logging.error("Timeout during license verification call.")
             QApplication.restoreOverrideCursor()
             QMessageBox.critical(None, "Activation Timeout", "The activation server did not respond in time. Please check your internet connection and try again.")
             sys.exit(1)
        except requests.exceptions.RequestException as e:
             # Network error, DNS error, etc.
             logging.error(f"Network Error during license verification: {e}")
             QApplication.restoreOverrideCursor()
             QMessageBox.critical(None, "Network Error", f"Could not connect to the activation server:\n{e}\nPlease check your internet connection and try again.")
             sys.exit(1)
        except Exception as e:
             # Other unexpected errors (e.g., JSON decoding if response is not JSON)
             logging.exception("Unexpected Error during license verification:")
             QApplication.restoreOverrideCursor()
             QMessageBox.critical(None, "Activation Error", f"An unexpected error occurred during activation:\n{e}")
             sys.exit(1)
        finally:
            # Ensure cursor is always restored
            QApplication.restoreOverrideCursor()

    elif ok and not key:
         # User pressed OK but entered nothing
         QMessageBox.warning(None, "License Required", "Please enter your license key.")
         return verify_license_with_backend() # Re-prompt
    else:
        # User cancelled the dialog
        QMessageBox.warning(None, "License Required", "A license key is required to use Snowball Annotation.")
        sys.exit(1)


if __name__ == "__main__":
    # --- Setup Logging ---
    log_path = "app_debug.log" # Default name
    try:
        # Ensure APP_DIR exists before trying to use it for logging
        if config.APP_DIR:
            os.makedirs(config.APP_DIR, exist_ok=True)
            log_path_candidate = os.path.join(config.APP_DIR, "app_debug.log")
            # Check if we can write to the directory
            if os.access(config.APP_DIR, os.W_OK):
                 log_path = log_path_candidate
            else:
                 print(f"[WARNING] No write access to {config.APP_DIR}. Logging to current directory.")
        else:
            print("[WARNING] config.APP_DIR not defined. Logging to current directory.")

        log_handlers = [logging.StreamHandler()] # Always log to console
        log_handlers.append(logging.FileHandler(log_path, mode='a')) # Append to log file

        # Configure logging
        logging.basicConfig(
            level=logging.INFO, # Set default level (DEBUG is very verbose)
            format="%(asctime)s - %(name)s [%(levelname)s] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=log_handlers,
            force=True # Override any existing logging config
        )
        logger = logging.getLogger(__name__)
        logger.info(f"--- Application Started ---")
        logger.info(f"Version: {config.VERSION}")
        logger.info(f"Logging initialized. Log file: {os.path.abspath(log_path)}")
        # Set lower level for specific modules if needed after basicConfig
        # logging.getLogger('state_manager').setLevel(logging.DEBUG)
        # logging.getLogger('training_pipeline').setLevel(logging.DEBUG)

    except Exception as log_ex:
        print(f"[CRITICAL] Failed to initialize logging: {log_ex}")
        # Continue without file logging if setup fails

    # --- Run Application with Backend License Verification ---
    app = QApplication(sys.argv)


    logger.info(f"Verifying license...")

    if verify_license_with_backend():
        logger.info("License verified. Initializing main window...")
        try:
            window = AnnotatorWindow()
            window.show()
            logger.info("Main window displayed. Starting event loop.")
            sys.exit(app.exec())
        except Exception as main_win_err:
             logger.exception("CRITICAL ERROR initializing or showing main window:")
             QMessageBox.critical(None, "Application Error", f"Failed to start the main application window:\n{main_win_err}")
             sys.exit(1)
    else:
        # verify_license_with_backend should call sys.exit() on failure,
        # but this is a fallback just in case.
        logger.error("License verification failed or was cancelled. Exiting.")
        sys.exit(1)