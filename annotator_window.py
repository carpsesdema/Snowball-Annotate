# annotator_window.py (Refactored: Dummies Moved, Graphing Update Added, Dashboard Modeless)
# (Applied fix: handle_training_run_completed passes run_dir_path to dashboard)
import logging
import os
import sys
import shutil

# --- PyQt6 Imports ---
from PyQt6.QtCore import (
    Qt, pyqtSlot, QRectF, QCoreApplication, pyqtSignal, QObject, QTimer, QUrl
)
from PyQt6.QtGui import (
    QAction, QColor, QPen, QDesktopServices, QIcon  # QIcon might be needed later
)
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog,
    QSplitter, QInputDialog, QMessageBox, QSpinBox, QGroupBox, QCheckBox, QToolButton,
    QGraphicsItem, QGraphicsScene  # Added QGraphicsScene here
)

import config

# --- State Manager Import ---
_StateManager = None
try:
    from state_manager import StateManager as _StateManager  # Import real one
    if not hasattr(_StateManager, 'add_annotation'):  # Basic check if it's real
        logging.warning(
            "Imported StateManager looks incomplete, falling back to dummy.")
        _StateManager = None  # Force fallback
    else:
        logging.info("OK: StateManager imported.")
except ImportError as e:
    logging.critical(f"FAIL: StateManager Import: {e}", exc_info=True)
    _StateManager = None
except Exception as e_sm:
    logging.critical(
        f"FAIL: Error during StateManager import/check: {e_sm}", exc_info=True)
    _StateManager = None

if _StateManager is None:
    try:
        # Ensure this matches the class name in dummy_components.py
        from dummy_components import _DummyStateManager as _StateManager
        logging.warning("Using DUMMY StateManager from dummy_components.")
    except ImportError as e_dummy_sm:
        logging.critical(
            f"CRITICAL: Failed to import even DUMMY StateManager: {e_dummy_sm}")
        # Need QApplication context for QMessageBox here, might not be available yet
        # Use print for critical startup failures before app exists.
        print(f"[CRITICAL] Cannot load StateManager or its dummy: {e_dummy_sm}")
        sys.exit(1)  # Exit if essential state management cannot be loaded

# Assign the determined class (real or dummy) to the name used in the rest of the file
StateManager = _StateManager


# --- GUI Component Import ---
_AnnotationScene = None
_AnnotatorGraphicsView = None
_SettingsDialog = None
_ResizableRectItem = None
_TrainingDashboard = None
try:
    # Try importing real GUI components
    from gui import (
        AnnotationScene as _AnnotationScene,
        AnnotatorGraphicsView as _AnnotatorGraphicsView,
        SettingsDialog as _SettingsDialog,
        ResizableRectItem as _ResizableRectItem,
        TrainingDashboard as _TrainingDashboard
    )
    # Basic check (can add more checks if needed)
    if not issubclass(_AnnotationScene, QGraphicsScene):
        logging.warning(
            "Imported AnnotationScene is not a QGraphicsScene subclass. Falling back.")
        _AnnotationScene = None  # Force fallback
    else:
        logging.info("OK: gui components imported.")

except ImportError as e_gui:
    logging.critical(f"FAIL: gui components import: {e_gui}", exc_info=True)
    # Ensure all are None if any fail
    _AnnotationScene = None
    _AnnotatorGraphicsView = None
    _SettingsDialog = None
    _ResizableRectItem = None
    _TrainingDashboard = None
except Exception as e_gui_other:
    logging.critical(
        f"FAIL: Error during GUI component import/check: {e_gui_other}", exc_info=True)
    # Ensure all are None if any fail
    _AnnotationScene = None
    _AnnotatorGraphicsView = None
    _SettingsDialog = None
    _ResizableRectItem = None
    _TrainingDashboard = None


# Fallback to dummies if real ones failed or weren't assigned
if _AnnotationScene is None:
    try:
        from dummy_components import DummyAnnotationScene as _AnnotationScene
        from dummy_components import DummyAnnotatorGraphicsView as _AnnotatorGraphicsView
        from dummy_components import DummySettingsDialog as _SettingsDialog
        from dummy_components import DummyResizableRectItem as _ResizableRectItem
        from dummy_components import DummyTrainingDashboard as _TrainingDashboard
        logging.warning("Using DUMMY GUI components from dummy_components.")
    except ImportError as e_dummy_gui:
        logging.critical(
            f"CRITICAL: Failed to import DUMMY GUI components: {e_dummy_gui}")
        print(f"[CRITICAL] Cannot load GUI components or dummies: {e_dummy_gui}")
        sys.exit(1)  # Exit if essential UI components cannot be loaded

# Assign determined classes (real or dummy) to names used later
AnnotationScene = _AnnotationScene
AnnotatorGraphicsView = _AnnotatorGraphicsView
SettingsDialog = _SettingsDialog
ResizableRectItem = _ResizableRectItem
TrainingDashboard = _TrainingDashboard

# Check ResizableRectItem specifically as it caused issues before
# Use __name__ for comparison as the class object itself might differ
if ResizableRectItem.__name__ == 'DummyResizableRectItem':
    logging.warning(
        "Assigned DummyResizableRectItem. Annotation functionality will be limited.")
# Check if the assigned ResizableRectItem is actually a QGraphicsItem subclass (important!)
elif not issubclass(ResizableRectItem, QGraphicsItem):
    logging.critical(
        f"CRITICAL: Imported ResizableRectItem ('{ResizableRectItem.__name__}') is not a QGraphicsItem subclass. Type: {type(ResizableRectItem)}")
    # Handle this critical failure - maybe force dummy or exit?
    try:
        from dummy_components import DummyResizableRectItem
        ResizableRectItem = DummyResizableRectItem  # Force dummy
        logging.critical("Forcing DummyResizableRectItem due to type mismatch.")
    except ImportError:
        print("[CRITICAL] Cannot force DummyResizableRectItem. Exiting.")
        sys.exit(1)


logger = logging.getLogger(__name__)


class AnnotatorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Snowball Annotator")
        self.setGeometry(100, 100, 1200, 800)
        self.logger = logger
        self.state = None
        self._ml_task_active = False

        self.graphics_scene = None
        self.graphics_view = None
        self.image_count_label = None
        self.annotated_count_label = None
        self.auto_box_items = []
        self.last_box_data = None
        self.training_dashboard_instance = None  # Added for tracking dashboard

        # Initialize StateManager
        try:
            # Provide default class if needed - gets class_list from StateManager itself if real
            # Dummy needs explicit list
            self.state = StateManager(class_list=["Object"])
            logger.info("StateManager initialized OK.")
        except Exception as e:
            logger.exception(
                "CRITICAL FAILURE during StateManager initialization")
            QMessageBox.critical(
                self, "StateManager Init Error", f"Could not initialize StateManager:\n{e}")
            # Fallback already handled by import logic, self.state should be the dummy here
            if not isinstance(self.state, StateManager) or StateManager.__name__ != '_DummyStateManager':
                # This case should ideally not happen if import logic is correct
                logger.critical(
                    "StateManager instance is unexpectedly not the dummy after init failure.")
                QMessageBox.critical(self, "Fatal Error",
                                     "Could not initialize any StateManager. Exiting.")
                sys.exit(1)

        # Initialize Graphics Components
        try:
            # Pass self (AnnotatorWindow) as parent
            self.graphics_scene = AnnotationScene(self)
            self.graphics_view = AnnotatorGraphicsView(
                self.graphics_scene, self)
            logger.info("Graphics Scene & View initialized OK.")
        except Exception as e:
            logger.critical(
                f"CRITICAL FAILURE during Graphics initialization: {e}", exc_info=True)
            QMessageBox.critical(
                self, "UI Init Error", f"Could not initialize graphics components:\n{e}")
            # Try to continue with dummy components if possible, otherwise exit
            if AnnotationScene.__name__ == 'DummyAnnotationScene':
                logger.warning("Falling back to dummy graphics components.")
            else:
                sys.exit(1)  # Exit if real graphics fail badly

        # Initialize UI Layout and Widgets
        try:
            self.initUI()
            # Basic checks after UI init
            if not getattr(self, 'image_count_label', None):
                logger.critical(
                    "!!! UI INIT FAILURE: image_count_label not created !!!")
            if not getattr(self, 'annotated_count_label', None):
                logger.critical(
                    "!!! UI INIT FAILURE: annotated_count_label not created !!!")
            if not getattr(self, 'export_model_action', None):
                logger.critical(
                    "!!! UI INIT FAILURE: export_model_action not created !!!")
            if not getattr(self, 'force_mini_train_button', None):
                logger.critical(
                    "!!! UI INIT FAILURE: force_mini_train_button not created !!!")
            logger.info("initUI completed.")
        except Exception as init_ui_err:
            logger.critical(
                f"CRITICAL FAILURE during initUI method: {init_ui_err}", exc_info=True)
            QMessageBox.critical(
                self, "Fatal UI Error", f"An error occurred during UI initialization:\n{init_ui_err}")
            sys.exit(1)  # Exit if UI init fails

        # Connect StateManager Signals
        if self.state:
            try:
                # Check signal existence before connecting
                if hasattr(self.state, 'task_running'):
                    self.state.task_running.connect(self.on_ml_task_running_changed)
                if hasattr(self.state, 'settings_changed'):
                    self.state.settings_changed.connect(self.handle_settings_changed)
                # Prediction signals
                if hasattr(self.state, 'prediction_progress'):
                    self.state.prediction_progress.connect(self.update_status)
                if hasattr(self.state, 'prediction_finished'):
                    self.state.prediction_finished.connect(
                        self.handle_prediction_results)
                if hasattr(self.state, 'prediction_error'):
                    self.state.prediction_error.connect(self.handle_task_error)
                # Training signals
                if hasattr(self.state, 'training_progress'):
                    self.state.training_progress.connect(self.update_status)
                if hasattr(self.state, 'training_run_completed'):
                    self.state.training_run_completed.connect(
                        self.handle_training_run_completed)  # Connect completion
                if hasattr(self.state, 'training_error'):
                    self.state.training_error.connect(self.handle_task_error)
                logger.debug(
                    "StateManager signals connected OK (or skipped missing ones).")
            except Exception as sig_err:
                logger.error(
                    f"Error connecting StateManager signals: {sig_err}", exc_info=True)
                QMessageBox.warning(
                    self, "Signal Error", f"Could not connect all StateManager signals:\n{sig_err}")
        else:
            logger.error(
                "CRITICAL: No StateManager instance available for signal connection.")

        # Initial UI State
        if hasattr(self, 'bbox_tool_button'):
            self.set_tool_active("bbox")  # Default tool
        self.update_status("Ready. Load directory or session.")
        self._update_image_count_label()
        self._update_annotated_count_label()
        # Set initial enabled states based on whether a task might be running (should be false)
        self.on_ml_task_running_changed(self.state.is_task_active(
        ) if self.state and hasattr(self.state, 'is_task_active') else False)

        # Set initial confidence value if possible
        if self.state:
            try:
                conf_key = config.SETTING_KEYS.get("confidence_threshold")
                conf_default = config.DEFAULT_CONFIDENCE_THRESHOLD
                # Use getattr for safety, check if key exists
                conf = self.state.get_setting(conf_key, conf_default) if conf_key and hasattr(
                    self.state, 'get_setting') else conf_default
                if hasattr(self, 'confidence_spinbox'):
                    # Ensure value is within spinbox range before setting
                    conf_percent = int(conf * 100)
                    min_val = self.confidence_spinbox.minimum()
                    max_val = self.confidence_spinbox.maximum()
                    clamped_val = max(min_val, min(conf_percent, max_val))
                    self.confidence_spinbox.setValue(clamped_val)
            except Exception as e:
                logger.error(f"Failed to set initial confidence spinbox value: {e}")

        # Clear image if none loaded
        if isinstance(self.graphics_scene, AnnotationScene):  # Check if it's the real one
            current_img_exists = False
            if self.state and hasattr(self.state, 'get_current_image'):
                current_img_exists = bool(self.state.get_current_image())

            if not current_img_exists:
                try:
                    self.graphics_scene.set_image(None)
                except Exception as clear_err:
                    logger.error(
                        f"Error initially clearing graphics scene: {clear_err}")
        elif AnnotationScene.__name__ == 'DummyAnnotationScene':
            logger.warning("Skipping initial scene clear - using dummy scene.")

        logger.info("AnnotatorWindow initialization complete.")
        print("--- AnnotatorWindow Initialized ---")

    # --- Methods ---

    def set_enabled_safe(self, widget_attr_name, enabled_state):
        """Safely sets the enabled state of a widget attribute."""
        widget = getattr(self, widget_attr_name, None)
        if widget and hasattr(widget, 'setEnabled'):
            try:
                widget.setEnabled(enabled_state)
            except Exception as e:
                logger.error(f"Error setting enabled state for {widget_attr_name}: {e}")

    def _update_image_count_label(self):
        """Updates the image count label (e.g., 'Image 5 / 100')."""
        count_label = getattr(self, "image_count_label", None)
        if not count_label:
            return

        current_num_str, total_num_str = "-", "-"
        if self.state and hasattr(self.state, "image_list") and self.state.image_list is not None:
            try:
                total_num = len(self.state.image_list)
                total_num_str = str(total_num)
                if hasattr(self.state, "current_index") and isinstance(self.state.current_index, int) and 0 <= self.state.current_index < total_num:
                    current_num_str = str(self.state.current_index + 1)
                else:
                    current_num_str = "0" if total_num == 0 else "?"
            except TypeError:
                logger.warning("State.image_list is not iterable for count label.")
                total_num_str = "Err"
            except Exception as e:
                logger.error(f"Error updating image count label state access: {e}")
                total_num_str = "Err"

        is_dummy = StateManager.__name__ == '_DummyStateManager'
        label_text = f"Image {current_num_str} / {total_num_str}"
        if is_dummy:
            label_text += " (Dummy)"

        count_label.setText(label_text)

    def _update_annotated_count_label(self):
        """Updates the annotated count label (e.g., 'Annotated: 25')."""
        count_label = getattr(self, "annotated_count_label", None)
        if not count_label:
            return

        annotated_num_str = "-"
        if self.state and hasattr(self.state, "approved_count"):
            is_dummy = StateManager.__name__ == '_DummyStateManager'
            if is_dummy:
                annotated_num_str = f"{self.state.approved_count} (Dummy)"
            else:
                try:
                    count_val = self.state.approved_count
                    if isinstance(count_val, int):
                        annotated_num_str = str(count_val)
                    elif count_val is None:
                        annotated_num_str = "0"
                        logger.debug("state.approved_count was None, displaying '0'.")
                    else:
                        annotated_num_str = "Invalid"
                        logger.warning(
                            f"Unexpected type for state.approved_count: {type(count_val)}")
                except AttributeError:
                    annotated_num_str = "Error"
                    logger.error(
                        "Attribute 'approved_count' not found on StateManager instance.")
                except Exception as e:
                    annotated_num_str = "Error"
                    logger.error(
                        f"Error accessing state.approved_count: {e}", exc_info=True)

        count_label.setText(f"Annotated: {annotated_num_str}")

    def initUI(self):
        """Initializes the main UI layout and widgets."""
        print("--- Starting initUI ---")
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)

        # --- Left Panel Setup ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        # --- Controls Group ---
        controls_group = QGroupBox("Controls")
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setContentsMargins(5, 8, 5, 8)
        controls_layout.setSpacing(5)

        # --- Tools Group (BBox button) ---
        tool_group = QGroupBox("Tools")
        tool_layout = QHBoxLayout(tool_group)
        tool_layout.setContentsMargins(5, 5, 5, 5)
        tool_layout.setSpacing(6)
        self.bbox_tool_button = QToolButton()
        self.bbox_tool_button.setText("Draw BBox")
        self.bbox_tool_button.setCheckable(True)
        self.bbox_tool_button.setChecked(True)
        self.bbox_tool_button.setToolTip(
            "Select to draw bounding boxes (Double-click box to change class, 'C' to copy last box)")
        self.bbox_tool_button.clicked.connect(lambda: self.set_tool_active("bbox"))
        tool_layout.addWidget(self.bbox_tool_button)
        controls_layout.addWidget(tool_group)

        # --- Main Buttons Stack ---
        btn_stack_widget = QWidget()
        btn_stack_layout = QVBoxLayout(btn_stack_widget)
        btn_stack_layout.setContentsMargins(0, 0, 0, 0)
        btn_stack_layout.setSpacing(8)

        self.load_button = QPushButton("Load Image Directory")
        self.load_button.setToolTip("Load all images from a selected folder")
        self.load_button.clicked.connect(self.load_directory)
        btn_stack_layout.addWidget(self.load_button)

        self.load_session_button = QPushButton("Load Session")
        self.load_session_button.setToolTip(
            "Load a previously saved annotation session (.json)")
        self.load_session_button.clicked.connect(self.load_session_explicitly)
        btn_stack_layout.addWidget(self.load_session_button)

        self.save_session_button = QPushButton("Save Session")
        self.save_session_button.setToolTip(
            "Save current annotations and image list")
        self.save_session_button.clicked.connect(self.save_session)
        btn_stack_layout.addWidget(self.save_session_button)

        nav_layout = QHBoxLayout()
        self.prev_button = QPushButton("Previous")
        self.prev_button.setToolTip("Go to the previous image")
        self.prev_button.clicked.connect(self.prev_image)
        nav_layout.addWidget(self.prev_button)
        self.next_button = QPushButton("Next")
        self.next_button.setToolTip("Go to the next image")
        self.next_button.clicked.connect(self.next_image)
        nav_layout.addWidget(self.next_button)
        btn_stack_layout.addLayout(nav_layout)

        self.manage_classes_button = QPushButton("Manage Classes")
        self.manage_classes_button.setToolTip(
            "Add, remove, or rename annotation classes")
        self.manage_classes_button.clicked.connect(self.manage_classes)
        btn_stack_layout.addWidget(self.manage_classes_button)

        self.force_mini_train_button = QPushButton("Force Mini-Train")
        self.force_mini_train_button.setToolTip(
            "Manually trigger training using the '20 image' parameters (requires >0 approved images)")
        self.force_mini_train_button.clicked.connect(self.force_mini_training)
        btn_stack_layout.addWidget(self.force_mini_train_button)

        self.training_dashboard_button = QPushButton("Training Dashboard")
        self.training_dashboard_button.setToolTip(
            "Open the training dashboard to view stats and graphs.")
        self.training_dashboard_button.clicked.connect(self.open_training_dashboard)
        btn_stack_layout.addWidget(self.training_dashboard_button)

        controls_layout.addWidget(btn_stack_widget)
        left_layout.addWidget(controls_group)

        # --- Info Labels ---
        self.image_count_label = QLabel("Image - / -")
        self.image_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.image_count_label)
        self.annotated_count_label = QLabel("Annotated: -")
        self.annotated_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.annotated_count_label)

        # --- Auto Annotation Group ---
        auto_group = QGroupBox("Auto Annotation")
        auto_layout = QVBoxLayout(auto_group)
        auto_layout.setContentsMargins(5, 8, 5, 8)
        auto_layout.setSpacing(5)
        self.auto_box_button = QCheckBox("Show Suggestions")
        self.auto_box_button.setToolTip(
            "Show AI-generated bounding box suggestions (if model is trained)")
        self.auto_box_button.toggled.connect(self.toggle_auto_boxes)
        auto_layout.addWidget(self.auto_box_button)

        conf_layout = QHBoxLayout()
        conf_layout.addWidget(QLabel("Confidence:"))
        self.confidence_spinbox = QSpinBox()
        self.confidence_spinbox.setRange(0, 100)
        self.confidence_spinbox.setSuffix("%")
        self.confidence_spinbox.setToolTip(
            "Minimum confidence for suggestions (0-100%)")
        try:
            default_conf = config.DEFAULT_CONFIDENCE_THRESHOLD
            self.confidence_spinbox.setValue(int(default_conf * 100))
        except Exception as e:
            logger.error(f"Error setting default confidence spinbox value: {e}")
            self.confidence_spinbox.setValue(25)
        conf_layout.addWidget(self.confidence_spinbox)
        auto_layout.addLayout(conf_layout)
        left_layout.addWidget(auto_group)

        left_layout.addStretch(1)

        # --- Graphics View Setup ---
        if not self.graphics_view:
            logger.critical("!!! graphics_view is None during initUI !!!")
            # Create a dummy widget to avoid crashing the layout if view init failed
            self.graphics_view = QWidget()
            QMessageBox.critical(
                self, "UI Error", "Graphics view component failed to initialize correctly.")
        else:
            self.graphics_view.setMinimumWidth(400)

        # --- Splitter Setup ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.graphics_view)
        splitter.setStretchFactor(0, 0) # Left panel fixed size initially
        splitter.setStretchFactor(1, 1) # Graphics view takes available space
        splitter.setSizes([260, 640]) # Initial size distribution

        # --- Bottom Layout (Approve Button) ---
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch(1)
        self.approve_button = QPushButton("Approve && Next Unannotated")
        self.approve_button.setStyleSheet(
            "background-color: lightgreen; padding: 5px; font-weight: bold;")
        self.approve_button.setToolTip(
            "Mark current image annotations as reviewed and move to the next unannotated image")
        self.approve_button.clicked.connect(self.approve_image)
        bottom_layout.addWidget(self.approve_button)

        # --- Add Major Components to Main Layout ---
        main_layout.addWidget(splitter, 1) # Splitter takes most space
        main_layout.addLayout(bottom_layout)

        self.setCentralWidget(central_widget)

        # --- Status Bar ---
        self.status_bar = self.statusBar()
        self.status_label = QLabel("Initializing...")
        self.status_bar.addWidget(self.status_label)

        # --- Menu Bar ---
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")

        self.load_dir_action = QAction("Load Directory", self)
        self.load_dir_action.setShortcut("Ctrl+O")
        self.load_dir_action.triggered.connect(self.load_directory)
        file_menu.addAction(self.load_dir_action)

        self.load_sess_action = QAction("Load Session", self)
        self.load_sess_action.setShortcut("Ctrl+L")
        self.load_sess_action.triggered.connect(self.load_session_explicitly)
        file_menu.addAction(self.load_sess_action)

        self.save_sess_action = QAction("Save Session", self)
        self.save_sess_action.setShortcut("Ctrl+S")
        self.save_sess_action.triggered.connect(self.save_session)
        file_menu.addAction(self.save_sess_action)

        file_menu.addSeparator()

        self.export_model_action = QAction("Export Trained Model...", self)
        self.export_model_action.setToolTip(
            "Save the latest trained model (.pt) to a location of your choice")
        self.export_model_action.triggered.connect(self.export_model)
        file_menu.addAction(self.export_model_action)

        self.export_data_action = QAction("Export Annotated Data (YOLO)...", self)
        self.export_data_action.setToolTip(
            "Export approved annotations and images in YOLO format to a folder")
        self.export_data_action.triggered.connect(self.export_annotated_data)
        file_menu.addAction(self.export_data_action)

        file_menu.addSeparator()

        self.settings_action = QAction("Legacy Settings...", self)
        self.settings_action.triggered.connect(self.open_settings_dialog)
        file_menu.addAction(self.settings_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        print("--- Finished initUI ---")

    def set_tool_active(self, tool_name):
        """Sets the active tool in the graphics scene."""
        logger.debug(f"Set tool requested: {tool_name}")
        scene = getattr(self, "graphics_scene", None)
        if isinstance(scene, AnnotationScene) and hasattr(scene, 'set_tool'):
            if tool_name == "bbox":
                scene.set_tool(tool_name)
                btn = getattr(self, "bbox_tool_button", None)
                if btn and not btn.isChecked():
                    btn.setChecked(True) # Ensure button state matches
                self.update_status("Tool: Draw BBox")
            # Add other tools here if needed
            # elif tool_name == "other_tool":
            #    scene.set_tool(tool_name)
            #    # Update button states
            #    self.update_status("Tool: Other Tool")
            else:
                logger.warning(
                    f"Unhandled tool name: {tool_name}, reverting to 'bbox'.")
                scene.set_tool("bbox")
                btn = getattr(self, "bbox_tool_button", None)
                if btn and not btn.isChecked():
                    btn.setChecked(True)
                self.update_status("Tool: Reverted to BBox Tool")
        else:
            logger.error(
                f"Cannot set tool: Graphics scene is invalid or dummy ({type(scene)}).")
            # Ensure button state reflects failure
            btn = getattr(self, "bbox_tool_button", None)
            if btn:
                btn.setChecked(False)


    def paste_last_box(self):
        """Pastes the last approved bounding box onto the center of the current image."""
        logger.debug("Paste last box requested (centered).")
        scene = getattr(self, "graphics_scene", None)

        # Check if scene is valid and has an image displayed
        scene_is_valid = isinstance(scene, AnnotationScene) and hasattr(scene, 'image_item') \
            and scene.image_item and not scene.image_item.pixmap().isNull()

        if self.last_box_data and scene_is_valid:
            try:
                # Get data stored during approve_image
                stored_rect_scene_coords = self.last_box_data.get("rect")
                class_label = self.last_box_data.get("class")

                # Validate stored data structure
                if not isinstance(stored_rect_scene_coords, QRectF) or not class_label:
                    logger.warning(
                        "Invalid last_box_data structure for pasting (expected scene QRectF).")
                    self.update_status("Paste failed: Invalid stored data.")
                    return

                # Validate stored size
                width = stored_rect_scene_coords.width()
                height = stored_rect_scene_coords.height()
                if width <= 0 or height <= 0:
                    logger.warning(
                        f"Invalid size in last_box_data for pasting: {width}x{height}")
                    self.update_status("Paste failed: Invalid stored size.")
                    return
                logger.debug(
                    f"--- Paste Debug: Stored Size = {width}x{height}, Class = {class_label}")

                # Get current image boundaries in scene coordinates
                current_scene_rect = scene.image_item.sceneBoundingRect()
                logger.debug(
                    f"--- Paste Debug: Current Image Scene Rect = {current_scene_rect}")
                if not current_scene_rect.isValid() or current_scene_rect.isEmpty():
                    logger.warning(
                        "Cannot paste: Current scene rectangle is invalid or empty.")
                    self.update_status("Paste failed: Scene invalid.")
                    return

                # Calculate center position
                center_x = current_scene_rect.center().x()
                center_y = current_scene_rect.center().y()
                logger.debug(
                    f"--- Paste Debug: Scene Center = ({center_x}, {center_y})")

                # Calculate desired top-left based on center and stored size
                paste_x = center_x - (width / 2.0)
                paste_y = center_y - (height / 2.0)
                logger.debug(
                    f"--- Paste Debug: Calculated Top-Left (Pre-Clamp) = ({paste_x}, {paste_y})")

                # Clamp the position to stay within the image boundaries
                paste_x_clamped = max(current_scene_rect.left(), min(
                    paste_x, current_scene_rect.right() - width))
                paste_y_clamped = max(current_scene_rect.top(), min(
                    paste_y, current_scene_rect.bottom() - height))
                # Re-clamp just in case width/height calculation pushed it slightly out
                paste_x_clamped = max(current_scene_rect.left(), paste_x_clamped)
                paste_y_clamped = max(current_scene_rect.top(), paste_y_clamped)


                logger.debug(
                    f"--- Paste Debug: Calculated Top-Left (Post-Clamp) = ({paste_x_clamped}, {paste_y_clamped})")

                # Create the new rectangle in scene coordinates
                new_rect_scene = QRectF(paste_x_clamped, paste_y_clamped, width, height)
                logger.debug(
                    f"--- Paste Debug: Final New Scene Rect for Item = {new_rect_scene}")

                # Ensure we have the correct class for the rectangle item
                rect_item_class = ResizableRectItem
                if rect_item_class.__name__ == 'DummyResizableRectItem':
                    logger.error(
                        "Cannot paste: ResizableRectItem class is the dummy (likely import error).")
                    self.update_status("Paste failed: Internal UI error.")
                    return

                # Create and add the item
                item = rect_item_class(new_rect_scene, class_label)
                scene.addItem(item)
                logger.info(
                    f"Pasted box: {class_label} at scene coords {new_rect_scene}")

                # Optionally select the new item
                item.setSelected(True)
                self.update_status(f"Pasted box: {class_label} (centered)")

            except Exception as e:
                logger.error(f"Error pasting last box: {e}", exc_info=True)
                self.update_status("Paste failed.")
        elif not self.last_box_data:
            logger.warning("Paste last box failed: No box data stored.")
            self.update_status("Paste failed: No previous box.")
        else: # Scene not valid
            logger.warning("Paste last box failed: Scene or image not ready.")
            self.update_status("Paste failed: Load image first.")


    def open_settings_dialog(self):
        """Opens the legacy settings dialog."""
        is_dummy_state = StateManager.__name__ == '_DummyStateManager'
        if not self.state or is_dummy_state:
            QMessageBox.warning(
                self, "Error", "Settings unavailable (State Manager missing or dummy).")
            return

        dlg_class = SettingsDialog
        if dlg_class.__name__ == 'DummySettingsDialog':
            QMessageBox.warning(
                self, "UI Error", "SettingsDialog unavailable (using dummy component).")
            return

        try:
            # Pass the state manager and parent window
            dlg = dlg_class(self.state, self)
            dlg.exec() # Blocks until dialog is closed
        except Exception as e:
            logger.exception("Legacy Settings dialog failed to open or execute")
            QMessageBox.critical(self, "Dialog Error",
                                 f"Error opening legacy settings:\n{e}")


    def open_training_dashboard(self):
        """Opens the training dashboard dialog non-modally."""
        is_dummy_state = StateManager.__name__ == '_DummyStateManager'
        if not self.state or is_dummy_state:
            QMessageBox.warning(
                self, "Error", "Dashboard unavailable (State Manager missing or dummy).")
            return

        dashboard_class = TrainingDashboard
        if dashboard_class.__name__ == 'DummyTrainingDashboard':
            QMessageBox.warning(
                self, "Error", "Dashboard unavailable (using dummy component).")
            return

        # Check if an instance already exists
        if self.training_dashboard_instance is not None:
            logger.info("Training dashboard already open. Activating.")
            self.training_dashboard_instance.raise_() # Bring to front
            self.training_dashboard_instance.activateWindow() # Give focus
            return

        # Create and show the dashboard
        try:
            dlg = dashboard_class(self.state, self) # Pass state manager and parent
            self.training_dashboard_instance = dlg # Store reference
            # Connect finished signal to clear the instance reference when closed
            dlg.finished.connect(self.clear_dashboard_instance)
            dlg.show() # Show non-modally
        except Exception as e:
            logger.exception("Training dashboard failed to open or show")
            QMessageBox.critical(self, "Dialog Error",
                                 f"Error opening training dashboard:\n{e}")
            self.training_dashboard_instance = None # Ensure cleared on error

    @pyqtSlot()
    def clear_dashboard_instance(self):
        """Slot called when the training dashboard dialog is closed."""
        logger.debug("Training dashboard closed, clearing instance reference.")
        self.training_dashboard_instance = None


    def export_model(self):
        print("--- export_model called ---")
        is_dummy_state = StateManager.__name__ == '_DummyStateManager'
        if not self.state or is_dummy_state:
            QMessageBox.warning(
                self, "Error", "Export unavailable (State Manager missing or dummy).")
            return

        # Get the configured internal path for the trained model
        model_key = config.SETTING_KEYS.get("model_save_path")
        if not model_key:
            QMessageBox.critical(self, "Config Error", "Model save path key missing.")
            return

        internal_model_path = self.state.get_setting(
            model_key, config.DEFAULT_MODEL_SAVE_PATH)
        logger.debug(f"Checking for internal model at: {internal_model_path}")

        # Check if the model file actually exists
        if not internal_model_path or not os.path.exists(internal_model_path):
            QMessageBox.warning(self, "Model Not Found",
                                f"Trained model not found:\n{internal_model_path}\n\n"
                                "Train the model at least once.")
            logger.warning(
                f"Export failed: Model file not found at {internal_model_path}")
            return

        # Suggest a filename and location for saving
        default_filename = os.path.basename(internal_model_path)
        start_dir = os.path.expanduser("~") # Start in user's home directory
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save Trained Model As...", os.path.join(start_dir, default_filename),
            "PyTorch Model (*.pt)"
        )

        # If user selected a path, copy the file
        if save_path:
            # Ensure correct extension
            if not save_path.lower().endswith(".pt"):
                save_path += ".pt"
            try:
                self.update_status(
                    f"Exporting model to {os.path.basename(save_path)}...")
                QCoreApplication.processEvents() # Update UI
                shutil.copy2(internal_model_path, save_path) # Use copy2 to preserve metadata
                self.update_status(f"Model exported: {os.path.basename(save_path)}.")
                logger.info(f"Model exported from {internal_model_path} to {save_path}")
                # Ask user if they want to open the containing folder
                reply = QMessageBox.question(self, "Export Complete",
                                             f"Model exported successfully to:\n{os.path.dirname(save_path)}\n\n"
                                             "Open this folder?",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                             QMessageBox.StandardButton.No)
                if reply == QMessageBox.StandardButton.Yes:
                    QDesktopServices.openUrl(
                        QUrl.fromLocalFile(os.path.dirname(save_path)))
            except Exception as e:
                logger.exception(f"Failed to export model to {save_path}")
                QMessageBox.critical(self, "Export Error",
                                     f"Failed to copy model file:\n{e}")
                self.update_status("Model export failed.")
        else:
            self.update_status("Model export cancelled.")
            logger.info("Model export cancelled by user.")

    def export_annotated_data(self):
        print("--- export_annotated_data called ---")
        is_dummy_state = StateManager.__name__ == '_DummyStateManager'
        if not self.state or is_dummy_state:
            QMessageBox.warning(
                self, "Error", "Export unavailable (State Manager missing or dummy).")
            return
        # Check if the required method exists on the state manager
        if not hasattr(self.state, 'export_data_for_yolo'):
            QMessageBox.critical(self, "Internal Error",
                                 "State Manager missing 'export_data_for_yolo' method.")
            logger.error("Export failed: StateManager missing 'export_data_for_yolo'.")
            return

        # Check if there's any approved data to export
        approved_exists = False
        if hasattr(self.state, 'annotations') and isinstance(self.state.annotations, dict):
             # Check if any value in the annotations dict has 'approved': True
             approved_exists = any(d.get("approved", False) for d in self.state.annotations.values())

        if not approved_exists:
            QMessageBox.information(
                self, "No Data", "No approved annotations available to export.")
            logger.info("Data export cancelled: No approved annotations.")
            return

        # Get last used directory as starting point for dialog
        last_img_dir_key = config.SETTING_KEYS.get("last_image_dir")
        start_dir = self.state.get_setting(last_img_dir_key, os.path.expanduser(
            "~")) if last_img_dir_key else os.path.expanduser("~")
        start_dir = start_dir if os.path.isdir(start_dir) else os.path.expanduser("~") # Fallback if saved path invalid

        # Ask user to select an *existing* directory
        export_dir = QFileDialog.getExistingDirectory(
            self, "Select Directory to Export YOLO Data Into", start_dir
        )

        if export_dir:
            logger.info(f"User selected directory for YOLO export: {export_dir}")

            # Check if directory is empty and warn if not
            try:
                if os.listdir(export_dir):
                    reply = QMessageBox.warning(
                        self, "Directory Not Empty",
                        f"Directory is not empty:\n{export_dir}\n"
                        "Exporting will create/overwrite 'images', 'labels', 'dataset.yaml'.\n\nContinue?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                        QMessageBox.StandardButton.Cancel
                    )
                    if reply == QMessageBox.StandardButton.Cancel:
                        self.update_status("Data export cancelled.")
                        logger.info("Data export cancelled by user (non-empty dir).")
                        return
            except OSError as e:
                QMessageBox.critical(
                    self, "Directory Error", f"Cannot access directory:\n{export_dir}\nError: {e}")
                return

            # Call the state manager's export method
            try:
                self.update_status(
                    f"Exporting YOLO data to {os.path.basename(export_dir)}...")
                QCoreApplication.processEvents() # Update UI

                # State manager handles the actual export process
                yaml_path = self.state.export_data_for_yolo(export_dir)

                if yaml_path and os.path.exists(yaml_path):
                    self.update_status(
                        f"YOLO data exported: {os.path.basename(export_dir)}.")
                    logger.info(
                        f"YOLO data export successful. Target: {export_dir}, YAML: {yaml_path}")
                    # Ask to open folder
                    reply = QMessageBox.question(self, "Export Complete",
                                                 f"Data exported to:\n{export_dir}\n\nOpen folder?",
                                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                                 QMessageBox.StandardButton.No)
                    if reply == QMessageBox.StandardButton.Yes:
                        QDesktopServices.openUrl(QUrl.fromLocalFile(export_dir))
                else:
                    # State manager method returned None or invalid path
                    logger.error(
                        f"Data export process failed (StateManager returned: {yaml_path}). Check logs.")
                    QMessageBox.warning(self, "Export Failed",
                                        "Failed to export data. Check application logs (app_debug.log).")
                    self.update_status("Data export failed.")

            except Exception as e:
                logger.exception(f"Unexpected error during data export to {export_dir}")
                QMessageBox.critical(self, "Export Error",
                                     f"Unexpected error during data export:\n{e}")
                self.update_status("Data export failed.")
        else:
            # User cancelled the directory selection dialog
            self.update_status("Data export cancelled.")
            logger.info("Data export cancelled by user (no directory selected).")


    @pyqtSlot()
    def force_mini_training(self):
        logger.info("Force mini-training requested by user.")
        is_dummy_state = StateManager.__name__ == '_DummyStateManager'
        if not self.state or is_dummy_state:
            QMessageBox.warning(
                self, "Error", "Training unavailable (State Manager missing or dummy).")
            return
        # Prevent starting if another task is active
        if self.state.is_task_active():
            QMessageBox.warning(
                self, "Busy", "Another background task is currently running.")
            return

        # Get current approved count robustly
        current_approved_count = 0
        if hasattr(self.state, 'approved_count'):
             current_approved_count = self.state.approved_count
        elif hasattr(self.state, 'annotations'):
             # Fallback: count manually if property doesn't exist
             current_approved_count = sum(1 for d in self.state.annotations.values() if d.get("approved"))

        if current_approved_count <= 0:
            QMessageBox.information(
                self, "No Data", "Cannot force training without approved images.")
            logger.warning("Force training aborted: No approved images.")
            return

        try:
            # Get training parameters from settings
            epochs_key = config.SETTING_KEYS.get("epochs_20")
            lr_key = config.SETTING_KEYS.get("lr_20")
            if not epochs_key or not lr_key:
                QMessageBox.critical(
                    self, "Config Error", "Training param keys ('epochs_20', 'lr_20') missing.")
                logger.error("Force training failed: Config keys missing.")
                return

            epochs = self.state.get_setting(epochs_key, config.DEFAULT_EPOCHS_20)
            lr = self.state.get_setting(lr_key, config.DEFAULT_LR_20)
            prefix = "force_mini" # Specific prefix for forced runs

            # Confirm with user
            reply = QMessageBox.question(
                self, "Confirm Training",
                f"Start mini-training run with:\n"
                f"- Epochs: {epochs}\n"
                f"- Learning Rate: {lr:.6f}\n"
                f"Using {current_approved_count} approved image(s).\n\nProceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Cancel:
                self.update_status("Forced training cancelled.")
                logger.info("User cancelled forced mini-training.")
                return

            self.update_status(
                f"Starting forced mini-training ({epochs} epochs, LR {lr:.6f})...")
            QCoreApplication.processEvents() # Update UI

            # Check for the start method
            if not hasattr(self.state, 'start_training_task'):
                 logger.error("State manager missing 'start_training_task' method.")
                 QMessageBox.critical(self, "Internal Error",
                                      "Cannot start training task.")
                 self.update_status("Error starting forced training.")
                 return

            # Call the state manager to start the task
            success = self.state.start_training_task(epochs, lr, prefix)

            if not success:
                 # start_training_task might return False if task couldn't be started
                 self.update_status("Failed to start forced training task.")
                 logger.warning(
                     "state.start_training_task returned False for forced run.")
                 # State manager should handle emitting task_running(False) if it fails early

        except Exception as e:
            logger.exception("Error initiating forced mini-training.")
            QMessageBox.critical(
                self, "Error", f"Could not start forced training:\n{e}")
            self.update_status("Error starting forced training.")


    @pyqtSlot()
    def handle_settings_changed(self):
        """Update relevant UI elements when settings change."""
        logger.info("GUI: Settings changed signal received.")
        is_dummy_state = StateManager.__name__ == '_DummyStateManager'
        if self.state and not is_dummy_state:
            try:
                # Update confidence spinbox
                spin = getattr(self, "confidence_spinbox", None)
                if spin:
                    conf_key = config.SETTING_KEYS.get("confidence_threshold")
                    conf_default = config.DEFAULT_CONFIDENCE_THRESHOLD
                    conf = self.state.get_setting(
                        conf_key, conf_default) if conf_key else conf_default
                    # Block signals temporarily to prevent loops if spinbox change triggers setting change
                    spin.blockSignals(True)
                    conf_percent = int(conf * 100)
                    min_val, max_val = spin.minimum(), spin.maximum()
                    clamped_val = max(min_val, min(conf_percent, max_val))
                    spin.setValue(clamped_val)
                    spin.blockSignals(False)
                    logger.debug(
                        f"Updated confidence spinbox from settings to {clamped_val}%")

                # Update enabled state of ML controls based on pipeline availability
                pipeline_ok = hasattr(self.state, 'training_pipeline') and bool(
                    self.state.training_pipeline)
                blocking_task_active = self.state.is_task_active() if hasattr(
                    self.state, 'is_task_active') else False
                enable_ml_controls = pipeline_ok and not blocking_task_active

                self.set_enabled_safe("auto_box_button", enable_ml_controls)
                # Confidence spinbox only enabled if suggestions are possible AND check box is checked
                self.set_enabled_safe(
                    "confidence_spinbox", enable_ml_controls and self.auto_box_button.isChecked())

                # Update status bar message
                status_msg = "Settings updated."
                if not pipeline_ok:
                    status_msg += " Warning: ML Pipeline may be unavailable."
                self.update_status(status_msg)

                # Potentially update other UI elements if needed based on settings

            except Exception as e:
                logger.error(
                    f"Error applying settings changes to UI: {e}", exc_info=True)
        else:
            logger.warning(
                "Cannot apply settings changes to UI: State Manager unavailable or dummy.")

    @pyqtSlot(str)
    def update_status(self, message: str):
        """Updates the status bar label."""
        lbl = getattr(self, "status_label", None)
        if lbl:
            try:
                # Ensure message is a string
                lbl.setText(str(message) if message is not None else "")
                # Process events briefly to ensure UI updates, especially for longer tasks
                QCoreApplication.processEvents()
            except Exception as e:
                # Avoid crashing if status update fails
                logger.error(f"Failed to update status label: {e}")

        # Log status updates differently based on content
        lower_msg = str(message).lower() if message else ""
        is_progress_update = any(k in lower_msg for k in [
                                 "predict", "update", "train", "loading", "saving", "requesting", "checking", "navigat", "starting", "exporting"])
        is_final_state = any(k in lower_msg for k in ["complete", "error", "fail", "approved",
                             "loaded", "saved", "ready", "found", "unavailable", "cancelled", "exported", "finished", "unchanged"])

        # Log progress updates at DEBUG, final states or general info at INFO
        if is_progress_update and not is_final_state:
            logger.debug(f"Status Update: {message}")
        else:
            logger.info(f"Status Update: {message}")


    def load_directory(self):
        """Opens dialog to select image directory and loads images via StateManager."""
        if self.state and hasattr(self.state, 'is_task_active') and self.state.is_task_active():
            QMessageBox.warning(self, "Busy", "Background task running. Please wait.")
            return

        is_dummy_state = StateManager.__name__ == '_DummyStateManager'
        if not self.state: # Check if state exists at all
             QMessageBox.warning(self, "Error", "State Manager not available.")
             return
        elif is_dummy_state: # State exists but is dummy
             logger.info("Using dummy state manager for load directory.")
             # Allow dummy load to proceed for UI testing if desired

        # Get last used directory from settings
        last_dir_key = config.SETTING_KEYS.get("last_image_dir")
        last_dir = self.state.get_setting(last_dir_key, os.path.expanduser(
            "~")) if last_dir_key else os.path.expanduser("~")
        last_dir = last_dir if os.path.isdir(last_dir) else os.path.expanduser("~") # Fallback

        # Open directory dialog
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Image Directory", last_dir)

        if dir_path and self.state: # Check state again just in case
            # Save selected directory path to settings
            if last_dir_key and hasattr(self.state, 'set_setting'):
                try:
                    self.state.set_setting(last_dir_key, dir_path)
                except Exception as e_set:
                    logger.error(f"Failed to save last image directory setting: {e_set}")

            self.update_status(f"Loading images from: {os.path.basename(dir_path)}...")
            QCoreApplication.processEvents() # Show status update

            # Ask state manager to load images
            try:
                if hasattr(self.state, 'load_images_from_directory'):
                    self.state.load_images_from_directory(dir_path)
                    logger.info("StateManager finished loading images from directory.")
                else:
                    logger.error("State manager missing 'load_images_from_directory'.")
                    raise AttributeError("Missing load method in state manager.")
            except Exception as e:
                logger.exception("Failed during StateManager.load_images_from_directory")
                QMessageBox.critical(self, "Load Error", f"Failed to process directory contents:\n{e}")
                self.update_status("Directory load error.")
                self.clear_ui_on_load_failure() # Reset UI
                return

            # Check if images were loaded and update UI
            current_image_list = getattr(self.state, 'image_list', [])
            if current_image_list:
                current_index = getattr(self.state, 'current_index', -1)
                # Ensure index is valid after load
                if not (isinstance(current_index, int) and 0 <= current_index < len(current_image_list)):
                    logger.warning("Index invalid after load, resetting to 0.")
                    if hasattr(self.state, 'go_to_image'): self.state.go_to_image(0)
                self.load_image() # Load the first/current image into the view
                self._update_annotated_count_label() # Update counts
                self.update_status(f"Loaded {len(current_image_list)} images from {os.path.basename(dir_path)}.")
            else:
                # No images found or loaded
                self.clear_ui_on_load_failure() # Clear graphics view etc.
                self.update_status("No supported image files found.")
                QMessageBox.information(self, "No Images", "No supported images found in the selected directory.")
        elif not dir_path:
            # User cancelled the dialog
            self.update_status("Load directory cancelled.")
            logger.info("User cancelled loading directory.")


    def clear_ui_on_load_failure(self):
        """Clears image display and resets counts when loading fails or finds no images."""
        logger.debug("Clearing UI due to load failure or empty list.")
        scene = getattr(self, "graphics_scene", None)
        if isinstance(scene, AnnotationScene):
            scene.set_image(None) # Clear image in scene
            scene.clear_annotations() # Remove any previous boxes
        self.clear_suggestion_boxes() # Remove suggestion boxes
        self.setWindowTitle("Annotator") # Reset title
        self._update_image_count_label() # Reset image count display
        self._update_annotated_count_label() # Reset annotated count display
        self.last_box_data = None # Clear last pasted box data


    def load_session_explicitly(self):
        """Opens dialog to select session file and loads via StateManager."""
        if self.state and hasattr(self.state, 'is_task_active') and self.state.is_task_active():
            QMessageBox.warning(self, "Busy", "Background task running.")
            return

        is_dummy_state = StateManager.__name__ == '_DummyStateManager'
        if not self.state:
             QMessageBox.warning(self, "Error", "State Manager unavailable.")
             return
        elif is_dummy_state:
             logger.info("Using dummy state manager for load session.")
             # Allow dummy load for UI testing

        # Determine starting path for dialog
        session_key = config.SETTING_KEYS.get("session_path")
        start_path = self.state.get_setting(
            session_key, config.DEFAULT_SESSION_PATH) if session_key else config.DEFAULT_SESSION_PATH
        start_dir = os.path.dirname(start_path) if start_path and os.path.dirname(start_path) else "."
        start_dir = start_dir if os.path.isdir(start_dir) else os.path.expanduser("~") # Fallback

        # Define file filter
        session_ext = os.path.splitext(config.DEFAULT_SESSION_FILENAME)[1]
        file_filter = f"Session Files (*{session_ext});;All Files (*)"
        # Open file dialog
        file_path, _ = QFileDialog.getOpenFileName(self, "Load Session", start_dir, file_filter)

        if file_path:
            self.update_status(f"Loading session: {os.path.basename(file_path)}...")
            QCoreApplication.processEvents() # Show status update
            load_ok = False
            try:
                if hasattr(self.state, 'load_session'):
                    # StateManager handles the actual loading
                    load_ok = self.state.load_session(file_path=file_path)
                else:
                    logger.error("State manager missing 'load_session' method.")
                    raise AttributeError("Missing load method")
            except Exception as e:
                logger.exception("Critical error during StateManager.load_session")
                QMessageBox.critical(self, "Load Error", f"Critical error loading session:\n{e}")
                self.update_status("Session load failed critically.")
                self.clear_ui_on_load_failure() # Reset UI
                return

            # If StateManager reported success, update UI
            if load_ok:
                logger.info("StateManager reported session loaded successfully.")
                self.update_status(f"Session loaded: {os.path.basename(file_path)}.")
                self.load_image() # Load the current image from the session
                self._update_annotated_count_label() # Update counts
                self.handle_settings_changed() # Apply any settings loaded with session

                # Re-evaluate ML control states after session load
                pipeline_ok = hasattr(self.state, 'training_pipeline') and bool(self.state.training_pipeline)
                blocking_task_active = self.state.is_task_active() if hasattr(self.state, 'is_task_active') else False
                enable_ml_controls = pipeline_ok and not blocking_task_active
                self.set_enabled_safe("auto_box_button", enable_ml_controls)
                self.set_enabled_safe("confidence_spinbox", enable_ml_controls and self.auto_box_button.isChecked())

                status_msg = "Session loaded successfully."
                if not pipeline_ok: status_msg += " Warning: ML Pipeline unavailable."
                self.update_status(status_msg)
            else:
                # StateManager reported failure
                logger.error(f"StateManager reported failure loading session: {file_path}")
                QMessageBox.critical(self, "Load Error", f"Failed to load session file:\n{file_path}\nMay be corrupt or invalid.")
                self.update_status("Session load failed.")
                self.clear_ui_on_load_failure() # Reset UI
        else:
            # User cancelled dialog
            self.update_status("Load session cancelled.")
            logger.info("User cancelled loading session.")


    def save_session(self):
        """Saves the current session via StateManager."""
        if self.state and hasattr(self.state, 'is_task_active') and self.state.is_task_active():
            QMessageBox.warning(self, "Busy", "Background task running.")
            return

        is_dummy_state = StateManager.__name__ == '_DummyStateManager'
        if not self.state:
             QMessageBox.warning(self, "Error", "State Manager unavailable.")
             return
        elif is_dummy_state:
             logger.info("Using dummy state manager for save session.")
             self.update_status("Session save skipped (Dummy).")
             return # Don't attempt save with dummy

        self.update_status("Saving session...")
        QCoreApplication.processEvents() # Show status
        try:
            if hasattr(self.state, 'save_session'):
                 self.state.save_session() # StateManager handles file path etc.
                 # Check status *after* save attempt, in case save_session updates it on error
                 current_status = getattr(self.status_label, 'text', lambda: '')()
                 if "error" not in current_status.lower() and "fail" not in current_status.lower():
                     self.update_status("Session saved.")
                     logger.info("Session saved successfully via StateManager.")
                 else:
                     # save_session might have already set an error status
                     logger.warning("Save completed but status indicates error during save.")
            else:
                 logger.error("State manager missing 'save_session' method.")
                 raise AttributeError("Missing save method")
        except Exception as e:
            logger.exception("Failed to save session via StateManager")
            QMessageBox.critical(self, "Save Error", f"Failed to save session:\n{e}")
            self.update_status("Session save error.")


    def next_image(self):
        """Navigate to the next image."""
        if self.state and hasattr(self.state, 'is_task_active') and self.state.is_task_active():
            self.update_status("Busy with background task.")
            return
        if not self.state or not hasattr(self.state, 'next_image'):
            self.update_status("Navigation unavailable.")
            return
        try:
            # State manager handles index change
            if self.state.next_image():
                self.load_image() # Load the new image
            else:
                 # Only show 'end' message if not busy (prevent overwriting task status)
                 if not (self.state and hasattr(self.state, 'is_task_active') and self.state.is_task_active()):
                     self.update_status("Already at the end.")
        except Exception as e:
            logger.exception("Error navigating next image.")
            self.update_status("Navigation error.")


    def prev_image(self):
        """Navigate to the previous image."""
        if self.state and hasattr(self.state, 'is_task_active') and self.state.is_task_active():
            self.update_status("Busy with background task.")
            return
        if not self.state or not hasattr(self.state, 'prev_image'):
            self.update_status("Navigation unavailable.")
            return
        try:
            # State manager handles index change
            if self.state.prev_image():
                self.load_image() # Load the new image
            else:
                 # Only show 'start' message if not busy
                 if not (self.state and hasattr(self.state, 'is_task_active') and self.state.is_task_active()):
                      self.update_status("Already at the start.")
        except Exception as e:
            logger.exception("Error navigating previous image.")
            self.update_status("Navigation error.")


    def manage_classes(self):
        """Opens dialog to manage annotation classes."""
        if self.state and hasattr(self.state, 'is_task_active') and self.state.is_task_active():
            QMessageBox.warning(self, "Busy", "Background task running.")
            return

        is_dummy_state = StateManager.__name__ == '_DummyStateManager'
        if not self.state or is_dummy_state:
             QMessageBox.warning(self, "Error", "State Manager unavailable or dummy.")
             return

        current_classes = getattr(self.state, "class_list", [])
        current_text = "\n".join(current_classes) # Present one class per line

        # Get user input using multi-line text dialog
        new_text, ok = QInputDialog.getMultiLineText(
            self, "Manage Classes", "Edit Classes (one per line):", current_text
        )

        if ok: # User clicked OK
            # Process input: split lines, strip whitespace, remove empty lines, ensure unique, sort
            new_classes_list = sorted(list(set(line.strip() for line in new_text.splitlines() if line.strip())))

            # Check if changes were actually made
            if new_classes_list != current_classes:
                logger.info(f"User proposed class change: {current_classes} -> {new_classes_list}")
                # Warn about consequences
                reply = QMessageBox.warning(
                    self, "Confirm Class Change",
                    "Changing classes removes annotations using removed classes.\nThis cannot be undone.\n\nUpdate classes?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel
                )
                if reply == QMessageBox.StandardButton.Yes:
                    logger.info("User confirmed class change.")
                    if hasattr(self.state, "update_classes"):
                        try:
                            # Ask StateManager to update classes and handle annotation cleanup
                            self.state.update_classes(new_classes_list)
                            self._update_annotated_count_label() # Update count display
                            self.update_status("Classes updated. Removed annotations deleted.")
                            # Reload current image to reflect potential annotation changes
                            self.load_image()
                        except Exception as e:
                            logger.exception("Failed during state.update_classes call")
                            QMessageBox.critical(self, "Error", f"Failed to update classes:\n{e}")
                    else:
                        logger.error("StateManager missing 'update_classes' method.")
                        QMessageBox.critical(self, "Internal Error", "Cannot update classes.")
                else:
                    self.update_status("Class change cancelled.")
                    logger.info("User cancelled class change.")
            else:
                self.update_status("Classes unchanged.")
                logger.info("User edited classes, no effective changes.")
        else:
            # User clicked Cancel
            self.update_status("Class management cancelled.")
            logger.info("User cancelled managing classes.")


    def load_image(self, image_path=None):
        """Loads an image into the scene, or clears it. Optionally loads specific path."""
        # Determine the path to load
        path_to_load = image_path # Use explicit path if given
        source_info = "explicit path"
        current_img = None

        if not path_to_load:
            # If no explicit path, get current image from state manager
            if self.state and hasattr(self.state, 'get_current_image'):
                current_img = self.state.get_current_image()
                if current_img:
                    path_to_load = current_img
                    idx = getattr(self.state, 'current_index', '?')
                    source_info = f"state index {idx}"
                else:
                    # State manager exists but has no current image (e.g., list empty)
                    source_info = "state has no current image"
            else:
                 # State manager doesn't exist or lacks method
                 source_info = "state unavailable or missing method"

        base_name = os.path.basename(path_to_load) if path_to_load else "None"
        logger.info(f"Load Image Request: '{base_name}' (Source: {source_info}).")

        # Get the graphics scene
        scene = getattr(self, "graphics_scene", None)
        if not isinstance(scene, AnnotationScene):
            logger.critical(f"Cannot load image: Graphics scene is invalid or dummy ({type(scene)})!")
            self.update_status("Error: Graphics scene unavailable.")
            self.clear_ui_on_load_failure() # Attempt to clear UI
            return

        # Clear previous annotations and suggestions from scene
        try:
            scene.clear_annotations()
            self.clear_suggestion_boxes()
            logger.debug("Cleared existing items from scene.")
        except Exception as e:
            logger.exception("Error clearing scene before loading image.")
            # Attempt to continue if clearing failed

        # Attempt to load the image into the scene
        load_ok = False
        img_width, img_height = 0, 0
        if path_to_load and os.path.exists(path_to_load):
            try:
                if hasattr(scene, 'set_image'):
                     load_ok = scene.set_image(path_to_load)
                     if load_ok and hasattr(scene, 'get_image_size'):
                         # Get dimensions from scene after successful load
                         img_width, img_height = scene.get_image_size()
                         if img_width <= 0 or img_height <= 0:
                             logger.error(f"Scene returned invalid size ({img_width}x{img_height}) for {base_name}")
                             load_ok = False # Treat as load failure
                     elif not load_ok:
                         # scene.set_image itself reported failure
                         logger.error(f"scene.set_image returned False for {base_name}")
                else:
                     logger.error("Scene object missing 'set_image' method.")
                     load_ok = False # Cannot load
            except Exception as e:
                logger.exception(f"Error during scene.set_image for {base_name}.")
                self.update_status(f"Error loading image file: {base_name}")
                load_ok = False
        elif path_to_load:
             # Path provided but file doesn't exist
             logger.error(f"Image path specified but file not found: {path_to_load}")
             self.update_status("Error: Image file not found.")
             load_ok = False
        else:
             # No path to load (list empty, index invalid, etc.)
             logger.info("No image path to load (list empty or index invalid).")
             try:
                 # Explicitly clear the scene if no image is loaded
                 if hasattr(scene, 'set_image'): scene.set_image(None)
             except Exception as clear_err:
                 logger.error(f"Error clearing scene when no image path: {clear_err}")
             load_ok = False

        # Update image count label regardless of success
        self._update_image_count_label()
        view = getattr(self, "graphics_view", None)

        if load_ok:
            # --- Actions on successful load ---
            logger.info(f"Image loaded: {base_name} ({img_width}x{img_height})")
            self.setWindowTitle(f"Annotator - {base_name}")
            self.update_status(f"Loaded: {base_name}")

            # Fit view to image
            if view and isinstance(view, AnnotatorGraphicsView) and hasattr(view, 'fitInView'):
                try:
                    scene_rect = scene.sceneRect()
                    if scene_rect.isValid() and not scene_rect.isEmpty():
                        view.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatio)
                        # Reset zoom level after fitInView
                        if hasattr(view, '_zoom'): view._zoom = 0
                        logger.debug("View fit to image.")
                    else:
                        logger.warning("Cannot fit view: Scene rect invalid after load.")
                except Exception as e:
                     logger.error(f"Error fitting view: {e}")

            # Load existing annotations from state manager
            annotation_data = None
            if self.state and hasattr(self.state, 'annotations') and isinstance(self.state.annotations, dict):
                annotation_data = self.state.annotations.get(path_to_load)

            if annotation_data:
                # Check flags
                is_negative = annotation_data.get("negative", False)
                is_approved = annotation_data.get("approved", False)
                box_list = annotation_data.get("annotations_list", [])
                logger.info(f"Annotation data: Approved={is_approved}, Negative={is_negative}, Boxes={len(box_list)}")

                # Get the class for drawing boxes (check it's not the dummy)
                rect_item_class = ResizableRectItem
                if rect_item_class.__name__ != 'DummyResizableRectItem':
                    items_added_count = 0
                    # Add annotation items to the scene
                    for ann in box_list:
                         if hasattr(scene, "add_annotation_item_from_data"):
                              try:
                                   # Scene method handles conversion from pixel to scene coords
                                   item_added = scene.add_annotation_item_from_data(ann, img_width, img_height)
                                   if item_added: items_added_count += 1
                                   else: logger.warning(f"add_annotation_item_from_data failed for: {ann}")
                              except Exception as e_add:
                                   logger.error(f"Failed add annotation item {ann}: {e_add}", exc_info=True)
                         else:
                              logger.error("Scene missing 'add_annotation_item_from_data'.")
                              break # Stop trying if method missing
                    if items_added_count > 0: logger.info(f"Displayed {items_added_count} saved annotation boxes.")
                else:
                     logger.critical("Cannot display saved annotations: Using DummyResizableRectItem.")

                # Add visual indicator for negative images if applicable
                if is_negative:
                    try:
                        from PyQt6.QtWidgets import QGraphicsTextItem # Local import if only needed here
                        neg_indicator = QGraphicsTextItem("[Negative Image]")
                        neg_indicator.setDefaultTextColor(QColor(200, 200, 200, 180)) # Semi-transparent grey
                        neg_indicator.setPos(10, 10) # Position near top-left
                        neg_indicator.setZValue(10) # Ensure it's above image but below boxes
                        scene.addItem(neg_indicator)
                        logger.debug("Added [Negative Image] indicator.")
                    except Exception as e:
                        logger.error(f"Failed to add [Negative Image] indicator: {e}")
            else:
                # No annotation data found in state for this image
                logger.info(f"No annotation data in state for: {base_name}")

            # Check if auto-suggestions should be displayed
            auto_box_checkbox = getattr(self, "auto_box_button", None)
            if auto_box_checkbox and auto_box_checkbox.isChecked():
                 logger.debug("Auto-suggestions checked, triggering check.")
                 self.toggle_auto_boxes() # Will request predictions if needed
            else:
                 self.clear_suggestion_boxes() # Ensure suggestions are cleared if box unchecked

            # Set focus to the graphics view for keyboard events (delete, etc.)
            if view and isinstance(view, AnnotatorGraphicsView):
                logger.debug("Setting focus to graphics view.")
                view.setFocus()
        else:
            # --- Actions on failed load ---
            self.setWindowTitle("Annotator")
            # Avoid overwriting specific error messages if already set
            current_status = getattr(self.status_label, 'text', lambda: '')()
            if "error" not in current_status.lower() and "fail" not in current_status.lower():
                 if path_to_load: self.update_status(f"Failed to load image: {base_name}")
                 else: self.update_status("No image selected or list empty.")
            # Ensure scene is cleared
            if isinstance(scene, AnnotationScene): scene.set_image(None)
            self.clear_suggestion_boxes()

# --- Start of Part 2 ---

    def approve_image(self):
        """Marks the current image as approved and navigates to the next unannotated one."""
        is_dummy_state = StateManager.__name__ == '_DummyStateManager'
        if not self.state or is_dummy_state:
            QMessageBox.warning(self, "Error", "State Manager unavailable or dummy.")
            return

        # Get current image path and scene
        current_path = self.state.get_current_image() if hasattr(self.state, 'get_current_image') else None
        scene = getattr(self, "graphics_scene", None)

        # Check if image is validly loaded in scene
        scene_is_valid = isinstance(scene, AnnotationScene) and hasattr(scene, 'image_item') \
                         and scene.image_item and not scene.image_item.pixmap().isNull()

        if not current_path or not scene_is_valid:
            QMessageBox.warning(self, "Error", "No valid image loaded to approve.")
            return

        # Get annotations currently drawn on the scene
        current_annotations_list = []
        try:
            if hasattr(scene, 'get_all_annotations'):
                 # This method should return annotations in the required format (pixel coords)
                 current_annotations_list = scene.get_all_annotations()
                 logger.debug(f"Retrieved {len(current_annotations_list)} annotations from scene.")
            else:
                 logger.error("Scene missing 'get_all_annotations' method.")
                 raise AttributeError("Missing get_all_annotations")
        except Exception as e:
            logger.exception("Failed to retrieve annotations from scene.")
            QMessageBox.warning(self, "Approval Error", f"Could not retrieve annotations:\n{e}")
            return

        # --- Store last box data for pasting ---
        self.last_box_data = None
        # Find ResizableRectItems currently in the scene
        rect_items = [item for item in scene.items() if isinstance(item, ResizableRectItem)]
        if rect_items:
             # Store data from the last item added (or a specific selected one if desired)
             last_item = rect_items[-1] # Simple heuristic: last one drawn/added
             self.last_box_data = {
                 "rect": last_item.sceneBoundingRect(), # Store scene coords
                 "class": getattr(last_item, 'class_label', 'Unknown')
             }
             logger.debug(f"Stored last box: Class='{self.last_box_data['class']}', SceneRect={self.last_box_data['rect']}")
        else:
             logger.debug("No annotation boxes on image, clearing last box data.")
        # --- End store last box data ---

        # Determine if image is marked as negative (no boxes)
        is_negative_image = not current_annotations_list

        # Prepare data structure for state manager
        annotation_data_to_save = {
            "annotations_list": current_annotations_list,
            "approved": True, # Mark as approved
            "negative": is_negative_image
        }

        status_msg = f"Approving '{os.path.basename(current_path)}' ({'Negative' if is_negative_image else str(len(current_annotations_list)) + ' box(es)'})..."
        self.update_status(status_msg)
        logger.info(status_msg.replace("...", "."))
        QCoreApplication.processEvents() # Show status

        # Send data to state manager
        try:
            logger.debug("Calling state.add_annotation...")
            if hasattr(self.state, 'add_annotation'):
                 # State manager handles saving, updating counts, and triggering training
                 success = self.state.add_annotation(current_path, annotation_data_to_save)
                 if not success:
                     # State manager indicated an issue saving
                     logger.error("state.add_annotation reported failure.")
                     QMessageBox.warning(self, "Approval Error", "Failed to save annotation data.")
                     self.update_status("Approval failed.")
                     return # Don't navigate if save failed
            else:
                 logger.error("State manager missing 'add_annotation' method.")
                 QMessageBox.critical(self, "Internal Error", "Cannot save annotation.")
                 self.update_status("Approval failed.")
                 return

            # Update UI count
            self._update_annotated_count_label()
            self.update_status(f"Approved: {os.path.basename(current_path)}. Navigating...")

            # Navigate after a short delay to allow UI updates
            logger.debug("Scheduling navigation via QTimer.")
            QTimer.singleShot(50, self.navigate_to_next_unannotated)

        except Exception as e:
            logger.exception("Critical error during approval process.")
            QMessageBox.critical(self, "Approval Error", f"Critical error during approval:\n{e}")
            self.update_status("Approval failed critically.")


    def navigate_to_next_unannotated(self):
        """Finds and navigates to the next image that hasn't been approved."""
        logger.info("Navigating to next unannotated image...")
        is_dummy_state = StateManager.__name__ == '_DummyStateManager'
        img_list = getattr(self.state, 'image_list', []) if self.state else []

        if not self.state or is_dummy_state or not img_list:
            logger.warning("Navigation aborted: Invalid state or empty list.")
            self.update_status("Navigation failed: No images loaded.")
            return

        annotations_map = getattr(self.state, "annotations", {})
        total_images = len(img_list)
        start_index = getattr(self.state, "current_index", -1)

        if total_images == 0:
             logger.warning("Navigation impossible: Image list empty.")
             self.update_status("Image list empty.")
             return

        # Start checking from the image *after* the current one, wrapping around
        current_check_index = (start_index + 1) % total_images
        checked_count = 0
        found_unannotated = False

        while checked_count < total_images:
            image_path_to_check = img_list[current_check_index]
            # Check the 'approved' flag in the state manager's annotation data
            is_approved = annotations_map.get(image_path_to_check, {}).get("approved", False)
            logger.debug(f"Nav Check: Idx {current_check_index} ('{os.path.basename(image_path_to_check)}'), Approved={is_approved}")

            if not is_approved:
                # Found an unannotated image
                logger.info(f"Navigation found unannotated at Index {current_check_index}.")
                try:
                    # Ask state manager to change index and load the image
                    if hasattr(self.state, 'go_to_image') and self.state.go_to_image(current_check_index):
                        self.load_image()
                        found_unannotated = True
                        break # Stop searching
                    else:
                        # state.go_to_image failed
                        logger.error(f"Navigation failed: state.go_to_image({current_check_index}) failed.")
                        self.update_status("Error loading next image (state error).")
                        break # Stop searching on error
                except Exception as e:
                    logger.exception(f"Navigation failed: Error loading image at index {current_check_index}.")
                    self.update_status("Error loading next image.")
                    break # Stop searching on error

            # Move to the next index, wrapping around
            current_check_index = (current_check_index + 1) % total_images
            checked_count += 1

        if not found_unannotated:
            # Scanned all images, none were unannotated
            logger.info("Navigation complete: No unannotated images found.")
            self.update_status("All images appear to be annotated.")


    def clear_suggestion_boxes(self):
        """Removes all suggestion boxes from the scene."""
        scene = getattr(self, "graphics_scene", None)
        if isinstance(scene, AnnotationScene):
            # Find items stored in self.auto_box_items that are currently in the scene
            items_to_remove = [item for item in self.auto_box_items if item and item.scene() == scene]
            if items_to_remove:
                logger.debug(f"Clearing {len(items_to_remove)} suggestion boxes.")
                for item in items_to_remove:
                    try:
                        scene.removeItem(item)
                    except Exception as e:
                        logger.error(f"Error removing suggestion item: {e}")
        # Clear the list regardless
        self.auto_box_items = []


    def toggle_auto_boxes(self):
        """Handles the 'Show Suggestions' checkbox state change."""
        checkbox = getattr(self, "auto_box_button", None)
        if not checkbox:
            logger.error("Auto-box checkbox widget not found.")
            return

        # Check prerequisites for getting suggestions
        is_dummy_state = StateManager.__name__ == '_DummyStateManager'
        state_ok = self.state and not is_dummy_state
        pipeline_ok = state_ok and hasattr(self.state, 'training_pipeline') and bool(self.state.training_pipeline)
        task_active = state_ok and hasattr(self.state, 'is_task_active') and self.state.is_task_active()

        # Disable checkbox if prerequisites not met
        if not pipeline_ok:
            if checkbox.isChecked():
                self.update_status("Suggestions unavailable: ML Pipeline missing.")
                checkbox.setChecked(False) # Uncheck if user tried to check it
            self.clear_suggestion_boxes(); return # Ensure boxes are cleared
        if task_active:
            if checkbox.isChecked():
                self.update_status("Suggestions unavailable: Task running.")
                checkbox.setChecked(False) # Uncheck
            # Don't clear boxes here, might resume after task
            return

        # Handle checkbox state
        if checkbox.isChecked():
            # --- Request suggestions ---
            current_image_path = self.state.get_current_image() if state_ok and hasattr(self.state, 'get_current_image') else None
            scene = getattr(self, "graphics_scene", None)
            scene_has_image = isinstance(scene, AnnotationScene) and hasattr(scene, 'image_item') \
                              and scene.image_item and not scene.image_item.pixmap().isNull()

            if not current_image_path or not os.path.exists(current_image_path) or not scene_has_image:
                self.update_status("Cannot get suggestions: No valid image loaded.")
                checkbox.setChecked(False); self.clear_suggestion_boxes(); return

            # Clear old suggestions and request new ones
            self.clear_suggestion_boxes()
            self.update_status("Requesting AI suggestions...")
            QCoreApplication.processEvents() # Show status update
            try:
                if hasattr(self.state, 'start_prediction'):
                     # State manager starts the background prediction task
                     success = self.state.start_prediction(current_image_path)
                     if not success:
                         # Task didn't start for some reason (e.g., another task conflict?)
                         logger.warning("state.start_prediction failed or task didn't start.")
                         self.update_status("Failed to start suggestion task.")
                         checkbox.setChecked(False); self.clear_suggestion_boxes()
                         # Ensure state manager resets blocking flag if needed
                else:
                     logger.error("State manager missing 'start_prediction' method.")
                     self.update_status("Suggestion feature unavailable.")
                     checkbox.setChecked(False)
            except Exception as e:
                logger.exception("Critical error starting prediction task.")
                QMessageBox.critical(self, "Suggestion Error", f"Critical error starting suggestion task:\n{e}")
                self.update_status("Suggestion task failed critically.")
                checkbox.setChecked(False); self.clear_suggestion_boxes()
                # Attempt to reset blocking state if possible on critical failure
                if hasattr(self.state, '_blocking_task_running'):
                    try: self.state._blocking_task_running = False
                    except: pass
                self.on_ml_task_running_changed(False) # Manually update UI state
        else:
            # --- Hide suggestions ---
            self.clear_suggestion_boxes()
            self.update_status("Suggestions hidden.")


    @pyqtSlot(bool)
    def on_ml_task_running_changed(self, is_blocking_task_running: bool):
        """Updates UI element enabled states based on whether a background task is running."""
        self._ml_task_active = is_blocking_task_running
        logger.info(f"UI Update: Blocking Task Active = {is_blocking_task_running}.")

        is_dummy_state = StateManager.__name__ == '_DummyStateManager'
        # Check if a real pipeline instance exists
        pipeline_exists = (self.state and not is_dummy_state
                           and hasattr(self.state, 'training_pipeline')
                           and bool(self.state.training_pipeline))

        # General controls should be disabled during blocking tasks
        enable_general_controls = not is_blocking_task_running
        # ML-specific controls require pipeline AND no blocking task
        enable_ml_controls = pipeline_exists and not is_blocking_task_running

        # List widgets affected by general blocking state
        general_widgets = [
            "load_button", "load_session_button", "save_session_button",
            "prev_button", "next_button", "manage_classes_button",
            "bbox_tool_button", "approve_button",
            "load_dir_action", "load_sess_action", "save_sess_action",
            "settings_action", "export_model_action", "export_data_action",
            "force_mini_train_button", "training_dashboard_button"
        ]
        for widget_name in general_widgets:
            self.set_enabled_safe(widget_name, enable_general_controls)

        # List widgets specifically requiring the ML pipeline
        ml_widgets = ["auto_box_button", "confidence_spinbox"]
        for widget_name in ml_widgets:
            self.set_enabled_safe(widget_name, enable_ml_controls)

        # Special handling for confidence spinbox (depends on checkbox state too)
        conf_spin = getattr(self, "confidence_spinbox", None)
        sugg_check = getattr(self, "auto_box_button", None)
        if conf_spin and sugg_check:
             conf_spin.setEnabled(enable_ml_controls and sugg_check.isChecked())

        # Update status bar if task just finished
        if not is_blocking_task_running:
            current_status = getattr(self.status_label, "text", lambda: "")()
            lower_status = current_status.lower()
            # Check if status indicates a completed action or error state
            is_final_state = any(k in lower_status for k in [
                "complete", "error", "fail", "loaded", "saved", "ready", "found",
                "cancelled", "exported", "finished", "approved", "unavailable", "unchanged"
            ])
            # If status doesn't reflect completion, reset to "Ready."
            if not is_final_state:
                self.update_status("Ready.")


    @pyqtSlot(list)
    def handle_prediction_results(self, boxes: list):
        """Displays bounding box suggestions received from the prediction worker."""
        logger.info(f"GUI: Received {len(boxes)} prediction results.")
        self.clear_suggestion_boxes() # Clear any previous suggestions

        # --- Validation ---
        is_dummy_state = StateManager.__name__ == '_DummyStateManager'
        scene = getattr(self, "graphics_scene", None)
        scene_ok = isinstance(scene, AnnotationScene) and hasattr(scene, 'image_item') \
                   and scene.image_item and not scene.image_item.pixmap().isNull()
        rect_item_class = ResizableRectItem
        rect_item_ok = rect_item_class.__name__ != 'DummyResizableRectItem'
        auto_box_checkbox = getattr(self, "auto_box_button", None)

        if is_dummy_state or not scene_ok or not rect_item_ok:
            logger.warning(f"Cannot display suggestions: Invalid state/scene/item (StateDummy:{is_dummy_state}, SceneOK:{scene_ok}, ItemOK:{rect_item_ok}).")
            if auto_box_checkbox: auto_box_checkbox.setChecked(False) # Uncheck if failed
            self.update_status("Error displaying suggestions (internal).")
            return

        img_width, img_height = scene.get_image_size() if hasattr(scene, 'get_image_size') else (0,0)
        if img_width <= 0 or img_height <= 0:
            logger.error("Cannot display suggestions: Invalid image dimensions retrieved from scene.")
            self.update_status("Error processing suggestions (img size).")
            if auto_box_checkbox: auto_box_checkbox.setChecked(False)
            return
        # --- End Validation ---

        items_added_count = 0
        # Define visual style for suggestions
        suggestion_pen = QPen(QColor(0, 255, 0, 180), 2, Qt.PenStyle.DashLine) # Green dashed line
        suggestion_text_color = QColor(200, 255, 200, 200) # Light green text

        img_item = scene.image_item # Cache for performance

        for box_data in boxes:
            try:
                # Extract data safely
                pixel_coords = box_data.get("box")
                confidence = box_data.get("confidence", 0.0)
                class_label = box_data.get("class", "Unknown")

                # Validate coordinates
                if not isinstance(pixel_coords, (list, tuple)) or len(pixel_coords) != 4:
                    logger.warning(f"Skipping suggestion with invalid 'box' format: {pixel_coords}")
                    continue
                px, py, pw, ph = map(float, pixel_coords)
                if pw <= 0 or ph <= 0:
                     logger.warning(f"Skipping suggestion with zero/negative dimensions: W={pw}, H={ph}")
                     continue

                # Convert pixel coordinates (relative to image) to scene coordinates
                if not img_item: continue # Should not happen if scene_ok check passed
                pixel_rect = QRectF(px, py, pw, ph)
                scene_rect = img_item.mapRectToScene(pixel_rect)

                # Create a non-interactive ResizableRectItem for the suggestion
                suggestion_item = rect_item_class(scene_rect, class_label)
                suggestion_item.setPen(suggestion_pen)

                # Add confidence score to the label
                if hasattr(suggestion_item, "textItem") and suggestion_item.textItem:
                    suggestion_item.textItem.setPlainText(f"{class_label} ({confidence:.2f})")
                    suggestion_item.textItem.setDefaultTextColor(suggestion_text_color)

                suggestion_item.setZValue(5) # Ensure suggestions are visible but below user boxes maybe?

                # --- Make suggestions non-interactive ---
                suggestion_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                suggestion_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
                suggestion_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, False)
                suggestion_item.setAcceptHoverEvents(False) # Don't show resize cursors etc.
                # ---

                scene.addItem(suggestion_item)
                self.auto_box_items.append(suggestion_item) # Keep track for clearing
                items_added_count += 1

            except (ValueError, TypeError, KeyError) as e:
                logger.error(f"Invalid data processing suggestion {box_data}: {e}")
            except Exception as e:
                logger.error(f"Error creating suggestion item {box_data}: {e}", exc_info=True)

        # Update status
        status_msg = f"Displayed {items_added_count} suggestion(s)."
        if items_added_count != len(boxes):
            status_msg += f" (Filtered from {len(boxes)})"
        self.update_status(status_msg); logger.info(status_msg)


    @pyqtSlot(str)
    def handle_training_run_completed(self, run_dir_path: str):
        """Handles the signal emitted when a training run finishes successfully."""
        run_name = os.path.basename(run_dir_path) if run_dir_path and os.path.isdir(run_dir_path) else "Unknown Run"
        logger.info(f"GUI: Received training completion signal for run: {run_name}")
        self.update_status(f"Training '{run_name}' finished successfully.")

        # --- Update the Training Dashboard if it's open ---
        if self.training_dashboard_instance and hasattr(self.training_dashboard_instance, 'update_graph'):
            logger.info(f"Updating open training dashboard with data from run directory: {run_dir_path}")
            # --- FIX: Pass the run directory path directly ---
            self.training_dashboard_instance.update_graph(run_dir_path)
            # -----------------------------------------------
        else:
             if not self.training_dashboard_instance: logger.info("Training dashboard not open, graph update skipped.")
             else: logger.error("Training dashboard instance lacks 'update_graph' method.")
        # --- End Dashboard Update ---

        # Optional: Show a confirmation message box
        QMessageBox.information(self, "Training Complete", f"Training run '{run_name}' completed.\nResults saved in:\n{run_dir_path}")


    @pyqtSlot(str)
    def handle_task_error(self, error_message: str):
        """Handles error signals from background workers."""
        # Try to determine task type from message for better context
        task_type = "ML Task"
        lower_msg = str(error_message).lower() if error_message else ""
        if "prediction" in lower_msg or "suggest" in lower_msg or "auto_box" in lower_msg:
            task_type = "Prediction"
            # If prediction failed, uncheck the suggestion box
            if hasattr(self, 'auto_box_button'):
                auto_box_checkbox = getattr(self, 'auto_box_button')
                if auto_box_checkbox and auto_box_checkbox.isChecked():
                    auto_box_checkbox.setChecked(False) # Keep UI consistent
            self.clear_suggestion_boxes() # Clear any partial suggestions
        elif "train" in lower_msg:
             # Try to be more specific about training errors if possible
             if "training failed:" in lower_msg: task_type = "Training Run"
             elif "training setup" in lower_msg: task_type = "Training Setup"
             else: task_type = "Training"

        logger.error(f"GUI Received Error Signal ({task_type}): {error_message}")

        # Display error message to user (limit length for readability)
        display_message = str(error_message)[:500] + ("..." if len(str(error_message)) > 500 else "")
        QMessageBox.warning(self, f"{task_type} Error", f"Background task error:\n\n{display_message}\n\n(Check app_debug.log for details)")
        self.update_status(f"{task_type} Error.") # Update status bar


    def closeEvent(self, event):
        """Handles the window close event, checks for running tasks and save prompts."""
        is_blocking_task_active = False
        if self.state and hasattr(self.state, 'is_task_active'):
             is_blocking_task_active = self.state.is_task_active()

        # Check if a task is running
        if is_blocking_task_active:
            task_desc = "A background task (Training/Prediction)"
            reply = QMessageBox.warning(
                self, "Task Running",
                f"{task_desc} is running.\nClosing might interrupt it.\n\nWait or Close Anyway?",
                QMessageBox.StandardButton.Wait | QMessageBox.StandardButton.Close,
                QMessageBox.StandardButton.Wait # Default to Wait
            )
            if reply == QMessageBox.StandardButton.Close:
                logger.warning("User closing window while task running. Attempting cleanup...")
                # Attempt to trigger state manager cleanup (which should try to stop worker)
                if self.state and hasattr(self.state, "cleanup"):
                    try: self.state.cleanup()
                    except Exception as cleanup_err: logger.error(f"Error during StateManager cleanup on forced exit: {cleanup_err}")
                event.accept(); return # Accept close event
            else:
                # User chose Wait
                event.ignore(); # Ignore close event
                self.update_status("Waiting for background task..."); return

        # Ask to save if not using dummy state and data exists
        save_reply = QMessageBox.StandardButton.No # Default if no prompt needed
        is_dummy_state = StateManager.__name__ == '_DummyStateManager'
        if self.state and not is_dummy_state:
             # Prompt if there are images loaded OR annotations exist
             needs_save_prompt = (hasattr(self.state, 'image_list') and self.state.image_list) or \
                                 (hasattr(self.state, 'annotations') and self.state.annotations)
             if needs_save_prompt:
                  save_reply = QMessageBox.question(
                      self, "Exit Confirmation", "Save current session before exiting?",
                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                      QMessageBox.StandardButton.Yes # Default to Yes
                  )
             else:
                  # No data loaded, no need to save
                  save_reply = QMessageBox.StandardButton.No

        # Handle user response to save prompt
        if save_reply == QMessageBox.StandardButton.Cancel:
            event.ignore(); logger.info("Window close cancelled by user."); return
        elif save_reply == QMessageBox.StandardButton.Yes:
            try:
                self.update_status("Saving session before exit..."); QCoreApplication.processEvents()
                self.save_session() # Call the save method
                # Check status *after* saving, in case save_session reported an error
                current_status = getattr(self.status_label, 'text', lambda: '')()
                if "error" not in current_status.lower() and "fail" not in current_status.lower():
                    self.update_status("Session saved. Exiting.")
                QCoreApplication.processEvents() # Show final status
            except Exception as save_e:
                logger.error("Failed to save session during exit.", exc_info=True)
                # Inform user but still exit
                QMessageBox.critical(self, "Save Error", f"Failed to save session on exit:\n{save_e}\n\nExiting without saving.")
        else: # User chose No
             self.update_status("Exiting without saving..."); QCoreApplication.processEvents()

        # Perform final cleanup (only if not forcing close during task)
        if not is_blocking_task_active: # Avoid double cleanup if forced close already called it
             if self.state and hasattr(self.state, "cleanup"):
                 try:
                     logger.info("Calling final StateManager cleanup...")
                     self.state.cleanup()
                     logger.info("StateManager cleanup completed.")
                 except Exception as e:
                     logger.exception("Error during final StateManager cleanup.")

        logger.info("Accepting close event. Application exiting.")
        event.accept() # Allow the window to close

# --- Main block removed --- (Should be in main.py)
# --- End of Part 2 ---