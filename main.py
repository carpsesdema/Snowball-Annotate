# main.py (Updated for Tiering - Storing Tier and Setting config.TIER)

import sys
import os
import logging
import requests  # Ensure 'requests' library is installed (pip install requests)
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QInputDialog
# Removed QSplashScreen imports for simplicity, add back if needed

# --- Import configuration ---
import config  # Needed for APP_DIR and setting config.TIER

# --- Import the main window ---
# This import happens AFTER config.TIER is potentially set later
# from annotator_window import AnnotatorWindow # Moved import lower

# --- Backend License Verification URL (ensure this is correct) ---
BACKEND_VERIFY_URL = "https://snowball-license-backend-frsu.vercel.app/api/verify-license"  # EXAMPLE URL - REPLACE!

# Setup logger for main module
logger_main = logging.getLogger(__name__)


def verify_license_with_backend():
    """
    Prompts user if needed and verifies key against the secure backend.
    Sets config.TIER based on verification result.

    Returns:
        bool: True if license is valid and tier is set, False otherwise.
    """
    activation_flag_file = os.path.join(config.APP_DIR, ".snowball_activated")
    tier_flag_file = os.path.join(
        config.APP_DIR, ".snowball_tier"
    )  # File to store tier

    try:
        # Check if BOTH flags exist
        if os.path.exists(activation_flag_file) and os.path.exists(tier_flag_file):
            with open(tier_flag_file, "r") as f_tier:
                cached_tier = f_tier.read().strip().upper()  # Read stored tier

            # Validate the cached tier
            if cached_tier in ["BASIC", "PRO"]:  # Add "COMMERCIAL" later if needed
                logger_main.info(
                    f"Local activation flags found. Skipping prompt. Cached Tier: {cached_tier}"
                )
                config.TIER = cached_tier  # <<< SET TIER FROM CACHE
                return True  # Assume valid if flags exist and tier is known
            else:
                logger_main.warning(
                    f"Invalid tier found in cache file: '{cached_tier}'. Re-verifying."
                )
                # Clean up bad flags if tier is invalid
                try:
                    if os.path.exists(activation_flag_file):
                        os.remove(activation_flag_file)
                    if os.path.exists(tier_flag_file):
                        os.remove(tier_flag_file)
                except Exception as rm_err:
                    logger_main.error(f"Error removing invalid flag files: {rm_err}")
        elif os.path.exists(activation_flag_file):
            # If only activation flag exists, something is wrong, force re-verify
            logger_main.warning(
                "Activation flag found, but tier flag missing. Re-verifying."
            )
            try:
                os.remove(activation_flag_file)
            except Exception as rm_err:
                logger_main.error(f"Error removing activation flag: {rm_err}")

    except Exception as e:
        logger_main.warning(f"Could not check for activation/tier flags: {e}")
        # Proceed to online check

    # --- Prompt user and perform ONLINE check if flags don't exist or were invalid ---
    key, ok = QInputDialog.getText(
        None, "Activate Snowball Annotation", "Please enter your license key:"
    )

    if ok and key:
        key = key.strip()
        if not key:
            QMessageBox.warning(
                None, "License Required", "Please enter a valid license key."
            )
            return verify_license_with_backend()  # Re-prompt

        logger_main.info(f"Attempting verification for key ending in ...{key[-4:]}")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        try:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": f"SnowballAnnotator/{config.VERSION}",
            }
            payload = {"licenseKey": key}
            logger_main.debug(f"Posting to backend: {BACKEND_VERIFY_URL}")
            response = requests.post(
                BACKEND_VERIFY_URL, headers=headers, json=payload, timeout=25
            )
            logger_main.debug(f"Backend response status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            logger_main.debug(f"Backend response data: {data}")

            if data.get("valid") is True:
                # --- Success! Get the tier ---
                # Default to BASIC if tier is missing or unknown from backend
                verified_tier = data.get("tier", "basic").upper()
                if verified_tier not in ["BASIC", "PRO"]:  # Add "COMMERCIAL" later
                    logger_main.warning(
                        f"Received unknown tier '{verified_tier}' from backend. Defaulting to BASIC."
                    )
                    verified_tier = "BASIC"

                config.TIER = verified_tier  # <<< SET TIER FROM BACKEND RESPONSE
                logger_main.info(f"--- Activated Tier: {config.TIER} ---")

                QApplication.restoreOverrideCursor()
                QMessageBox.information(
                    None,
                    "Activated",
                    f"Thank you! License verified successfully.\nTier: {verified_tier.capitalize()}",
                )

                # --- Store activation flag AND tier flag ---
                try:
                    os.makedirs(config.APP_DIR, exist_ok=True)
                    with open(activation_flag_file, "w") as f_act:
                        f_act.write("Activated")  # Simple content
                    with open(tier_flag_file, "w") as f_tier:
                        f_tier.write(config.TIER)  # Store the determined tier
                    logger_main.info(
                        f"Stored activation and tier flags in {config.APP_DIR}"
                    )
                except Exception as e_flag:
                    logger_main.error(
                        f"Failed to store activation/tier flags: {e_flag}"
                    )
                    # Non-critical, app can proceed but will ask next time

                return True  # Return success

            else:
                # Backend said invalid
                error_msg = data.get("error", "Invalid license key reported by server.")
                logger_main.warning(f"Backend reported invalid key: {error_msg}")
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(None, "Invalid Key", f"{error_msg}")
                # Let main block handle exit
                return False  # Failed verification

        except requests.exceptions.HTTPError as e:
            logger_main.error(
                f"HTTP Error: {e.response.status_code} - {e.response.text}",
                exc_info=True,
            )
            QApplication.restoreOverrideCursor()
            try:
                error_detail = e.response.json().get("error", e.response.reason)
            except:
                error_detail = (
                    e.response.reason
                    if hasattr(e.response, "reason")
                    else "Unknown HTTP Error"
                )
            QMessageBox.critical(
                None,
                "Activation Error",
                f"Could not verify license: {e.response.status_code} {error_detail}.",
            )
            return False  # Failed verification
        except requests.exceptions.Timeout:
            logger_main.error("Timeout during license verification call.")
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(
                None,
                "Activation Timeout",
                "Activation server timed out. Check internet and try again.",
            )
            return False  # Failed verification
        except requests.exceptions.RequestException as e:
            logger_main.error(
                f"Network Error during license verification: {e}", exc_info=True
            )
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(
                None,
                "Network Error",
                f"Could not connect to activation server:\n{e}\nCheck internet.",
            )
            return False  # Failed verification
        except Exception as e:
            logger_main.exception("Unexpected Error during license verification:")
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(
                None, "Activation Error", f"Unexpected error during activation:\n{e}"
            )
            return False  # Failed verification
        finally:
            QApplication.restoreOverrideCursor()

    elif ok and not key:
        QMessageBox.warning(None, "License Required", "Please enter your license key.")
        return verify_license_with_backend()  # Re-prompt
    else:
        # User cancelled
        QMessageBox.warning(None, "License Required", "A license key is required.")
        return False  # Indicate failure


if __name__ == "__main__":
    # --- Setup Logging ---
    # (Keep your existing logging setup here)
    log_path = "app_debug.log"
    try:
        # Ensure APP_DIR exists before trying to use it for logging
        if config.APP_DIR:
            os.makedirs(config.APP_DIR, exist_ok=True)
            log_path_candidate = os.path.join(config.APP_DIR, "app_debug.log")
            # Check if we can write to the directory
            if os.access(config.APP_DIR, os.W_OK):
                log_path = log_path_candidate
            else:
                print(
                    f"[WARNING] No write access to {config.APP_DIR}. Logging to current directory."
                )
        else:
            print("[WARNING] config.APP_DIR not defined. Logging to current directory.")

        log_handlers = [logging.StreamHandler()]  # Always log to console
        log_handlers.append(
            logging.FileHandler(log_path, mode="a")
        )  # Append to log file

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s [%(levelname)s] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=log_handlers,
            force=True,  # Override any existing logging config
        )
        # Define logger_main AFTER basicConfig
        logger_main = logging.getLogger(__name__)
        logger_main.info(f"--- Application Started ---")  # Log start first
        logger_main.info(f"Version: {config.VERSION}")  # Then version
        logger_main.info(f"Logging initialized. Log file: {os.path.abspath(log_path)}")

    except Exception as log_ex:
        print(f"[CRITICAL] Failed to initialize logging: {log_ex}")
        # Ensure logger_main exists even if file logging fails
        if "logger_main" not in locals():
            logging.basicConfig(level=logging.INFO)  # Basic console logging
            logger_main = logging.getLogger(__name__)
            logger_main.error("File logging failed, using basic console logging.")

    # --- Run Application ---
    app = QApplication(sys.argv)

    logger_main.info(f"Verifying license...")
    # --- Call the updated function ---
    # It now returns only True/False, and sets config.TIER internally
    license_ok = verify_license_with_backend()

    if license_ok:
        # --- config.TIER should now be set correctly ---
        logger_main.info(
            f"License verified for Tier: {config.TIER}. Initializing main window..."
        )

        # --- Import AnnotatorWindow *after* config.TIER is set ---
        # This allows AnnotatorWindow's conditional imports to work correctly
        try:
            from annotator_window import AnnotatorWindow
        except ImportError as e:
            logger_main.critical(
                f"Failed to import AnnotatorWindow: {e}", exc_info=True
            )
            QMessageBox.critical(
                None, "Startup Error", f"Failed to import main window components:\n{e}"
            )
            sys.exit(1)
        except Exception as e_aw_import:
            logger_main.critical(
                f"Error importing AnnotatorWindow: {e_aw_import}", exc_info=True
            )
            QMessageBox.critical(
                None, "Startup Error", f"Error loading main window:\n{e_aw_import}"
            )
            sys.exit(1)

        # --- Initialize and Show Window ---
        try:
            # AnnotatorWindow __init__ will now read config.TIER
            window = AnnotatorWindow()
            window.show()
            logger_main.info("Main window displayed. Starting event loop.")
            sys.exit(app.exec())  # Start the Qt event loop
        except Exception as main_win_err:
            logger_main.exception("CRITICAL ERROR initializing or showing main window:")
            QMessageBox.critical(
                None,
                "Application Error",
                f"Failed to start the main application window:\n{main_win_err}",
            )
            sys.exit(1)
    else:
        # Verification failed or was cancelled, exit message already shown
        logger_main.error(
            "License verification failed or was cancelled by user. Exiting."
        )
        sys.exit(1)  # Exit the application cleanly
