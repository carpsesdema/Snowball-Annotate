#!/usr/bin/env python3
"""
gui.py - TrainingDashboard updated to plot data directly from results.csv
         using pandas and matplotlib for a custom dark theme.
         Added Augmentation settings controls.
         Added ViewportUpdateMode setting to AnnotatorGraphicsView.
"""

import logging
import os
import matplotlib.pyplot as plt
# Use the unified Qt-based canvas (works for Qt5 or Qt6) in Matplotlib 3.7+:
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import pandas as pd  # <-- Added pandas import
import traceback  # <-- For more detailed error logging

from PyQt6.QtCore import (
    Qt, QRectF, QPointF, QSize, pyqtSignal, QUrl
)
from PyQt6.QtGui import (
    QPixmap, QPen, QColor, QPainter, QBrush, QFont, QCursor,
    QKeyEvent, QMouseEvent, QGuiApplication, QImageReader,
    QDesktopServices
)
from PyQt6.QtWidgets import (
    QVBoxLayout, QPushButton, QLabel,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsTextItem, QInputDialog,
    QMessageBox, QSpinBox, QGroupBox, QDialog, QDialogButtonBox,
    QFormLayout, QDoubleSpinBox, QStyleOptionGraphicsItem, QGraphicsItem, QGraphicsSceneMouseEvent, QStyle
)

import config

logger_gui = logging.getLogger(__name__)


# --- Fallback or Real StateManager ---
_StateManagerGUI = None
try:
    from state_manager import StateManager as _StateManagerGUI
    if not hasattr(_StateManagerGUI, 'get_setting'):
        _StateManagerGUI = None
    else:
        logger_gui.info("OK: StateManager imported in gui.py.")
except ImportError as e_sm_gui:
    logger_gui.warning(
        f"Failed StateManager import in gui.py: {e_sm_gui}. Will try dummy.")
    _StateManagerGUI = None
except Exception as e_sm_other_gui:
    logger_gui.error(
        f"Error importing/checking StateManager in gui.py: {e_sm_other_gui}")
    _StateManagerGUI = None

if _StateManagerGUI is None:
    try:
        from dummy_components import _DummyStateManager as _StateManagerGUI
        logger_gui.warning("--- Using DUMMY StateManager in gui.py ---")
    except ImportError as e_dummy_sm_gui:
        logger_gui.critical(
            f"CRITICAL: Failed to import DUMMY StateManager in gui.py: {e_dummy_sm_gui}"
        )
        raise ImportError(
            f"Cannot load StateManager or its dummy in gui.py: {e_dummy_sm_gui}"
        ) from e_dummy_sm_gui

StateManager = _StateManagerGUI


# --- ResizableRectItem Class ---
class ResizableRectItem(QGraphicsRectItem):
    handleSize = +8.0
    handleSpace = -4.0
    handleCursors = {
        1: Qt.CursorShape.SizeFDiagCursor, 2: Qt.CursorShape.SizeVerCursor,
        3.1: Qt.CursorShape.SizeBDiagCursor, 4: Qt.CursorShape.SizeHorCursor,
        5: Qt.CursorShape.SizeAllCursor, 6: Qt.CursorShape.SizeHorCursor,
        7.1: Qt.CursorShape.SizeFDiagCursor, 8: Qt.CursorShape.SizeVerCursor,
        9: Qt.CursorShape.SizeBDiagCursor,
    }

    def __init__(self, rect: QRectF, class_label: str = "Object", parent: QGraphicsItem | None = None):
        original_top_left = rect.topLeft()
        new_rect = QRectF(0, 0, rect.width(), rect.height())
        super().__init__(new_rect, parent)
        self.setPos(original_top_left)

        self.class_label = class_label
        self.handles = {}
        self.handleSelected = None
        self.mousePressPos = None
        self.mousePressRect = None
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(
            QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setPen(QPen(QColor(0, 255, 255), 3))

        # Create a text label inside the box
        self.textItem = QGraphicsTextItem(self.class_label, self)
        self.textItem.setDefaultTextColor(QColor(255, 255, 255))
        font = QFont()
        font.setPointSize(10)
        self.textItem.setFont(font)
        self.textItem.setPos(
            (self.rect().width() - self.textItem.boundingRect().width()) / 2, 0
        )

        self.updateHandlesPos()

    def handleAt(self, point):
        for k, v in self.handles.items():
            if v.contains(point):
                return k
        return None

    def hoverMoveEvent(self, moveEvent):
        cursor_shape = Qt.CursorShape.ArrowCursor
        if self.isSelected():
            handle = self.handleAt(moveEvent.pos())
            cursor_shape = self.handleCursors.get(
                handle, Qt.CursorShape.ArrowCursor)
            if handle is None and self.boundingRect().contains(moveEvent.pos()):
                cursor_shape = Qt.CursorShape.SizeAllCursor
        self.setCursor(QCursor(cursor_shape))
        super().hoverMoveEvent(moveEvent)

    def hoverLeaveEvent(self, leaveEvent):
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(leaveEvent)

    def mousePressEvent(self, mouseEvent):
        self.handleSelected = self.handleAt(mouseEvent.pos())
        if self.handleSelected:
            self.mousePressPos = mouseEvent.pos()
            self.mousePressRect = self.rect()
        super().mousePressEvent(mouseEvent)

    def mouseMoveEvent(self, mouseEvent):
        if self.handleSelected is not None and self.mousePressPos is not None:
            self.interactiveResize(mouseEvent.pos())
        else:
            super().mouseMoveEvent(mouseEvent)

    def mouseReleaseEvent(self, mouseEvent):
        super().mouseReleaseEvent(mouseEvent)
        self.handleSelected = None
        self.mousePressPos = None
        self.mousePressRect = None
        self.update()

    def interactiveResize(self, mousePos):
        if self.mousePressPos is None or self.mousePressRect is None:
            return
        diff = mousePos - self.mousePressPos
        self.prepareGeometryChange()
        new_rect = QRectF(self.mousePressRect)

        if self.handleSelected == 1:
            new_rect.setTopLeft(self.mousePressRect.topLeft() + diff)
        elif self.handleSelected == 2:
            new_rect.setTop(self.mousePressRect.top() + diff.y())
        elif self.handleSelected == 3.1:
            new_rect.setTopRight(self.mousePressRect.topRight() + diff)
        elif self.handleSelected == 4:
            new_rect.setLeft(self.mousePressRect.left() + diff.x())
        elif self.handleSelected == 6:
            new_rect.setRight(self.mousePressRect.right() + diff.x())
        elif self.handleSelected == 7.1:
            new_rect.setBottomLeft(self.mousePressRect.bottomLeft() + diff)
        elif self.handleSelected == 8:
            new_rect.setBottom(self.mousePressRect.bottom() + diff.y())
        elif self.handleSelected == 9:
            new_rect.setBottomRight(self.mousePressRect.bottomRight() + diff)

        normalized_rect = new_rect.normalized()
        minSize = 5.0
        if normalized_rect.width() < minSize:
            if self.handleSelected in [1, 4, 7.1]:
                normalized_rect.setWidth(minSize)
            else:
                normalized_rect.setLeft(normalized_rect.right() - minSize)
        if normalized_rect.height() < minSize:
            if self.handleSelected in [1, 2, 3.1]:
                normalized_rect.setHeight(minSize)
            else:
                normalized_rect.setTop(normalized_rect.bottom() - minSize)
        self.setRect(normalized_rect)
        self.updateHandlesPos()

    def updateHandlesPos(self):
        s, hs = self.handleSize, self.handleSpace
        r = self.rect()
        cx, cy = r.center().x(), r.center().y()
        self.handles[1] = QRectF(r.left() + hs, r.top() + hs, s, s)
        self.handles[2] = QRectF(cx - s / 2, r.top() + hs, s, s)
        self.handles[3.1] = QRectF(r.right() - s - hs, r.top() + hs, s, s)
        self.handles[4] = QRectF(r.left() + hs, cy - s / 2, s, s)
        self.handles[6] = QRectF(r.right() - s - hs, cy - s / 2, s, s)
        self.handles[7.1] = QRectF(r.left() + hs, r.bottom() - s - hs, s, s)
        self.handles[8] = QRectF(cx - s / 2, r.bottom() - s - hs, s, s)
        self.handles[9] = QRectF(r.right() - s - hs, r.bottom() - s - hs, s, s)

    def shape(self):
        path = super().shape()
        if self.isSelected():
            for hr in self.handles.values():
                path.addRect(hr)
        return path

    def paint(self, painter, option, widget=None):
        pen = self.pen()
        brush_color = QColor(
            pen.color().red(), pen.color().green(), pen.color().blue(), 50)
        painter.setBrush(QBrush(brush_color))
        current_option = QStyleOptionGraphicsItem(option)
        current_option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, current_option, widget)

        if option.state & QStyle.StateFlag.State_Selected:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            handle_fill = pen.color().darker(130)
            handle_fill.setAlpha(200)
            painter.setBrush(QBrush(handle_fill))
            painter.setPen(QPen(pen.color(), 1.0, Qt.PenStyle.SolidLine))
            for handle in self.handles.values():
                painter.drawEllipse(handle)

    def itemChange(self, change, value):
        if change in (
            QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemTransformHasChanged
        ):
            r = self.rect()
            tw = self.textItem.boundingRect().width()
            new_x = (r.width() - tw) / 2.0
            new_y = 0
            self.textItem.setPos(new_x, new_y)
        elif change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update()
        return super().itemChange(change, value)

    def get_annotation_data(self, image_width, image_height):
        scene_rect = self.sceneBoundingRect()
        img_item = self.scene().image_item if self.scene(
        ) and hasattr(self.scene(), "image_item") else None
        if not img_item or img_item.pixmap().isNull():
            logger_gui.error(
                "Cannot get pixel coords: Invalid image item in scene.")
            return None
        try:
            pixel_rect = img_item.mapRectFromScene(scene_rect)
        except Exception as map_err:
            logger_gui.error(
                f"Error mapping scene rect to pixel rect: {map_err}")
            return None

        x1 = max(0.0, pixel_rect.left())
        y1 = max(0.0, pixel_rect.top())
        x2 = min(float(image_width), pixel_rect.right())
        y2 = min(float(image_height), pixel_rect.bottom())
        pw, ph = x2 - x1, y2 - y1
        if pw >= 1.0 and ph >= 1.0:
            return {
                "rect": [round(x1), round(y1), round(pw), round(ph)],
                "class": self.class_label
            }
        else:
            logger_gui.warning(
                f"Item '{self.class_label}' invalid pixel coords: w={pw}, h={ph}. Skipping.")
            return None

    def mouseDoubleClickEvent(self, event):
        parent_window = self.scene().parent_window if self.scene(
        ) and hasattr(self.scene(), "parent_window") else None
        if parent_window and hasattr(parent_window, "state") and parent_window.state \
                and hasattr(parent_window.state, "class_list"):
            available_classes = getattr(parent_window.state, "class_list", [])
            if available_classes:
                current_index = -1
                try:
                    current_index = available_classes.index(self.class_label)
                except ValueError:
                    pass
                new_label, ok = QInputDialog.getItem(
                    None, "Change Class", "Select new class:",
                    available_classes, current_index if current_index != -1 else 0, False
                )
                if ok and new_label:
                    self.class_label = new_label
                    self.textItem.setPlainText(self.class_label)
                    self.update()
                    if self.scene() and hasattr(self.scene(), "annotationsModified"):
                        self.scene().annotationsModified.emit()
            else:
                logger_gui.warning(
                    "Double-clicked box, but no classes available.")
        else:
            logger_gui.warning("Could not get class list for double-click.")
        super().mouseDoubleClickEvent(event)


# --- AnnotationScene Class ---
class AnnotationScene(QGraphicsScene):
    annotationsModified = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.image_item = QGraphicsPixmapItem()
        self.addItem(self.image_item)
        self.image_item.setZValue(-10)
        self.start_point = QPointF()
        self.current_rect_item = None
        self.drawing = False
        self.selection_tool = "bbox"
        logger_gui.info("AnnotationScene initialized.")

    def set_image(self, image_path):
        if image_path is None:
            self.image_item.setPixmap(QPixmap())
            self.setSceneRect(QRectF(0, 0, 1, 1))
            logger_gui.info("Scene image cleared.")
            return True
        try:
            reader = QImageReader(image_path)
            if not reader.canRead():
                logger_gui.error(f"QImageReader cannot read: {image_path}")
                pixmap = QPixmap(image_path)
                if pixmap.isNull():
                    logger_gui.error(
                        f"Failed load (Pixmap fallback): {image_path}")
                    self.image_item.setPixmap(QPixmap())
                    self.setSceneRect(QRectF(0, 0, 1, 1))
                    return False
                else:
                    self.image_item.setPixmap(pixmap)
                    self.setSceneRect(self.image_item.boundingRect())
                    logger_gui.info(
                        f"Image loaded (Pixmap fallback): {os.path.basename(image_path)}")
                    return True
            original_size = reader.size()
            max_dim = 4096
            if original_size.width() > max_dim or original_size.height() > max_dim:
                scale_factor = min(max_dim / original_size.width(),
                                   max_dim / original_size.height())
                new_width = int(original_size.width() * scale_factor)
                new_height = int(original_size.height() * scale_factor)
                reader.setScaledSize(QSize(new_width, new_height))
                logger_gui.info(f"Scaled image to {new_width}x{new_height}")
            image = reader.read()
            if image.isNull():
                logger_gui.error(
                    f"Failed read image data: {image_path}, Error: {reader.errorString()}")
                self.image_item.setPixmap(QPixmap())
                self.setSceneRect(QRectF(0, 0, 1, 1))
                return False
            pixmap = QPixmap.fromImage(image)
            self.image_item.setPixmap(pixmap)
            self.setSceneRect(self.image_item.boundingRect())
            logger_gui.info(
                f"Image loaded into scene: {os.path.basename(image_path)}")
            return True
        except Exception as e:
            logger_gui.error(
                f"Exception loading image {image_path}: {e}", exc_info=True)
            self.image_item.setPixmap(QPixmap())
            self.setSceneRect(QRectF(0, 0, 1, 1))
            return False

    def get_image_size(self):
        if self.image_item and not self.image_item.pixmap().isNull():
            size = self.image_item.pixmap().size()
            return size.width(), size.height()
        return 0, 0

    def set_tool(self, tool_name):
        if tool_name in ["select", "bbox"]:
            self.selection_tool = tool_name
            self.cancel_drawing()
            logger_gui.info(f"Scene tool: {tool_name}")
            view = self.views()[0] if self.views() else None
            if view:
                view.setCursor(Qt.CursorShape.CrossCursor if tool_name ==
                               "bbox" else Qt.CursorShape.ArrowCursor)
        else:
            logger_gui.warning(f"Unknown tool: {tool_name}")

    def cancel_drawing(self):
        if self.current_rect_item and self.drawing:
            self.removeItem(self.current_rect_item)
            logger_gui.debug("Canceled drawing.")
        self.drawing = False
        self.current_rect_item = None
        view = self.views()[0] if self.views() else None
        if view and self.selection_tool != "bbox":
            view.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        super().mousePressEvent(event)
        if event.isAccepted():
            return
        if (event.button() == Qt.MouseButton.LeftButton and
            self.selection_tool == "bbox" and
                self.image_item and not self.image_item.pixmap().isNull()):
            self.start_point = event.scenePos()
            img_rect = self.image_item.sceneBoundingRect()
            self.start_point.setX(max(img_rect.left(), min(
                self.start_point.x(), img_rect.right())))
            self.start_point.setY(max(img_rect.top(), min(
                self.start_point.y(), img_rect.bottom())))
            self.drawing = True
            self.current_rect_item = QGraphicsRectItem(
                QRectF(self.start_point, self.start_point))
            self.current_rect_item.setPen(
                QPen(QColor(0, 255, 255), 2, Qt.PenStyle.DashLine))
            self.addItem(self.current_rect_item)
            logger_gui.debug("Started drawing.")
            event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self.drawing and self.current_rect_item and self.selection_tool == "bbox":
            if not self.image_item or self.image_item.pixmap().isNull():
                return
            current_pos = event.scenePos()
            img_rect = self.image_item.sceneBoundingRect()
            current_pos.setX(max(img_rect.left(), min(
                current_pos.x(), img_rect.right())))
            current_pos.setY(max(img_rect.top(), min(
                current_pos.y(), img_rect.bottom())))
            rect = QRectF(self.start_point, current_pos).normalized()
            self.current_rect_item.setRect(rect)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        if (event.button() == Qt.MouseButton.LeftButton and
            self.drawing and
            self.selection_tool == "bbox" and
                self.current_rect_item):
            final_rect_scene = self.current_rect_item.rect()
            self.removeItem(self.current_rect_item)
            self.current_rect_item = None
            self.drawing = False
            rect_item_class = globals().get("ResizableRectItem")
            is_dummy_item = rect_item_class.__name__ == 'DummyResizableRectItem'
            if final_rect_scene.width() > 5 and final_rect_scene.height() > 5 and not is_dummy_item:
                label, ok = self.prompt_for_label()
                if ok and label:
                    resizable_rect = rect_item_class(final_rect_scene, label)
                    self.addItem(resizable_rect)
                    logger_gui.info(f"Added bbox: {label}")
                    self.annotationsModified.emit()
                elif not ok:
                    logger_gui.debug("Label entry canceled.")
            elif is_dummy_item:
                logger_gui.error("Cannot add: DummyResizableRectItem.")
            else:
                logger_gui.debug("Bbox too small.")
            logger_gui.debug("Finished drawing.")
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            if self.drawing:
                logger_gui.debug("Esc: cancel drawing.")
                self.cancel_drawing()
                event.accept()
            else:
                selected = self.selectedItems()
                if selected:
                    logger_gui.debug(
                        f"Esc: Deselecting {len(selected)} items.")
                    [item.setSelected(False) for item in selected]
                    event.accept()
                else:
                    event.accept()
        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            rect_item_class = globals().get("ResizableRectItem")
            is_dummy_item = rect_item_class.__name__ == 'DummyResizableRectItem'
            if is_dummy_item:
                logger_gui.warning("Delete ignored: DummyResizableRectItem.")
                event.accept()
                return
            items_to_delete = self.selectedItems()
            deleted_items_info = []
            if items_to_delete:
                for item in items_to_delete:
                    if isinstance(item, rect_item_class):
                        label = getattr(item, 'class_label', 'Unk')
                        self.removeItem(item)
                        deleted_items_info.append(label)
                if deleted_items_info:
                    logger_gui.info(f"Deleted items: {deleted_items_info}")
                    self.annotationsModified.emit()
                event.accept()
            else:
                event.accept()
        elif event.key() == Qt.Key.Key_C:
            logger_gui.debug("Key 'C': request paste.")
            if hasattr(self.parent_window, "paste_last_box"):
                self.parent_window.paste_last_box()
                event.accept()
            else:
                logger_gui.warning("Parent lacks 'paste_last_box'.")
                event.ignore()
        else:
            super().keyPressEvent(event)

    def prompt_for_label(self):
        parent_widget = self.views()[0] if self.views() else None
        available_classes = []
        label_to_return = None
        ok_status = False

        if (hasattr(self, "parent_window") and self.parent_window and
            hasattr(self.parent_window, "state") and self.parent_window.state and
                hasattr(self.parent_window.state, "class_list")):
            available_classes = getattr(
                self.parent_window.state, "class_list", [])

        try:
            if available_classes:
                label, ok = QInputDialog.getItem(
                    parent_widget, "Select Label", "Class:",
                    available_classes, 0, False
                )
            else:
                logging.warning(
                    "No classes defined, prompting for text label.")
                label, ok = QInputDialog.getText(
                    parent_widget, "Enter Label", "Label:")

            if ok and label:
                clean_label = label.strip()
                if clean_label:
                    logging.debug(f"Label selected/entered: {clean_label}")
                    label_to_return = clean_label
                    ok_status = True
                else:
                    logging.warning("Label input was empty after stripping.")
            else:
                logging.debug("Label selection/entry canceled or empty.")
        except Exception as e:
            logging.error(f"Error during QInputDialog: {e}", exc_info=True)
            ok_status = False

        return label_to_return, ok_status

    def add_annotation_item_from_data(self, annotation_data, image_width, image_height):
        try:
            if "rect" not in annotation_data or "class" not in annotation_data:
                raise KeyError("Missing 'rect' or 'class'.")
            x, y, w, h = map(float, annotation_data["rect"])
            label = str(annotation_data["class"]).strip()
            if w <= 0 or h <= 0:
                logger_gui.warning(
                    f"Skip non-positive dims: {annotation_data}")
                return False
            if not label:
                logger_gui.warning(f"Skip empty label: {annotation_data}")
                return False
            if x < 0 or y < 0 or (x + w) > image_width or (y + h) > image_height:
                logger_gui.warning(
                    f"Coords outside bounds: {annotation_data}.")
            rect_item_class = globals().get("ResizableRectItem")
            if rect_item_class and rect_item_class.__name__ != 'DummyResizableRectItem':
                if not self.image_item or self.image_item.pixmap().isNull():
                    logger_gui.error("Cannot add: Image item invalid.")
                    return False
                pixel_qrect = QRectF(x, y, w, h)
                scene_qrect = self.image_item.mapRectToScene(pixel_qrect)
                item = rect_item_class(scene_qrect, label)
                self.addItem(item)
                return True
            else:
                logger_gui.error(
                    "Cannot add: ResizableRectItem unavailable/dummy.")
                return False
        except KeyError as e:
            logger_gui.error(f"Missing key {e}: {annotation_data}")
            return False
        except (ValueError, TypeError) as e:
            logger_gui.error(f"Invalid value type: {annotation_data} - {e}")
            return False
        except Exception as e:
            logger_gui.error(
                f"Error adding item: {annotation_data}: {e}", exc_info=True)
            return False

    def clear_annotations(self):
        rect_item_class = globals().get("ResizableRectItem")
        if not rect_item_class or rect_item_class.__name__ == 'DummyResizableRectItem':
            logger_gui.warning(
                "Cannot clear: ResizableRectItem unavailable/dummy.")
            return
        items_to_remove = [item for item in self.items(
        ) if isinstance(item, rect_item_class)]
        if items_to_remove:
            logger_gui.debug(f"Clearing {len(items_to_remove)} items.")
            [self.removeItem(item) for item in items_to_remove]
        else:
            logger_gui.debug("ClearAnnotations: No items found.")

    def get_all_annotations(self):
        annotations = []
        img_w, img_h = self.get_image_size()
        if img_w <= 0 or img_h <= 0:
            logger_gui.error("Cannot get ann: Image not loaded.")
            return []
        rect_item_class = globals().get("ResizableRectItem")
        if not rect_item_class or rect_item_class.__name__ == 'DummyResizableRectItem':
            logger_gui.error(
                "Cannot get ann: ResizableRectItem unavailable/dummy.")
            return []
        for item in self.items():
            if isinstance(item, rect_item_class):
                if hasattr(item, 'get_annotation_data'):
                    data = item.get_annotation_data(img_w, img_h)
                    if data:
                        annotations.append(data)
                else:
                    logger_gui.warning("Item lacks get_annotation_data.")
        logger_gui.debug(
            f"get_all_annotations found {len(annotations)} valid annotations.")
        return annotations


# --- AnnotatorGraphicsView Class ---
class AnnotatorGraphicsView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._zoom = 0
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setStyleSheet(
            "background-color: #333333; border: 1px solid #555;")

        # --- >>> ADDED Viewport Update Mode <<< ---
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        # --- >>> END ADDED LINE <<< ---

    def wheelEvent(self, event):
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        zoom_range = (-5, 7)
        modifiers = QGuiApplication.keyboardModifiers()
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                zoomFactor = zoom_in_factor
                self._zoom = min(zoom_range[1], self._zoom + 1)
            else:
                zoomFactor = zoom_out_factor
                self._zoom = max(zoom_range[0], self._zoom - 1)
            # Check if zoom level is within valid range before scaling
            if zoom_range[0] < self._zoom < zoom_range[1]:
                self.scale(zoomFactor, zoomFactor)
            # Removed the fitInView call here to allow zooming beyond the initial fit
            # else: # Optionally fit if zoom hits limits
            #    scene_rect = self.sceneRect()
            #    if scene_rect.isValid() and not scene_rect.isEmpty():
            #        self.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatio)
            #        self._zoom = 0 # Reset zoom level if fitting
            event.accept()
        else:
            # Allow default scrolling if Ctrl is not pressed
            super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        # Handle middle mouse button for panning
        if event.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            # Create a fake left-button event for QGraphicsView's panning implementation
            fake_event = QMouseEvent(
                event.type(), event.position(),
                Qt.MouseButton.LeftButton,  # Pretend left button
                Qt.MouseButton.LeftButton,  # Buttons state
                event.modifiers()
            )
            super().mousePressEvent(fake_event)
        else:
            # For left/right clicks, disable panning to allow scene interactions
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        # If panning with middle button, finalize it correctly
        if event.button() == Qt.MouseButton.MiddleButton:
            # Create a fake left-button release event
            fake_event = QMouseEvent(
                event.type(), event.position(),
                Qt.MouseButton.LeftButton,  # Pretend left button
                Qt.MouseButton.NoButton,  # Buttons state (no button down)
                event.modifiers()
            )
            super().mouseReleaseEvent(fake_event)
            # Restore NoDrag mode after panning is finished
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
        else:
            super().mouseReleaseEvent(event)


# --- SettingsDialog Class ---
class SettingsDialog(QDialog):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        if not state or not hasattr(state, 'get_setting'):
            logger_gui.error("SettingsDialog invalid state.")
            self.state = None
        else:
            self.state = state

        self.setWindowTitle("Legacy Settings")
        self.setModal(True)
        layout = QFormLayout(self)

        self.conf_thresh_spin = QDoubleSpinBox()
        self.conf_thresh_spin.setRange(0.0, 1.0)
        self.conf_thresh_spin.setSingleStep(0.05)
        default_conf = config.DEFAULT_CONFIDENCE_THRESHOLD
        current_conf = default_conf
        if self.state:
            conf_key = config.SETTING_KEYS.get("confidence_threshold")
            current_conf = self.state.get_setting(
                conf_key, default_conf) if conf_key else default_conf
        self.conf_thresh_spin.setValue(current_conf)
        layout.addRow("Confidence Threshold:", self.conf_thresh_spin)

        if not self.state:
            self.conf_thresh_spin.setEnabled(False)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        if not self.state:
            self.button_box.button(
                QDialogButtonBox.StandardButton.Ok).setEnabled(False)

    def accept(self):
        if not self.state:
            logger_gui.error("Accept on SettingsDialog with invalid state.")
            super().reject()
            return
        try:
            conf_key = config.SETTING_KEYS.get("confidence_threshold")
            if conf_key and hasattr(self.state, 'set_setting'):
                self.state.set_setting(conf_key, self.conf_thresh_spin.value())
                logger_gui.info("Settings updated.")
                super().accept()
            else:
                logger_gui.error("Failed save settings.")
                QMessageBox.critical(self, "Error", "Could not save settings.")
        except ValueError as e:
            QMessageBox.warning(self, "Input Error", f"Invalid numeric: {e}")
        except Exception as e:
            logger_gui.error(f"Error saving settings: {e}", exc_info=True)
            QMessageBox.critical(
                self, "Error", f"Could not save settings: {e}")


# --- TrainingDashboard Class (Includes Augmentation Widgets) ---
class TrainingDashboard(QDialog):
    """Dialog to manage training parameters and view results graph plotted from CSV."""
    DARK_BG_COLOR = "#2E2E2E"
    LIGHT_TEXT_COLOR = "#FFFFFF"
    GRID_COLOR = "#666666"
    MAP_COLOR = "#00FFFF"
    LOSS_COLOR_TRAIN = "#FFA500"
    LOSS_COLOR_VAL = "#FF00FF"

    def __init__(self, state_manager, parent=None):
        super().__init__(parent)
        if not state_manager or not hasattr(state_manager, 'get_setting'):
            logger_gui.error(
                "TrainingDashboard received invalid state_manager object.")
            QMessageBox.critical(
                self, "Init Error", "Cannot open dashboard: Invalid state manager.")
            self.state_manager = None
        else:
            self.state_manager = state_manager

        self.setWindowTitle("Training Dashboard & Settings")
        self.setMinimumWidth(600)
        layout = QVBoxLayout(self)
        param_group = QGroupBox("Training Parameters (Used on Triggers)")
        param_layout = QFormLayout(param_group)

        def _get_setting(key_name, default_val):
            if not self.state_manager:
                return default_val
            key = config.SETTING_KEYS.get(key_name)
            return self.state_manager.get_setting(key, default_val) if key and hasattr(self.state_manager, 'get_setting') else default_val

        self.epochs_20_spin = QSpinBox()
        self.epochs_20_spin.setRange(1, 1000)
        self.epochs_20_spin.setValue(_get_setting(
            "epochs_20", config.DEFAULT_EPOCHS_20))
        param_layout.addRow("Epochs (20 Img Trigger):", self.epochs_20_spin)
        self.lr_20_spin = QDoubleSpinBox()
        self.lr_20_spin.setRange(0.000001, 0.1)
        self.lr_20_spin.setDecimals(6)
        self.lr_20_spin.setSingleStep(0.0001)
        self.lr_20_spin.setValue(_get_setting("lr_20", config.DEFAULT_LR_20))
        param_layout.addRow("Learning Rate (20 Img):", self.lr_20_spin)
        self.epochs_100_spin = QSpinBox()
        self.epochs_100_spin.setRange(1, 1000)
        self.epochs_100_spin.setValue(_get_setting(
            "epochs_100", config.DEFAULT_EPOCHS_100))
        param_layout.addRow("Epochs (100 Img Trigger):", self.epochs_100_spin)
        self.lr_100_spin = QDoubleSpinBox()
        self.lr_100_spin.setRange(0.000001, 0.1)
        self.lr_100_spin.setDecimals(6)
        self.lr_100_spin.setSingleStep(0.0001)
        self.lr_100_spin.setValue(_get_setting(
            "lr_100", config.DEFAULT_LR_100))
        param_layout.addRow("Learning Rate (100 Img):", self.lr_100_spin)

        param_layout.addRow(QLabel("--- Augmentations ---"))  # Separator
        self.flipud_spin = QDoubleSpinBox()
        self.flipud_spin.setRange(0.0, 1.0)
        self.flipud_spin.setDecimals(2)
        self.flipud_spin.setSingleStep(0.05)
        self.flipud_spin.setValue(_get_setting(
            "aug_flipud", config.DEFAULT_AUG_FLIPUD))
        param_layout.addRow("Vertical Flip Prob:", self.flipud_spin)
        self.fliplr_spin = QDoubleSpinBox()
        self.fliplr_spin.setRange(0.0, 1.0)
        self.fliplr_spin.setDecimals(2)
        self.fliplr_spin.setSingleStep(0.05)
        self.fliplr_spin.setValue(_get_setting(
            "aug_fliplr", config.DEFAULT_AUG_FLIPLR))
        param_layout.addRow("Horizontal Flip Prob:", self.fliplr_spin)
        self.degrees_spin = QDoubleSpinBox()
        self.degrees_spin.setRange(0.0, 180.0)
        self.degrees_spin.setDecimals(1)
        self.degrees_spin.setSingleStep(5.0)
        self.degrees_spin.setValue(_get_setting(
            "aug_degrees", config.DEFAULT_AUG_DEGREES))
        param_layout.addRow("Rotation Degrees (+/-):", self.degrees_spin)

        layout.addWidget(param_group)
        results_group = QGroupBox(
            "Latest Training Run Results (from results.csv)")
        results_layout = QVBoxLayout(results_group)
        self.figure = plt.figure()
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setMinimumSize(550, 350)
        results_layout.addWidget(self.canvas)
        self.open_folder_button = QPushButton("Open Last Run Folder")
        self.open_folder_button.clicked.connect(self.open_last_run_folder)
        results_layout.addWidget(self.open_folder_button)
        layout.addWidget(results_group)
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Close)
        self.button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self.apply_settings)
        self.button_box.rejected.connect(self.reject)  # Close maps to reject
        layout.addWidget(self.button_box)
        self.load_initial_graph()
        if not self.state_manager:
            param_group.setEnabled(False)
            results_group.setEnabled(False)
            self.button_box.button(
                QDialogButtonBox.StandardButton.Apply).setEnabled(False)

    def load_initial_graph(self):
        last_run_dir = None
        if self.state_manager and hasattr(self.state_manager, 'get_last_run_path'):
            try:
                last_run_dir = self.state_manager.get_last_run_path()
                logger_gui.info(
                    f"Dashboard init: Attempting load from last run dir: {last_run_dir}")
            except Exception as e:
                logger_gui.error(f"Error calling get_last_run_path: {e}")
        else:
            logger_gui.warning(
                "State manager or 'get_last_run_path' unavailable for initial graph load.")
        self.update_graph(last_run_dir)

    def apply_settings(self):
        if not self.state_manager:
            logger_gui.error("Apply settings ignored: Invalid state manager.")
            return
        if not hasattr(self.state_manager, 'set_setting'):
            logger_gui.error(
                "Apply settings failed: State manager missing 'set_setting'.")
            QMessageBox.critical(self, "Internal Error",
                                 "Cannot save settings: State manager invalid.")
            return

        def _set_setting(kn, v):
            k = config.SETTING_KEYS.get(kn)
            if k:
                self.state_manager.set_setting(k, v)
            else:
                logger_gui.error(f"Configuration key '{kn}' not found.")
        try:
            _set_setting("epochs_20", self.epochs_20_spin.value())
            _set_setting("lr_20", self.lr_20_spin.value())
            _set_setting("epochs_100", self.epochs_100_spin.value())
            _set_setting("lr_100", self.lr_100_spin.value())
            _set_setting("aug_flipud", self.flipud_spin.value())
            _set_setting("aug_fliplr", self.fliplr_spin.value())
            _set_setting("aug_degrees", self.degrees_spin.value())
            logger_gui.info(
                "Training and augmentation parameters applied via dashboard.")
        except ValueError as e:
            QMessageBox.warning(self, "Input Error",
                                f"Invalid numeric value entered: {e}")
        except Exception as e:
            logger_gui.error(
                f"Error applying settings via dashboard: {e}", exc_info=True)
            QMessageBox.critical(
                self, "Error", f"Could not apply settings: {e}")

    def open_last_run_folder(self):
        lrp = None
        if self.state_manager and hasattr(self.state_manager, "get_last_run_path"):
            try:
                lrp = self.state_manager.get_last_run_path()
            except Exception as e:
                logger_gui.error(f"Error calling get_last_run_path: {e}")
        if lrp and os.path.isdir(lrp):
            try:
                logger_gui.info(f"Opening folder: {lrp}")
                QDesktopServices.openUrl(QUrl.fromLocalFile(lrp))
            except Exception as e:
                logger_gui.error(f"Failed open folder {lrp}: {e}")
                QMessageBox.warning(
                    self, "Error", f"Could not open folder:\n{lrp}\n\nError: {e}")
        elif lrp:
            QMessageBox.warning(
                self, "Not Found", f"Last run folder path is not a valid directory:\n{lrp}")
        else:
            QMessageBox.information(
                self, "No Run Data", "No training run folder has been recorded yet.")

    def update_graph(self, run_dir_path):
        logger_gui.debug(
            f"Attempting to update graph from run directory: {run_dir_path}")
        self.figure.clear()
        self.figure.patch.set_facecolor(self.DARK_BG_COLOR)
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(self.DARK_BG_COLOR)
        display_message = None
        dataframe = None
        if run_dir_path and os.path.isdir(run_dir_path):
            csv_path = os.path.join(run_dir_path, "results.csv")
            if os.path.exists(csv_path):
                try:
                    dataframe = pd.read_csv(csv_path)
                    dataframe.columns = dataframe.columns.str.strip()
                    logger_gui.info(
                        f"Successfully loaded results.csv from {run_dir_path}")
                    logger_gui.debug(f"CSV Columns: {list(dataframe.columns)}")
                except pd.errors.EmptyDataError:
                    display_message = "results.csv is empty."
                    logger_gui.warning(
                        f"Empty results.csv found in {run_dir_path}")
                except FileNotFoundError:
                    display_message = "results.csv not found."
                    logger_gui.warning(
                        f"results.csv not found at {csv_path} (should exist).")
                except Exception as e:
                    display_message = f"Error reading CSV:\n{e}"
                    logger_gui.error(
                        f"Error reading {csv_path}: {e}\n{traceback.format_exc()}")
            else:
                display_message = "results.csv not found in run directory."
                logger_gui.warning(f"results.csv not found in {run_dir_path}")
        elif run_dir_path:
            display_message = "Invalid run directory path."
            logger_gui.warning(
                f"Invalid run directory path provided: {run_dir_path}")
        else:
            display_message = "No training run data available."
            logger_gui.info("No run directory path provided for plotting.")

        plot_success = False
        if dataframe is not None:
            try:
                epoch_col = 'epoch'
                map_col = 'metrics/mAP50-95(B)'
                val_loss_col = 'val/box_loss'
                train_loss_col = 'train/box_loss'
                required_cols = [epoch_col, map_col]
                if not all(col in dataframe.columns for col in required_cols):
                    raise KeyError(
                        f"Missing required columns: {[c for c in required_cols if c not in dataframe.columns]}")
                ax.plot(dataframe[epoch_col], dataframe[map_col], color=self.MAP_COLOR,
                        marker='o', linestyle='-', linewidth=1.5, markersize=4, label='mAP50-95')
                ax.set_ylabel('mAP 50-95', color=self.LIGHT_TEXT_COLOR)
                ax.tick_params(axis='y', labelcolor=self.LIGHT_TEXT_COLOR)
                plot_loss = True
                loss_cols_exist = all(col in dataframe.columns for col in [
                                      val_loss_col, train_loss_col])
                if plot_loss and loss_cols_exist:
                    ax2 = ax.twinx()
                    ax2.plot(dataframe[epoch_col], dataframe[train_loss_col], color=self.LOSS_COLOR_TRAIN,
                             marker='.', linestyle='--', linewidth=1, markersize=3, label='Train Loss (Box)')
                    ax2.plot(dataframe[epoch_col], dataframe[val_loss_col], color=self.LOSS_COLOR_VAL,
                             marker='.', linestyle=':', linewidth=1, markersize=3, label='Val Loss (Box)')
                    ax2.set_ylabel('Loss', color=self.LIGHT_TEXT_COLOR)
                    ax2.tick_params(axis='y', labelcolor=self.LIGHT_TEXT_COLOR)
                    lines, labels = ax.get_legend_handles_labels()
                    lines2, labels2 = ax2.get_legend_handles_labels()
                    ax2.legend(lines + lines2, labels + labels2, loc='best',
                               fontsize='small', frameon=False, labelcolor=self.LIGHT_TEXT_COLOR)
                    for spine in ax2.spines.values():
                        spine.set_edgecolor(self.GRID_COLOR)
                elif ax.get_legend_handles_labels()[1]:
                    ax.legend(loc='best', fontsize='small',
                              frameon=False, labelcolor=self.LIGHT_TEXT_COLOR)
                ax.set_xlabel('Epoch', color=self.LIGHT_TEXT_COLOR)
                ax.set_title('Training Metrics',
                             color=self.LIGHT_TEXT_COLOR, fontsize=12)
                ax.grid(True, color=self.GRID_COLOR,
                        linestyle=':', linewidth=0.5)
                ax.tick_params(axis='x', colors=self.LIGHT_TEXT_COLOR)
                for spine in ax.spines.values():
                    spine.set_edgecolor(self.GRID_COLOR)
                plot_success = True
            except KeyError as e:
                display_message = f"Missing expected column in results.csv:\n{e}"
                logger_gui.error(f"Plotting failed due to missing column: {e}")
            except Exception as e:
                display_message = f"Error during plotting:\n{e}"
                logger_gui.error(
                    f"Error plotting data from {run_dir_path}: {e}\n{traceback.format_exc()}")
        if not plot_success:
            ax.text(0.5, 0.5, display_message or "Unknown error", ha="center", va="center",
                    color=self.LIGHT_TEXT_COLOR, fontsize=10, wrap=True, transform=ax.transAxes)
            ax.axis('off')
        try:
            self.figure.tight_layout()
            self.canvas.draw()
            logger_gui.debug("Canvas redrawn after plotting attempt.")
        except Exception as draw_err:
            logger_gui.error(
                f"Error finalizing or drawing canvas: {draw_err}", exc_info=True)
            try:
                self.figure.clear()
                ax_err = self.figure.add_subplot(111)
                ax_err.set_facecolor(self.DARK_BG_COLOR)
                ax_err.text(0.5, 0.5, "Canvas Draw Error",
                            ha="center", va="center", color="red")
                ax_err.axis('off')
                self.canvas.draw()
            except Exception:
                pass

# --- End of gui.py ---
