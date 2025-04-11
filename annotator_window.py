# annotator_window.py (Completed Tiering Integration)

import logging
import os
import sys
import shutil
import inspect  # Added for logging method names

# --- PyQt6 Imports ---
from PyQt6.QtCore import (
    Qt,
    pyqtSlot,
    QRectF,
    QCoreApplication,
    pyqtSignal,
    QObject,
    QTimer,
    QUrl,
)
from PyQt6.QtGui import (
    QAction,
    QColor,
    QPen,
    QDesktopServices,
    QIcon,
)
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QSplitter,
    QInputDialog,
    QMessageBox,
    QSpinBox,
    QGroupBox,
    QCheckBox,
    QToolButton,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsTextItem,  # Added for negative image indicator
)

import config  # --- TIERING: Needed for config.TIER ---

# --- State Manager Import (Conditional based on Tier) ---
_StateManager = None
# Use module-level logger early
logger = logging.getLogger(__name__)
# Ensure config.TIER was set by main.py before this module is imported.
logger.info(
    f"--- AnnotatorWindow: Checking Tier for StateManager Import "
    f"(Tier={getattr(config, 'TIER', 'UNKNOWN')}) ---"
)

# --- TIERING: Try importing REAL StateManager ONLY if PRO tier ---
if hasattr(config, "TIER") and config.TIER == "PRO":
    try:
        from state_manager import StateManager as _StateManager

        if not hasattr(_StateManager, "add_annotation"):
            logger.warning(
                "Imported StateManager looks incomplete, falling back to dummy."
            )
            _StateManager = None
        else:
            logger.info("OK: Real StateManager imported for PRO tier.")
    except ImportError as e:
        logger.critical(f"FAIL: PRO tier StateManager Import: {e}", exc_info=True)
        _StateManager = None
    except Exception as e_sm:
        logger.critical(
            f"FAIL: Error during PRO StateManager import/check: {e_sm}", exc_info=True
        )
        _StateManager = None
else:
    logger.info(
        f"[BASIC/UNKNOWN Tier] Tier detected ({getattr(config, 'TIER', 'UNKNOWN')}). "
        f"Will use DUMMY StateManager."
    )

# --- TIERING: Fallback to DUMMY if not PRO or if PRO import failed ---
if _StateManager is None:
    try:
        from dummy_components import _DummyStateManager as _StateManager

        logger.warning(
            f"Using DUMMY StateManager (Tier: {getattr(config, 'TIER', 'UNKNOWN')})."
        )
    except ImportError as e_dummy_sm:
        logger.critical(f"CRITICAL: Failed to import DUMMY StateManager: {e_dummy_sm}")
        print(f"[CRITICAL] Cannot load StateManager or its dummy: {e_dummy_sm}")
        # Avoid UI popup here, main.py handles startup errors. Raise exception?
        raise ImportError(
            f"Cannot load StateManager or its dummy: {e_dummy_sm}"
        ) from e_dummy_sm

# Assign the determined class
StateManager = _StateManager

# --- GUI Component Import (Conditional based on Tier) ---
_AnnotationScene = None
_AnnotatorGraphicsView = None
_SettingsDialog = None  # Assume Basic might need some settings?
_ResizableRectItem = None  # Needed for Basic
_TrainingDashboard = None  # PRO Only
# --- TIERING: Add import for backend TrainingPipeline to check its type ---
_TrainingPipeline = None  # Will be imported conditionally below

logger.info(
    f"--- AnnotatorWindow: Checking Tier for GUI Component Import "
    f"(Tier={getattr(config, 'TIER', 'UNKNOWN')}) ---"
)

try:
    # Try importing components needed for Basic (and potentially shared by Pro)
    from gui import (
        AnnotationScene as _AnnotationScene,
        AnnotatorGraphicsView as _AnnotatorGraphicsView,
        SettingsDialog as _SettingsDialog,  # Keep for Basic for now
        ResizableRectItem as _ResizableRectItem,  # Essential for Basic
    )

    # Basic check
    if not issubclass(_AnnotationScene, QGraphicsScene):
        logger.warning(
            "Imported AnnotationScene is not a QGraphicsScene subclass. Falling back."
        )
        _AnnotationScene = None  # Force fallback for essential component
    else:
        logger.info("OK: Basic GUI components imported.")

    # --- TIERING: Import PRO-only GUI components conditionally ---
    if hasattr(config, "TIER") and config.TIER == "PRO":
        try:
            from gui import TrainingDashboard as _TrainingDashboard

            logger.info("OK: TrainingDashboard imported for PRO tier.")
            # --- TIERING: Also import real TrainingPipeline for checks ---
            from training_pipeline import TrainingPipeline as _TrainingPipeline

            logger.info("OK: Real TrainingPipeline imported for PRO tier checks.")
        except ImportError as e_pro_gui:
            logger.warning(f"Could not import PRO tier component: {e_pro_gui}.")
            if "TrainingDashboard" in str(e_pro_gui):
                _TrainingDashboard = None
            if "TrainingPipeline" in str(e_pro_gui):
                _TrainingPipeline = None
    else:
        logger.info(
            f"[BASIC/UNKNOWN Tier] Tier detected ({getattr(config, 'TIER', 'UNKNOWN')}). "
            f"Skipping PRO GUI/Backend imports."
        )
        _TrainingDashboard = None
        _TrainingPipeline = None

except ImportError as e_gui:
    logger.critical(f"FAIL: Basic gui components import: {e_gui}", exc_info=True)
    # Ensure all are None if any basic fail, triggering full dummy fallback below
    _AnnotationScene = None
    _AnnotatorGraphicsView = None
    _SettingsDialog = None
    _ResizableRectItem = None
    _TrainingDashboard = None
    _TrainingPipeline = None
except Exception as e_gui_other:
    logger.critical(
        f"FAIL: Error during Basic GUI component import/check: {e_gui_other}",
        exc_info=True,
    )
    _AnnotationScene = None
    _AnnotatorGraphicsView = None
    _SettingsDialog = None
    _ResizableRectItem = None
    _TrainingDashboard = None
    _TrainingPipeline = None

# Fallback to dummies if real ones failed or weren't assigned
# Fallback for BASIC components
if (
    _AnnotationScene is None
    or _AnnotatorGraphicsView is None
    or _SettingsDialog is None
    or _ResizableRectItem is None
):
    logger.warning(
        "One or more basic GUI components failed import. Attempting DUMMY fallbacks."
    )
    try:
        if _AnnotationScene is None:
            from dummy_components import DummyAnnotationScene as _AnnotationScene
        if _AnnotatorGraphicsView is None:
            from dummy_components import (
                DummyAnnotatorGraphicsView as _AnnotatorGraphicsView,
            )
        if _SettingsDialog is None:
            from dummy_components import DummySettingsDialog as _SettingsDialog
        if _ResizableRectItem is None:
            from dummy_components import DummyResizableRectItem as _ResizableRectItem
        logger.warning(
            "Using DUMMY GUI components for Scene, View, Settings, RectItem as needed."
        )
    except ImportError as e_dummy_basic_gui:
        logger.critical(
            f"CRITICAL: Failed to import required DUMMY Basic GUI components: {e_dummy_basic_gui}"
        )
        print(
            f"[CRITICAL] Cannot load Basic GUI components or dummies: {e_dummy_basic_gui}"
        )
        raise ImportError(
            f"Cannot load Basic GUI components or dummies: {e_dummy_basic_gui}"
        ) from e_dummy_basic_gui

# Fallback for PRO components (only if needed)
if _TrainingDashboard is None:
    try:
        from dummy_components import DummyTrainingDashboard as _TrainingDashboard

        logger.warning(
            f"Using DUMMY TrainingDashboard (Tier: {getattr(config, 'TIER', 'UNKNOWN')})."
        )
    except ImportError as e_dummy_pro_gui:
        logger.error(f"Failed to import DUMMY TrainingDashboard: {e_dummy_pro_gui}")
# --- TIERING: Fallback for TrainingPipeline ---
if _TrainingPipeline is None:
    # We don't directly USE the pipeline class here, but need its NAME for checks
    # If it failed to import, assume it's the dummy for checks later
    class _DummyTrainingPipeline:
        pass  # Minimal dummy just for name check

    _TrainingPipeline = _DummyTrainingPipeline
    logger.warning(
        f"Using placeholder _DummyTrainingPipeline for checks (Tier: {getattr(config, 'TIER', 'UNKNOWN')})."
    )


# Assign determined classes (real or dummy) to names used later
AnnotationScene = _AnnotationScene
AnnotatorGraphicsView = _AnnotatorGraphicsView
SettingsDialog = _SettingsDialog
ResizableRectItem = _ResizableRectItem
TrainingDashboard = _TrainingDashboard
# --- TIERING: Assign TrainingPipeline class (real or dummy placeholder) ---
TrainingPipeline = _TrainingPipeline

# Check ResizableRectItem specifically as it's crucial
if ResizableRectItem.__name__ == "DummyResizableRectItem":
    logger.warning(
        "Assigned DummyResizableRectItem. Annotation functionality will be limited."
    )
elif not issubclass(ResizableRectItem, QGraphicsItem):
    logger.critical(
        f"CRITICAL: Imported ResizableRectItem ('{ResizableRectItem.__name__}') is not a QGraphicsItem subclass."
    )
    try:
        from dummy_components import DummyResizableRectItem

        ResizableRectItem = DummyResizableRectItem
        logger.critical("Forcing DummyResizableRectItem.")
    except ImportError:
        print("[CRITICAL] Cannot force DummyResizableRectItem. Exiting.")
        sys.exit(1)


class AnnotatorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # --- TIERING: Use config.TIER set by main.py ---
        self.current_tier = config.TIER
        self.setWindowTitle(f"Snowball Annotator [{self.current_tier}]")
        self.setGeometry(100, 100, 1200, 800)
        self.logger = logger  # Use module-level logger
        self.state = None
        self._ml_task_active = False  # Tracks if *any* blocking task is running

        self.graphics_scene = None
        self.graphics_view = None
        self.image_count_label = None
        self.annotated_count_label = None
        self.auto_box_items = []
        self.last_box_data = None
        self.training_dashboard_instance = None

        # Initialize StateManager (uses the class determined by tier logic via imports)
        try:
            # Dummy needs list, real gets from session/default
            self.state = StateManager(class_list=["Object"])
            logger.info(
                f"StateManager initialized OK (Class: {StateManager.__name__})."
            )
        except Exception as e:
            logger.exception("CRITICAL FAILURE during StateManager initialization")
            QMessageBox.critical(
                self,
                "StateManager Init Error",
                f"Could not initialize StateManager:\n{e}",
            )
            # If this happens, StateManager should be the dummy already
            # Check just in case the dummy failed somehow too
            if (
                not isinstance(self.state, StateManager)
                or StateManager.__name__ != "_DummyStateManager"
            ):
                QMessageBox.critical(
                    self, "Fatal Error", "Could not initialize ANY StateManager."
                )
                sys.exit(1)  # Critical failure if even dummy fails

        # Initialize Graphics Components
        try:
            # Uses class determined above
            self.graphics_scene = AnnotationScene(self)
            # Uses class determined above
            self.graphics_view = AnnotatorGraphicsView(self.graphics_scene, self)
            logger.info("Graphics Scene & View initialized OK.")
        except Exception as e:
            logger.critical(
                f"CRITICAL FAILURE during Graphics initialization: {e}", exc_info=True
            )
            QMessageBox.critical(
                self, "UI Init Error", f"Could not initialize graphics components:\n{e}"
            )
            # Check if we fell back to dummy scene; if not, exit
            if AnnotationScene.__name__ == "DummyAnnotationScene":
                logger.warning("Falling back to dummy graphics components.")
            else:
                sys.exit(1)  # Exit if real graphics failed and no dummy available

        # Initialize UI Layout and Widgets
        try:
            self.initUI()  # UI setup will now check self.current_tier
            logger.info("initUI completed.")
        except Exception as init_ui_err:
            logger.critical(
                f"CRITICAL FAILURE during initUI method: {init_ui_err}", exc_info=True
            )
            QMessageBox.critical(
                self,
                "Fatal UI Error",
                f"An error occurred during UI initialization:\n{init_ui_err}",
            )
            sys.exit(1)

        # Connect StateManager Signals
        if self.state:
            try:
                # Connect signals that exist on BOTH real and dummy
                if hasattr(self.state, "task_running"):
                    self.state.task_running.connect(self.on_ml_task_running_changed)
                if hasattr(self.state, "settings_changed"):
                    self.state.settings_changed.connect(self.handle_settings_changed)
                # Progress/error signals MIGHT exist on dummy
                if hasattr(self.state, "prediction_progress"):
                    self.state.prediction_progress.connect(self.update_status)
                if hasattr(self.state, "prediction_error"):
                    self.state.prediction_error.connect(self.handle_task_error)
                if hasattr(self.state, "training_progress"):
                    self.state.training_progress.connect(self.update_status)
                if hasattr(self.state, "training_error"):
                    self.state.training_error.connect(self.handle_task_error)

                # --- TIERING: Connect PRO-only signals conditionally ---
                if self.current_tier == "PRO":
                    if hasattr(self.state, "prediction_finished"):
                        self.state.prediction_finished.connect(
                            self.handle_prediction_results
                        )
                        logger.debug("[PRO] Connected prediction_finished signal.")
                    else:
                        logger.warning(
                            "[PRO] StateManager missing prediction_finished signal."
                        )
                    if hasattr(self.state, "training_run_completed"):
                        self.state.training_run_completed.connect(
                            self.handle_training_run_completed
                        )
                        logger.debug("[PRO] Connected training_run_completed signal.")
                    else:
                        logger.warning(
                            "[PRO] StateManager missing training_run_completed signal."
                        )
                logger.debug("StateManager signals connected OK (respecting tier).")
            except Exception as sig_err:
                logger.error(
                    f"Error connecting StateManager signals: {sig_err}", exc_info=True
                )
                QMessageBox.warning(
                    self,
                    "Signal Error",
                    f"Could not connect all StateManager signals:\n{sig_err}",
                )
        else:
            logger.error(
                "CRITICAL: No StateManager instance available for signal connection."
            )

        # Connect Scene Signals (should exist on real/dummy)
        if self.graphics_scene and hasattr(self.graphics_scene, "annotationsModified"):
            self.graphics_scene.annotationsModified.connect(
                self.handle_scene_modification
            )
        else:
            logger.warning("Cannot connect scene annotationsModified signal.")

        # Initial UI State
        if hasattr(self, "bbox_tool_button"):
            self.set_tool_active("bbox")
        self.update_status("Ready. Load directory or session.")
        self._update_image_count_label()
        self._update_annotated_count_label()
        # Set initial enabled state based on whether a task might be running (unlikely at init)
        self.on_ml_task_running_changed(
            self.state.is_task_active()
            if self.state and hasattr(self.state, "is_task_active")
            else False
        )

        # Set initial confidence value (Pro relevant)
        # Only do this if the spinbox actually exists (i.e., was created in initUI)
        if hasattr(self, "confidence_spinbox"):
            try:
                conf_key = config.SETTING_KEYS.get("confidence_threshold")
                conf_default = config.DEFAULT_CONFIDENCE_THRESHOLD
                conf = (
                    self.state.get_setting(conf_key, conf_default)
                    if self.state and conf_key and hasattr(self.state, "get_setting")
                    else conf_default
                )
                conf_percent = int(conf * 100)
                min_val, max_val = (
                    self.confidence_spinbox.minimum(),
                    self.confidence_spinbox.maximum(),
                )
                self.confidence_spinbox.setValue(
                    max(min_val, min(conf_percent, max_val))
                )
            except Exception as e:
                logger.error(f"Failed to set initial confidence spinbox value: {e}")

        # Connect confidence spinbox signal (Pro relevant)
        # Connect only if PRO tier and the widget exists
        if hasattr(self, "confidence_spinbox") and self.current_tier == "PRO":
            self.confidence_spinbox.valueChanged.connect(
                self.on_confidence_spinbox_changed
            )
            logger.debug("[PRO] Connected confidence_spinbox valueChanged signal.")

        # Clear image if none loaded
        if isinstance(self.graphics_scene, AnnotationScene):
            current_img_exists = (
                bool(self.state.get_current_image())
                if self.state and hasattr(self.state, "get_current_image")
                else False
            )
            if not current_img_exists:
                try:
                    self.graphics_scene.set_image(None)
                except Exception as clear_err:
                    logger.error(
                        f"Error initially clearing graphics scene: {clear_err}"
                    )
        elif AnnotationScene.__name__ == "DummyAnnotationScene":
            logger.warning("Skipping initial scene clear - using dummy scene.")

        logger.info(
            f"AnnotatorWindow initialization complete for Tier: {self.current_tier}."
        )
        print(f"--- AnnotatorWindow Initialized [{self.current_tier}] ---")

    # --- Methods ---

    def set_enabled_safe(self, widget_attr_name, enabled_state):
        """Safely sets the enabled state of a widget attribute."""
        widget = getattr(self, widget_attr_name, None)
        if widget and hasattr(widget, "setEnabled"):
            try:
                widget.setEnabled(bool(enabled_state))  # Ensure boolean
            except Exception as e:
                logger.error(f"Error setting enabled state for {widget_attr_name}: {e}")
        elif not widget:
            # Don't log error if widget just doesn't exist (Pro widget in Basic)
            # Check if it's expected for the current tier before logging debug
            is_pro_widget = widget_attr_name in [
                "auto_group",
                "auto_box_button",
                "confidence_spinbox",
                "force_mini_train_button",
                "training_dashboard_button",
                "export_model_action",
            ]
            if is_pro_widget and self.current_tier != "PRO":
                pass  # Expected missing widget in Basic tier
            else:
                logger.debug(
                    f"Widget not found for set_enabled_safe: {widget_attr_name}"
                )

    def _update_image_count_label(self):
        """Updates the image count label (e.g., 'Image 5 / 100')."""
        count_label = getattr(self, "image_count_label", None)
        if not count_label:
            return
        current_num_str, total_num_str = "-", "-"
        if (
            self.state
            and hasattr(self.state, "image_list")
            and self.state.image_list is not None
        ):
            try:
                total_num = len(self.state.image_list)
                total_num_str = str(total_num)
                if (
                    hasattr(self.state, "current_index")
                    and isinstance(self.state.current_index, int)
                    and 0 <= self.state.current_index < total_num
                ):
                    current_num_str = str(self.state.current_index + 1)
                else:
                    current_num_str = (
                        "0" if total_num == 0 else "?"
                    )  # Handle empty list or invalid index
            except Exception:
                total_num_str = "Err"  # Handle potential errors gracefully
        # Check if using dummy state manager
        is_dummy = StateManager.__name__ == "_DummyStateManager"
        label_text = f"Image {current_num_str} / {total_num_str}"
        if is_dummy:
            label_text += " (Dummy State)"
        count_label.setText(label_text)

    def _update_annotated_count_label(self):
        """Updates the annotated count label (e.g., 'Approved: 25')."""
        count_label = getattr(self, "annotated_count_label", None)
        if not count_label:
            return
        annotated_num_str = "-"
        if self.state and hasattr(self.state, "approved_count"):
            is_dummy = StateManager.__name__ == "_DummyStateManager"
            try:
                count_val = self.state.approved_count
                if isinstance(count_val, int):
                    annotated_num_str = str(count_val)
                elif count_val is None:
                    annotated_num_str = "0"  # Assume 0 if None
                else:
                    annotated_num_str = "Invalid"
                if is_dummy:
                    annotated_num_str += " (Dummy)"
            except Exception:
                annotated_num_str = "Error"
        count_label.setText(f"Approved: {annotated_num_str}")

    def initUI(self):
        """Initializes the main UI layout and widgets, respecting tier."""
        print("--- Starting initUI ---")
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(10)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        controls_group = QGroupBox("Controls")
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setContentsMargins(5, 8, 5, 8)
        controls_layout.setSpacing(5)

        # --- Tools Group (Basic & Pro) ---
        tool_group = QGroupBox("Tools")
        tool_layout = QHBoxLayout(tool_group)
        tool_layout.setContentsMargins(5, 5, 5, 5)
        tool_layout.setSpacing(6)
        self.bbox_tool_button = QToolButton()
        self.bbox_tool_button.setText("Draw BBox")
        self.bbox_tool_button.setCheckable(True)
        self.bbox_tool_button.setChecked(True)
        self.bbox_tool_button.setToolTip(
            "Select to draw bounding boxes (Double-click box to change class, 'C' to copy last box)"
        )
        self.bbox_tool_button.clicked.connect(lambda: self.set_tool_active("bbox"))
        tool_layout.addWidget(self.bbox_tool_button)
        controls_layout.addWidget(tool_group)

        # --- Main Buttons Stack (Create all, hide/disable later) ---
        btn_stack_widget = QWidget()
        btn_stack_layout = QVBoxLayout(btn_stack_widget)
        btn_stack_layout.setContentsMargins(0, 0, 0, 0)
        btn_stack_layout.setSpacing(8)

        # Basic Buttons
        self.load_button = QPushButton("Load Image Directory")
        self.load_button.setToolTip("Load all images from a selected folder")
        self.load_button.clicked.connect(self.load_directory)
        btn_stack_layout.addWidget(self.load_button)

        self.load_session_button = QPushButton("Load Session")
        self.load_session_button.setToolTip(
            "Load a previously saved annotation session (.json)"
        )
        self.load_session_button.clicked.connect(self.load_session_explicitly)
        btn_stack_layout.addWidget(self.load_session_button)

        self.save_session_button = QPushButton("Save Session")
        self.save_session_button.setToolTip("Save current annotations and image list")
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
            "Add, remove, or rename annotation classes"
        )
        self.manage_classes_button.clicked.connect(self.manage_classes)
        btn_stack_layout.addWidget(self.manage_classes_button)

        # Pro Buttons (Create them here, add [PRO] suffix for clarity)
        self.force_mini_train_button = QPushButton("Force Mini-Train [PRO]")
        self.force_mini_train_button.setToolTip(
            "[PRO] Manually trigger training using '20 image' parameters"
        )
        self.force_mini_train_button.clicked.connect(self.force_mini_training)
        btn_stack_layout.addWidget(self.force_mini_train_button)

        self.training_dashboard_button = QPushButton("Training Dashboard [PRO]")
        self.training_dashboard_button.setToolTip(
            "[PRO] Open dashboard for training stats and settings"
        )
        self.training_dashboard_button.clicked.connect(self.open_training_dashboard)
        btn_stack_layout.addWidget(self.training_dashboard_button)

        controls_layout.addWidget(btn_stack_widget)
        left_layout.addWidget(controls_group)

        # --- Info Labels (Basic & Pro) ---
        self.image_count_label = QLabel("Image - / -")
        self.image_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.image_count_label)
        self.annotated_count_label = QLabel("Approved: -")
        self.annotated_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.annotated_count_label)

        # --- Auto Annotation Group (Create all UI, hide/disable later) ---
        self.auto_group = QGroupBox("Auto Annotation [PRO]")  # Add [PRO] suffix
        auto_layout = QVBoxLayout(self.auto_group)
        auto_layout.setContentsMargins(5, 8, 5, 8)
        auto_layout.setSpacing(5)
        self.auto_box_button = QCheckBox("Show Suggestions")
        self.auto_box_button.setToolTip(
            "[PRO] Show AI suggestions (Double-click to accept)"
        )
        self.auto_box_button.toggled.connect(self.toggle_auto_boxes)
        auto_layout.addWidget(self.auto_box_button)

        self.conf_layout_widget = QWidget()  # Widget to hold label+spinbox
        conf_layout = QHBoxLayout(self.conf_layout_widget)
        conf_layout.setContentsMargins(0, 0, 0, 0)
        conf_layout.addWidget(QLabel("Confidence:"))
        self.confidence_spinbox = QSpinBox()
        self.confidence_spinbox.setRange(0, 100)
        self.confidence_spinbox.setSuffix("%")
        self.confidence_spinbox.setToolTip(
            "[PRO] Minimum confidence for suggestions (0-100%)"
        )
        try:
            default_conf = config.DEFAULT_CONFIDENCE_THRESHOLD
            self.confidence_spinbox.setValue(int(default_conf * 100))
        except Exception:
            self.confidence_spinbox.setValue(25)
        # Connect valueChanged signal in __init__ after spinbox is created
        conf_layout.addWidget(self.confidence_spinbox)
        auto_layout.addWidget(self.conf_layout_widget)  # Add inner widget
        left_layout.addWidget(self.auto_group)  # Add the group to the main layout

        left_layout.addStretch(1)

        # --- Graphics View Setup (Basic & Pro) ---
        if not self.graphics_view:
            logger.critical("!!! graphics_view is None during initUI !!!")
            self.graphics_view = QWidget()  # Dummy to prevent crash
        else:
            self.graphics_view.setMinimumWidth(400)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.graphics_view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 640])

        # --- Bottom Layout (Approve Button - Basic & Pro) ---
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch(1)
        self.approve_button = QPushButton("Approve && Next Unannotated")
        self.approve_button.setStyleSheet(
            "background-color: lightgreen; padding: 5px; font-weight: bold;"
        )
        self.approve_button.setToolTip(
            "Mark current annotations as reviewed and move to the next unannotated image"
        )
        self.approve_button.clicked.connect(self.approve_image)
        bottom_layout.addWidget(self.approve_button)

        main_layout.addWidget(splitter, 1)
        main_layout.addLayout(bottom_layout)
        self.setCentralWidget(central_widget)

        self.status_bar = self.statusBar()
        self.status_label = QLabel("Initializing...")
        self.status_bar.addWidget(self.status_label)

        # --- Menu Bar (Create all actions, hide/disable later) ---
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")

        # Basic Actions
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

        # Pro Action (Create it, add [PRO] suffix)
        self.export_model_action = QAction("Export Trained Model [PRO]...", self)
        self.export_model_action.setToolTip("[PRO] Save the latest trained model (.pt)")
        self.export_model_action.triggered.connect(self.export_model)
        file_menu.addAction(self.export_model_action)

        # Basic Action
        self.export_data_action = QAction("Export Annotated Data (YOLO)...", self)
        self.export_data_action.setToolTip(
            "Export approved annotations/images in YOLO format"
        )
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

        # --- APPLY TIER RESTRICTIONS ---
        self._apply_tier_restrictions()  # Call helper function

        print("--- Finished initUI ---")

    def _apply_tier_restrictions(self):
        """Hides or disables UI elements based on self.current_tier."""
        is_pro = self.current_tier == "PRO"
        logger.info(
            f"Applying UI restrictions for Tier: {self.current_tier} (Is Pro: {is_pro})"
        )

        # Find widgets safely using getattr
        auto_group_widget = getattr(self, "auto_group", None)
        force_train_btn = getattr(self, "force_mini_train_button", None)
        train_dash_btn = getattr(self, "training_dashboard_button", None)
        export_model_act = getattr(self, "export_model_action", None)
        auto_box_btn = getattr(self, "auto_box_button", None)
        conf_spinbox = getattr(self, "confidence_spinbox", None)
        conf_layout_widget = getattr(
            self, "conf_layout_widget", None
        )  # Get the layout holder too

        # Hide/Show entire sections or specific buttons/actions
        if auto_group_widget:
            auto_group_widget.setVisible(is_pro)
        if force_train_btn:
            force_train_btn.setVisible(is_pro)
        if train_dash_btn:
            train_dash_btn.setVisible(is_pro)
        if export_model_act:
            export_model_act.setVisible(is_pro)

        # Also set enabled state (might be redundant if hidden, but good practice)
        self.set_enabled_safe("auto_box_button", is_pro)
        # self.set_enabled_safe("confidence_spinbox", is_pro) # Enabled state depends on checkbox
        self.set_enabled_safe("force_mini_train_button", is_pro)
        self.set_enabled_safe("training_dashboard_button", is_pro)
        if export_model_act:
            export_model_act.setEnabled(is_pro)

        # Ensure checkbox is off if not Pro
        if auto_box_btn and not is_pro:
            auto_box_btn.setChecked(False)

        # Update confidence spinbox enabled state based on checkbox (if Pro)
        # Also enable/disable the layout holder for visual consistency
        if conf_spinbox and auto_box_btn:
            is_conf_enabled = is_pro and auto_box_btn.isChecked()
            conf_spinbox.setEnabled(is_conf_enabled)
            if conf_layout_widget:
                conf_layout_widget.setEnabled(is_conf_enabled)

        logger.info("Finished applying tier restrictions to UI.")

    # --- Scene Modification Slot ---
    @pyqtSlot()
    def handle_scene_modification(self):
        """Handles signal that annotations were modified in the scene."""
        logger.debug("Scene annotations modified by user interaction.")
        # Could potentially enable the save button here

    @pyqtSlot(int)
    def on_confidence_spinbox_changed(self, value: int):
        """Updates confidence threshold setting (PRO ONLY)."""
        # --- TIER CHECK ---
        if self.current_tier != "PRO":
            # This shouldn't be called if basic, but check anyway
            logger.warning("[BASIC] on_confidence_spinbox_changed called unexpectedly.")
            return
        # --- END TIER CHECK ---

        is_dummy_state = StateManager.__name__ == "_DummyStateManager"
        if not self.state or is_dummy_state:
            return  # Ignore if dummy

        conf_key = config.SETTING_KEYS.get("confidence_threshold")
        if conf_key and hasattr(self.state, "set_setting"):
            try:
                new_threshold_float = float(value) / 100.0
                self.state.set_setting(conf_key, new_threshold_float)
                logger.debug(
                    f"[PRO] Confidence threshold setting updated to {new_threshold_float:.2f} ({value}%)"
                )
                # No need to re-trigger prediction here, happens when checkbox is toggled or image loaded
            except Exception as e:
                logger.error(f"Error updating confidence setting from spinbox: {e}")
        else:
            logger.error(
                "Cannot update confidence: Setting key or set_setting missing."
            )

    def set_tool_active(self, tool_name):
        """Sets the active tool in the graphics scene."""
        logger.debug(f"Set tool requested: {tool_name}")
        scene = getattr(self, "graphics_scene", None)
        # Check if it's the *real* AnnotationScene
        if isinstance(scene, AnnotationScene) and hasattr(scene, "set_tool"):
            if tool_name == "bbox":
                scene.set_tool(tool_name)
                btn = getattr(self, "bbox_tool_button", None)
                if btn and not btn.isChecked():
                    btn.setChecked(True)
                self.update_status("Tool: Draw BBox")
            # Add other tools here if needed
            # elif tool_name == "select":
            #     scene.set_tool(tool_name)
            #     # Update button states if you add a select tool button
            #     self.update_status("Tool: Select/Modify")
            else:
                logger.warning(f"Unhandled tool: {tool_name}, reverting.")
                scene.set_tool("bbox")  # Default back to bbox
                btn = getattr(self, "bbox_tool_button", None)
                if btn and not btn.isChecked():
                    btn.setChecked(True)
                self.update_status("Tool: Reverted to BBox Tool")
        else:
            # Log error if scene is invalid or the dummy scene
            logger.error(f"Cannot set tool: Scene invalid/dummy ({type(scene)}).")
            btn = getattr(self, "bbox_tool_button", None)
            if btn:
                btn.setChecked(False)  # Uncheck button if scene is bad

    def paste_last_box(self):
        """Pastes last approved box (Basic & Pro)."""
        logger.debug("Paste last box requested (centered).")
        scene = getattr(self, "graphics_scene", None)
        # Check if it's the real scene and has a valid image
        scene_is_valid = (
            isinstance(scene, AnnotationScene)
            and hasattr(scene, "image_item")
            and scene.image_item
            and not scene.image_item.pixmap().isNull()
        )

        if self.last_box_data and scene_is_valid:
            try:
                stored_rect = self.last_box_data.get("rect")
                class_label = self.last_box_data.get("class")
                if not isinstance(stored_rect, QRectF) or not class_label:
                    logger.warning("Invalid last_box_data format.")
                    return

                width, height = stored_rect.width(), stored_rect.height()
                if width <= 0 or height <= 0:
                    logger.warning(f"Invalid size in last_box_data: {width}x{height}")
                    return

                # Get current image scene rect
                current_rect = scene.image_item.sceneBoundingRect()
                if not current_rect.isValid() or current_rect.isEmpty():
                    logger.warning("Cannot paste: Scene rect invalid.")
                    return

                # Calculate center and new top-left
                center_x = current_rect.center().x()
                center_y = current_rect.center().y()
                paste_x = center_x - (width / 2.0)
                paste_y = center_y - (height / 2.0)

                # Clamp position to be within image boundaries
                paste_x_c = max(
                    current_rect.left(), min(paste_x, current_rect.right() - width)
                )
                paste_y_c = max(
                    current_rect.top(), min(paste_y, current_rect.bottom() - height)
                )
                # Ensure it doesn't go past left/top edge if size makes it impossible
                paste_x_c = max(current_rect.left(), paste_x_c)
                paste_y_c = max(current_rect.top(), paste_y_c)

                new_rect = QRectF(paste_x_c, paste_y_c, width, height)

                # Check if using Dummy ResizableRectItem
                rect_item_class = (
                    ResizableRectItem  # Use the assigned class (real or dummy)
                )
                if rect_item_class.__name__ == "DummyResizableRectItem":
                    logger.error("Cannot paste: Using DummyResizableRectItem.")
                    return

                # Create and add the new item
                item = rect_item_class(new_rect, class_label, is_suggestion=False)
                scene.addItem(item)
                item.setSelected(True)  # Select the newly pasted item
                logger.info(f"Pasted box: {class_label} at {new_rect}")
                self.update_status(f"Pasted box: {class_label} (centered)")
                if hasattr(scene, "annotationsModified"):
                    scene.annotationsModified.emit()  # Signal modification

            except Exception as e:
                logger.error(f"Error pasting last box: {e}", exc_info=True)
                self.update_status("Paste failed.")
        elif not self.last_box_data:
            logger.warning("Paste failed: No box data stored.")
            self.update_status("Paste failed: No previous box.")
        else:  # Scene not valid
            logger.warning("Paste failed: Scene or image not ready.")
            self.update_status("Paste failed: Load image first.")

    def open_settings_dialog(self):
        """Opens legacy settings dialog (Basic & Pro)."""
        if not self.state:
            QMessageBox.warning(
                self, "Error", "Settings unavailable (State Manager missing)."
            )
            return

        dlg_class = SettingsDialog  # Use assigned class (real or dummy)
        if dlg_class.__name__ == "DummySettingsDialog":
            QMessageBox.warning(
                self, "UI Error", "Settings unavailable (dummy component)."
            )
            return

        try:
            # Pass the state manager instance to the dialog
            dlg = dlg_class(self.state, self)
            dlg.exec()  # Show modally
        except Exception as e:
            logger.exception("Legacy Settings dialog failed")
            QMessageBox.critical(self, "Dialog Error", f"Error opening settings: {e}")

    def open_training_dashboard(self):
        """Opens training dashboard dialog (PRO ONLY)."""
        # --- TIER CHECK ---
        if self.current_tier != "PRO":
            QMessageBox.information(
                self,
                "Feature Unavailable",
                "The Training Dashboard requires the Pro tier.",
            )
            logger.warning("[BASIC] Attempted to open Training Dashboard.")
            return
        # --- END TIER CHECK ---

        is_dummy_state = StateManager.__name__ == "_DummyStateManager"
        if not self.state or is_dummy_state:
            QMessageBox.warning(
                self, "Error", "Dashboard unavailable (State Manager missing or dummy)."
            )
            return

        dashboard_class = TrainingDashboard  # Use assigned class (real or dummy)
        if dashboard_class.__name__ == "DummyTrainingDashboard":
            QMessageBox.warning(
                self, "Error", "Dashboard unavailable (using dummy component)."
            )
            return

        # Prevent opening multiple instances
        if self.training_dashboard_instance is not None:
            logger.info("Training dashboard already open. Activating.")
            self.training_dashboard_instance.raise_()
            self.training_dashboard_instance.activateWindow()
            return

        try:
            dlg = dashboard_class(self.state, self)
            self.training_dashboard_instance = dlg  # Store reference
            # Connect finished signal to clear the reference when closed
            dlg.finished.connect(self.clear_dashboard_instance)
            dlg.show()  # Show non-modally
        except Exception as e:
            logger.exception("Training dashboard failed to open")
            QMessageBox.critical(self, "Dialog Error", f"Error opening dashboard:\n{e}")
            self.training_dashboard_instance = None  # Clear ref on error

    @pyqtSlot()
    def clear_dashboard_instance(self):
        """Slot called when training dashboard closes."""
        logger.debug("Training dashboard closed, clearing instance reference.")
        self.training_dashboard_instance = None

    def export_model(self):
        """Exports trained model file (PRO ONLY)."""
        # --- TIER CHECK ---
        if self.current_tier != "PRO":
            QMessageBox.information(
                self, "Feature Unavailable", "Model Export requires the Pro tier."
            )
            logger.warning("[BASIC] Attempted to export model.")
            return
        # --- END TIER CHECK ---

        print("--- export_model called ---")
        is_dummy_state = StateManager.__name__ == "_DummyStateManager"
        if not self.state or is_dummy_state:
            QMessageBox.warning(
                self, "Error", "Export unavailable (State Manager missing or dummy)."
            )
            return

        model_key = config.SETTING_KEYS.get("model_save_path")
        if not model_key:
            QMessageBox.critical(
                self, "Config Error", "Model save path key missing in config."
            )
            return

        internal_model_path = self.state.get_setting(
            model_key, config.DEFAULT_MODEL_SAVE_PATH
        )
        logger.debug(f"Checking for internal model at: {internal_model_path}")

        if not internal_model_path or not os.path.exists(internal_model_path):
            QMessageBox.warning(
                self,
                "Model Not Found",
                f"Trained model not found:\n{internal_model_path}\n\nTrain the model at least once.",
            )
            return

        # Suggest filename and location
        default_filename = os.path.basename(internal_model_path)
        start_dir = os.path.expanduser("~")  # Default to user's home directory
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Trained Model As...",
            os.path.join(start_dir, default_filename),
            "PyTorch Model (*.pt)",
        )

        if save_path:
            # Ensure .pt extension
            if not save_path.lower().endswith(".pt"):
                save_path += ".pt"
            try:
                self.update_status(
                    f"Exporting model to {os.path.basename(save_path)}..."
                )
                QCoreApplication.processEvents()  # Update UI
                shutil.copy2(internal_model_path, save_path)  # Copy the file
                self.update_status(f"Model exported: {os.path.basename(save_path)}.")
                logger.info(
                    f"[PRO] Model exported from {internal_model_path} to {save_path}"
                )
            except Exception as e:
                logger.exception(f"Failed to export model to {save_path}")
                QMessageBox.critical(
                    self, "Export Error", f"Failed to copy model file:\n{e}"
                )
                self.update_status("Model export failed.")
        else:
            self.update_status("Model export cancelled.")
            logger.info("Model export cancelled by user.")

    def export_annotated_data(self):
        """Exports approved annotations in YOLO format (Basic & Pro)."""
        print("--- export_annotated_data called ---")
        is_dummy_state = StateManager.__name__ == "_DummyStateManager"
        if not self.state or is_dummy_state:
            QMessageBox.warning(
                self, "Error", "Export unavailable (State Manager missing or dummy)."
            )
            return
        # Check if the state manager (real or dummy) has the required method
        if not hasattr(self.state, "export_data_for_yolo"):
            QMessageBox.critical(
                self,
                "Internal Error",
                "State Manager missing 'export_data_for_yolo' method.",
            )
            return

        # Check if there's anything approved to export
        approved_exists = False
        if hasattr(self.state, "annotations") and isinstance(
            self.state.annotations, dict
        ):
            approved_exists = any(
                d.get("approved", False) for d in self.state.annotations.values()
            )

        if not approved_exists:
            QMessageBox.information(
                self, "No Data", "No approved annotations available to export."
            )
            return

        # Suggest starting directory (last image dir or home)
        last_img_dir_key = config.SETTING_KEYS.get("last_image_dir")
        start_dir = (
            self.state.get_setting(last_img_dir_key, os.path.expanduser("~"))
            if self.state and last_img_dir_key and hasattr(self.state, "get_setting")
            else os.path.expanduser("~")
        )
        start_dir = (
            start_dir if os.path.isdir(start_dir) else os.path.expanduser("~")
        )  # Fallback if saved path invalid

        export_dir = QFileDialog.getExistingDirectory(
            self, "Select Directory to Export YOLO Data Into", start_dir
        )

        if export_dir:
            logger.info(f"User selected directory for YOLO export: {export_dir}")
            # Check if directory is empty, warn if not
            try:
                if os.listdir(export_dir):
                    reply = QMessageBox.warning(
                        self,
                        "Directory Not Empty",
                        f"Directory is not empty:\n{export_dir}\nExporting will create/overwrite 'images', 'labels', 'dataset.yaml'.\n\nContinue?",
                        QMessageBox.StandardButton.Yes
                        | QMessageBox.StandardButton.Cancel,
                        QMessageBox.StandardButton.Cancel,
                    )
                    if reply == QMessageBox.StandardButton.Cancel:
                        self.update_status("Data export cancelled.")
                        return
            except OSError as e:
                QMessageBox.critical(
                    self,
                    "Directory Error",
                    f"Cannot access directory:\n{export_dir}\nError: {e}",
                )
                return

            # Proceed with export
            try:
                self.update_status(
                    f"Exporting YOLO data to {os.path.basename(export_dir)}..."
                )
                QCoreApplication.processEvents()
                # State Manager handles the details of copying files and creating YAML
                yaml_path = self.state.export_data_for_yolo(export_dir)
                if yaml_path and os.path.exists(yaml_path):
                    self.update_status(
                        f"YOLO data exported: {os.path.basename(export_dir)}."
                    )
                    logger.info(
                        f"YOLO data export successful. Target: {export_dir}, YAML: {yaml_path}"
                    )
                else:
                    logger.error(
                        f"Data export failed (StateManager returned: {yaml_path}). Check logs."
                    )
                    QMessageBox.warning(
                        self,
                        "Export Failed",
                        "Failed to export data. Check logs (app_debug.log).",
                    )
                    self.update_status("Data export failed.")

            except Exception as e:
                logger.exception(f"Unexpected error during data export to {export_dir}")
                QMessageBox.critical(
                    self, "Export Error", f"Unexpected error during data export:\n{e}"
                )
                self.update_status("Data export failed.")
        else:
            self.update_status("Data export cancelled.")
            logger.info("Data export cancelled by user.")

    @pyqtSlot()
    def force_mini_training(self):
        """Manually triggers training run (PRO ONLY)."""
        # --- TIER CHECK ---
        if self.current_tier != "PRO":
            QMessageBox.information(
                self, "Feature Unavailable", "Manual Training requires the Pro tier."
            )
            logger.warning("[BASIC] Attempted to force mini-training.")
            return
        # --- END TIER CHECK ---

        logger.info("[PRO] Force mini-training requested by user.")
        is_dummy_state = StateManager.__name__ == "_DummyStateManager"
        if not self.state or is_dummy_state:
            QMessageBox.warning(
                self, "Error", "Training unavailable (State Manager missing or dummy)."
            )
            return
        if self.state.is_task_active():
            QMessageBox.warning(
                self, "Busy", "Another background task is currently running."
            )
            return

        # Check if there are approved images
        current_approved_count = 0
        if hasattr(self.state, "approved_count"):
            current_approved_count = self.state.approved_count
        elif hasattr(self.state, "annotations"):  # Fallback count
            current_approved_count = sum(
                1 for d in self.state.annotations.values() if d.get("approved")
            )

        if current_approved_count <= 0:
            QMessageBox.information(
                self, "No Data", "Cannot force training without any approved images."
            )
            return

        try:
            # Get relevant settings for mini-train
            epochs_key = config.SETTING_KEYS.get("epochs_20")
            lr_key = config.SETTING_KEYS.get("lr_20")
            if not epochs_key or not lr_key:
                QMessageBox.critical(
                    self,
                    "Config Error",
                    "Training parameter keys ('epochs_20', 'lr_20') missing.",
                )
                return

            epochs = self.state.get_setting(epochs_key, config.DEFAULT_EPOCHS_20)
            lr = self.state.get_setting(lr_key, config.DEFAULT_LR_20)
            prefix = "force_mini"  # Use a specific prefix for manual runs

            self.update_status(
                f"Starting forced mini-training ({epochs} epochs, LR {lr:.6f})..."
            )
            QCoreApplication.processEvents()

            if not hasattr(self.state, "start_training_task"):
                logger.error("State manager missing 'start_training_task' method.")
                QMessageBox.critical(
                    self, "Internal Error", "Cannot start training task."
                )
                return

            # State manager handles data preparation and worker start
            success = self.state.start_training_task(epochs, lr, prefix)
            if not success:
                # StateManager should have emitted an error signal or logged
                self.update_status("Failed to start forced training task.")

        except Exception as e:
            logger.exception("Error initiating forced mini-training.")
            QMessageBox.critical(
                self, "Error", f"Could not start forced training:\n{e}"
            )
            self.update_status("Error starting forced training.")

    @pyqtSlot()
    def handle_settings_changed(self):
        """Updates relevant UI elements when settings change."""
        logger.info("GUI: Settings changed signal received.")
        if self.state:
            try:
                # Update confidence spinbox (only if Pro and widget exists)
                if self.current_tier == "PRO":
                    spin = getattr(self, "confidence_spinbox", None)
                    if spin:
                        conf_key = config.SETTING_KEYS.get("confidence_threshold")
                        conf_default = config.DEFAULT_CONFIDENCE_THRESHOLD
                        conf = (
                            self.state.get_setting(conf_key, conf_default)
                            if conf_key and hasattr(self.state, "get_setting")
                            else conf_default
                        )
                        spin.blockSignals(True)  # Prevent triggering valueChanged slot
                        conf_percent = int(conf * 100)
                        min_val, max_val = spin.minimum(), spin.maximum()
                        spin.setValue(max(min_val, min(conf_percent, max_val)))
                        spin.blockSignals(False)
                        logger.debug(
                            f"[PRO] Updated confidence spinbox to {conf_percent}% from settings"
                        )

                # Re-evaluate enabled state based on new settings and task status
                self.on_ml_task_running_changed(self._ml_task_active)

                status_msg = "Settings updated."
                # Add warning if pipeline seems missing (relevant for Pro)
                is_dummy_state = StateManager.__name__ == "_DummyStateManager"
                is_dummy_pipeline = TrainingPipeline.__name__.startswith("_Dummy")
                if self.current_tier == "PRO" and (
                    is_dummy_state
                    or is_dummy_pipeline
                    or not hasattr(self.state, "training_pipeline")
                    or not self.state.training_pipeline
                ):
                    status_msg += " Warning: ML Pipeline may be unavailable."
                self.update_status(status_msg)

            except Exception as e:
                logger.error(
                    f"Error applying settings changes to UI: {e}", exc_info=True
                )
        else:
            logger.warning("Cannot apply settings changes: State Manager unavailable.")

    @pyqtSlot(str)
    def update_status(self, message: str):
        """Updates the status bar label."""
        lbl = getattr(self, "status_label", None)
        if lbl:
            try:
                lbl.setText(str(message) if message is not None else "")
                QCoreApplication.processEvents()  # Ensure update is visible
            except Exception:
                logger.error("Failed to update status label.")

        # Simple logging distinction for progress vs final messages
        lower_msg = str(message).lower() if message else ""
        progress_keys = [
            "predict",
            "update",
            "train",
            "loading",
            "saving",
            "requesting",
            "checking",
            "navigat",
            "starting",
            "exporting",
        ]
        final_keys = [
            "complete",
            "error",
            "fail",
            "approved",
            "loaded",
            "saved",
            "ready",
            "found",
            "unavailable",
            "cancelled",
            "exported",
            "finished",
            "unchanged",
        ]
        is_progress = any(k in lower_msg for k in progress_keys)
        is_final = any(k in lower_msg for k in final_keys)
        if is_progress and not is_final:
            logger.debug(f"Status Update: {message}")
        else:
            logger.info(f"Status Update: {message}")

    # Inside the AnnotatorWindow class definition:

    def save_session(self):
        """Saves the current session via the StateManager."""
        if (
            self.state
            and hasattr(self.state, "is_task_active")
            and self.state.is_task_active()
        ):
            QMessageBox.warning(
                self, "Busy", "Cannot save session while a background task is running."
            )
            return
        if not self.state:
            QMessageBox.warning(
                self, "Error", "Save unavailable (State Manager missing)."
            )
            return
        if not hasattr(self.state, "save_session"):
            QMessageBox.critical(
                self, "Internal Error", "State Manager missing 'save_session' method."
            )
            return

        try:
            # Get the intended save path from settings (could be default or user-set)
            session_path_key = config.SETTING_KEYS.get("session_path")
            session_file = (
                self.state.get_setting(session_path_key, config.DEFAULT_SESSION_PATH)
                if session_path_key
                else config.DEFAULT_SESSION_PATH
            )

            self.update_status(f"Saving session to {os.path.basename(session_file)}...")
            QCoreApplication.processEvents()  # Update UI

            self.state.save_session()  # Call the state manager's save method

            # Check if save was successful (StateManager should log errors)
            # We can assume success if no exception occurred, but could add checks later if needed
            self.update_status(f"Session saved: {os.path.basename(session_file)}.")
            logger.info(f"Session saved successfully via UI action to {session_file}.")

        except Exception as e:
            logger.exception(f"Error during save_session UI action")
            QMessageBox.critical(self, "Save Error", f"Failed to save session:\n{e}")
            self.update_status("Session save failed.")

    # ... (rest of your AnnotatorWindow methods) ...

    def load_directory(self):
        """Opens dialog to select image directory and loads images."""
        if (
            self.state
            and hasattr(self.state, "is_task_active")
            and self.state.is_task_active()
        ):
            QMessageBox.warning(
                self,
                "Busy",
                "Cannot load directory while a background task is running.",
            )
            return
        if not self.state:
            QMessageBox.warning(self, "Error", "State Manager unavailable.")
            return

        last_dir_key = config.SETTING_KEYS.get("last_image_dir")
        last_dir = (
            self.state.get_setting(last_dir_key, os.path.expanduser("~"))
            if self.state and last_dir_key and hasattr(self.state, "get_setting")
            else os.path.expanduser("~")
        )
        last_dir = (
            last_dir if os.path.isdir(last_dir) else os.path.expanduser("~")
        )  # Fallback
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Image Directory", last_dir
        )

        if dir_path and self.state:
            # Save the selected directory path
            if last_dir_key and hasattr(self.state, "set_setting"):
                try:
                    self.state.set_setting(last_dir_key, dir_path)
                except Exception:
                    pass  # Non-critical if saving setting fails

            self.update_status(f"Loading images from: {os.path.basename(dir_path)}...")
            QCoreApplication.processEvents()
            try:
                if hasattr(self.state, "load_images_from_directory"):
                    self.state.load_images_from_directory(dir_path)
                else:
                    raise AttributeError(
                        "State Manager missing 'load_images_from_directory' method."
                    )
            except Exception as e:
                logger.exception("Failed StateManager.load_images_from_directory")
                QMessageBox.critical(self, "Load Error", f"Failed to load images:\n{e}")
                self.clear_ui_on_load_failure()  # Clear UI state
                return

            # Check if images were actually loaded
            img_list = getattr(self.state, "image_list", [])
            if img_list:
                # Ensure current index is valid (should be handled by state manager, but double check)
                idx = getattr(self.state, "current_index", -1)
                if not (isinstance(idx, int) and 0 <= idx < len(img_list)):
                    if hasattr(self.state, "go_to_image"):
                        self.state.go_to_image(0)  # Go to first if index invalid

                self.load_image()  # Load the first/current image
                self._update_annotated_count_label()  # Update count based on potentially reset state
                self.update_status(f"Loaded {len(img_list)} images.")
            else:
                self.clear_ui_on_load_failure()  # Clear UI if no images found
                self.update_status("No supported images found in directory.")
                QMessageBox.information(
                    self,
                    "No Images",
                    "No supported image files found in the selected directory.",
                )
        elif not dir_path:
            self.update_status("Load cancelled.")

    def clear_ui_on_load_failure(self):
        """Clears UI elements when loading fails or finds no images."""
        logger.debug("Clearing UI on load failure/empty.")
        scene = getattr(self, "graphics_scene", None)
        if isinstance(scene, AnnotationScene):
            scene.set_image(None)
            scene.clear_annotations()
        self.clear_suggestion_boxes()  # Clear any old suggestions
        self.setWindowTitle(f"Annotator [{self.current_tier}]")  # Reset title
        self._update_image_count_label()
        self._update_annotated_count_label()
        self.last_box_data = None  # Clear last pasted box

    def load_session_explicitly(self):
        """Opens dialog to select session file and loads."""
        if (
            self.state
            and hasattr(self.state, "is_task_active")
            and self.state.is_task_active()
        ):
            QMessageBox.warning(
                self, "Busy", "Cannot load session while a background task is running."
            )
            return
        if not self.state:
            QMessageBox.warning(self, "Error", "State Manager unavailable.")
            return

        session_key = config.SETTING_KEYS.get("session_path")
        start_path = (
            self.state.get_setting(session_key, config.DEFAULT_SESSION_PATH)
            if self.state and session_key and hasattr(self.state, "get_setting")
            else config.DEFAULT_SESSION_PATH
        )
        start_dir = (
            os.path.dirname(start_path)
            if start_path and os.path.dirname(start_path)
            else "."
        )
        start_dir = (
            start_dir if os.path.isdir(start_dir) else os.path.expanduser("~")
        )  # Fallback
        session_ext = os.path.splitext(config.DEFAULT_SESSION_FILENAME)[1]
        file_filter = f"Session Files (*{session_ext});;All Files (*)"
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Session", start_dir, file_filter
        )

        if file_path:
            self.update_status(f"Loading session: {os.path.basename(file_path)}...")
            QCoreApplication.processEvents()
            load_ok = False
            try:
                if hasattr(self.state, "load_session"):
                    load_ok = self.state.load_session(
                        file_path=file_path
                    )  # Pass specific path
                else:
                    raise AttributeError("State Manager missing 'load_session' method.")
            except Exception as e:
                logger.exception("Error during StateManager.load_session")
                QMessageBox.critical(self, "Load Error", f"Error loading session:\n{e}")
                self.clear_ui_on_load_failure()  # Clear UI state
                return

            if load_ok:
                self.update_status(f"Session loaded: {os.path.basename(file_path)}.")
                self.load_image()  # Load the image at the restored index
                self._update_annotated_count_label()  # Update count based on loaded data
                self.handle_settings_changed()  # Apply any settings potentially loaded from session/defaults
                # Re-apply enable state (task should not be running after load)
                self.on_ml_task_running_changed(False)
                # Add pipeline warning if needed
                status_msg = "Session loaded."
                is_dummy_state = StateManager.__name__ == "_DummyStateManager"
                is_dummy_pipeline = TrainingPipeline.__name__.startswith("_Dummy")
                if self.current_tier == "PRO" and (
                    is_dummy_state
                    or is_dummy_pipeline
                    or not hasattr(self.state, "training_pipeline")
                    or not self.state.training_pipeline
                ):
                    status_msg += " Warning: ML Pipeline may be unavailable."
                self.update_status(status_msg)
            else:
                # State manager reported failure (e.g., file corrupt)
                logger.error(
                    f"StateManager reported failure loading session file: {file_path}"
                )
                QMessageBox.critical(
                    self, "Load Error", f"Failed to load session file:\n{file_path}"
                )
                self.update_status("Session load failed.")
                self.clear_ui_on_load_failure()  # Clear UI state
        else:
            self.update_status("Load cancelled.")

    def next_image(self):
        """Navigate to the next image."""
        if (
            self.state
            and hasattr(self.state, "is_task_active")
            and self.state.is_task_active()
        ):
            self.update_status("Busy. Cannot navigate now.")
            return
        if not self.state or not hasattr(self.state, "next_image"):
            self.update_status("Navigation unavailable.")
            return
        try:
            if self.state.next_image():
                self.load_image()
            elif not self._ml_task_active:
                self.update_status("Already at the end.")  # Only show if not busy
        except Exception as e:
            logger.exception("Error navigating next")
            self.update_status("Navigation error.")

    def prev_image(self):
        """Navigate to the previous image."""
        if (
            self.state
            and hasattr(self.state, "is_task_active")
            and self.state.is_task_active()
        ):
            self.update_status("Busy. Cannot navigate now.")
            return
        if not self.state or not hasattr(self.state, "prev_image"):
            self.update_status("Navigation unavailable.")
            return
        try:
            if self.state.prev_image():
                self.load_image()
            elif not self._ml_task_active:
                self.update_status("Already at the start.")  # Only show if not busy
        except Exception as e:
            logger.exception("Error navigating previous")
            self.update_status("Navigation error.")

    def load_image(self, image_path=None):
        """Loads an image, displays annotations, triggers suggestions if Pro."""
        path_to_load = image_path
        source_info = "explicit path"
        current_img = None
        # If no path given, get from state manager
        if not path_to_load:
            if self.state and hasattr(self.state, "get_current_image"):
                current_img = self.state.get_current_image()
                if current_img:
                    path_to_load = current_img
                    idx = getattr(self.state, "current_index", "?")
                    source_info = f"state index {idx}"
                else:
                    source_info = "state has no current image"
            else:
                source_info = "state unavailable"

        base_name = os.path.basename(path_to_load) if path_to_load else "None"
        logger.info(f"Load Image Request: '{base_name}' (Source: {source_info}).")

        scene = getattr(self, "graphics_scene", None)
        # Check if scene is the real one, not dummy
        if not isinstance(scene, AnnotationScene):
            logger.critical(f"Cannot load image: Scene invalid/dummy ({type(scene)})!")
            self.clear_ui_on_load_failure()  # Clear UI if scene is bad
            return

        # Clear existing annotations and suggestions before loading new image
        try:
            scene.clear_annotations()
            self.clear_suggestion_boxes()
            logger.debug("Cleared scene items before loading new image.")
        except Exception:
            logger.exception("Error clearing scene before load.")

        load_ok = False
        img_width, img_height = 0, 0
        if path_to_load and os.path.exists(path_to_load):
            try:
                if hasattr(scene, "set_image"):
                    load_ok = scene.set_image(path_to_load)
                    if load_ok and hasattr(scene, "get_image_size"):
                        img_width, img_height = scene.get_image_size()
                        if img_width <= 0 or img_height <= 0:
                            logger.error(
                                f"Scene reported invalid image size {img_width}x{img_height} after load."
                            )
                            load_ok = False
                    elif not load_ok:
                        logger.error(
                            f"scene.set_image reported failure for {base_name}"
                        )
                else:
                    logger.error("Scene missing 'set_image' method.")
                    load_ok = False
            except Exception as e:
                logger.exception(f"Error during scene.set_image for {base_name}.")
                self.update_status(f"Error loading image: {base_name}")
                load_ok = False
        elif path_to_load:  # Path provided but doesn't exist
            logger.error(f"Image file not found: {path_to_load}")
            self.update_status("Error: Image file not found.")
            load_ok = False
        else:  # No path to load (e.g., empty list)
            logger.info("No image path to load (list empty or index invalid).")
            try:
                scene.set_image(None)  # Clear the scene
            except Exception:
                pass
            load_ok = False

        self._update_image_count_label()  # Update count regardless of success
        view = getattr(self, "graphics_view", None)

        if load_ok:
            logger.info(
                f"Image loaded successfully: {base_name} ({img_width}x{img_height})"
            )
            self.setWindowTitle(f"Annotator - {base_name} [{self.current_tier}]")
            self.update_status(f"Loaded: {base_name}")
            # Fit view to the new image
            if (
                view
                and isinstance(view, AnnotatorGraphicsView)
                and hasattr(view, "fitInView")
            ):
                try:
                    scene_rect = scene.sceneRect()
                    view.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatio)
                    if hasattr(view, "_zoom"):
                        view._zoom = 0  # Reset zoom level
                except Exception:
                    logger.error("Error fitting view to image.")

            # Load annotations for this image from state manager
            annotation_data = None
            if self.state and hasattr(self.state, "annotations"):
                annotation_data = self.state.annotations.get(path_to_load)

            if annotation_data:
                is_neg = annotation_data.get("negative", False)
                is_appr = annotation_data.get("approved", False)
                box_list = annotation_data.get("annotations_list", [])
                logger.info(
                    f"Annotation data found: Approved={is_appr}, Negative={is_neg}, Boxes={len(box_list)}"
                )
                # Check if using Dummy ResizableRectItem
                rect_item_class = ResizableRectItem
                if rect_item_class.__name__ != "DummyResizableRectItem":
                    items_added = 0
                    for ann in box_list:
                        if hasattr(scene, "add_annotation_item_from_data"):
                            try:
                                # Pass image dimensions for coordinate mapping
                                if scene.add_annotation_item_from_data(
                                    ann, img_width, img_height
                                ):
                                    items_added += 1
                                else:
                                    logger.warning(
                                        f"Failed to add annotation item from data: {ann}"
                                    )
                            except Exception as e_add:
                                logger.error(
                                    f"Error adding annotation item {ann}: {e_add}",
                                    exc_info=True,
                                )
                        else:
                            logger.error(
                                "Scene missing 'add_annotation_item_from_data' method."
                            )
                            break  # Stop if method missing
                    if items_added > 0:
                        logger.info(f"Displayed {items_added} saved annotations.")
                else:
                    logger.critical(
                        "Cannot display saved annotations: Using DummyResizableRectItem."
                    )

                # Add visual indicator for negative images
                if is_neg:
                    try:
                        neg_ind = QGraphicsTextItem("[Negative Image]")
                        neg_ind.setDefaultTextColor(QColor(200, 200, 200, 180))
                        neg_ind.setPos(10, 10)  # Position near top-left
                        neg_ind.setZValue(10)  # Ensure it's above image but below boxes
                        scene.addItem(neg_ind)
                    except Exception:
                        logger.error("Failed to add [Negative Image] indicator.")
            else:
                logger.info(f"No annotation data found in state for: {base_name}")

            # --- TIERING: Trigger suggestions if Pro and checkbox is checked ---
            auto_box_btn = getattr(self, "auto_box_button", None)
            if self.current_tier == "PRO" and auto_box_btn and auto_box_btn.isChecked():
                logger.debug(
                    "[PRO] Auto-suggestions checkbox is checked, triggering toggle_auto_boxes."
                )
                # Use QTimer to ensure UI is fully updated before starting task
                QTimer.singleShot(50, self.toggle_auto_boxes)
            else:
                self.clear_suggestion_boxes()  # Ensure suggestions are cleared if not Pro or box unchecked

            # Set focus to the view for keyboard events
            if view and isinstance(view, AnnotatorGraphicsView):
                view.setFocus()

        else:  # Load failed
            self.setWindowTitle(f"Annotator [{self.current_tier}]")  # Reset title
            current_status = getattr(self.status_label, "text", lambda: "")()
            # Update status only if it wasn't already an error message
            if (
                "error" not in current_status.lower()
                and "fail" not in current_status.lower()
            ):
                if path_to_load:
                    self.update_status(f"Failed to load image: {base_name}")
                else:
                    self.update_status("No image selected or list empty.")
            if isinstance(scene, AnnotationScene):
                scene.set_image(None)  # Clear scene on failure
            self.clear_suggestion_boxes()  # Clear suggestions on failure

    def approve_image(self):
        """Marks image approved, saves, navigates (Basic & Pro)."""
        is_dummy_state = StateManager.__name__ == "_DummyStateManager"
        if not self.state or is_dummy_state:
            QMessageBox.warning(
                self, "Error", "Approval unavailable (State Manager missing or dummy)."
            )
            return

        current_path = (
            self.state.get_current_image()
            if hasattr(self.state, "get_current_image")
            else None
        )
        scene = getattr(self, "graphics_scene", None)
        # Check if scene is real and has an image loaded
        scene_is_valid = (
            isinstance(scene, AnnotationScene)
            and hasattr(scene, "image_item")
            and scene.image_item
            and not scene.image_item.pixmap().isNull()
        )
        if not current_path or not scene_is_valid:
            QMessageBox.warning(self, "Error", "No valid image loaded to approve.")
            return

        # Get current annotations from the scene
        current_annotations_list = []
        try:
            if hasattr(scene, "get_all_annotations"):
                current_annotations_list = scene.get_all_annotations()
            else:
                raise AttributeError("Scene missing 'get_all_annotations' method.")
        except Exception as e:
            logger.exception("Failed to retrieve annotations from scene")
            QMessageBox.warning(
                self, "Approval Error", f"Could not retrieve annotations: {e}"
            )
            return

        # Store data for the last non-suggestion box for pasting ('C' key)
        self.last_box_data = None
        rect_item_class = ResizableRectItem
        rect_items = [
            item
            for item in scene.items()
            if isinstance(item, rect_item_class) and not item.is_suggestion
        ]
        if rect_items:
            # Get the last one added (usually the last one in the list)
            last_item = rect_items[-1]
            # Store its scene bounding rect and class label
            self.last_box_data = {
                "rect": last_item.sceneBoundingRect(),  # Use scene rect directly
                "class": getattr(last_item, "class_label", "Unknown"),
            }
            logger.debug(
                f"Stored last box data: Class='{self.last_box_data['class']}', SceneRect={self.last_box_data['rect']}"
            )
        else:
            logger.debug(
                "No NON-SUGGESTION boxes found on scene, clearing last box data."
            )

        # Determine if it's a negative image (no boxes drawn)
        is_negative_image = not current_annotations_list

        # Prepare data structure for state manager
        annotation_data = {
            "annotations_list": current_annotations_list,  # Contains pixel coords from scene.get_all_annotations()
            "approved": True,
            "negative": is_negative_image,
        }

        status_msg = f"Approving '{os.path.basename(current_path)}' ({'Negative' if is_negative_image else str(len(current_annotations_list)) + ' box(es)'})..."
        self.update_status(status_msg)
        logger.info(status_msg.replace("...", "."))
        QCoreApplication.processEvents()  # Update UI

        try:
            logger.debug("Calling state.add_annotation...")
            if hasattr(self.state, "add_annotation"):
                success = self.state.add_annotation(current_path, annotation_data)
                if not success:
                    logger.error("state.add_annotation reported failure.")
                    QMessageBox.warning(
                        self, "Approval Error", "Failed to save annotation state."
                    )
                    self.update_status("Approval failed.")
                    return
            else:
                logger.error("State manager missing 'add_annotation' method.")
                QMessageBox.critical(
                    self, "Internal Error", "Cannot save annotation state."
                )
                self.update_status("Approval failed.")
                return

            # Update UI count and status
            self._update_annotated_count_label()
            self.update_status(
                f"Approved: {os.path.basename(current_path)}. Navigating..."
            )

            # Schedule navigation to next unannotated shortly after
            logger.debug("Scheduling navigation to next unannotated via QTimer.")
            QTimer.singleShot(50, self.navigate_to_next_unannotated)

        except Exception as e:
            logger.exception("Critical error during approval process")
            QMessageBox.critical(
                self,
                "Approval Error",
                f"A critical error occurred during approval:\n{e}",
            )
            self.update_status("Approval failed critically.")

    def navigate_to_next_unannotated(self):
        """Finds and navigates to the next unapproved image."""
        logger.info("Navigating to next unannotated image...")
        is_dummy_state = StateManager.__name__ == "_DummyStateManager"
        img_list = getattr(self.state, "image_list", []) if self.state else []
        if not self.state or is_dummy_state or not img_list:
            logger.warning("Navigation aborted: Invalid state or empty image list.")
            self.update_status("Navigation failed: No images loaded.")
            return

        annotations_map = getattr(self.state, "annotations", {})
        total_images = len(img_list)
        start_index = getattr(self.state, "current_index", -1)

        if total_images == 0:
            logger.warning("Navigation impossible: Image list is empty.")
            self.update_status("Image list empty.")
            return

        # Start checking from the image *after* the current one
        current_idx = (start_index + 1) % total_images
        checked_count = 0
        found = False

        while checked_count < total_images:
            img_path = img_list[current_idx]
            is_approved = annotations_map.get(img_path, {}).get("approved", False)
            logger.debug(
                f"Nav Check: Index {current_idx} ('{os.path.basename(img_path)}'), Approved={is_approved}"
            )

            if not is_approved:
                logger.info(
                    f"Navigation found unannotated image at Index {current_idx}."
                )
                try:
                    if hasattr(self.state, "go_to_image") and self.state.go_to_image(
                        current_idx
                    ):
                        self.load_image()  # Load the found image
                        found = True
                        break  # Exit loop once found and loaded
                    else:
                        logger.error(
                            f"Navigation failed: state.go_to_image({current_idx}) reported failure."
                        )
                        self.update_status(
                            "Error loading next unannotated (state error)."
                        )
                        break
                except Exception as e:
                    logger.exception(
                        f"Navigation failed: Error loading image at index {current_idx}."
                    )
                    self.update_status("Error loading next unannotated image.")
                    break  # Exit loop on error

            # Move to the next index, wrapping around
            current_idx = (current_idx + 1) % total_images
            checked_count += 1

        if not found and checked_count >= total_images:
            # If we checked all images and didn't find an unannotated one
            logger.info("Navigation complete: No unannotated images found.")
            self.update_status("All images appear to be annotated.")

    def clear_suggestion_boxes(self):
        """Removes all suggestion boxes (items marked as is_suggestion=True)."""
        scene = getattr(self, "graphics_scene", None)
        if isinstance(scene, AnnotationScene):
            # Find items in the scene that are suggestions
            items_to_remove = [
                item
                for item in scene.items()
                if isinstance(item, ResizableRectItem) and item.is_suggestion
            ]
            if items_to_remove:
                logger.debug(f"Clearing {len(items_to_remove)} suggestion boxes.")
                for item in items_to_remove:
                    try:
                        scene.removeItem(item)
                    except Exception:
                        pass  # Ignore errors during removal
        # Also clear our internal list reference
        self.auto_box_items = []

    def toggle_auto_boxes(self):
        """Handles 'Show Suggestions' checkbox state change (PRO ONLY)."""
        # --- TIER CHECK ---
        if self.current_tier != "PRO":
            logger.warning("[BASIC] toggle_auto_boxes called unexpectedly.")
            checkbox = getattr(self, "auto_box_button", None)
            if checkbox:
                checkbox.setChecked(False)  # Ensure it's off
            self.clear_suggestion_boxes()
            return
        # --- END TIER CHECK ---

        checkbox = getattr(self, "auto_box_button", None)
        conf_spinbox = getattr(self, "confidence_spinbox", None)
        conf_layout = getattr(self, "conf_layout_widget", None)
        if not checkbox:
            return  # Should not happen

        # Update enabled state of confidence controls based on checkbox
        is_checked = checkbox.isChecked()
        if conf_spinbox:
            conf_spinbox.setEnabled(is_checked)
        if conf_layout:
            conf_layout.setEnabled(is_checked)

        is_dummy_state = StateManager.__name__ == "_DummyStateManager"
        state_ok = self.state and not is_dummy_state
        # Check for REAL pipeline specifically
        pipeline_ok = (
            state_ok
            and hasattr(self.state, "training_pipeline")
            and bool(self.state.training_pipeline)
            and TrainingPipeline.__name__
            != "_DummyTrainingPipeline"  # Check class name
        )
        task_active = (
            state_ok
            and hasattr(self.state, "is_task_active")
            and self.state.is_task_active()
        )

        # Conditions under which suggestions cannot be shown
        if is_checked and not pipeline_ok:
            self.update_status(
                "[PRO] Suggestions unavailable: ML Pipeline missing or dummy."
            )
            checkbox.setChecked(False)
            self.clear_suggestion_boxes()
            return
        if is_checked and task_active:
            self.update_status(
                "[PRO] Suggestions unavailable: Background task running."
            )
            # Don't uncheck here, maybe task finishes soon. User can uncheck manually.
            # Keep existing suggestions hidden if checkbox is toggled off while task runs.
            self.clear_suggestion_boxes()  # Clear existing ones if toggled off
            return

        if is_checked:  # User wants suggestions ON
            current_path = (
                self.state.get_current_image()
                if state_ok and hasattr(self.state, "get_current_image")
                else None
            )
            scene = getattr(self, "graphics_scene", None)
            # Check if scene is real and has an image
            scene_has_img = (
                isinstance(scene, AnnotationScene)
                and hasattr(scene, "image_item")
                and scene.image_item
                and not scene.image_item.pixmap().isNull()
            )

            if (
                not current_path
                or not os.path.exists(current_path)
                or not scene_has_img
            ):
                self.update_status(
                    "[PRO] Cannot get suggestions: No valid image loaded."
                )
                checkbox.setChecked(False)  # Turn off if no image
                self.clear_suggestion_boxes()
                return

            # Clear previous suggestions and request new ones
            self.clear_suggestion_boxes()
            self.update_status("[PRO] Requesting AI suggestions...")
            QCoreApplication.processEvents()  # Update UI
            try:
                if hasattr(self.state, "start_prediction"):
                    # State manager handles confidence threshold internally now
                    success = self.state.start_prediction(current_path)
                    if not success:
                        # State manager should emit error signal
                        self.update_status("[PRO] Failed to start suggestion task.")
                        checkbox.setChecked(False)  # Turn off on failure
                        self.clear_suggestion_boxes()
                else:
                    logger.error(
                        "[PRO] State manager missing 'start_prediction' method."
                    )
                    self.update_status("[PRO] Suggestion feature unavailable.")
                    checkbox.setChecked(False)
            except Exception as e:
                logger.exception("[PRO] Critical error starting prediction task.")
                QMessageBox.critical(
                    self,
                    "Suggestion Error",
                    f"Critical error requesting suggestions:\n{e}",
                )
                self.update_status("[PRO] Suggestion task failed critically.")
                checkbox.setChecked(False)
                self.clear_suggestion_boxes()
                # Try to reset task running state if exception occurred here
                if hasattr(self.state, "_blocking_task_running"):
                    try:
                        self.state._blocking_task_running = False
                    except Exception:
                        pass
                self.on_ml_task_running_changed(False)  # Force UI update

        else:  # User wants suggestions OFF
            self.clear_suggestion_boxes()
            self.update_status("[PRO] Suggestions hidden.")

    @pyqtSlot(bool)
    def on_ml_task_running_changed(self, is_blocking_task_running: bool):
        """Updates UI element enabled states based on task status and tier."""
        self._ml_task_active = is_blocking_task_running  # Store state
        logger.info(
            f"UI Update: Blocking Task Active = {is_blocking_task_running}. Tier = {self.current_tier}."
        )

        is_pro_tier = self.current_tier == "PRO"
        is_dummy_state = StateManager.__name__ == "_DummyStateManager"
        # Check for REAL pipeline specifically
        pipeline_exists_and_real = (
            self.state
            and not is_dummy_state
            and hasattr(self.state, "training_pipeline")
            and bool(self.state.training_pipeline)
            and TrainingPipeline.__name__
            != "_DummyTrainingPipeline"  # Check class name
        )

        # General controls are disabled if *any* task is running
        enable_general_controls = not is_blocking_task_running

        # ML controls require Pro tier, a real pipeline, AND no task running
        enable_ml_controls = (
            is_pro_tier and pipeline_exists_and_real and not is_blocking_task_running
        )

        # --- Update Basic Controls ---
        basic_widgets = [
            "load_button",
            "load_session_button",
            "save_session_button",
            "prev_button",
            "next_button",
            "manage_classes_button",
            "bbox_tool_button",
            "approve_button",
            "load_dir_action",
            "load_sess_action",
            "save_sess_action",
            "settings_action",
            "export_data_action",  # Export data is basic
        ]
        for name in basic_widgets:
            self.set_enabled_safe(name, enable_general_controls)

        # --- Update Pro Controls ---
        # These depend on the combined 'enable_ml_controls' flag
        pro_widgets = [
            # "auto_box_button", # Enabled state handled by toggle_auto_boxes
            # "confidence_spinbox", # Enabled state handled by toggle_auto_boxes
            "force_mini_train_button",
            "training_dashboard_button",
        ]
        for name in pro_widgets:
            self.set_enabled_safe(name, enable_ml_controls)

        # Handle Pro menu actions
        export_model_act = getattr(self, "export_model_action", None)
        if export_model_act:
            export_model_act.setEnabled(enable_ml_controls)

        # Special handling for auto-annotation group based on checkbox state *and* ML availability
        auto_box_btn = getattr(self, "auto_box_button", None)
        conf_spinbox = getattr(self, "confidence_spinbox", None)
        conf_layout_widget = getattr(self, "conf_layout_widget", None)
        auto_group_widget = getattr(self, "auto_group", None)

        # Auto-box checkbox itself should be enabled based on ML controls availability
        self.set_enabled_safe("auto_box_button", enable_ml_controls)

        # Confidence controls enabled only if ML is available AND checkbox is checked
        is_conf_enabled = (
            enable_ml_controls and auto_box_btn and auto_box_btn.isChecked()
        )
        if conf_spinbox:
            conf_spinbox.setEnabled(is_conf_enabled)
        if conf_layout_widget:
            conf_layout_widget.setEnabled(is_conf_enabled)
        # The group box itself can just follow the checkbox enable state
        # if auto_group_widget: auto_group_widget.setEnabled(enable_ml_controls) # Or keep enabled and just disable contents?

        # If task just finished, update status unless already set
        if not is_blocking_task_running:
            current_status = getattr(self.status_label, "text", lambda: "")()
            lower_status = current_status.lower()
            # Check if status indicates a final state
            final_keys = [
                "complete",
                "error",
                "fail",
                "loaded",
                "saved",
                "ready",
                "found",
                "cancelled",
                "exported",
                "finished",
                "approved",
                "unavailable",
                "unchanged",
            ]
            is_final = any(k in lower_status for k in final_keys)
            if not is_final:
                self.update_status("Ready.")

    @pyqtSlot(list)
    def handle_prediction_results(self, boxes: list):
        """Displays bounding box suggestions (PRO ONLY)."""
        # --- TIER CHECK ---
        if self.current_tier != "PRO":
            logger.warning("[BASIC] Received prediction results unexpectedly.")
            return
        # --- END TIER CHECK ---

        logger.info(f"GUI: Received {len(boxes)} prediction results.")
        self.clear_suggestion_boxes()  # Clear any old ones first

        is_dummy_state = StateManager.__name__ == "_DummyStateManager"
        scene = getattr(self, "graphics_scene", None)
        # Check if scene is real and has image
        scene_ok = (
            isinstance(scene, AnnotationScene)
            and hasattr(scene, "image_item")
            and scene.image_item
            and not scene.image_item.pixmap().isNull()
        )
        # Check if ResizableRectItem is real
        rect_item_class = ResizableRectItem
        rect_item_ok = rect_item_class.__name__ != "DummyResizableRectItem"
        auto_box_checkbox = getattr(self, "auto_box_button", None)

        # Conditions where we cannot display suggestions
        if is_dummy_state or not scene_ok or not rect_item_ok:
            logger.warning(
                f"Cannot display suggestions: Invalid state/scene/item (Dummy:{is_dummy_state}, SceneOK:{scene_ok}, ItemOK:{rect_item_ok})."
            )
            if auto_box_checkbox:
                auto_box_checkbox.setChecked(False)  # Turn off checkbox
            self.update_status("Error displaying suggestions (internal error).")
            return

        # Get image dimensions for coordinate mapping
        img_width, img_height = (
            scene.get_image_size() if hasattr(scene, "get_image_size") else (0, 0)
        )
        if img_width <= 0 or img_height <= 0:
            logger.error("Cannot display suggestions: Invalid image dimensions.")
            self.update_status("Error processing suggestions.")
            return

        items_added_count = 0
        img_item = scene.image_item  # Reference image item for mapping
        for box_data in boxes:
            try:
                # Extract data (pixel coordinates expected from state manager)
                pixel_coords = box_data.get("box")  # Should be [x, y, w, h] in pixels
                confidence = box_data.get("confidence", 0.0)
                class_label = box_data.get("class", "Unknown")

                if (
                    not isinstance(pixel_coords, (list, tuple))
                    or len(pixel_coords) != 4
                ):
                    logger.warning(
                        f"Skipping suggestion with invalid box data: {box_data}"
                    )
                    continue
                px, py, pw, ph = map(float, pixel_coords)
                if pw <= 0 or ph <= 0:
                    logger.warning(
                        f"Skipping suggestion with non-positive size: w={pw}, h={ph}"
                    )
                    continue

                # Convert pixel QRectF to scene QRectF
                pixel_rect = QRectF(px, py, pw, ph)
                scene_rect = img_item.mapRectToScene(pixel_rect)

                # Create suggestion item
                suggestion_item = rect_item_class(
                    scene_rect, class_label, is_suggestion=True, confidence=confidence
                )
                suggestion_item.setZValue(
                    5
                )  # Ensure suggestions are slightly above image but below user boxes
                scene.addItem(suggestion_item)
                self.auto_box_items.append(suggestion_item)  # Keep track
                items_added_count += 1
            except Exception as e:
                logger.error(
                    f"Error creating suggestion item from data {box_data}: {e}",
                    exc_info=True,
                )

        status_msg = f"Displayed {items_added_count} suggestion(s)."
        self.update_status(status_msg)
        logger.info(status_msg)

    @pyqtSlot(str)
    def handle_training_run_completed(self, run_dir_path: str):
        """Handles successful training run signal (PRO ONLY)."""
        # --- TIER CHECK ---
        if self.current_tier != "PRO":
            logger.warning("[BASIC] Received training completion signal unexpectedly.")
            return
        # --- END TIER CHECK ---

        run_name = (
            os.path.basename(run_dir_path)
            if run_dir_path and os.path.isdir(run_dir_path)
            else "Unknown Run"
        )
        logger.info(
            f"[PRO] GUI: Received training completion signal for run: {run_name}"
        )
        self.update_status(f"Training run '{run_name}' finished successfully.")

        # Update the dashboard if it's open
        if self.training_dashboard_instance and hasattr(
            self.training_dashboard_instance, "update_graph"
        ):
            logger.info(
                f"[PRO] Updating open training dashboard with data from: {run_dir_path}"
            )
            self.training_dashboard_instance.update_graph(run_dir_path)
        else:
            logger.info(
                "[PRO] Training dashboard not open or invalid, graph update skipped."
            )

    @pyqtSlot(str)
    def handle_task_error(self, error_message: str):
        """Handles error signals from background workers."""
        task_type = "ML Task"  # Generic default
        lower_msg = str(error_message).lower() if error_message else ""

        # Determine task type from message content
        if (
            "prediction" in lower_msg
            or "suggest" in lower_msg
            or "auto_box" in lower_msg
        ):
            task_type = "Prediction"
            # If prediction failed, turn off suggestions checkbox
            if self.current_tier == "PRO":
                checkbox = getattr(self, "auto_box_button", None)
                if checkbox and checkbox.isChecked():
                    checkbox.setChecked(False)
            self.clear_suggestion_boxes()  # Clear any partial suggestions
        elif "train" in lower_msg:
            task_type = "Training"

        logger.error(f"GUI Received Error Signal ({task_type}): {error_message}")
        # Truncate long messages for display
        display_message = str(error_message)[:500] + (
            "..." if len(str(error_message)) > 500 else ""
        )
        QMessageBox.warning(
            self,
            f"{task_type} Error",
            f"A background task encountered an error:\n\n{display_message}\n\n(Check app_debug.log for details)",
        )
        self.update_status(f"{task_type} Error.")
        # Ensure UI is re-enabled (task_running should have been set to False by state manager)
        # self.on_ml_task_running_changed(False) # Redundant if state manager emits task_running(False) on error

    def closeEvent(self, event):
        """Handles window close, checks tasks, prompts save."""
        # Check if a task is running
        is_blocking = (
            self.state.is_task_active()
            if self.state and hasattr(self.state, "is_task_active")
            else False
        )

        if is_blocking:
            reply = QMessageBox.warning(
                self,
                "Task Running",
                "A background task is still running.\nClosing now might interrupt it and lead to incomplete results or corrupted files.\n\nWait for the task to finish or Close Anyway?",
                QMessageBox.StandardButton.Wait | QMessageBox.StandardButton.Close,
                QMessageBox.StandardButton.Wait,
            )
            if reply == QMessageBox.StandardButton.Close:
                logger.warning(
                    "User chose to close while task running. Attempting cleanup..."
                )
                if self.state and hasattr(self.state, "cleanup"):
                    try:
                        self.state.cleanup()  # Attempt graceful shutdown
                    except Exception:
                        pass
                event.accept()  # Allow close
                return
            else:
                event.ignore()  # Don't close
                self.update_status("Waiting for background task to complete...")
                return

        # Prompt to save session if data exists and not using dummy
        save_reply = QMessageBox.StandardButton.No
        is_dummy_state = StateManager.__name__ == "_DummyStateManager"
        if self.state and not is_dummy_state:
            # Check if there's anything worth saving
            needs_save = (
                hasattr(self.state, "image_list") and self.state.image_list
            ) or (hasattr(self.state, "annotations") and self.state.annotations)
            if needs_save:
                save_reply = QMessageBox.question(
                    self,
                    "Exit Confirmation",
                    "Save current session before exiting?",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.No
                    | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Yes,
                )
            else:
                save_reply = QMessageBox.StandardButton.No  # Nothing to save

        if save_reply == QMessageBox.StandardButton.Cancel:
            event.ignore()
            logger.info("Close cancelled by user.")
            return
        elif save_reply == QMessageBox.StandardButton.Yes:
            try:
                self.update_status("Saving session before exit...")
                QCoreApplication.processEvents()
                self.save_session()  # Call the save method
                # Check status bar to see if save failed (though save_session should handle errors)
                current_status = getattr(self.status_label, "text", lambda: "")()
                if (
                    "error" not in current_status.lower()
                    and "fail" not in current_status.lower()
                ):
                    self.update_status("Session saved. Exiting.")
                QCoreApplication.processEvents()
            except Exception as save_e:
                logger.error("Failed to save session on exit.", exc_info=True)
                QMessageBox.critical(
                    self,
                    "Save Error",
                    f"Failed to save session on exit:\n{save_e}\n\nExiting without saving.",
                )
                # Continue exiting even if save fails
        else:  # No or Don't Save
            self.update_status("Exiting without saving...")
            QCoreApplication.processEvents()

        # Final cleanup if no task was running initially
        if not is_blocking:
            if self.state and hasattr(self.state, "cleanup"):
                try:
                    logger.info("Calling final StateManager cleanup...")
                    self.state.cleanup()
                except Exception:
                    logger.exception("Error during final StateManager cleanup.")

        logger.info("Accepting close event. Application exiting.")
        event.accept()  # Allow close

    # --- Add Manage Classes Method ---
    def manage_classes(self):
        """Opens a dialog to manage annotation classes (Basic & Pro)."""
        if (
            not self.state
            or not hasattr(self.state, "class_list")
            or not hasattr(self.state, "update_classes")
        ):
            QMessageBox.warning(
                self, "Error", "Class management unavailable (State Manager error)."
            )
            return

        current_classes = self.state.class_list
        # Simple dialog for now, could be more complex later
        classes_text, ok = QInputDialog.getMultiLineText(
            self,
            "Manage Classes",
            "Enter class names (one per line):",
            "\n".join(current_classes),
        )

        if ok:
            new_classes_raw = [line.strip() for line in classes_text.splitlines()]
            new_classes_clean = sorted(
                list(set(c for c in new_classes_raw if c))
            )  # Remove empty and duplicates, sort

            if new_classes_clean != current_classes:
                reply = QMessageBox.question(
                    self,
                    "Confirm Class Update",
                    f"Update classes to:\n{', '.join(new_classes_clean) or '(None)'}\n\n"
                    f"WARNING: Annotations using removed classes will be deleted.\nContinue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    try:
                        self.update_status("Updating class list...")
                        self.state.update_classes(new_classes_clean)
                        self.update_status("Class list updated.")
                        # Reload current image to reflect potential annotation changes
                        self.load_image()
                    except Exception as e:
                        logger.error(f"Error updating classes: {e}", exc_info=True)
                        QMessageBox.critical(
                            self, "Error", f"Failed to update classes:\n{e}"
                        )
                        self.update_status("Error updating classes.")
                else:
                    self.update_status("Class update cancelled.")
            else:
                self.update_status("Class list unchanged.")
        else:
            self.update_status("Class management cancelled.")
