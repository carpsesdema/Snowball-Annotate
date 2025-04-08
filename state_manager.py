# state_manager.py (Corrected - Includes Export Method, DS Handler Refactor, Persistent Last Run Dir, Aug Keys, No Auto Load, Trigger Enables)

import os
import json
import logging
import torch
import shutil
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QTimer

import config

# Import TrainingPipeline and DatasetHandler
# Use a logger specific to this module scope
logger_sm = logging.getLogger(__name__)

try:
    from training_pipeline import TrainingPipeline, DatasetHandler

    logger_sm.info("OK: training_pipeline components imported.")
except ImportError as e:
    logger_sm.critical(
        f"Failed to import TrainingPipeline/DatasetHandler: {e}", exc_info=True
    )
    # Define dummies here if import fails, for basic functionality
    if "DatasetHandler" not in globals():

        class DatasetHandler:
            def __init__(self):
                self.annotations = {}

            def update_annotation(self, p, d):
                pass

            def get_annotation(self, p):
                return None

            def export_for_yolo(self, paths, base_dir, class_map, split=0.2):
                return None

        logger_sm.warning("Using dummy DatasetHandler defined in state_manager.py")

    if "TrainingPipeline" not in globals():

        class TrainingPipeline:
            def __init__(self, cl, s, dh):
                pass

            def cleanup(self):
                pass

            def update_classes(self, cl):
                pass

            def update_settings(self, s):
                pass

            def run_training_session(self, p, a, e, lr, pfx):
                return None

            def auto_box(self, img, conf):
                return []

            class_to_id = {}

        logger_sm.warning("Using dummy TrainingPipeline defined in state_manager.py")

# Import worker classes
try:
    from workers import PredictionWorker, TrainingWorker

    logger_sm.info("OK: Worker classes imported.")
except ImportError:
    logger_sm.error("Could not import worker classes. Threading will not work.")
    # Define dummy workers if import fails
    if "PredictionWorker" not in globals():

        class PredictionWorker(QObject):
            progress = pyqtSignal(str)
            finished = pyqtSignal(list)
            error = pyqtSignal(str)

            def __init__(self, *args):
                super().__init__()

            def run(self):
                self.error.emit("Dummy Worker: Prediction unavailable")

            def stop(self):
                pass

        logger_sm.warning("Using dummy PredictionWorker defined in state_manager.py")

    if "TrainingWorker" not in globals():

        class TrainingWorker(QObject):
            progress = pyqtSignal(str)
            finished = pyqtSignal(str)  # Emits run_dir path on success
            error = pyqtSignal(str)

            def __init__(self, *args):
                super().__init__()

            def run(self):
                self.error.emit("Dummy Worker: Training unavailable")

            def stop(self):
                pass

        logger_sm.warning("Using dummy TrainingWorker defined in state_manager.py")


class StateManager(QObject):
    # Signals
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

        # Ensure directories exist based on loaded/default settings
        os.makedirs(os.path.dirname(self._user_settings_path), exist_ok=True)
        session_path_key = config.SETTING_KEYS.get("session_path", "paths.session_path")
        session_dir = os.path.dirname(
            self.get_setting(session_path_key, config.DEFAULT_SESSION_PATH)
        )
        if session_dir:
            os.makedirs(session_dir, exist_ok=True)
        self.session_path = self.get_setting(
            session_path_key, config.DEFAULT_SESSION_PATH
        )  # Store current path

        self.approved_count = 0
        self.class_list = sorted(list(set(class_list))) if class_list else []
        self.last_successful_run_dir = None  # Initialize

        # Create DatasetHandler instance
        try:
            # Use the potentially dummied DatasetHandler class from globals()
            self.dataset_handler = DatasetHandler()
            logger_sm.info("DatasetHandler initialized in StateManager.")
        except Exception as e:
            logger_sm.exception("FATAL: Failed DatasetHandler init.")
            self.dataset_handler = None

        # Pass dataset_handler to TrainingPipeline
        try:
            # Use the potentially dummied TrainingPipeline class from globals()
            # Check if it's the real one by name convention
            if (
                "TrainingPipeline" in globals()
                and TrainingPipeline.__name__ != "_DummyTrainingPipeline"
            ):
                self.training_pipeline = TrainingPipeline(
                    class_list=self.class_list,
                    settings=self._settings,
                    dataset_handler=self.dataset_handler,
                )
                logger_sm.info("Real TrainingPipeline initialized.")
            else:  # It's the dummy
                # Make sure dummy can be initialized similarly if needed
                self.training_pipeline = TrainingPipeline(
                    self.class_list, self._settings, self.dataset_handler
                )
                logger_sm.warning("Using dummy TrainingPipeline instance.")
        except Exception as e:
            logger_sm.exception("FATAL: Failed TrainingPipeline init.")
            self.training_pipeline = None

        # Apply loaded settings to pipeline etc.
        self.update_internal_from_settings()

        # Task management attributes
        self._current_thread = None
        self._current_worker = None
        self._blocking_task_running = False

        logger_sm.info(f"StateManager initialized. Save path: {self.session_path}")
        logger_sm.info(f"User settings path: {self._user_settings_path}")
        logger_sm.info(f"Initial last run dir: {self.last_successful_run_dir}")

    # --- Settings Management Methods ---

    def load_settings(self):
        self._settings = config.get_default_settings()
        logger_sm.info(f"Loading settings from: {self._user_settings_path}")
        try:
            if os.path.exists(self._user_settings_path):
                with open(self._user_settings_path, "r") as f:
                    user_settings = json.load(f)
                self._settings.update(user_settings)
                logger_sm.info("Loaded user settings.")
            else:
                logger_sm.info("No user settings file found, using defaults.")
        except (json.JSONDecodeError, IOError, TypeError) as e:
            logger_sm.error(
                f"Failed load/decode settings from {self._user_settings_path}: {e}. Using defaults.",
                exc_info=True,
            )
            self._settings = config.get_default_settings()  # Reset on error

    def save_settings(self):
        logger_sm.debug(f"Saving settings to: {self._user_settings_path}")
        try:
            os.makedirs(os.path.dirname(self._user_settings_path), exist_ok=True)
            with open(self._user_settings_path, "w") as f:
                json.dump(self._settings, f, indent=4)
            logger_sm.info("User settings saved.")
        except Exception as e:
            logger_sm.error(
                f"Failed save settings {self._user_settings_path}: {e}", exc_info=True
            )

    def get_setting(self, key, default=None):
        config_default = config.get_default_settings().get(key)
        effective_default = config_default if config_default is not None else default
        if isinstance(effective_default, bool):
            return bool(self._settings.get(key, effective_default))
        return self._settings.get(key, effective_default)

    def set_setting(self, key, value):
        is_known_key = any(key == kp for kp in config.SETTING_KEYS.values())
        if not is_known_key:
            logger_sm.warning(f"Setting unknown key: {key}")
        original_value = self._settings.get(key)
        new_value = value
        try:
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
                f"Invalid type for setting '{key}': '{value}' (expected {expected_type}). Keeping previous value ('{original_value}')."
            )
            return
        if original_value != new_value:
            self._settings[key] = new_value
            logger_sm.info(f"Setting '{key}' updated to: {new_value}")
            self.save_settings()  # Save immediately on change
            self.update_internal_from_settings(key)
            self.settings_changed.emit()
        else:
            logger_sm.debug(f"Setting '{key}' value unchanged: {new_value}")

    def update_internal_from_settings(self, changed_key=None):
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
            ]
            if config.SETTING_KEYS.get(k)
        ]
        if (
            hasattr(self, "training_pipeline")
            and self.training_pipeline
            and hasattr(self.training_pipeline, "update_settings")
        ):
            if changed_key is None or changed_key in pipeline_relevant_keys:
                logger_sm.info(
                    f"Pushing updated settings to TrainingPipeline (triggered by '{changed_key or 'initial load'}')."
                )
                try:
                    self.training_pipeline.update_settings(self._settings)
                except Exception as e_pipe_update:
                    logger_sm.error(
                        f"Error updating training pipeline settings: {e_pipe_update}",
                        exc_info=True,
                    )

    def get_last_run_path(self):
        return self.last_successful_run_dir

    # --- Core State Methods ---

    def load_session(self, file_path=None):
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
                    f"Session file not found: {session_file}. Initializing empty state."
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

            loaded_run_dir = session_data.get("last_successful_run_dir")
            if (
                loaded_run_dir
                and isinstance(loaded_run_dir, str)
                and os.path.isdir(loaded_run_dir)
            ):
                self.last_successful_run_dir = loaded_run_dir
                logger_sm.info(
                    f"Loaded last successful run dir: {self.last_successful_run_dir}"
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

            keys_to_remove = [p for p in self.annotations if p not in self.image_list]
            if keys_to_remove:
                logger_sm.warning(
                    f"Removing {len(keys_to_remove)} annotations for missing images."
                )
                for k in keys_to_remove:
                    self.annotations.pop(k, None)

            if not (
                isinstance(loaded_index, int)
                and 0 <= loaded_index < len(self.image_list)
            ):
                self.current_index = 0 if self.image_list else -1
                logger_sm.warning(
                    f"Loaded index {loaded_index} invalid, reset to {self.current_index}."
                )
            else:
                self.current_index = loaded_index

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
                    logger_sm.warning(
                        f"Invalid annotation data type for {img_path} in session."
                    )

            if classes_changed:
                self.update_pipeline_classes()

            logger_sm.info(
                f"Session loaded: {len(self.image_list)} images, {len(self.annotations)} annotations. "
                f"Index: {self.current_index}. Approved: {self.approved_count}. "
                f"Last Run: {os.path.basename(self.last_successful_run_dir) if self.last_successful_run_dir else 'None'}"
            )
            self.settings_changed.emit()
            return True

        except json.JSONDecodeError as e:
            logger_sm.error(
                f"Error decoding JSON from {session_file}: {e}", exc_info=True
            )
            return False
        except Exception as e:
            logger_sm.error(
                f"Failed to load session from {session_file}: {e}", exc_info=True
            )
            return False

    def save_session(self):
        session_file = self.get_setting(
            config.SETTING_KEYS["session_path"], self.session_path
        )
        logger_sm.info(f"Saving session to: {session_file}")
        session_data = {
            "image_list": self.image_list,
            "annotations": self.annotations,
            "current_index": self.current_index,
            "class_list": self.class_list,
            "last_successful_run_dir": self.last_successful_run_dir,
        }
        try:
            save_dir = os.path.dirname(session_file)
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
            else:
                logger_sm.warning(
                    f"Session path '{session_file}' has no directory? Saving to current dir."
                )
            with open(session_file, "w") as f:
                json.dump(session_data, f, indent=4)
            logger_sm.info("Session saved successfully.")
        except Exception as e:
            logger_sm.error(
                f"Failed to save session to {session_file}: {e}", exc_info=True
            )

    def load_images_from_directory(self, directory_path):
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
                logger_sm.warning(
                    f"No supported images found in {directory_path}. Clearing current state."
                )
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
                    logger_sm.info(
                        "New directory or content change detected. Resetting annotations and index."
                    )
                    self.image_list = image_files
                    self.current_index = 0
                    self.annotations = {}
                    self.approved_count = 0
                    self.last_successful_run_dir = None
                    if self.dataset_handler:
                        self.dataset_handler.annotations.clear()
                else:
                    logger_sm.info(
                        "Directory reloaded, image list content is identical. State unchanged."
                    )

            if not (0 <= self.current_index < len(self.image_list)):
                self.current_index = 0 if self.image_list else -1

            logger_sm.info(
                f"Loaded {len(self.image_list)} images. Current index: {self.current_index}."
            )
        except FileNotFoundError:
            logger_sm.error(f"Directory not found: {directory_path}")
            raise
        except Exception as e:
            logger_sm.error(f"Failed load images {directory_path}: {e}", exc_info=True)
            raise

    def get_current_image(self):
        if self.image_list and 0 <= self.current_index < len(self.image_list):
            return self.image_list[self.current_index]
        return None

    def next_image(self):
        if not self.image_list:
            return False
        if self.current_index < len(self.image_list) - 1:
            self.current_index += 1
            logger_sm.debug(f"Navigated to next index: {self.current_index}")
            return True
        logger_sm.debug("Already at last image.")
        return False

    def prev_image(self):
        if not self.image_list:
            return False
        if self.current_index > 0:
            self.current_index -= 1
            logger_sm.debug(f"Navigated to previous index: {self.current_index}")
            return True
        logger_sm.debug("Already at first image.")
        return False

    def go_to_image(self, index):
        if self.image_list and 0 <= index < len(self.image_list):
            if self.current_index != index:
                self.current_index = index
                logger_sm.debug(f"Navigated directly to index: {self.current_index}")
            return True
        logger_sm.warning(
            f"Invalid goto index: {index} (List size: {len(self.image_list)})"
        )
        return False

    def update_classes(self, new_class_list):
        new_classes_clean = sorted(
            list(set(str(cls).strip() for cls in new_class_list if str(cls).strip()))
        )
        if new_classes_clean != self.class_list:
            logger_sm.info(
                f"Updating class list from {self.class_list} to {new_classes_clean}"
            )
            old_class_set = set(self.class_list)
            self.class_list = new_classes_clean
            valid_new_set = set(self.class_list)
            updated_anns = {}
            removed_box_count = 0
            affected_image_count = 0
            if self.dataset_handler:
                self.dataset_handler.annotations.clear()

            for img_path, data in self.annotations.items():
                if not isinstance(data, dict):
                    logger_sm.warning(
                        f"Skipping invalid annotation data for {img_path} during class update."
                    )
                    continue
                if data.get("negative", False):
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
                    self.dataset_handler.update_annotation(
                        img_path, updated_anns[img_path]
                    )

            if removed_box_count > 0:
                logger_sm.warning(
                    f"Removed {removed_box_count} annotation boxes from {affected_image_count} images due to class change."
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
        if self.training_pipeline and hasattr(self.training_pipeline, "update_classes"):
            logger_sm.info("Updating TrainingPipeline classes...")
            try:
                self.training_pipeline.update_classes(self.class_list)
                logger_sm.info("Pipeline classes updated successfully.")
            except Exception as e:
                logger_sm.error("Failed to update pipeline classes.", exc_info=True)
        elif self.training_pipeline:
            logger_sm.error(
                "TrainingPipeline instance missing 'update_classes' method."
            )
        else:
            logger_sm.warning(
                "Cannot update pipeline classes: No TrainingPipeline instance."
            )

    # --- Annotation & Training Trigger ---

    def add_annotation(self, image_path, annotation_data):
        if not image_path:
            logger_sm.error("add_annotation failed: No image_path provided.")
            return False
        if not isinstance(annotation_data, dict):
            logger_sm.error(
                f"add_annotation failed: Invalid annotation_data type for {image_path}"
            )
            return False

        logger_sm.info(f"Updating annotation state for {os.path.basename(image_path)}")
        was_approved_before = self.annotations.get(image_path, {}).get(
            "approved", False
        )
        is_approved_now = annotation_data.get("approved", False)
        self.annotations[image_path] = annotation_data

        if is_approved_now and not was_approved_before:
            self.approved_count += 1
        elif not is_approved_now and was_approved_before:
            self.approved_count -= 1
        self.approved_count = max(0, self.approved_count)
        logger_sm.debug(f"Approved count updated: {self.approved_count}")

        if self.dataset_handler and hasattr(self.dataset_handler, "update_annotation"):
            self.dataset_handler.update_annotation(image_path, annotation_data)
        else:
            logger_sm.warning(
                "Cannot update DatasetHandler: Instance or method missing."
            )

        QTimer.singleShot(100, self.save_session)  # Save asynchronously

        # --- Training Triggers (MODIFIED) ---
        if is_approved_now and not was_approved_before and self.training_pipeline:
            current_approved_count = self.approved_count
            epochs, lr, prefix = None, None, None
            trigger_level = None

            # Get Enable Settings
            trigger_20_enabled = self.get_setting(
                config.SETTING_KEYS["training.trigger_20_enabled"], True
            )
            trigger_100_enabled = self.get_setting(
                config.SETTING_KEYS["training.trigger_100_enabled"], True
            )
            logger_sm.debug(
                f"Checking triggers: 20_enabled={trigger_20_enabled}, 100_enabled={trigger_100_enabled}"
            )

            # Apply Enable Settings to Trigger Logic
            if (
                trigger_100_enabled
                and current_approved_count > 0
                and current_approved_count % 100 == 0
            ):
                trigger_level = 100
            elif (
                trigger_20_enabled
                and current_approved_count > 0
                and current_approved_count % 20 == 0
            ):
                if trigger_level != 100:
                    trigger_level = 20

            # Determine parameters based on triggered level
            if trigger_level == 100:
                logger_sm.info(
                    f"Approved count {current_approved_count}: Triggering MAJOR (100) training."
                )
                epochs_key = config.SETTING_KEYS.get("epochs_100")
                lr_key = config.SETTING_KEYS.get("lr_100")
                epochs = self.get_setting(epochs_key, config.DEFAULT_EPOCHS_100)
                lr = self.get_setting(lr_key, config.DEFAULT_LR_100)
                prefix = f"major_{current_approved_count}"
            elif trigger_level == 20:
                logger_sm.info(
                    f"Approved count {current_approved_count}: Triggering MINI (20) training."
                )
                epochs_key = config.SETTING_KEYS.get("epochs_20")
                lr_key = config.SETTING_KEYS.get("lr_20")
                epochs = self.get_setting(epochs_key, config.DEFAULT_EPOCHS_20)
                lr = self.get_setting(lr_key, config.DEFAULT_LR_20)
                prefix = f"mini_{current_approved_count}"

            # Schedule Task if parameters determined
            if epochs is not None and lr is not None and prefix is not None:
                logger_sm.info(
                    f"Scheduling {prefix} training task (Epochs: {epochs}, LR: {lr:.6f})."
                )
                QTimer.singleShot(
                    150,
                    lambda e=epochs, l=lr, p=prefix: self.start_training_task(e, l, p),
                )
        elif not self.training_pipeline and is_approved_now and not was_approved_before:
            logger_sm.error(
                f"Annotation approved, but cannot trigger training: Pipeline unavailable."
            )

        return True

    # --- Task Management ---

    def start_prediction(self, image_path):
        logger_sm.debug(f"Request start prediction for {os.path.basename(image_path)}")
        if "PredictionWorker" not in globals() or not issubclass(
            globals()["PredictionWorker"], QObject
        ):
            logger_sm.error("PredictionWorker class unavailable or invalid.")
            self.prediction_error.emit("Prediction unavailable (Worker missing).")
            return False
        current_confidence = self.get_setting(
            config.SETTING_KEYS["confidence_threshold"]
        )
        return self._start_task(
            globals()["PredictionWorker"], image_path, current_confidence
        )

    def start_training_task(self, epochs, lr, run_name_prefix):
        if "TrainingWorker" not in globals() or not issubclass(
            globals()["TrainingWorker"], QObject
        ):
            logger_sm.error("TrainingWorker class unavailable or invalid.")
            self.training_error.emit("Training unavailable (Worker missing).")
            return False

        logger_sm.info(f"Preparing data for training run '{run_name_prefix}'...")
        approved_annotations = {
            p: data
            for p, data in self.annotations.items()
            if isinstance(data, dict) and data.get("approved")
        }
        approved_paths = list(approved_annotations.keys())

        if not approved_paths:
            logger_sm.warning("No approved images found for training.")
            self.training_error.emit("No approved images for training")
            return False

        logger_sm.info(
            f"Request start {run_name_prefix} training on {len(approved_paths)} images (Epochs: {epochs}, LR: {lr})."
        )
        return self._start_task(
            globals()["TrainingWorker"],
            approved_paths,
            approved_annotations,
            epochs,
            lr,
            run_name_prefix,
        )

    def _start_task(self, worker_class, *args):
        task_name = worker_class.__name__
        if not self.training_pipeline or not hasattr(
            self.training_pipeline, "run_training_session"
        ):
            error_msg = f"Cannot start {task_name}: Pipeline unavailable or invalid."
            logger_sm.error(error_msg)
            if task_name == "PredictionWorker":
                self.prediction_error.emit(error_msg)
            elif task_name == "TrainingWorker":
                self.training_error.emit(error_msg)
            return False

        if self._blocking_task_running:
            logger_sm.warning(f"Cannot start {task_name}: Another task running.")
            if task_name == "PredictionWorker":
                self.prediction_error.emit("Busy: Another task running.")
            elif task_name == "TrainingWorker":
                self.training_error.emit("Busy: Another task running.")
            return False

        self._blocking_task_running = True
        self.task_running.emit(True)

        try:
            self._current_thread = QThread()
            self._current_worker = worker_class(self.training_pipeline, *args)
            self._current_worker.moveToThread(self._current_thread)

            if isinstance(self._current_worker, PredictionWorker):
                self._current_worker.progress.connect(self.prediction_progress)
                self._current_worker.finished.connect(self.prediction_finished)
                self._current_worker.error.connect(self.prediction_error)
                self._current_worker.finished.connect(
                    lambda result=None,
                    worker=self._current_worker: self._on_task_finished(
                        worker.__class__.__name__, result
                    )
                )
                self._current_worker.error.connect(
                    lambda worker=self._current_worker: self._on_task_finished(
                        worker.__class__.__name__, None
                    )
                )
            elif isinstance(self._current_worker, TrainingWorker):
                self._current_worker.progress.connect(self.training_progress)
                self._current_worker.finished.connect(self.training_run_completed)
                self._current_worker.error.connect(self.training_error)
                self._current_worker.finished.connect(
                    lambda result=None,
                    worker=self._current_worker: self._on_task_finished(
                        worker.__class__.__name__, result
                    )
                )
                self._current_worker.error.connect(
                    lambda worker=self._current_worker: self._on_task_finished(
                        worker.__class__.__name__, None
                    )
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
            if task_name == "PredictionWorker":
                self.prediction_error.emit(error_msg)
            elif task_name == "TrainingWorker":
                self.training_error.emit(error_msg)
            if self._current_thread:
                self._current_thread.quit()
            self._blocking_task_running = False
            self.task_running.emit(False)
            self._current_thread = None
            self._current_worker = None
            return False

    def _on_task_finished(self, task_name, result=None):
        logger_sm.info(
            f"Internal handler: Background task ({task_name}) finished/errored."
        )

        if (
            task_name == "TrainingWorker"
            and isinstance(result, str)
            and os.path.isdir(result)
        ):
            self.last_successful_run_dir = result
            logger_sm.info(f"Stored last successful run directory: {result}")
            QTimer.singleShot(50, self.save_session)
        elif task_name == "PredictionWorker" and isinstance(result, list):
            logger_sm.debug(f"Prediction task finished with {len(result)} results.")
        elif result is None:
            logger_sm.warning(f"{task_name} task finished with error or no result.")

        thread_to_clean = self._current_thread
        if thread_to_clean:
            logger_sm.debug(f"Cleaning up thread for {task_name}...")
            if thread_to_clean.isRunning():
                thread_to_clean.quit()
                if not thread_to_clean.wait(5000):
                    logger_sm.warning(
                        f"Thread ({task_name}) did not finish cleanup within 5s."
                    )
                else:
                    logger_sm.debug(f"Thread ({task_name}) finished cleanly.")
            else:
                logger_sm.debug(f"Thread ({task_name}) was already finished.")

        if self._blocking_task_running:
            self._blocking_task_running = False
            self.task_running.emit(False)  # Notify GUI

        self._current_thread = None
        self._current_worker = None
        logger_sm.debug(f"{task_name} task finished processing complete.")

    def is_task_active(self):
        return self._blocking_task_running

    def cleanup(self):
        logger_sm.info("StateManager cleanup initiated.")
        if (
            self._blocking_task_running
            and self._current_worker
            and hasattr(self._current_worker, "stop")
        ):
            worker_name = self._current_worker.__class__.__name__
            logger_sm.warning(
                f"Attempting cooperative stop of running worker ({worker_name})."
            )
            try:
                self._current_worker.stop()
            except Exception as e:
                logger_sm.error(f"Error signaling worker ({worker_name}) stop: {e}")

        thread_to_clean = self._current_thread
        if thread_to_clean and thread_to_clean.isRunning():
            logger_sm.info("Waiting for running thread during cleanup...")
            if not thread_to_clean.wait(7000):
                logger_sm.warning(
                    "Worker thread did not finish gracefully during cleanup."
                )
            else:
                logger_sm.info("Worker thread finished during cleanup.")

        if self.training_pipeline and hasattr(self.training_pipeline, "cleanup"):
            try:
                self.training_pipeline.cleanup()
                logger_sm.info("Training pipeline cleanup called.")
            except Exception as e:
                logger_sm.error(
                    f"Error during TrainingPipeline cleanup: {e}", exc_info=True
                )

        self._current_worker = None
        self._current_thread = None
        self._blocking_task_running = False
        logger_sm.info("StateManager cleanup finished.")

    # --- Data Export ---

    def export_data_for_yolo(self, target_dir):
        logger_sm.info(f"Attempting export YOLO data to: {target_dir}")
        if not self.dataset_handler:
            logger_sm.error("Cannot export: DatasetHandler not available.")
            return None
        if not hasattr(self.dataset_handler, "export_for_yolo"):
            logger_sm.error(
                "Cannot export: DatasetHandler missing 'export_for_yolo' method."
            )
            return None
        if not self.training_pipeline or not hasattr(
            self.training_pipeline, "class_to_id"
        ):
            logger_sm.error(
                "Cannot export: Training pipeline or class_to_id map missing."
            )
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
            logger_sm.error("No valid annotation data found for approved paths.")
            return None

        class_to_id = self.training_pipeline.class_to_id
        if not class_to_id:
            logger_sm.error(
                "Cannot export: Class map from pipeline is empty or invalid."
            )
            return None

        original_handler_anns = None
        yaml_path = None
        try:
            original_handler_anns = self.dataset_handler.annotations.copy()
            self.dataset_handler.annotations = export_annotations
            logger_sm.debug(
                f"Temporarily set DatasetHandler with {len(export_annotations)} annotations for export."
            )
            yaml_path = self.dataset_handler.export_for_yolo(
                image_paths_to_export=list(export_annotations.keys()),
                base_export_dir=target_dir,
                class_to_id=class_to_id,
                val_split=0.0,
            )
        except Exception as e:
            logger_sm.exception(
                f"Error during dataset_handler.export_for_yolo call to {target_dir}"
            )
            yaml_path = None
        finally:
            if original_handler_anns is not None and self.dataset_handler:
                self.dataset_handler.annotations = original_handler_anns
                logger_sm.debug(
                    "Restored original annotations in DatasetHandler after export attempt."
                )
            elif not self.dataset_handler:
                logger_sm.error("Cannot restore annotations: DatasetHandler is None.")
        return yaml_path


# --- End of state_manager.py Modifications ---
