# config.py (Updated with new training settings and augmentations)
import os
VERSION = "1.0.0"
# --- Paths ---
# Use os.path.join for cross-platform compatibility and os.path.abspath for clarity
# APP_DIR: Base directory for application data (settings, models, logs, etc.)
APP_DIR = os.path.abspath(os.path.join(os.path.expanduser("~"), ".snowball_annotator"))

DEFAULT_SESSION_FILENAME = "annotation_session.json"
DEFAULT_MODEL_FILENAME = "yolo_finetuned.pt"
DEFAULT_SETTINGS_FILENAME = "user_settings.json"
DEFAULT_RUNS_DIR_NAME = "yolo_runs"  # Subdirectory within APP_DIR for YOLO training outputs

# Construct full default paths using APP_DIR
DEFAULT_SESSION_PATH = os.path.join(APP_DIR, DEFAULT_SESSION_FILENAME)
DEFAULT_MODEL_SAVE_PATH = os.path.join(APP_DIR, DEFAULT_MODEL_FILENAME)
DEFAULT_SETTINGS_PATH = os.path.join(APP_DIR, DEFAULT_SETTINGS_FILENAME)
DEFAULT_ULTRALYTICS_RUNS_DIR = os.path.join(APP_DIR, DEFAULT_RUNS_DIR_NAME)

# --- Model & Prediction ---
DEFAULT_BASE_MODEL = 'yolov8n.pt'       # Base model for initial training (small and fast)
DEFAULT_CONFIDENCE_THRESHOLD = 0.25     # Default for auto-boxing suggestion confidence
DEFAULT_IMG_SIZE = 640                  # Image size for training/prediction (YOLO default)

# --- Training Parameters ---
DEFAULT_EPOCHS_20 = 3                   # Default epochs for 20-image trigger
DEFAULT_LR_20 = 0.005                   # Default learning rate for 20-image trigger
DEFAULT_EPOCHS_100 = 7                  # Default epochs for 100-image trigger
DEFAULT_LR_100 = 0.001                  # Default learning rate for 100-image trigger

# --- <<< ADDED: Augmentation Defaults >>> ---
DEFAULT_AUG_FLIPUD = 0.0         # Default probability for up/down flip
DEFAULT_AUG_FLIPLR = 0.5         # Default probability for left/right flip (often useful)
DEFAULT_AUG_DEGREES = 0.0        # Default degrees for random rotation
# Add others like DEFAULT_AUG_SCALE, DEFAULT_AUG_TRANSLATE if needed
# --- <<< END ADDED >>> ---


# --- Annotation Workflow ---
# (Removed old macro threshold and auto update flags as logic changed)

# --- YOLO Data Export (NEW CONSTANTS) ---
IMAGES_SUBDIR = "images"                # Subdirectory for images within export/dataset path
LABELS_SUBDIR = "labels"                # Subdirectory for labels within export/dataset path
TRAIN_SUBDIR = "train"                  # Subdirectory for training set within images/labels
VALID_SUBDIR = "valid"                  # Subdirectory for validation set within images/labels
DATA_YAML_NAME = "dataset.yaml"         # Name of the dataset config file YOLO uses

# --- Keys for Settings Dictionary ---
# Using consistent keys makes accessing settings less error-prone
SETTING_KEYS = {
    # Paths
    "session_path": "paths.session_path",
    "model_save_path": "paths.model_save_path",
    "runs_dir": "paths.runs_dir",
    "last_image_dir": "paths.last_image_dir",
    # Prediction
    "base_model": "prediction.base_model",
    "img_size": "prediction.img_size", # Used for prediction and training
    "confidence_threshold": "prediction.confidence_threshold",
    # Training
    "epochs_20": "training.epochs_20",
    "lr_20": "training.lr_20",
    "epochs_100": "training.epochs_100",
    "lr_100": "training.lr_100",
    # --- <<< ADDED: Augmentation Settings Keys >>> ---
    "aug_flipud": "training.augment.flipud",
    "aug_fliplr": "training.augment.fliplr",
    "aug_degrees": "training.augment.degrees",
    # Add keys for scale, translate, etc. if implementing
    # --- <<< END ADDED >>> ---
}

# --- Function to get all default settings ---
def get_default_settings():
    """Returns a dictionary containing all default settings."""
    return {
        # Paths
        SETTING_KEYS["session_path"]: DEFAULT_SESSION_PATH,
        SETTING_KEYS["model_save_path"]: DEFAULT_MODEL_SAVE_PATH,
        SETTING_KEYS["runs_dir"]: DEFAULT_ULTRALYTICS_RUNS_DIR,
        SETTING_KEYS["last_image_dir"]: os.path.expanduser("~"),
        # Prediction
        SETTING_KEYS["base_model"]: DEFAULT_BASE_MODEL,
        SETTING_KEYS["confidence_threshold"]: DEFAULT_CONFIDENCE_THRESHOLD,
        SETTING_KEYS["img_size"]: DEFAULT_IMG_SIZE,
        # Training
        SETTING_KEYS["epochs_20"]: DEFAULT_EPOCHS_20,
        SETTING_KEYS["lr_20"]: DEFAULT_LR_20,
        SETTING_KEYS["epochs_100"]: DEFAULT_EPOCHS_100,
        SETTING_KEYS["lr_100"]: DEFAULT_LR_100,
        # --- <<< ADDED: Augmentation Defaults >>> ---
        SETTING_KEYS["aug_flipud"]: DEFAULT_AUG_FLIPUD,
        SETTING_KEYS["aug_fliplr"]: DEFAULT_AUG_FLIPLR,
        SETTING_KEYS["aug_degrees"]: DEFAULT_AUG_DEGREES,
        # Add others if implementing
        # --- <<< END ADDED >>> ---
    }

# --- Optional: Add simple validation or logging ---
try:
    # Ensure the base application directory exists on module load
    os.makedirs(APP_DIR, exist_ok=True)
    # print(f"Config loaded. Application data directory: {APP_DIR}")  # Optional print
except Exception as e:
    print(f"[ERROR] Could not create application directory: {APP_DIR} - {e}")