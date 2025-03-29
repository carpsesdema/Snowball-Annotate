# workers.py (Updated: Removed Micro, Renamed Macro, Updated Signals)
import logging
import os
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

class PredictionWorker(QObject):
    """Worker for running pipeline.auto_box."""
    progress = pyqtSignal(str); finished = pyqtSignal(list); error = pyqtSignal(str)
    def __init__(self, pipeline, image_data, confidence_threshold):
        super().__init__(); self.pipeline = pipeline; self.image_data = image_data
        self.confidence_threshold = confidence_threshold; self._is_running = True
    def run(self):
        try:
            if not self.pipeline: raise RuntimeError("Predict Worker: Pipeline unavailable.")
            self.progress.emit("Starting prediction..."); logger.info(f"Worker: Running auto_box...")
            boxes = self.pipeline.auto_box(self.image_data, self.confidence_threshold)
            if self._is_running: logger.info(f"Worker: Predict finished, {len(boxes)} boxes."); self.progress.emit(f"Predict complete. Found {len(boxes)} boxes."); self.finished.emit(boxes)
            else: logger.info("Worker: Predict cancelled."); self.progress.emit("Predict cancelled.")
        except Exception as e: logger.exception("Worker: Error prediction"); self.error.emit(f"Prediction failed: {e}")
        finally: self._is_running = False
    def stop(self): self._is_running = False


# --- <<< REMOVED MicroUpdateWorker >>> ---


# --- <<< RENAMED MacroUpdateWorker to TrainingWorker >>> ---
# --- <<< UPDATED __init__, run args, and finished signal >>> ---
class TrainingWorker(QObject):
    """Worker for running pipeline.run_training_session."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(str) # Emit run_dir path on success
    error = pyqtSignal(str)

    def __init__(self, pipeline, image_paths, all_annotations, epochs, lr, run_name_prefix):
        super().__init__()
        self.pipeline = pipeline
        self.image_paths = image_paths
        self.all_annotations = all_annotations
        self.epochs = epochs
        self.lr = lr
        self.run_name_prefix = run_name_prefix
        self._is_running = True

    def run(self):
        """Executes the training task."""
        run_dir = None # To store the result path
        try:
            if not self.pipeline: raise RuntimeError("Training Worker: Pipeline unavailable.")
            if not self.image_paths: raise ValueError("No image paths for training.")
            num_images = len(self.image_paths)
            self.progress.emit(f"Starting {self.run_name_prefix} training on {num_images} images...")
            logger.info(f"Worker: Running {self.run_name_prefix} training on {num_images} images (E={self.epochs}, LR={self.lr}).")

            # Call the renamed pipeline method, passing new parameters
            run_dir = self.pipeline.run_training_session(
                self.image_paths, self.all_annotations, self.epochs, self.lr, self.run_name_prefix
            )

            if self._is_running:
                if run_dir: # Check if training returned a valid path
                     logger.info(f"Worker: Training run '{self.run_name_prefix}' finished successfully. Run dir: {run_dir}")
                     self.progress.emit(f"{self.run_name_prefix.capitalize()} training complete.")
                     self.finished.emit(str(run_dir)) # Emit path on success
                else:
                     # Training pipeline method returned None, indicating failure
                     logger.error(f"Worker: Training run '{self.run_name_prefix}' failed (pipeline returned None).")
                     self.error.emit(f"{self.run_name_prefix.capitalize()} training failed (see logs).")
            else:
                logger.info(f"Worker: Training run '{self.run_name_prefix}' cancelled.")
                self.progress.emit(f"{self.run_name_prefix.capitalize()} training cancelled.")

        except Exception as e:
            logger.exception(f"Worker: Error during {self.run_name_prefix} training")
            self.error.emit(f"{self.run_name_prefix.capitalize()} training failed: {e}")
        finally:
            self._is_running = False # Ensure flag is reset

    def stop(self):
        self._is_running = False
# --- <<< END RENAMED/MODIFIED >>> ---