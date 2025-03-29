# training_pipeline.py (Refactored)
import logging
import os
import shutil
import math
import tempfile
import random
import yaml
from PIL import Image
from ultralytics import YOLO
import torch
import config

logger = logging.getLogger(__name__)
if not logger.handlers:
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s [%(threadName)s] - %(levelname)s - %(message)s"
    )
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)


class DatasetHandler:
    """Handles storing annotations and exporting data in YOLO format with train/val split."""

    def __init__(self):
        self.annotations = {}
        logger.info("DatasetHandler initialized.")

    def update_annotation(self, image_path, annotation_data):
        """Update annotation for a given image."""
        self.annotations[image_path] = annotation_data

    def get_annotation(self, image_path):
        """Retrieve annotation data for a given image."""
        return self.annotations.get(image_path)

    def export_for_yolo(self, image_paths_to_export, base_export_dir, class_to_id, val_split=0.2):
        if not class_to_id:
            logger.error("Class map is empty. Cannot export dataset.")
            return None
        if not image_paths_to_export:
            logger.warning("No image paths provided for export.")
            return None

        eligible_paths = self._filter_eligible_paths(image_paths_to_export)
        if not eligible_paths:
            logger.warning("No eligible images with valid annotations found for YOLO export.")
            return None

        num_train, num_valid = self._calculate_split(len(eligible_paths), val_split)
        logger.info(f"Calculated split: {num_train} train, {num_valid} valid (val_split={val_split:.2f})")
        random.shuffle(eligible_paths)
        train_paths = eligible_paths[:num_train]
        valid_paths = eligible_paths[num_train:]

        dirs = self._prepare_directories(base_export_dir, num_valid)
        if dirs is None:
            return None
        (img_train_dir, lbl_train_dir, img_valid_dir, lbl_valid_dir) = dirs

        exported_train_count, exported_valid_count = 0, 0
        for img_path in eligible_paths:
            try:
                ann_data = self.get_annotation(img_path)
                yolo_lines, img_w, img_h = self._process_image_annotation(img_path, ann_data, class_to_id)
                if not yolo_lines:
                    continue

                is_validation = img_path in valid_paths
                target_img_dir = img_valid_dir if is_validation else img_train_dir
                target_lbl_dir = lbl_valid_dir if is_validation else lbl_train_dir

                base_name = os.path.basename(img_path)
                label_name = os.path.splitext(base_name)[0] + ".txt"
                target_img_path = os.path.join(target_img_dir, base_name)
                target_lbl_path = os.path.join(target_lbl_dir, label_name)

                with open(target_lbl_path, "w") as f:
                    f.writelines(yolo_lines)
                shutil.copy2(img_path, target_img_path)

                if is_validation:
                    exported_valid_count += 1
                else:
                    exported_train_count += 1
            except FileNotFoundError:
                logger.error(f"Image file not found: {img_path}. Skipping.")
            except Exception as e:
                logger.error(f"Error processing image {img_path}: {e}", exc_info=True)

        if exported_train_count == 0 and exported_valid_count == 0:
            logger.error("Export failed: No images or labels were successfully processed.")
            return None
        elif exported_train_count == 0:
            logger.error("Export failed: Only validation images exported; train set missing.")
            return None

        yaml_path = self._create_yaml_file(base_export_dir, img_train_dir, img_valid_dir, exported_valid_count, class_to_id)
        return yaml_path

    def _filter_eligible_paths(self, image_paths):
        eligible = []
        for p in image_paths:
            ann_data = self.get_annotation(p)
            if ann_data and ann_data.get("approved") and not ann_data.get("negative") and ann_data.get("annotations_list"):
                eligible.append(p)
            elif ann_data:
                logger.debug(f"Skipping {os.path.basename(p)}: Not approved, negative, or missing boxes.")
            else:
                logger.warning(f"Annotation data missing for {os.path.basename(p)}.")
        return eligible

    def _calculate_split(self, num_eligible, val_split):
        if not (0.0 <= val_split < 1.0):
            logger.warning(f"Invalid val_split ({val_split}). Clamping to default 0.2.")
            val_split = 0.2
        num_valid = 0
        if val_split > 0 and num_eligible > 1:
            num_valid = math.ceil(num_eligible * val_split)
            if num_valid >= num_eligible:
                num_valid = num_eligible - 1
            if num_valid == 0:
                num_valid = 1
        elif num_eligible <= 1:
            logger.warning("Only one eligible image; forcing all to train set.")
            val_split = 0.0
        return num_eligible - num_valid, num_valid

    def _prepare_directories(self, base_export_dir, num_valid):
        img_train_dir = os.path.join(base_export_dir, config.IMAGES_SUBDIR, config.TRAIN_SUBDIR)
        lbl_train_dir = os.path.join(base_export_dir, config.LABELS_SUBDIR, config.TRAIN_SUBDIR)
        img_valid_dir = os.path.join(base_export_dir, config.IMAGES_SUBDIR, config.VALID_SUBDIR) if num_valid > 0 else None
        lbl_valid_dir = os.path.join(base_export_dir, config.LABELS_SUBDIR, config.VALID_SUBDIR) if num_valid > 0 else None

        dirs_to_create = [img_train_dir, lbl_train_dir]
        if img_valid_dir:
            dirs_to_create.extend([img_valid_dir, lbl_valid_dir])

        for dir_path in dirs_to_create:
            try:
                if os.path.exists(dir_path):
                    shutil.rmtree(dir_path)
                    logger.debug(f"Removed directory: {dir_path}")
                os.makedirs(dir_path, exist_ok=True)
                logger.debug(f"Created directory: {dir_path}")
            except Exception as e:
                logger.error(f"Failed to prepare directory {dir_path}: {e}", exc_info=True)
                return None
        return img_train_dir, lbl_train_dir, img_valid_dir, lbl_valid_dir

    def _process_image_annotation(self, img_path, ann_data, class_to_id):
        with Image.open(img_path) as img:
            img_w, img_h = img.size
        if img_w <= 0 or img_h <= 0:
            raise ValueError(f"Invalid image dimensions: {img_w}x{img_h}")

        yolo_lines = []
        for box_ann in ann_data.get("annotations_list", []):
            box = box_ann.get("rect")
            class_name = box_ann.get("class")
            if not box or not class_name:
                logger.warning(f"Skipping incomplete box in {os.path.basename(img_path)}.")
                continue
            if class_name not in class_to_id:
                logger.error(f"Class '{class_name}' not in class map for {os.path.basename(img_path)}.")
                continue

            class_id = class_to_id[class_name]
            center_x, center_y, norm_w, norm_h = self._normalize_box(box, img_w, img_h)
            if norm_w <= 0 or norm_h <= 0:
                logger.warning(f"Skipping box with non-positive size for {class_name} in {os.path.basename(img_path)}.")
                continue

            yolo_lines.append(f"{class_id} {center_x:.6f} {center_y:.6f} {norm_w:.6f} {norm_h:.6f}\n")
        return yolo_lines, img_w, img_h

    def _normalize_box(self, box, img_w, img_h):
        px, py, pw, ph = map(float, box)
        center_x = (px + pw / 2) / img_w
        center_y = (py + ph / 2) / img_h
        norm_w = pw / img_w
        norm_h = ph / img_h
        center_x = max(0.0, min(1.0, center_x))
        center_y = max(0.0, min(1.0, center_y))
        norm_w = max(0.0, min(1.0, norm_w))
        norm_h = max(0.0, min(1.0, norm_h))
        return center_x, center_y, norm_w, norm_h

    def _create_yaml_file(self, base_export_dir, img_train_dir, img_valid_dir, exported_valid_count, class_to_id):
        yaml_path = os.path.join(base_export_dir, config.DATA_YAML_NAME)
        class_names_sorted = sorted(class_to_id.keys(), key=lambda k: class_to_id[k])
        train_rel_path = os.path.relpath(img_train_dir, start=base_export_dir)
        valid_rel_path = (
            os.path.relpath(img_valid_dir, start=base_export_dir)
            if img_valid_dir and exported_valid_count > 0
            else train_rel_path
        )
        if valid_rel_path == train_rel_path and exported_valid_count == 0:
            logger.warning("No validation images exported; setting 'val' to train path in YAML.")

        yaml_content = {
            "path": os.path.abspath(base_export_dir),
            "train": train_rel_path.replace(os.sep, '/'),
            "val": valid_rel_path.replace(os.sep, '/'),
            "nc": len(class_names_sorted),
            "names": class_names_sorted,
        }
        try:
            with open(yaml_path, "w") as f:
                yaml.dump(yaml_content, f, default_flow_style=None, sort_keys=False)
            logger.info(f"Dataset YAML created at: {yaml_path}")
            return yaml_path
        except Exception as e:
            logger.error(f"Failed to write YAML file at {yaml_path}: {e}", exc_info=True)
            return None


class TrainingPipeline:
    """Manages YOLOv8 model training and prediction."""

    def __init__(self, class_list, settings, dataset_handler):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Using device: {self.device}")
        self._settings = settings

        self.class_list = sorted(list(set(class_list))) if class_list else []
        self.update_class_mappings()
        logger.info(f"Initialized with classes: {self.class_list}")

        if not dataset_handler or not isinstance(dataset_handler, DatasetHandler):
            logger.error("Invalid or missing DatasetHandler.")
            raise ValueError("TrainingPipeline requires a valid DatasetHandler instance.")
        self.dataset_handler = dataset_handler
        logger.info("TrainingPipeline received DatasetHandler instance.")

        self.model_save_path = self.get_setting(config.SETTING_KEYS["model_save_path"])
        self.project_dir = os.path.dirname(self.model_save_path)
        self.base_model_name = self.get_setting(config.SETTING_KEYS["base_model"])
        self.ultralytics_runs_dir = self.get_setting(config.SETTING_KEYS["runs_dir"])
        os.makedirs(self.project_dir, exist_ok=True)
        os.makedirs(self.ultralytics_runs_dir, exist_ok=True)

        self.model = self._load_initial_model()
        self.latest_weights_path = self._determine_latest_weights()
        logger.info(f"Tracking latest weights path: {self.latest_weights_path}")

        try:
            self.temp_export_dir_obj = tempfile.TemporaryDirectory(prefix="yolo_export_", dir=self.project_dir)
            self.current_export_dir = self.temp_export_dir_obj.name
            logger.info(f"Created temporary export directory: {self.current_export_dir}")
        except Exception as e:
            logger.error(f"Failed to create temporary directory in {self.project_dir}: {e}", exc_info=True)
            raise RuntimeError(f"Failed to create temporary directory: {e}")

        self._update_training_params_from_settings()
        logger.info("TrainingPipeline initialized successfully.")

    def update_class_mappings(self):
        self.class_to_id = {name: i for i, name in enumerate(self.class_list)}
        self.id_to_class = {i: name for name, i in self.class_to_id.items()}

    def get_setting(self, key, default=None):
        config_default = config.get_default_settings().get(key)
        effective_default = config_default if config_default is not None else default
        return self._settings.get(key, effective_default)

    def _update_training_params_from_settings(self):
        self.epochs_20 = self.get_setting(config.SETTING_KEYS["epochs_20"], config.DEFAULT_EPOCHS_20)
        self.lr_20 = self.get_setting(config.SETTING_KEYS["lr_20"], config.DEFAULT_LR_20)
        self.epochs_100 = self.get_setting(config.SETTING_KEYS["epochs_100"], config.DEFAULT_EPOCHS_100)
        self.lr_100 = self.get_setting(config.SETTING_KEYS["lr_100"], config.DEFAULT_LR_100)
        self.imgsz = self.get_setting(config.SETTING_KEYS["img_size"], config.DEFAULT_IMG_SIZE)
        logger.info(
            f"Training params: 20img(E={self.epochs_20}, LR={self.lr_20:.6f}) | "
            f"100img(E={self.epochs_100}, LR={self.lr_100:.6f}) | ImgSz={self.imgsz}"
        )

    def update_settings(self, new_settings):
        logger.debug("Received updated settings.")
        self._settings = new_settings
        self.model_save_path = self.get_setting(config.SETTING_KEYS["model_save_path"])
        self.ultralytics_runs_dir = self.get_setting(config.SETTING_KEYS["runs_dir"])
        self._update_training_params_from_settings()

    def update_classes(self, new_class_list):
        new_classes_sorted = sorted(list(set(new_class_list)))
        if new_classes_sorted != self.class_list:
            self.class_list = new_classes_sorted
            self.update_class_mappings()
            logger.info(f"Updated classes: {self.class_list}")
        else:
            logger.debug("Classes unchanged.")

    def _determine_latest_weights(self):
        if self.model and hasattr(self.model, 'ckpt_path') and self.model.ckpt_path and os.path.exists(self.model.ckpt_path):
            return self.model.ckpt_path
        elif os.path.exists(self.model_save_path):
            return self.model_save_path
        else:
            logger.error("Could not determine latest weights path after model load!")
            return None

    def _load_initial_model(self):
        model_to_load = None
        if os.path.exists(self.model_save_path):
            logger.info(f"Loading existing model: {self.model_save_path}")
            model_to_load = self.model_save_path
        else:
            logger.info(f"No model at {self.model_save_path}. Using base model: {self.base_model_name}")
            if not os.path.exists(self.base_model_name) and self.base_model_name.endswith('.pt'):
                logger.info(f"Assuming '{self.base_model_name}' is a standard YOLO model.")
                model_to_load = self.base_model_name
            elif os.path.exists(self.base_model_name):
                logger.info(f"Found base model at: {self.base_model_name}")
                model_to_load = self.base_model_name
            else:
                logger.error(f"Base model '{self.base_model_name}' not found.")
                raise RuntimeError(f"Base model not found: {self.base_model_name}")

        if model_to_load is None:
            raise RuntimeError("Could not determine model to load.")

        try:
            model = YOLO(model_to_load)
            if hasattr(model, "predictor") and hasattr(model, "train"):
                logger.info(f"Model '{model_to_load}' loaded successfully.")
                if model_to_load == self.base_model_name and not os.path.exists(self.model_save_path):
                    try:
                        os.makedirs(os.path.dirname(self.model_save_path), exist_ok=True)
                        model.save(self.model_save_path)
                        logger.info(f"Saved initial model state to {self.model_save_path}")
                    except Exception as save_err:
                        logger.error(f"Failed to save model to {self.model_save_path}: {save_err}")
                return model
            else:
                logger.error(f"Loaded object from '{model_to_load}' is not a valid YOLO model.")
                raise RuntimeError(f"Invalid model loaded from {model_to_load}")
        except Exception as e:
            logger.error(f"Error loading model '{model_to_load}': {e}", exc_info=True)
            raise RuntimeError(f"Could not load model '{model_to_load}': {e}")

    def _find_best_weights(self, run_dir):
        weights_dir = os.path.join(run_dir, "weights")
        if not os.path.isdir(weights_dir):
            logger.error(f"Weights directory not found: {run_dir}")
            return None
        best_weights = os.path.join(weights_dir, "best.pt")
        if os.path.exists(best_weights):
            logger.info(f"Found best weights: {best_weights}")
            return best_weights
        else:
            last_weights = os.path.join(weights_dir, "last.pt")
            if os.path.exists(last_weights):
                logger.warning(f"Using last weights: {last_weights}")
                return last_weights
            else:
                logger.error(f"No valid weights found in {weights_dir}.")
                return None

    def _run_training(self, yaml_path, epochs, learning_rate, run_name_prefix):
        if not yaml_path or not os.path.exists(yaml_path):
            logger.error(f"Invalid dataset YAML path: {yaml_path}")
            return None
        if not self.class_list:
            logger.error("Class list is empty; cannot train.")
            return None
        if not isinstance(epochs, int) or epochs <= 0:
            logger.error(f"Invalid epochs: {epochs}")
            return None
        if not isinstance(learning_rate, (float, int)) or learning_rate <= 0:
            logger.error(f"Invalid learning rate: {learning_rate}")
            return None
        if not self.latest_weights_path or not os.path.exists(self.latest_weights_path):
            logger.error(f"No valid starting weights: '{self.latest_weights_path}'")
            return None

        try:
            with open(yaml_path, 'r') as f:
                yaml_data = yaml.safe_load(f)
            if not yaml_data:
                raise ValueError("YAML file is empty.")
            base_path = yaml_data.get('path', os.path.dirname(yaml_path))
            train_abs = os.path.abspath(os.path.join(base_path, yaml_data.get('train')))
            val_abs = os.path.abspath(os.path.join(base_path, yaml_data.get('val')))
            if not os.path.isdir(train_abs) or not os.path.isdir(val_abs):
                raise FileNotFoundError("Train or validation directory not found.")
            logger.info(f"Using dataset from {yaml_path}")
        except Exception as e:
            logger.error(f"Failed to read/validate YAML '{yaml_path}': {e}", exc_info=True)
            return None

        logger.info(
            f"Starting training '{run_name_prefix}' with epochs={epochs}, lr={learning_rate:.6f}, imgsz={self.imgsz}"
        )
        try:
            trainer = YOLO(self.latest_weights_path)
            train_args = dict(
                data=yaml_path,
                epochs=epochs,
                imgsz=self.imgsz,
                device=self.device,
                project=self.ultralytics_runs_dir,
                name=f"{run_name_prefix}_run",
                exist_ok=True,
                save=True,
                save_period=max(1, epochs // 5),
                verbose=False,
                plots=True,
                optimizer='auto',
                lr0=learning_rate,
            )
            logger.debug(f"Training arguments: {train_args}")
            results = trainer.train(**train_args)
            run_dir = results.save_dir
            logger.info(f"Training complete. Results saved in: {run_dir}")

            new_weights = self._find_best_weights(run_dir)
            if new_weights:
                try:
                    shutil.copy2(new_weights, self.model_save_path)
                    self.latest_weights_path = self.model_save_path
                    self.model = YOLO(self.latest_weights_path)
                    logger.info("Model reloaded with new weights.")
                    return run_dir
                except Exception as copy_err:
                    logger.error(f"Failed to copy weights: {copy_err}", exc_info=True)
                    return run_dir
            else:
                logger.error(f"Training finished but no output weights found in {run_dir}.")
                return None
        except Exception as e:
            logger.exception(f"Error during training '{run_name_prefix}': {e}")
            return None

    def run_training_session(self, image_paths, all_annotations, epochs, learning_rate, run_name_prefix):
        if not image_paths:
            logger.warning("No image paths provided for training session.")
            return None
        if not all_annotations:
            logger.warning("No annotations provided for training session.")
            return None

        logger.info(f"Starting training session '{run_name_prefix}' for {len(image_paths)} images.")
        yaml_path = None
        original_annotations = None
        try:
            if not self.dataset_handler:
                raise RuntimeError("DatasetHandler not available.")
            original_annotations = self.dataset_handler.annotations.copy()
            self.dataset_handler.annotations = {p: all_annotations[p] for p in image_paths if p in all_annotations}
            yaml_path = self.dataset_handler.export_for_yolo(
                image_paths_to_export=image_paths,
                base_export_dir=self.current_export_dir,
                class_to_id=self.class_to_id,
                val_split=0.15,
            )
        except Exception as e:
            logger.error(f"Failed to export data for training session '{run_name_prefix}': {e}", exc_info=True)
            yaml_path = None
        finally:
            if original_annotations is not None:
                self.dataset_handler.annotations = original_annotations
                logger.debug("Restored original annotations.")

        if not yaml_path:
            logger.error(f"Data export failed for training session '{run_name_prefix}'.")
            return None

        run_dir = self._run_training(yaml_path, epochs, learning_rate, run_name_prefix)
        if not run_dir:
            logger.error(f"Training session '{run_name_prefix}' failed during training.")
            return None

        logger.info(f"Training session '{run_name_prefix}' completed. Run directory: {run_dir}")
        return run_dir

    def auto_box(self, image_data, confidence_threshold):
        if not self.latest_weights_path or not os.path.exists(self.latest_weights_path):
            logger.error(f"Model weights not found at '{self.latest_weights_path}'.")
            if os.path.exists(self.model_save_path):
                logger.warning("Falling back to main save path.")
                self.latest_weights_path = self.model_save_path
                try:
                    self.model = YOLO(self.latest_weights_path)
                except Exception as e:
                    logger.error(f"Fallback model reload failed: {e}")
                    return []
            else:
                logger.error("No valid model weights available.")
                return []

        if not self.class_list:
            logger.error("Class list is empty; cannot predict.")
            return []
        if not self.model:
            logger.error("Model not loaded; cannot predict.")
            return []

        try:
            results = self.model.predict(source=image_data, conf=confidence_threshold, device=self.device, verbose=False)
            boxes = []
            if results and len(results) > 0:
                res = results[0]
                if res.boxes is None:
                    logger.debug("No bounding boxes detected.")
                    return []
                for box_data in res.boxes:
                    xyxy = box_data.xyxy[0].cpu().numpy()
                    conf = box_data.conf[0].cpu().numpy().item()
                    class_id = int(box_data.cls[0].cpu().numpy().item())
                    class_name = self.id_to_class.get(class_id)
                    if class_name is None:
                        logger.warning(f"Unknown class ID {class_id}; skipping.")
                        continue
                    x1, y1, x2, y2 = map(float, xyxy)
                    pixel_w = x2 - x1
                    pixel_h = y2 - y1
                    if pixel_w > 0 and pixel_h > 0:
                        boxes.append({"box": [x1, y1, pixel_w, pixel_h], "confidence": float(conf), "class": class_name})
                    else:
                        logger.warning(f"Skipping box with invalid dimensions: {pixel_w}x{pixel_h}")
            logger.info(f"Auto-box found {len(boxes)} boxes (Conf >= {confidence_threshold:.2f})")
            return boxes
        except Exception as e:
            logger.exception(f"Error during auto_box prediction: {e}")
            return []

    def cleanup(self):
        logger.info("Initiating TrainingPipeline cleanup.")
        try:
            if hasattr(self, "temp_export_dir_obj") and self.temp_export_dir_obj:
                self.temp_export_dir_obj.cleanup()
                logger.info(f"Cleaned up temporary directory: {self.current_export_dir}")
                self.temp_export_dir_obj = None
                self.current_export_dir = None
            else:
                logger.warning("No temporary directory found for cleanup.")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)
