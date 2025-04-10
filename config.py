# config.py (Updated with new training settings, augmentations, and trigger enables)

import os

VERSION = "1.0.1"
# --- TIERING: Add a placeholder for the tier, will be set by main.py ---
TIER = "UNKNOWN"  # Will be set to "BASIC" or "PRO" after license check

# --- Paths ---
# Use os.path.join for cross-platform compatibility and os.path.abspath for clarity
# APP_DIR: Base directory for application data (settings, models, logs, etc.)
APP_DIR = os.path.abspath(os.path.join(os.path.expanduser("~"), ".snowball_annotator"))

DEFAULT_SESSION_FILENAME = "annotation_session.json"
DEFAULT_MODEL_FILENAME = "yolo_finetuned.pt"  # Pro feature artifact
DEFAULT_SETTINGS_FILENAME = "user_settings.json"
DEFAULT_RUNS_DIR_NAME = (
    "yolo_runs"  # Subdirectory within APP_DIR for YOLO training outputs (Pro)
)

# Construct full default paths using APP_DIR
DEFAULT_SESSION_PATH = os.path.join(APP_DIR, DEFAULT_SESSION_FILENAME)
DEFAULT_MODEL_SAVE_PATH = os.path.join(
    APP_DIR, DEFAULT_MODEL_FILENAME
)  # Pro feature path
DEFAULT_SETTINGS_PATH = os.path.join(APP_DIR, DEFAULT_SETTINGS_FILENAME)
DEFAULT_ULTRALYTICS_RUNS_DIR = os.path.join(
    APP_DIR, DEFAULT_RUNS_DIR_NAME
)  # Pro feature path

# --- Model & Prediction (Pro Features primarily) ---
DEFAULT_BASE_MODEL = "yolov8n.pt"  # Base model for initial training (Pro)
DEFAULT_CONFIDENCE_THRESHOLD = (
    0.25  # Default for auto-boxing suggestion confidence (Pro)
)
DEFAULT_IMG_SIZE = 640  # Image size for training/prediction (Pro uses this heavily)

# --- Training Parameters (Pro Features) ---
DEFAULT_EPOCHS_20 = 3  # Default epochs for 20-image trigger (Pro)
DEFAULT_LR_20 = 0.005  # Default learning rate for 20-image trigger (Pro)
DEFAULT_EPOCHS_100 = 7  # Default epochs for 100-image trigger (Pro)
DEFAULT_LR_100 = 0.001  # Default learning rate for 100-image trigger (Pro)

# --- <<< Training Trigger Enables (Pro Features) >>> ---
DEFAULT_TRAIN_TRIGGER_20_ENABLED = True  # ADDED: Default for 20 image trigger (Pro)
DEFAULT_TRAIN_TRIGGER_100_ENABLED = True  # ADDED: Default for 100 image trigger (Pro)

# --- Augmentation Defaults (Pro Features) ---
DEFAULT_AUG_FLIPUD = 0.0  # Default probability for up/down flip (Pro)
DEFAULT_AUG_FLIPLR = 0.5  # Default probability for left/right flip (Pro)
DEFAULT_AUG_DEGREES = 0.0  # Default degrees for random rotation (Pro)

# --- Annotation Workflow ---
# (Relevant to Basic & Pro)

# --- YOLO Data Export (Basic & Pro) ---
IMAGES_SUBDIR = "images"  # Subdirectory for images within export/dataset path
LABELS_SUBDIR = "labels"  # Subdirectory for labels within export/dataset path
TRAIN_SUBDIR = "train"  # Subdirectory for training set within images/labels
VALID_SUBDIR = "valid"  # Subdirectory for validation set within images/labels
DATA_YAML_NAME = "dataset.yaml"  # Name of the dataset config file YOLO uses

# --- Keys for Settings Dictionary ---
# Using consistent keys makes accessing settings less error-prone
SETTING_KEYS = {
    # Paths (Basic & Pro, though some paths are Pro-specific artifacts)
    "session_path": "paths.session_path",
    "model_save_path": "paths.model_save_path",  # Pro
    "runs_dir": "paths.runs_dir",  # Pro
    "last_image_dir": "paths.last_image_dir",
    # Prediction (Pro)
    "base_model": "prediction.base_model",  # Pro
    "img_size": "prediction.img_size",  # Pro (Prediction & Training)
    "confidence_threshold": "prediction.confidence_threshold",  # Pro
    # Training (Pro)
    "epochs_20": "training.epochs_20",  # Pro
    "lr_20": "training.lr_20",  # Pro
    "epochs_100": "training.epochs_100",  # Pro
    "lr_100": "training.lr_100",  # Pro
    "training.trigger_20_enabled": "training.trigger_20_enabled",  # Pro
    "training.trigger_100_enabled": "training.trigger_100_enabled",  # Pro
    # Augmentations (Pro)
    "aug_flipud": "training.augment.flipud",  # Pro
    "aug_fliplr": "training.augment.fliplr",  # Pro
    "aug_degrees": "training.augment.degrees",  # Pro
}


# --- Function to get all default settings ---
def get_default_settings():
    """Returns a dictionary containing all default settings."""
    # Note: This returns ALL defaults, even for Pro features.
    # The application logic will decide whether to USE these based on the TIER.
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
        SETTING_KEYS["training.trigger_20_enabled"]: DEFAULT_TRAIN_TRIGGER_20_ENABLED,
        SETTING_KEYS["training.trigger_100_enabled"]: DEFAULT_TRAIN_TRIGGER_100_ENABLED,
        # Augmentations
        SETTING_KEYS["aug_flipud"]: DEFAULT_AUG_FLIPUD,
        SETTING_KEYS["aug_fliplr"]: DEFAULT_AUG_FLIPLR,
        SETTING_KEYS["aug_degrees"]: DEFAULT_AUG_DEGREES,
    }


# --- Optional: Add simple validation or logging ---
try:
    # Ensure the base application directory exists on module load
    os.makedirs(APP_DIR, exist_ok=True)
except Exception as e:
    print(f"[ERROR] Could not create application directory: {APP_DIR} - {e}")
