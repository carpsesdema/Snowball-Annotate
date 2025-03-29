# dummy_components.py
import logging
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget
import config # Needed for dummy state manager settings
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

    def __init__(self, cl): # Accepts class list argument
        super().__init__()
        self._settings = config.get_default_settings()
        self.image_list = []
        self.annotations = {}
        # Use passed class list or default
        self.class_list = cl if isinstance(cl, list) else ["Object"]
        self.training_pipeline = None
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

    def get_current_image(self):
        return None # Or return a dummy path if needed for testing

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
        logger.warning(f"Dummy StateManager: load_images_from_directory called with path {p}. Simulating load.")
        # Simulate loading a few images for UI testing
        self.image_list = [os.path.join(p, f"dummy_image_{i+1}.jpg") for i in range(5)]
        self.annotations = {}
        self.current_index = 0 if self.image_list else -1
        self.approved_count = 0
        logger.info(f"Dummy StateManager: Simulated loading {len(self.image_list)} images.")

    def save_session(self):
        logger.warning("Dummy StateManager: save_session called, doing nothing.")
        pass

    def load_session(self, p=None):
        logger.warning(f"Dummy StateManager: load_session called with path {p}. Simulating load.")
        # Simulate loading session data
        self.image_list = [f"dummy_session_img_{i+1}.png" for i in range(3)]
        self.class_list = ["LoadedClass1", "LoadedClass2"]
        self.annotations = {
             self.image_list[0]: {"annotations_list": [], "approved": True, "negative": False},
             self.image_list[1]: {"annotations_list": [], "approved": False, "negative": False}
        }
        self.current_index = 0
        self.approved_count = 1 # Count approved ones
        self.settings_changed.emit() # Simulate settings potentially changing on load
        logger.info(f"Dummy StateManager: Simulated loading session.")
        return True # Indicate success

    def cleanup(self):
        logger.warning("Dummy StateManager: cleanup called.")
        pass

    def add_annotation(self, p, d):
        logger.warning(f"Dummy StateManager: add_annotation called for path {p}.")
        was_approved = self.annotations.get(p, {}).get("approved", False)
        is_approved = d.get("approved", False)
        self.annotations[p] = d # Store dummy data
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
        return True # Simulate success

    def start_prediction(self, p):
        logger.warning(f"Dummy StateManager: start_prediction called for {p}.")
        # Simulate prediction starting and maybe finishing/erroring later
        self.task_running.emit(True)
        self.prediction_progress.emit("Dummy Prediction: Running...")
        # In a real dummy, you might use QTimer to emit finished/error later
        # For now, just indicate it started but won't finish successfully here.
        # self.prediction_error.emit("Dummy Prediction Failed")
        # self.task_running.emit(False)
        logger.warning("Dummy prediction started, but will not complete in this simple version.")
        return True # Indicate task was accepted

    def start_training_task(self, epochs, lr, run_name_prefix):
        logger.warning(f"Dummy StateManager: start_training_task called ({epochs=}, {lr=}, {run_name_prefix=}).")
        self.task_running.emit(True)
        self.training_progress.emit(f"Dummy Training '{run_name_prefix}': Starting...")
        # Simulate completion or error - maybe error immediately
        self.training_error.emit(f"Dummy Manager: Training '{run_name_prefix}' not available")
        self.task_running.emit(False)
        logger.warning("Dummy training started and immediately emitted error.")
        return False # Indicate immediate failure/unavailability

    def is_task_active(self):
        # Simple dummy logic - needs external update or QTimer for realistic behavior
        # For now, assume false unless start_* sets it and error/finish resets it immediately.
        # A better dummy might track this state more realistically.
        return False

    def update_pipeline_classes(self):
        logger.warning("Dummy StateManager: update_pipeline_classes called.")
        pass

    def update_classes(self, nl):
        logger.warning(f"Dummy StateManager: update_classes called with {nl}.")
        self.class_list = nl
        # Simulate approved count change for UI testing
        self.approved_count = max(0, self.approved_count - 1)

    def get_last_run_path(self):
        logger.warning("Dummy StateManager: get_last_run_path called.")
        return None # No dummy run path

    def export_data_for_yolo(self, target_dir):
        logger.warning(f"Dummy StateManager: export_data_for_yolo called for {target_dir}.")
        # Simulate creating a dummy file maybe?
        dummy_yaml = os.path.join(target_dir, "dummy_dataset.yaml")
        try:
            os.makedirs(target_dir, exist_ok=True)
            with open(dummy_yaml, "w") as f:
                f.write("# Dummy YAML created by DummyStateManager\n")
            logger.info(f"Created dummy YAML at {dummy_yaml}")
            return dummy_yaml
        except Exception as e:
            logger.error(f"Dummy export failed: {e}")
            return None

# --- Dummy GUI Components ---
# These inherit from QWidget so they can be added to layouts without error,
# but they won't display anything functional.

class DummyAnnotationScene(QWidget):
    annotationsModified = pyqtSignal() # Keep signal for connection checks
    def __init__(self, parent=None):
        super().__init__(parent)
        logger.warning("--- Using DUMMY AnnotationScene ---")
    def set_image(self, path): return False
    def get_image_size(self): return (0, 0)
    def set_tool(self, tool_name): pass
    def clear_annotations(self): pass
    def get_all_annotations(self): return []
    def add_annotation_item_from_data(self, data, w, h): return False
    # Add other methods expected by AnnotatorWindow if needed, returning dummy values

class DummyAnnotatorGraphicsView(QWidget):
    def __init__(self, scene, parent=None):
        super().__init__(parent)
        logger.warning("--- Using DUMMY AnnotatorGraphicsView ---")
    def fitInView(self, *args): pass
    def setFocus(self): pass
    # Add other methods if needed

class DummySettingsDialog(QWidget): # QDialog might be better if exec_ is called
    def __init__(self, state, parent=None):
        super().__init__(parent)
        logger.warning("--- Using DUMMY SettingsDialog ---")
    def exec(self): # QDialog uses exec(), QWidget doesn't have it directly
        logger.warning("Dummy SettingsDialog exec() called.")
        return 0 # Simulate rejection

class DummyResizableRectItem(QWidget): # Not ideal, should be QGraphicsItem based
     # This dummy is problematic as it needs to be added to a QGraphicsScene
     # A better dummy might inherit QGraphicsRectItem but do nothing.
     # For now, QWidget prevents crashes but won't work visually.
    def __init__(self, rect, label, parent=None):
         super().__init__(parent) # QWidget doesn't take rect/label
         logger.warning("--- Using DUMMY ResizableRectItem (non-functional) ---")
    # Add methods expected by AnnotatorWindow/AnnotationScene if needed

class DummyTrainingDashboard(QWidget): # QDialog might be better
    def __init__(self, state, parent=None):
        super().__init__(parent)
        logger.warning("--- Using DUMMY TrainingDashboard ---")
    def exec(self):
        logger.warning("Dummy TrainingDashboard exec() called.")
        return 0
    def update_graph(self, path):
        logger.warning(f"Dummy TrainingDashboard update_graph called with path: {path}")