# dummy_components.py
import logging
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget
import config  # Needed for dummy state manager settings
import os

logger = logging.getLogger(__name__)


# --- Dummy StateManager ---
class _DummyStateManager(QObject):
    # Minimal signals needed for AnnotatorWindow connections
    task_running = pyqtSignal(bool)
    settings_changed = pyqtSignal()
    prediction_progress = pyqtSignal(str)
    prediction_finished = pyqtSignal(list)
    prediction_error = pyqtSignal(str)
    training_progress = pyqtSignal(str)
    training_run_completed = pyqtSignal(str)
    training_error = pyqtSignal(str)

    # --- MODIFIED: Changed 'cl' parameter name to 'class_list' ---
    def __init__(self, class_list):  # Now accepts 'class_list' keyword argument
        super().__init__()
        self._settings = config.get_default_settings()
        self.image_list = []
        self.annotations = {}
        # Use passed class list or default
        # --- MODIFIED: Use the 'class_list' parameter variable ---
        self.class_list = class_list if isinstance(class_list, list) else ["Object"]
        self.training_pipeline = None  # Dummy doesn't have a real pipeline
        self.current_index = -1
        self.approved_count = 0
        logger.warning("--- Using DUMMY StateManager from dummy_components.py ---")

    def get_setting(self, k, d=None):
        default = config.get_default_settings().get(k)
        effective_default = default if default is not None else d
        return self._settings.get(k, effective_default)

    def set_setting(self, k, v):
        self._settings[k] = v
        logger.debug(f"Dummy setting '{k}' set to {v}")
        # Simulate emitting signal on change for UI updates
        self.settings_changed.emit()

    def get_current_image(self):
        if self.image_list and 0 <= self.current_index < len(self.image_list):
            return self.image_list[self.current_index]
        return None  # Or return a dummy path if needed for testing

    def next_image(self):
        logger.debug("Dummy StateManager: next_image called.")
        # Simulate moving if list has items (for basic UI testing)
        if len(self.image_list) > 1 and self.current_index < len(self.image_list) - 1:
            self.current_index += 1
            return True
        return False

    def prev_image(self):
        logger.debug("Dummy StateManager: prev_image called.")
        if len(self.image_list) > 1 and self.current_index > 0:
            self.current_index -= 1
            return True
        return False

    def go_to_image(self, i):
        logger.debug(f"Dummy StateManager: go_to_image({i}) called.")
        if 0 <= i < len(self.image_list):
            self.current_index = i
            return True
        return False

    def load_images_from_directory(self, p):
        logger.warning(
            f"Dummy StateManager: load_images_from_directory called with path {p}. Simulating load."
        )
        # Simulate loading a few images for UI testing
        self.image_list = [
            os.path.join(p, f"dummy_image_{i + 1}.jpg") for i in range(5)
        ]
        self.annotations = {}
        self.current_index = 0 if self.image_list else -1
        self.approved_count = 0
        logger.info(
            f"Dummy StateManager: Simulated loading {len(self.image_list)} images."
        )

    def save_session(self):
        logger.warning("Dummy StateManager: save_session called, doing nothing.")
        pass

    def load_session(self, file_path=None):
        logger.warning(
            f"Dummy StateManager: load_session called with path {file_path}. Simulating load."
        )
        # Simulate loading session data
        self.image_list = [f"dummy_session_img_{i + 1}.png" for i in range(3)]
        self.class_list = ["LoadedClass1", "LoadedClass2"]
        self.annotations = {
            self.image_list[0]: {
                "annotations_list": [],
                "approved": True,
                "negative": False,
            },
            self.image_list[1]: {
                "annotations_list": [],
                "approved": False,
                "negative": False,
            },
        }
        self.current_index = 0
        self.approved_count = 1  # Count approved ones
        self.settings_changed.emit()  # Simulate settings potentially changing on load
        logger.info(f"Dummy StateManager: Simulated loading session.")
        return True  # Indicate success

    def cleanup(self):
        logger.warning("Dummy StateManager: cleanup called.")
        pass

    def add_annotation(self, p, d):
        logger.warning(f"Dummy StateManager: add_annotation called for path {p}.")
        was_approved = self.annotations.get(p, {}).get("approved", False)
        is_approved = d.get("approved", False)
        self.annotations[p] = d  # Store dummy data
        if is_approved and not was_approved:
            self.approved_count += 1
        elif not is_approved and was_approved:
            self.approved_count -= 1
        self.approved_count = max(0, self.approved_count)
        logger.debug(f"Dummy approved count: {self.approved_count}")
        # Simulate training trigger sometimes for UI testing
        if self.approved_count > 0 and self.approved_count % 3 == 0:
            logger.info("Dummy training trigger (simulated)")
            self.training_progress.emit("Dummy Training: Starting...")
            # Simulate completion/error after a delay elsewhere if needed
        return True  # Simulate success

    def start_prediction(self, p):
        logger.warning(f"Dummy StateManager: start_prediction called for {p}.")
        # Simulate prediction starting and maybe finishing/erroring later
        self.task_running.emit(True)
        self.prediction_progress.emit("Dummy Prediction: Running...")
        # In a real dummy, you might use QTimer to emit finished/error later
        # For now, just indicate it started but won't finish successfully here.
        # Example: emit error immediately
        self.prediction_error.emit("Dummy Prediction Failed: Feature unavailable.")
        self.task_running.emit(False)
        logger.warning("Dummy prediction started, but immediately emitted error.")
        return False  # Indicate task could not proceed

    def start_training_task(self, epochs, lr, run_name_prefix):
        logger.warning(
            f"Dummy StateManager: start_training_task called ({epochs=}, {lr=}, {run_name_prefix=})."
        )
        self.task_running.emit(True)
        self.training_progress.emit(f"Dummy Training '{run_name_prefix}': Starting...")
        # Simulate completion or error - maybe error immediately
        self.training_error.emit(
            f"Dummy Manager: Training '{run_name_prefix}' not available"
        )
        self.task_running.emit(False)
        logger.warning("Dummy training started and immediately emitted error.")
        return False  # Indicate immediate failure/unavailability

    def is_task_active(self):
        # Simple dummy logic - Assume false unless start_* sets it and error/finish resets it.
        # In this dummy, tasks emit error immediately, so it should always be false after call.
        return False

    def update_pipeline_classes(self):
        logger.warning("Dummy StateManager: update_pipeline_classes called.")
        pass

    def update_classes(self, nl):
        logger.warning(f"Dummy StateManager: update_classes called with {nl}.")
        old_classes = set(self.class_list)
        new_classes = set(nl)
        removed_classes = old_classes - new_classes
        if removed_classes:
            logger.warning(
                f"Dummy: Simulating removal of annotations for classes: {removed_classes}"
            )
            # Simulate some approved count change if classes were removed
            self.approved_count = max(0, self.approved_count - 1)
        self.class_list = nl
        logger.debug(f"Dummy class list set to: {self.class_list}")
        logger.debug(f"Dummy approved count is now: {self.approved_count}")

    def get_last_run_path(self):
        logger.warning("Dummy StateManager: get_last_run_path called.")
        return None  # No dummy run path

    def export_data_for_yolo(self, target_dir):
        logger.warning(
            f"Dummy StateManager: export_data_for_yolo called for {target_dir}."
        )
        # Simulate creating a dummy file maybe?
        dummy_yaml = os.path.join(target_dir, "dummy_dataset.yaml")
        try:
            os.makedirs(
                os.path.join(target_dir, config.IMAGES_SUBDIR, config.TRAIN_SUBDIR),
                exist_ok=True,
            )
            os.makedirs(
                os.path.join(target_dir, config.LABELS_SUBDIR, config.TRAIN_SUBDIR),
                exist_ok=True,
            )
            with open(dummy_yaml, "w") as f:
                f.write(f"# Dummy YAML created by DummyStateManager\n")
                f.write(f"path: {os.path.abspath(target_dir)}\n")
                f.write(
                    f"train: {os.path.join(config.IMAGES_SUBDIR, config.TRAIN_SUBDIR)}\n"
                )
                f.write(
                    f"val: {os.path.join(config.IMAGES_SUBDIR, config.TRAIN_SUBDIR)}\n"
                )  # Point val to train for dummy
                f.write(f"nc: {len(self.class_list)}\n")
                f.write(f"names: {self.class_list}\n")
            logger.info(f"Created dummy YAML at {dummy_yaml}")
            return dummy_yaml
        except Exception as e:
            logger.error(f"Dummy export failed: {e}")
            return None


# --- Dummy GUI Components ---
# These inherit from QWidget so they can be added to layouts without error,
# but they won't display anything functional.


class DummyAnnotationScene(QWidget):
    annotationsModified = pyqtSignal()  # Keep signal for connection checks

    def __init__(self, parent=None):
        super().__init__(parent)
        logger.warning("--- Using DUMMY AnnotationScene ---")
        self.image_item = None  # No real image item

    def set_image(self, path):
        logger.debug(f"Dummy Scene: set_image({path}) called.")
        return False  # Indicate failure or no change

    def get_image_size(self):
        return (0, 0)

    def set_tool(self, tool_name):
        logger.debug(f"Dummy Scene: set_tool({tool_name}) called.")

    def clear_annotations(self):
        logger.debug("Dummy Scene: clear_annotations called.")

    def get_all_annotations(self):
        return []

    def add_annotation_item_from_data(self, data, w, h):
        logger.debug(f"Dummy Scene: add_annotation_item_from_data({data}) called.")
        return False

    # Add other methods expected by AnnotatorWindow if needed, returning dummy values
    def items(self):
        return []  # Return empty list for item iteration

    def removeItem(self, item):
        pass  # Do nothing

    def addItem(self, item):
        pass  # Do nothing

    def sceneRect(self):
        from PyQt6.QtCore import QRectF

        return QRectF(0, 0, 1, 1)  # Minimal rect


class DummyAnnotatorGraphicsView(QWidget):
    def __init__(self, scene, parent=None):
        super().__init__(parent)
        logger.warning("--- Using DUMMY AnnotatorGraphicsView ---")

    def fitInView(self, *args):
        pass

    def setFocus(self):
        pass

    # Add other methods if needed


class DummySettingsDialog(QWidget):  # QDialog might be better if exec_ is called
    def __init__(self, state, parent=None):
        super().__init__(parent)
        logger.warning("--- Using DUMMY SettingsDialog ---")

    def exec(self):  # QDialog uses exec(), QWidget doesn't have it directly
        logger.warning("Dummy SettingsDialog exec() called.")
        # Need to import QMessageBox here if not already imported globally
        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.information(
            self, "Dummy Dialog", "This is a dummy settings dialog."
        )
        return 0  # Simulate rejection


class DummyResizableRectItem(QWidget):  # Not ideal, should be QGraphicsItem based
    # This dummy is problematic as it needs to be added to a QGraphicsScene
    # A better dummy might inherit QGraphicsRectItem but do nothing.
    # For now, QWidget prevents crashes but won't work visually.
    is_suggestion = False  # Add expected attribute

    def __init__(self, rect, label, is_suggestion=False, confidence=None, parent=None):
        # QWidget doesn't take rect/label/is_suggestion/confidence
        super().__init__(parent)
        self.class_label = label  # Store label for logging
        self.is_suggestion = is_suggestion
        logger.warning(
            f"--- Using DUMMY ResizableRectItem (non-functional) for label '{label}' ---"
        )

    # Add methods expected by AnnotatorWindow/AnnotationScene if needed
    def sceneBoundingRect(self):
        from PyQt6.QtCore import QRectF

        return QRectF(0, 0, 1, 1)  # Dummy rect

    def setSelected(self, selected):
        pass

    def scene(self):
        return None  # No real scene


class DummyTrainingDashboard(QWidget):  # QDialog might be better
    finished = pyqtSignal()  # Add signal expected by AnnotatorWindow

    def __init__(self, state, parent=None):
        super().__init__(parent)
        logger.warning("--- Using DUMMY TrainingDashboard ---")
        # Optionally set size or add a label
        from PyQt6.QtWidgets import QLabel, QVBoxLayout

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Dummy Training Dashboard (Non-functional)"))
        self.setWindowTitle("Dummy Dashboard")
        self.resize(400, 200)

    # QWidget doesn't have exec, use show() like a non-modal dialog
    def show(self):
        logger.warning("Dummy TrainingDashboard show() called.")
        super().show()

    # Add other methods expected by AnnotatorWindow
    def update_graph(self, path):
        logger.warning(f"Dummy TrainingDashboard update_graph called with path: {path}")

    def raise_(self):  # Mimic QDialog method
        self.show()
        self.activateWindow()

    def activateWindow(self):  # Mimic QDialog method
        if self.windowHandle():
            self.windowHandle().requestActivate()
        super().activateWindow()

    # Emit finished when closed (QWidget doesn't do this automatically like QDialog)
    def closeEvent(self, event):
        self.finished.emit()
        super().closeEvent(event)
