
import os
import json
import logging
import torch
import shutil
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer

import config  # --- TIERING: Needed for config.TIER ---

# Import TrainingPipeline and DatasetHandler (Real or Dummy based on Tier)
# Use a logger specific to this module scope
logger_sm = logging.getLogger(__name__)

# --- TIERING: Conditionally import REAL backend components only if PRO ---
_TrainingPipeline = None
_DatasetHandler = None  # DatasetHandler needed for Basic export.
_PredictionWorker = None  # Pro
_TrainingWorker = None  # Pro

# Ensure config.TIER is set before this module is fully processed
# Use getattr for safety in case config hasn't been fully initialized somehow
current_tier_for_import = getattr(config, "TIER", "UNKNOWN")
logger_sm.info(
    f"--- StateManager: Checking Tier for Backend Component Import "
    f"(Tier={current_tier_for_import}) ---"
)

# DatasetHandler is needed for Basic export logic as well. Assume real one always.
try:
    from training_pipeline import DatasetHandler as _DatasetHandler

    logger_sm.info("OK: Real DatasetHandler imported (needed for Basic & Pro).")
except ImportError as e_dh:
    logger_sm.critical(f"Failed to import REAL DatasetHandler: {e_dh}", exc_info=True)
    # Define a minimal dummy if real fails, as export needs it.

    class _DummyDatasetHandler:
        def __init__(self):
            self.annotations = {}

        def update_annotation(self, p, d):
            pass

        def get_annotation(self, p):
            return None

        def export_for_yolo(self, paths, base_dir, class_map, split=0.2):
            logger_sm.error("Dummy DH cannot export.")
            return None

    _DatasetHandler = _DummyDatasetHandler
    logger_sm.warning("Using dummy DatasetHandler defined in state_manager.py")


# Import PRO components only if PRO tier
if current_tier_for_import == "PRO":
    try:
        from training_pipeline import TrainingPipeline as _TrainingPipeline

        logger_sm.info("[PRO] OK: training_pipeline.TrainingPipeline imported.")
    except ImportError as e_pipe:
        logger_sm.error(
            f"[PRO] Failed to import TrainingPipeline: {e_pipe}", exc_info=True
        )
        _TrainingPipeline = None  # Ensure it's None

    try:
        from workers import (
            PredictionWorker as _PredictionWorker,
            TrainingWorker as _TrainingWorker,
        )

        logger_sm.info("[PRO] OK: Worker classes imported.")
    except ImportError as e_work:
        logger_sm.error(f"[PRO] Could not import worker classes: {e_work}")
        _PredictionWorker, _TrainingWorker = None, None  # Ensure None
else:
    logger_sm.info(
        f"[BASIC/UNKNOWN Tier] Tier detected ({current_tier_for_import}). "
        f"Skipping PRO backend component imports."
    )


# --- TIERING: Fallback to DUMMIES for PRO components if needed ---
if _TrainingPipeline is None:
    # Avoid re-defining if already defined above or globally
    if "TrainingPipeline" not in globals() or globals().get("TrainingPipeline") is None:

        class _DummyTrainingPipeline:
            def __init__(self, cl, s, dh):
                self.class_to_id = {}
                logger_sm.warning("Using dummy TrainingPipeline INSTANCE.")

            def cleanup(self):
                pass

            def update_classes(self, cl):
                pass

            def update_settings(self, s):
                pass

            def run_training_session(self, p, a, e, lr, pfx):
                logger_sm.error("Dummy TP cannot run training.")
                return None

            def auto_box(self, img, conf):
                logger_sm.error("Dummy TP cannot auto_box.")
                return []

        _TrainingPipeline = _DummyTrainingPipeline
        logger_sm.warning(
            f"Using dummy TrainingPipeline CLASS (Tier: {current_tier_for_import})."
        )

if _PredictionWorker is None:
    if "PredictionWorker" not in globals() or globals().get("PredictionWorker") is None:

        class _DummyPredictionWorker(QObject):
            progress = pyqtSignal(str)
            finished = pyqtSignal(list)
            error = pyqtSignal(str)

            def __init__(self, *args):
                super().__init__()
                logger_sm.warning("Using dummy PredictionWorker INSTANCE.")

            def run(self):
                self.error.emit("Dummy Worker: Prediction unavailable")

            def stop(self):
                pass

        _PredictionWorker = _DummyPredictionWorker
        logger_sm.warning(
            f"Using dummy PredictionWorker CLASS (Tier: {current_tier_for_import})."
        )

if _TrainingWorker is None:
    if "TrainingWorker" not in globals() or globals().get("TrainingWorker") is None:

        class _DummyTrainingWorker(QObject):
            progress = pyqtSignal(str)
            finished = pyqtSignal(str)
            error = pyqtSignal(str)

            def __init__(self, *args):
                super().__init__()
                logger_sm.warning("Using dummy TrainingWorker INSTANCE.")

            def run(self):
                self.error.emit("Dummy Worker: Training unavailable")

            def stop(self):
                pass

        _TrainingWorker = _DummyTrainingWorker
        logger_sm.warning(
            f"Using dummy TrainingWorker CLASS (Tier: {current_tier_for_import})."
        )

# Assign final classes to be used
DatasetHandler = _DatasetHandler
TrainingPipeline = _TrainingPipeline  # Will be real (Pro) or dummy
PredictionWorker = _PredictionWorker  # Will be real (Pro) or dummy
TrainingWorker = _TrainingWorker  # Will be real (Pro) or dummy


class StateManager(QObject):
    # Signals (Define all, but some only emitted in Pro)
    prediction_progress = pyqtSignal(str)
    prediction_finished = pyqtSignal(list)
    prediction_error = pyqtSignal(str)
    training_progress = pyqtSignal(str)
    training_run_completed = pyqtSignal(str)  # Emits run_dir path
    training_error = pyqtSignal(str)
    task_running = pyqtSignal(bool)
    settings_changed = pyqtSignal()

    def __init__(self, class_list):
        super().__init__()
        self.image_list = []
        self.current_index = -1
        self.annotations = {}
        self._settings = {}
        self._user_settings_path = config.DEFAULT_SETTINGS_PATH
        self.load_settings()  # Load settings first

        # Determine session path based on loaded settings
        session_path_key = config.SETTING_KEYS.get("session_path", "paths.session_path")
        session_dir = os.path.dirname(
            self.get_setting(session_path_key, config.DEFAULT_SESSION_PATH)
        )
        if session_dir:
            os.makedirs(session_dir, exist_ok=True)
        self.session_path = self.get_setting(
            session_path_key, config.DEFAULT_SESSION_PATH
        )

        self.approved_count = 0
        self.class_list = sorted(list(set(class_list))) if class_list else []
        self.last_successful_run_dir = None  # Pro feature artifact

        # Create DatasetHandler instance (using determined class)
        try:
            self.dataset_handler = DatasetHandler()
            logger_sm.info("DatasetHandler initialized in StateManager.")
        except Exception as e:
            logger_sm.exception("FATAL: Failed DatasetHandler init.")
            self.dataset_handler = None

        # --- TIERING: Initialize TrainingPipeline (Real or Dummy) ---
        try:
            # Use the TrainingPipeline class determined by import logic
            self.training_pipeline = TrainingPipeline(
                class_list=self.class_list,
                settings=self._settings,
                dataset_handler=self.dataset_handler,  # Pass DH instance
            )
            # Log if it's the dummy
            if TrainingPipeline.__name__.startswith("_Dummy"):
                logger_sm.warning("Initialized DUMMY TrainingPipeline instance.")
            else:
                logger_sm.info("[PRO] Initialized REAL TrainingPipeline instance.")
        except Exception as e:
            logger_sm.exception("FATAL: Failed TrainingPipeline init.")
            self.training_pipeline = None  # Ensure it's None on failure

        # --- MOVED TIER ASSIGNMENT HERE ---
        # Set the instance's tier based on the global config value (set by main.py)
        self.current_tier = getattr(config, "TIER", "UNKNOWN")
        logger_sm.info(f"StateManager instance tier set to: {self.current_tier}")
        # -----------------------------------

        # Apply loaded settings to pipeline etc. NOW that self.current_tier exists
        self.update_internal_from_settings()

        # Initialize worker/thread attributes
        self._current_thread = None
        self._current_worker = None
        self._blocking_task_running = False

        # Final log message confirming initialization
        logger_sm.info(
            f"StateManager initialized for Tier: {self.current_tier}. "
            f"Save path: {self.session_path}"
        )
        logger_sm.info(f"User settings path: {self._user_settings_path}")

    # --- Settings Management Methods ---

    def load_settings(self):
        """Loads settings, applying defaults first."""
        self._settings = config.get_default_settings()
        logger_sm.info(f"Loading settings from: {self._user_settings_path}")
        try:
            if os.path.exists(self._user_settings_path):
                with open(self._user_settings_path, "r") as f:
                    user_settings = json.load(f)
                # Optional TIERING: Filter loaded settings here if needed
                self._settings.update(user_settings)
                logger_sm.info("Loaded user settings.")
            else:
                logger_sm.info("No user settings file found, using defaults.")
        except Exception as e:
            logger_sm.error(
                f"Failed load/decode settings {self._user_settings_path}: {e}. "
                f"Using defaults.",
                exc_info=True,
            )
            self._settings = config.get_default_settings()  # Reset on error

    def save_settings(self):
        """Saves current settings dictionary to file."""
        logger_sm.debug(f"Saving settings to: {self._user_settings_path}")
        try:
            os.makedirs(os.path.dirname(self._user_settings_path), exist_ok=True)
            # Optional TIERING: Filter settings before saving if needed
            with open(self._user_settings_path, "w") as f:
                json.dump(self._settings, f, indent=4)
            logger_sm.info("User settings saved.")
        except Exception as e:
            logger_sm.error(
                f"Failed save settings {self._user_settings_path}: {e}", exc_info=True
            )

    def get_setting(self, key, default=None):
        """Gets a setting value, falling back to config defaults, then provided default."""
        config_default = config.get_default_settings().get(key)
        effective_default = config_default if config_default is not None else default
        val = self._settings.get(key, effective_default)
        # Ensure bools stay bools
        if isinstance(effective_default, bool):
            return bool(val)
        return val

    def set_setting(self, key, value):
        """Sets a setting value, attempts type conversion, saves, and notifies."""
        is_known_key = any(key == kp for kp in config.SETTING_KEYS.values())
        if not is_known_key:
            logger_sm.warning(f"Setting unknown key: {key}")

        # Optional TIERING: Prevent setting Pro keys if Basic
        # if self.current_tier == "BASIC" and key in PRO_ONLY_KEYS: return

        original_value = self._settings.get(key)
        new_value = value
        try:  # Attempt type conversion based on default type
            default_val = config.get_default_settings().get(key)
            expected_type = type(default_val) if default_val is not None else None
            if expected_type == bool:
                new_value = bool(value)
            elif expected_type == int:
                new_value = int(value)
            elif expected_type == float:
                new_value = float(value)
            elif expected_type == str:
                new_value = str(value)
        except (ValueError, TypeError):
            logger_sm.error(
                f"Invalid type for setting '{key}': '{value}'. Keeping '{original_value}'."
            )
            return

        if original_value != new_value:
            self._settings[key] = new_value
            logger_sm.info(f"Setting '{key}' updated to: {new_value}")
            self.save_settings()
            self.update_internal_from_settings(key)
            self.settings_changed.emit()
        else:
            logger_sm.debug(f"Setting '{key}' value unchanged: {new_value}")

    def update_internal_from_settings(self, changed_key=None):
        """Updates internal state (like session path, pipeline settings) from settings dict."""
        # --- IMPORTANT: Check if self.current_tier exists before using it ---
        if not hasattr(self, 'current_tier'):
             logger_sm.error("CRITICAL: update_internal_from_settings called before self.current_tier was set!")
             # You might want to force set it here as a fallback, though the __init__ order should prevent this now.
             # self.current_tier = getattr(config, "TIER", "UNKNOWN")
             # logger_sm.warning(f"Force-set current_tier to {self.current_tier} in update_internal")
             return # Or raise an error? Better to return and rely on correct init order.

        logger_sm.debug(
            f"Updating internal state from settings (changed: {changed_key})."
        )
        session_path_key = config.SETTING_KEYS.get("session_path")
        if session_path_key and (
            changed_key is None or changed_key == session_path_key
        ):
            self.session_path = self.get_setting(
                session_path_key, config.DEFAULT_SESSION_PATH
            )

        # --- TIERING: Only update REAL pipeline if Pro ---
        pipeline_relevant_keys = [
            config.SETTING_KEYS.get(k)
            for k in [
                "epochs_20",
                "lr_20",
                "epochs_100",
                "lr_100",
                "img_size",
                "aug_flipud",
                "aug_fliplr",
                "aug_degrees",
                "base_model",
                "model_save_path",
                "runs_dir",
            ]
            if config.SETTING_KEYS.get(k)
        ]
        is_real_pipeline = (
            self.training_pipeline
            and hasattr(self.training_pipeline, "update_settings")
            and TrainingPipeline.__name__ != "_DummyTrainingPipeline"
        )

        if (
            self.current_tier == "PRO" # Now safe to access self.current_tier
            and is_real_pipeline
            and (changed_key is None or changed_key in pipeline_relevant_keys)
        ):
            logger_sm.info(
                f"[PRO] Pushing updated settings to REAL TrainingPipeline "
                f"(triggered by '{changed_key or 'initial load'}')."
            )
            try:
                self.training_pipeline.update_settings(self._settings)
            except Exception as e_pipe_update:
                logger_sm.error(
                    f"Error updating REAL training pipeline settings: {e_pipe_update}",
                    exc_info=True,
                )
        elif changed_key in pipeline_relevant_keys:
            # Log if a pipeline-relevant key changed but we skipped update
            logger_sm.debug(
                f"[{self.current_tier}/Pipeline:{TrainingPipeline.__name__}] "
                f"Skipping pipeline settings update for key '{changed_key}'."
            )

    def get_last_run_path(self):
        """Returns the path to the last successful training run directory (Pro only)."""
        # --- TIERING: This is a Pro artifact ---
        if self.current_tier != "PRO":
            return None
        return self.last_successful_run_dir

    # --- Core State Methods ---

    def load_session(self, file_path=None):
        """Loads session data from a JSON file."""
        session_file = (
            file_path
            if file_path
            else self.get_setting(
                config.SETTING_KEYS["session_path"], self.session_path
            )
        )
        logger_sm.info(f"Attempting to load session from: {session_file}")
        try:
            if not os.path.exists(session_file):
                logger_sm.warning(
                    f"Session file not found: {session_file}. Init empty state."
                )
                self.image_list = []
                self.annotations = {}
                self.current_index = -1
                self.approved_count = 0
                self.last_successful_run_dir = None
                if self.dataset_handler:
                    self.dataset_handler.annotations.clear()
                self.settings_changed.emit()
                return True

            with open(session_file, "r") as f:
                session_data = json.load(f)

            loaded_images = session_data.get("image_list", [])
            loaded_anns = session_data.get("annotations", {})
            loaded_index = session_data.get("current_index", -1)
            loaded_classes = session_data.get("class_list", self.class_list)

            # --- TIERING: Load Pro artifacts only if Pro ---
            loaded_run_dir = (
                session_data.get("last_successful_run_dir")
                if self.current_tier == "PRO"
                else None
            )
            if (
                loaded_run_dir
                and isinstance(loaded_run_dir, str)
                and os.path.isdir(loaded_run_dir)
            ):
                self.last_successful_run_dir = loaded_run_dir
                logger_sm.info(
                    f"[PRO] Loaded last successful run dir: {self.last_successful_run_dir}"
                )
            else:
                self.last_successful_run_dir = None
                if loaded_run_dir:
                    logger_sm.warning(
                        f"Invalid last run directory in session: {loaded_run_dir}"
                    )

            classes_changed = False
            if loaded_classes and isinstance(loaded_classes, list):
                new_classes = sorted(list(set(map(str, loaded_classes))))
                if new_classes != self.class_list:
                    logger_sm.info(f"Updating class list from session: {new_classes}")
                    self.class_list = new_classes
                    classes_changed = True
            else:
                logger_sm.warning(
                    "No valid class list in session file. Keeping existing."
                )

            self.image_list = loaded_images if isinstance(loaded_images, list) else []
            self.annotations = loaded_anns if isinstance(loaded_anns, dict) else {}

            # Clean up annotations for images not in the list
            keys_to_remove = [p for p in self.annotations if p not in self.image_list]
            if keys_to_remove:
                logger_sm.warning(
                    f"Removing {len(keys_to_remove)} annotations for missing images."
                )
                for k in keys_to_remove:
                    self.annotations.pop(k, None)

            # Validate and set current index
            if not (
                isinstance(loaded_index, int)
                and 0 <= loaded_index < len(self.image_list)
            ):
                self.current_index = 0 if self.image_list else -1
            else:
                self.current_index = loaded_index

            # Recalculate approved count and update dataset handler
            self.approved_count = 0
            if self.dataset_handler:
                self.dataset_handler.annotations.clear()
            for img_path, data in self.annotations.items():
                if isinstance(data, dict):
                    if data.get("approved"):
                        self.approved_count += 1
                    if self.dataset_handler:
                        self.dataset_handler.update_annotation(img_path, data)
                else:
                    logger_sm.warning(f"Invalid ann data type for {img_path}.")

            if classes_changed:
                self.update_pipeline_classes()  # Updates real or dummy

            logger_sm.info(
                f"Session loaded: {len(self.image_list)} images, "
                f"{len(self.annotations)} annots. Index: {self.current_index}. "
                f"Approved: {self.approved_count}."
            )
            self.settings_changed.emit()
            return True
        except Exception as e:
            logger_sm.error(f"Failed load session {session_file}: {e}", exc_info=True)
            return False

    def save_session(self):
        """Saves current state (images, annotations, index, classes) to session file."""
        session_file = self.get_setting(
            config.SETTING_KEYS["session_path"], self.session_path
        )
        logger_sm.info(f"Saving session to: {session_file}")
        session_data = {
            "image_list": self.image_list,
            "annotations": self.annotations,
            "current_index": self.current_index,
            "class_list": self.class_list,
            # --- TIERING: Only include Pro artifacts if Pro ---
            "last_successful_run_dir": self.last_successful_run_dir
            if self.current_tier == "PRO"
            else None,
        }
        try:
            save_dir = os.path.dirname(session_file)
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
            with open(session_file, "w") as f:
                json.dump(session_data, f, indent=4)
            logger_sm.info("Session saved successfully.")
        except Exception as e:
            logger_sm.error(f"Failed save session {session_file}: {e}", exc_info=True)

    def load_images_from_directory(self, directory_path):
        """Loads image paths from a directory, resetting state if different."""
        logger_sm.info(f"Loading images from directory: {directory_path}")
        formats = tuple(
            f".{ext}"
            for ext in ["png", "jpg", "jpeg", "bmp", "gif", "tiff", "tif", "webp"]
        )
        try:
            image_files = sorted(
                [
                    os.path.abspath(os.path.join(directory_path, f))
                    for f in os.listdir(directory_path)
                    if os.path.isfile(os.path.join(directory_path, f))
                    and f.lower().endswith(formats)
                ]
            )
            if not image_files:
                logger_sm.warning(f"No supported images in {directory_path}. Clearing.")
                self.image_list = []
                self.current_index = -1
                self.annotations = {}
                self.approved_count = 0
                self.last_successful_run_dir = None
                if self.dataset_handler:
                    self.dataset_handler.annotations.clear()
            else:
                is_new_or_different = set(image_files) != set(self.image_list)
                if is_new_or_different:
                    logger_sm.info("New directory/content. Resetting annotations.")
                    self.image_list = image_files
                    self.current_index = 0
                    self.annotations = {}
                    self.approved_count = 0
                    self.last_successful_run_dir = None
                    if self.dataset_handler:
                        self.dataset_handler.annotations.clear()
                else:
                    logger_sm.info("Directory reloaded, content identical.")

            # Ensure index is valid after potential reset
            if not (0 <= self.current_index < len(self.image_list)):
                self.current_index = 0 if self.image_list else -1
            logger_sm.info(
                f"Loaded {len(self.image_list)} images. Current index: {self.current_index}."
            )
        except Exception as e:
            logger_sm.error(f"Failed load images {directory_path}: {e}", exc_info=True)
            raise

    def get_current_image(self):
        """Returns the path of the currently active image."""
        if self.image_list and 0 <= self.current_index < len(self.image_list):
            return self.image_list[self.current_index]
        return None

    def next_image(self):
        """Moves to the next image index if possible."""
        if not self.image_list:
            return False
        if self.current_index < len(self.image_list) - 1:
            self.current_index += 1
            return True
        return False

    def prev_image(self):
        """Moves to the previous image index if possible."""
        if not self.image_list:
            return False
        if self.current_index > 0:
            self.current_index -= 1
            return True
        return False

    def go_to_image(self, index):
        """Moves directly to the specified image index if valid."""
        if self.image_list and 0 <= index < len(self.image_list):
            if self.current_index != index:
                self.current_index = index
            return True
        return False

    def update_classes(self, new_class_list):
        """Updates the class list, removing annotations for deleted classes."""
        new_classes_clean = sorted(
            list(set(str(cls).strip() for cls in new_class_list if str(cls).strip()))
        )
        if new_classes_clean != self.class_list:
            logger_sm.info(
                f"Updating class list from {self.class_list} to {new_classes_clean}"
            )
            self.class_list = new_classes_clean
            valid_new_set = set(self.class_list)
            updated_anns = {}
            removed_box_count = 0
            affected_image_count = 0
            if self.dataset_handler:
                self.dataset_handler.annotations.clear()

            for img_path, data in self.annotations.items():
                if not isinstance(data, dict):
                    continue
                if data.get("negative", False):  # Keep negatives
                    updated_anns[img_path] = data
                    if self.dataset_handler:
                        self.dataset_handler.update_annotation(img_path, data)
                    continue

                original_boxes = data.get("annotations_list", [])
                filtered_boxes = []
                img_had_removed = False
                for b in original_boxes:
                    if isinstance(b, dict) and b.get("class") in valid_new_set:
                        filtered_boxes.append(b)
                    else:
                        img_had_removed = True
                        removed_box_count += 1

                new_data = data.copy()
                new_data["annotations_list"] = filtered_boxes
                updated_anns[img_path] = new_data
                if img_had_removed:
                    affected_image_count += 1
                if self.dataset_handler:
                    self.dataset_handler.update_annotation(img_path, new_data)

            if removed_box_count > 0:
                logger_sm.warning(
                    f"Removed {removed_box_count} boxes from {affected_image_count} images."
                )
            self.annotations = updated_anns
            self.approved_count = sum(
                1
                for d in self.annotations.values()
                if isinstance(d, dict) and d.get("approved")
            )
            logger_sm.info(f"Approved count after class change: {self.approved_count}")
            self.update_pipeline_classes()
            self.save_session()
            self.settings_changed.emit()
        else:
            logger_sm.info("Class list unchanged.")

    def update_pipeline_classes(self):
        """Updates the classes in the training pipeline instance (if real)."""
        is_real_pipeline = (
            self.training_pipeline
            and hasattr(self.training_pipeline, "update_classes")
            and TrainingPipeline.__name__ != "_DummyTrainingPipeline"
        )
        if self.current_tier == "PRO" and is_real_pipeline:
            logger_sm.info("[PRO] Updating REAL TrainingPipeline classes...")
            try:
                self.training_pipeline.update_classes(self.class_list)
                logger_sm.info("Pipeline classes updated.")
            except Exception as e:
                logger_sm.error("Failed update pipeline classes.", exc_info=True)
        elif self.training_pipeline:
            logger_sm.debug("Skipping pipeline class update (Dummy/method missing).")
        else:
            logger_sm.warning("Cannot update pipeline classes: No Pipeline instance.")

    # --- Annotation & Training Trigger ---

    def add_annotation(self, image_path, annotation_data):
        """Adds/updates annotation for an image, updates counts, saves, triggers training (Pro)."""
        if not image_path or not isinstance(annotation_data, dict):
            return False
        logger_sm.info(f"Updating annotation state for {os.path.basename(image_path)}")
        was_approved_before = self.annotations.get(image_path, {}).get(
            "approved", False
        )
        is_approved_now = annotation_data.get("approved", False)
        self.annotations[image_path] = annotation_data

        # Update approved count
        if is_approved_now != was_approved_before:
            self.approved_count += 1 if is_approved_now else -1
            self.approved_count = max(0, self.approved_count)
            logger_sm.debug(f"Approved count updated: {self.approved_count}")

        # Update dataset handler
        if self.dataset_handler:
            self.dataset_handler.update_annotation(image_path, annotation_data)

        # Save session asynchronously
        QTimer.singleShot(100, self.save_session)

        # --- TIERING: Training Triggers (PRO ONLY) ---
        if is_approved_now and not was_approved_before:
            is_real_pipeline = (
                self.training_pipeline
                and TrainingPipeline.__name__ != "_DummyTrainingPipeline"
            )
            # Only check triggers if PRO tier and REAL pipeline exists
            if self.current_tier == "PRO" and is_real_pipeline:
                current_count = self.approved_count
                epochs, lr, prefix = None, None, None
                trigger_level = None

                trig_20_en = self.get_setting(
                    config.SETTING_KEYS["training.trigger_20_enabled"], True
                )
                trig_100_en = self.get_setting(
                    config.SETTING_KEYS["training.trigger_100_enabled"], True
                )
                logger_sm.debug(
                    f"[PRO] Checking triggers: 20={trig_20_en}, 100={trig_100_en}"
                )

                if trig_100_en and current_count > 0 and current_count % 100 == 0:
                    trigger_level = 100
                elif trig_20_en and current_count > 0 and current_count % 20 == 0:
                    if trigger_level != 100:  # 100 takes precedence
                        trigger_level = 20

                if trigger_level == 100:
                    logger_sm.info(
                        f"[PRO] Count {current_count}: Triggering MAJOR train."
                    )
                    epochs = self.get_setting(
                        config.SETTING_KEYS.get("epochs_100"), config.DEFAULT_EPOCHS_100
                    )
                    lr = self.get_setting(
                        config.SETTING_KEYS.get("lr_100"), config.DEFAULT_LR_100
                    )
                    prefix = f"major_{current_count}"
                elif trigger_level == 20:
                    logger_sm.info(
                        f"[PRO] Count {current_count}: Triggering MINI train."
                    )
                    epochs = self.get_setting(
                        config.SETTING_KEYS.get("epochs_20"), config.DEFAULT_EPOCHS_20
                    )
                    lr = self.get_setting(
                        config.SETTING_KEYS.get("lr_20"), config.DEFAULT_LR_20
                    )
                    prefix = f"mini_{current_count}"

                if epochs is not None and lr is not None and prefix is not None:
                    logger_sm.info(
                        f"[PRO] Scheduling {prefix} training task (E:{epochs}, LR:{lr:.6f})."
                    )
                    QTimer.singleShot(
                        150,
                        lambda e=epochs, l=lr, p=prefix: self.start_training_task(
                            e, l, p
                        ),
                    )
            elif not self.training_pipeline:
                logger_sm.error("Approved, but cannot trigger train: Pipeline missing.")
            else:  # Basic tier or dummy pipeline
                logger_sm.debug("[BASIC/Dummy] Skipping auto train triggers.")
        return True

    # --- Task Management ---

    def start_prediction(self, image_path):
        """Starts a background prediction task (PRO ONLY)."""
        # --- TIERING: PRO ONLY ---
        if self.current_tier != "PRO":
            logger_sm.warning("[BASIC] AI Suggestions (Prediction) require Pro.")
            self.prediction_error.emit("AI Suggestions require Pro tier.")
            return False

        logger_sm.debug(
            f"[PRO] Request start prediction for {os.path.basename(image_path)}"
        )
        # Check if the REAL worker class is available
        if PredictionWorker.__name__.startswith("_Dummy"):
            logger_sm.error("[PRO] PredictionWorker is DUMMY. Prediction unavailable.")
            self.prediction_error.emit("Prediction unavailable (Worker missing/dummy).")
            return False

        current_conf = self.get_setting(config.SETTING_KEYS["confidence_threshold"])
        return self._start_task(PredictionWorker, image_path, current_conf)

    def start_training_task(self, epochs, lr, run_name_prefix):
        """Starts a background training task (PRO ONLY)."""
        # --- TIERING: PRO ONLY ---
        if self.current_tier != "PRO":
            logger_sm.warning("[BASIC] Training requires Pro tier.")
            self.training_error.emit("Training requires Pro tier.")
            return False

        # Check if the REAL worker class is available
        if TrainingWorker.__name__.startswith("_Dummy"):
            logger_sm.error("[PRO] TrainingWorker is DUMMY. Training unavailable.")
            self.training_error.emit("Training unavailable (Worker missing/dummy).")
            return False

        logger_sm.info(f"[PRO] Preparing data for training run '{run_name_prefix}'...")
        approved_anns = {
            p: data
            for p, data in self.annotations.items()
            if isinstance(data, dict) and data.get("approved")
        }
        approved_paths = list(approved_anns.keys())

        if not approved_paths:
            logger_sm.warning("No approved images for training.")
            self.training_error.emit("No approved images")
            return False

        logger_sm.info(
            f"[PRO] Request start {run_name_prefix} training on "
            f"{len(approved_paths)} images (E: {epochs}, LR: {lr})."
        )
        return self._start_task(
            TrainingWorker, approved_paths, approved_anns, epochs, lr, run_name_prefix
        )

    def _start_task(self, worker_class, *args):
        """Internal helper to create and start worker threads."""
        task_name = worker_class.__name__
        is_real_pipeline = (
            self.training_pipeline
            and TrainingPipeline.__name__ != "_DummyTrainingPipeline"
        )
        is_real_worker = not worker_class.__name__.startswith("_Dummy")

        # Prevent REAL workers if pipeline is DUMMY
        if is_real_worker and not is_real_pipeline:
            error_msg = (
                f"Cannot start REAL {task_name}: Pipeline is dummy or unavailable."
            )
            logger_sm.error(error_msg)
            is_pred = "Prediction" in task_name
            if is_pred:
                self.prediction_error.emit(error_msg)
            else:
                self.training_error.emit(error_msg)
            return False

        if self._blocking_task_running:
            logger_sm.warning(f"Cannot start {task_name}: Another task running.")
            is_pred = "Prediction" in task_name
            if is_pred:
                self.prediction_error.emit("Busy: Another task running.")
            else:
                self.training_error.emit("Busy: Another task running.")
            return False

        self._blocking_task_running = True
        self.task_running.emit(True)

        try:
            self._current_thread = QThread()
            self._current_worker = worker_class(self.training_pipeline, *args)
            self._current_worker.moveToThread(self._current_thread)

            # Connect signals (should exist on both real and dummy)
            is_pred = "Prediction" in task_name
            if hasattr(self._current_worker, "progress"):
                sig = self.prediction_progress if is_pred else self.training_progress
                self._current_worker.progress.connect(sig)
            if hasattr(self._current_worker, "finished"):
                sig = (
                    self.prediction_finished if is_pred else self.training_run_completed
                )
                self._current_worker.finished.connect(sig)
            if hasattr(self._current_worker, "error"):
                sig = self.prediction_error if is_pred else self.training_error
                self._current_worker.error.connect(sig)

            # Connect finished/error to internal cleanup handler
            task_id_name = self._current_worker.__class__.__name__
            if hasattr(self._current_worker, "finished"):
                self._current_worker.finished.connect(
                    lambda result=None, name=task_id_name: self._on_task_finished(
                        name, result
                    )
                )
            if hasattr(self._current_worker, "error"):
                self._current_worker.error.connect(
                    lambda name=task_id_name: self._on_task_finished(name, None)
                )

            self._current_thread.started.connect(self._current_worker.run)
            self._current_thread.finished.connect(self._current_thread.deleteLater)
            if hasattr(self._current_worker, "finished"):
                self._current_worker.finished.connect(self._current_thread.quit)
                self._current_worker.finished.connect(self._current_worker.deleteLater)
            if hasattr(self._current_worker, "error"):
                self._current_worker.error.connect(self._current_thread.quit)
                self._current_worker.error.connect(self._current_worker.deleteLater)

            self._current_thread.start()
            logger_sm.info(f"Started {task_name} in background thread.")
            return True

        except Exception as e:
            logger_sm.exception(f"Error starting worker thread {task_name}")
            error_msg = f"Setup error for {task_name}: {e}"
            is_pred = "Prediction" in task_name
            if is_pred:
                self.prediction_error.emit(error_msg)
            else:
                self.training_error.emit(error_msg)
            if self._current_thread:
                self._current_thread.quit()
            self._blocking_task_running = False
            self.task_running.emit(False)
            self._current_thread = None
            self._current_worker = None
            return False

    def _on_task_finished(self, task_name, result=None):
        """Internal slot called when a worker finishes or errors."""
        logger_sm.info(
            f"Internal handler: Background task ({task_name}) finished/errored."
        )

        # --- TIERING: Store last run dir only if Pro ---
        is_training_task = "TrainingWorker" in task_name
        if (
            self.current_tier == "PRO"
            and is_training_task
            and isinstance(result, str)
            and os.path.isdir(result)
        ):
            self.last_successful_run_dir = result
            logger_sm.info(f"[PRO] Stored last successful run directory: {result}")
            QTimer.singleShot(50, self.save_session)  # Persist run dir
        elif "PredictionWorker" in task_name and isinstance(result, list):
            logger_sm.debug(f"Prediction task finished with {len(result)} results.")
        elif result is None:
            logger_sm.warning(f"{task_name} task finished with error or no result.")

        # Thread cleanup logic
        thread_to_clean = self._current_thread
        if thread_to_clean:
            logger_sm.debug(f"Cleaning up thread for {task_name}...")
            if thread_to_clean.isRunning():
                thread_to_clean.quit()
                if not thread_to_clean.wait(5000):
                    logger_sm.warning(f"Thread ({task_name}) didn't finish cleanup.")
                else:
                    logger_sm.debug(f"Thread ({task_name}) finished cleanly.")
            else:
                logger_sm.debug(f"Thread ({task_name}) was already finished.")

        if self._blocking_task_running:
            self._blocking_task_running = False
            self.task_running.emit(False)

        self._current_thread = None
        self._current_worker = None
        logger_sm.debug(f"{task_name} task finished processing complete.")

    def is_task_active(self):
        """Returns True if a blocking background task is running."""
        return self._blocking_task_running

    def cleanup(self):
        """Cleans up resources, attempts to stop running workers."""
        logger_sm.info("StateManager cleanup initiated.")
        if (
            self._blocking_task_running
            and self._current_worker
            and hasattr(self._current_worker, "stop")
        ):
            worker_name = self._current_worker.__class__.__name__
            logger_sm.warning(f"Attempting stop of running worker ({worker_name}).")
            try:
                self._current_worker.stop()
            except Exception as e:
                logger_sm.error(f"Error signaling worker ({worker_name}) stop: {e}")

        thread_to_clean = self._current_thread
        if thread_to_clean and thread_to_clean.isRunning():
            logger_sm.info("Waiting for running thread during cleanup...")
            if not thread_to_clean.wait(7000):
                logger_sm.warning("Worker thread didn't finish gracefully.")
            else:
                logger_sm.info("Worker thread finished during cleanup.")

        # --- TIERING: Only cleanup REAL pipeline if Pro ---
        is_real_pipeline = (
            self.training_pipeline
            and hasattr(self.training_pipeline, "cleanup")
            and TrainingPipeline.__name__ != "_DummyTrainingPipeline"
        )
        if self.current_tier == "PRO" and is_real_pipeline:
            try:
                self.training_pipeline.cleanup()
                logger_sm.info("[PRO] REAL Training pipeline cleanup called.")
            except Exception as e:
                logger_sm.error(
                    f"Error during REAL TrainingPipeline cleanup: {e}", exc_info=True
                )
        elif self.training_pipeline and hasattr(self.training_pipeline, "cleanup"):
            logger_sm.debug("Skipping cleanup for DUMMY pipeline.")

        self._current_worker = None
        self._current_thread = None
        self._blocking_task_running = False
        logger_sm.info("StateManager cleanup finished.")

    # --- Data Export (Basic & Pro) ---

    def export_data_for_yolo(self, target_dir):
        """Exports approved annotations in YOLO format."""
        # This is needed for Basic tier as well.
        logger_sm.info(f"Attempting export YOLO data to: {target_dir}")
        if not self.dataset_handler:
            logger_sm.error("Cannot export: DatasetHandler unavailable.")
            return None
        if not hasattr(self.dataset_handler, "export_for_yolo"):
            logger_sm.error("Cannot export: DH missing 'export_for_yolo'.")
            return None

        # Get class map - needed for export regardless of tier.
        if not self.training_pipeline or not hasattr(
            self.training_pipeline, "class_to_id"
        ):
            logger_sm.error("Cannot export: Pipeline (real/dummy) or map missing.")
            return None
        class_to_id = self.training_pipeline.class_to_id
        if not class_to_id:  # Check if map is empty
            logger_sm.error("Cannot export: Class map is empty.")
            return None

        approved_paths = [
            p
            for p, data in self.annotations.items()
            if isinstance(data, dict) and data.get("approved")
        ]
        if not approved_paths:
            logger_sm.warning("No approved images found for export.")
            return None

        export_annotations = {
            p: self.annotations[p] for p in approved_paths if p in self.annotations
        }
        if not export_annotations:
            logger_sm.error("No valid annotation data for approved paths.")
            return None

        # Use the potentially DUMMY DatasetHandler instance
        original_handler_anns = None
        yaml_path = None
        try:
            # Temporarily set the annotations on the handler instance
            original_handler_anns = self.dataset_handler.annotations.copy()
            self.dataset_handler.annotations = export_annotations
            logger_sm.debug(
                f"Temporarily set DH with {len(export_annotations)} annotations."
            )
            # Call export on the handler instance (could be real or dummy)
            yaml_path = self.dataset_handler.export_for_yolo(
                image_paths_to_export=list(export_annotations.keys()),
                base_export_dir=target_dir,
                class_to_id=class_to_id,
                val_split=0.2,  # Basic can still have a validation split
            )
        except Exception as e:
            logger_sm.exception(
                f"Error during dataset_handler.export_for_yolo call to {target_dir}"
            )
            yaml_path = None
        finally:  # Restore original annotations on the handler
            if original_handler_anns is not None and self.dataset_handler:
                self.dataset_handler.annotations = original_handler_anns
                logger_sm.debug("Restored original annotations in DatasetHandler.")

        return yaml_path
