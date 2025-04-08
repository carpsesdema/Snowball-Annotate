#!/usr/bin/env python3
"""
gui.py
"""

import logging
import os
import matplotlib.pyplot as plt
from PyQt6.QtCore import QTimer  # ADDED: For itemChange update

# Use the unified Qt-based canvas (works for Qt5 or Qt6) in Matplotlib 3.7+:
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
import pandas as pd
import traceback

from PyQt6.QtCore import (
    Qt,
    QRectF,
    QPointF,
    QSize,
    pyqtSignal,
    QUrl,
    QObject,
)
from PyQt6.QtGui import (
    QPixmap,
    QPen,
    QColor,
    QPainter,
    QBrush,
    QFont,
    QCursor,
    QKeyEvent,
    QMouseEvent,
    QGuiApplication,
    QImageReader,
    QDesktopServices,
    QPainterPath,
    QTransform,
)
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QPushButton,
    QLabel,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
    QInputDialog,
    QMessageBox,
    QSpinBox,
    QGroupBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QDoubleSpinBox,
    QStyleOptionGraphicsItem,
    QGraphicsItem,
    QGraphicsSceneMouseEvent,
    QStyle,
    QCheckBox,  # ADDED: CheckBox import
)

import config

logger_gui = logging.getLogger(__name__)


# --- Fallback or Real StateManager ---
# (Assuming StateManager import logic remains as originally provided in gui.txt)
_StateManagerGUI = None
try:
    from state_manager import StateManager as _StateManagerGUI

    if not hasattr(_StateManagerGUI, "get_setting"):
        _StateManagerGUI = None
    else:
        logger_gui.info("OK: StateManager imported in gui.py.")
except ImportError as e_sm_gui:
    logger_gui.warning(
        f"Failed StateManager import in gui.py: {e_sm_gui}. Will try dummy."
    )
    _StateManagerGUI = None
except Exception as e_sm_other_gui:
    logger_gui.error(
        f"Error importing/checking StateManager in gui.py: {e_sm_other_gui}"
    )
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


# --- ResizableRectItem Class (Modified for Suggestions) ---
class ResizableRectItem(QGraphicsRectItem):
    """
    A QGraphicsRectItem that is resizable via handles at the corners
    and displays a class label. Modified for a more modern look
    with rounded corners and corner bracket handles instead of dots.
    Can also represent AI suggestions which are initially non-interactive
    but can be converted to regular annotations.
    """

    handleSize = 10.0
    handleSpace = -5.0
    handleRegions = {
        1: "TopLeft",
        2: "Top",
        3: "TopRight",
        4: "Left",
        5: "Center",
        6: "Right",
        7: "BottomLeft",
        8: "Bottom",
        9: "BottomRight",
    }
    handleCursors = {
        1: Qt.CursorShape.SizeFDiagCursor,
        2: Qt.CursorShape.SizeVerCursor,
        3: Qt.CursorShape.SizeBDiagCursor,
        4: Qt.CursorShape.SizeHorCursor,
        5: Qt.CursorShape.SizeAllCursor,
        6: Qt.CursorShape.SizeHorCursor,
        7: Qt.CursorShape.SizeBDiagCursor,
        8: Qt.CursorShape.SizeVerCursor,
        9: Qt.CursorShape.SizeFDiagCursor,
    }
    cornerHandles = [1, 3, 7, 9]

    # MODIFICATION: Added is_suggestion flag
    def __init__(
        self,
        rect: QRectF,
        class_label: str = "Object",
        parent: QGraphicsItem | None = None,
        is_suggestion: bool = False,  # ADDED: Flag to indicate if this is a suggestion
        confidence: float | None = None,  # ADDED: Store confidence for suggestions
    ):
        """
        Initializes the item.
        Sets position based on rect.topLeft() and makes the item rect start at (0,0).
        """
        original_top_left = rect.topLeft()
        new_rect = QRectF(0, 0, rect.width(), rect.height())
        super().__init__(new_rect, parent)
        self.setPos(original_top_left)

        # ADDED: Store suggestion state and confidence
        self.is_suggestion = is_suggestion
        self.confidence = confidence
        # Store original label in case conversion fails or is cancelled
        self._original_label = class_label
        # Use provided label, potentially adding confidence if it's a suggestion
        self.class_label = (
            f"{class_label} ({confidence:.2f})"
            if is_suggestion and confidence is not None
            else class_label
        )

        self.handles = {}
        self.handleSelected = None
        self.mousePressPos = None
        self.mousePressRect = None

        # --- Item Flags and Properties ---
        self.setAcceptHoverEvents(True)
        # MODIFICATION: Flags are now conditional based on is_suggestion
        self.setFlag(
            QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True
        )  # Always selectable
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True
        )  # Always focusable (for delete key)
        # Movable flag depends on whether it's a suggestion
        self.setFlag(
            QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, not self.is_suggestion
        )

        # --- Visuals ---
        # Define base colors (will be adjusted in paint based on state)
        self._regular_pen_color = QColor(0, 255, 255, 220)  # Cyan
        self._regular_brush_color = QColor(0, 150, 150, 50)  # Cyan fill
        self._selected_pen_color = QColor(255, 255, 0, 255)  # Yellow
        self._selected_brush_color = QColor(150, 150, 0, 70)  # Yellow fill
        # ADDED: Suggestion-specific colors
        self._suggestion_pen_color = QColor(0, 255, 0, 180)  # Green
        self._suggestion_brush_color = QColor(
            0, 150, 0, 30
        )  # Lighter green fill for suggestions
        self._suggestion_selected_pen_color = QColor(
            100, 255, 255, 220
        )  # Light blue when suggestion is selected

        # Pen will be set dynamically in paint()
        self.setPen(QPen(self._regular_pen_color, 2))
        self.pen().setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setBrush(QBrush(self._regular_brush_color))

        # --- Text Label ---
        # ADDED: Text color also depends on state
        self._regular_text_color = QColor(255, 255, 255, 200)  # White
        self._suggestion_text_color = QColor(200, 255, 200, 200)  # Light green

        self.textItem = QGraphicsTextItem(self.class_label, self)
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        self.textItem.setFont(font)
        self._updateTextPosition()

        self.updateHandlesPos()
        self.update_visuals()  # ADDED: Apply initial visuals based on state

    # ADDED: Helper to update visuals based on state
    def update_visuals(self):
        """Sets the pen, brush, and text color based on current state."""
        is_selected = self.isSelected()

        if self.is_suggestion:
            current_pen = QPen(
                self._suggestion_selected_pen_color
                if is_selected
                else self._suggestion_pen_color,
                2,
            )
            current_pen.setStyle(Qt.PenStyle.DashLine)  # Dashed line for suggestions
            current_brush = QBrush(
                self._suggestion_brush_color
                if not is_selected
                else QColor(100, 150, 150, 60)
            )
            text_color = self._suggestion_text_color
            label_text = (
                f"{self._original_label} ({self.confidence:.2f})"
                if self.confidence is not None
                else self._original_label
            )
        else:
            current_pen = QPen(
                self._selected_pen_color if is_selected else self._regular_pen_color,
                2.5 if is_selected else 2,
            )
            current_pen.setStyle(Qt.PenStyle.SolidLine)
            current_brush = QBrush(
                self._selected_brush_color if is_selected else self._regular_brush_color
            )
            text_color = self._regular_text_color
            label_text = self.class_label

        current_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(current_pen)
        self.setBrush(current_brush)
        if self.textItem:
            self.textItem.setDefaultTextColor(text_color)
            if self.textItem.toPlainText() != label_text:
                self.textItem.setPlainText(label_text)
                self._updateTextPosition()  # Recenter if text changed
        self.update()  # Trigger repaint

    def _updateTextPosition(self):
        """Centers the text label within the bounding box."""
        if self.textItem:
            text_rect = self.textItem.boundingRect()
            item_rect = self.rect()
            x = (item_rect.width() - text_rect.width()) / 2
            y = 2  # Small offset from the top edge
            self.textItem.setPos(x, y)

    def handleAt(self, point: QPointF) -> int | None:
        """Check if the point is within any handle region."""
        for k in reversed(sorted(self.handles.keys())):
            if self.handles[k].contains(point):
                return k
        return None

    def hoverMoveEvent(self, moveEvent: QGraphicsSceneMouseEvent):
        """Change cursor based on hover position over handles or item body."""
        cursor_shape = Qt.CursorShape.ArrowCursor
        if self.isSelected() and not self.is_suggestion:
            handle_key = self.handleAt(moveEvent.pos())
            cursor_shape = self.handleCursors.get(
                handle_key, Qt.CursorShape.ArrowCursor
            )
            if handle_key is None and self.rect().contains(moveEvent.pos()):
                cursor_shape = self.handleCursors.get(5)  # Center/Move cursor
        elif self.is_suggestion:
            cursor_shape = (
                Qt.CursorShape.PointingHandCursor
            )  # Indicate clickable suggestion

        self.setCursor(QCursor(cursor_shape))
        super().hoverMoveEvent(moveEvent)

    def hoverLeaveEvent(self, leaveEvent: QGraphicsSceneMouseEvent):
        """Reset cursor when mouse leaves the item."""
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().hoverLeaveEvent(leaveEvent)

    def mousePressEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
        """Select handle or prepare for moving the item (if not a suggestion)."""
        if not self.is_suggestion:
            self.handleSelected = self.handleAt(mouseEvent.pos())
            if self.handleSelected:
                self.mousePressPos = mouseEvent.pos()
                self.mousePressRect = self.rect()
            else:
                pass  # Let base class handle moving
        else:
            self.handleSelected = None  # Suggestions are not resized this way

        super().mousePressEvent(mouseEvent)

    def mouseMoveEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
        """Resize the item if a handle is selected (and not suggestion), otherwise move."""
        if (
            self.handleSelected is not None
            and self.mousePressPos is not None
            and not self.is_suggestion
        ):
            self.interactiveResize(mouseEvent.pos())
        elif not self.is_suggestion:
            super().mouseMoveEvent(mouseEvent)
        # Do nothing on move if it IS a suggestion

    def mouseReleaseEvent(self, mouseEvent: QGraphicsSceneMouseEvent):
        """Finalize resize/move operation."""
        super().mouseReleaseEvent(mouseEvent)
        self.handleSelected = None
        self.mousePressPos = None
        self.mousePressRect = None
        self.update()
        if (
            not self.is_suggestion
            and self.scene()
            and hasattr(self.scene(), "annotationsModified")
        ):
            self.scene().annotationsModified.emit()

    def interactiveResize(self, mousePos: QPointF):
        """Calculates the new rectangle geometry based on the handle dragged."""
        if self.mousePressPos is None or self.mousePressRect is None:
            return
        diff = mousePos - self.mousePressPos
        self.prepareGeometryChange()
        new_rect = QRectF(self.mousePressRect)
        if self.handleSelected == 1:
            new_rect.setTopLeft(self.mousePressRect.topLeft() + diff)
        elif self.handleSelected == 2:
            new_rect.setTop(self.mousePressRect.top() + diff.y())
        elif self.handleSelected == 3:
            new_rect.setTopRight(self.mousePressRect.topRight() + diff)
        elif self.handleSelected == 4:
            new_rect.setLeft(self.mousePressRect.left() + diff.x())
        elif self.handleSelected == 6:
            new_rect.setRight(self.mousePressRect.right() + diff.x())
        elif self.handleSelected == 7:
            new_rect.setBottomLeft(self.mousePressRect.bottomLeft() + diff)
        elif self.handleSelected == 8:
            new_rect.setBottom(self.mousePressRect.bottom() + diff.y())
        elif self.handleSelected == 9:
            new_rect.setBottomRight(self.mousePressRect.bottomRight() + diff)

        normalized_rect = new_rect.normalized()
        minSize = 5.0
        if normalized_rect.width() < minSize:
            if self.handleSelected in [1, 4, 7]:
                normalized_rect.setWidth(minSize)
            else:
                normalized_rect.setLeft(normalized_rect.right() - minSize)
        if normalized_rect.height() < minSize:
            if self.handleSelected in [1, 2, 3]:
                normalized_rect.setHeight(minSize)
            else:
                normalized_rect.setTop(normalized_rect.bottom() - minSize)

        self.setRect(normalized_rect)
        self.updateHandlesPos()
        self._updateTextPosition()

    def updateHandlesPos(self):
        """Calculate the positions of the handle *regions* based on the current rect."""
        s = self.handleSize
        hs = self.handleSpace
        r = self.rect()
        cx = r.center().x()
        cy = r.center().y()
        self.handles[1] = QRectF(r.left() + hs, r.top() + hs, s, s)
        self.handles[2] = QRectF(cx - s / 2, r.top() + hs, s, s)
        self.handles[3] = QRectF(r.right() - s - hs, r.top() + hs, s, s)
        self.handles[4] = QRectF(r.left() + hs, cy - s / 2, s, s)
        self.handles[6] = QRectF(r.right() - s - hs, cy - s / 2, s, s)
        self.handles[7] = QRectF(r.left() + hs, r.bottom() - s - hs, s, s)
        self.handles[8] = QRectF(cx - s / 2, r.bottom() - s - hs, s, s)
        self.handles[9] = QRectF(r.right() - s - hs, r.bottom() - s - hs, s, s)

    def shape(self) -> QPainterPath:
        """Define the collision shape, including handle areas when selected (and not suggestion)."""
        path = QPainterPath()
        path.addRect(self.rect())
        if self.isSelected() and not self.is_suggestion:
            for k, hr in self.handles.items():
                if k in self.cornerHandles:
                    path.addRect(hr)
        return path

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        """Paint the rounded rectangle, text label, and corner handles (if applicable)."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        current_pen = self.pen()
        current_brush = self.brush()
        painter.setPen(current_pen)
        painter.setBrush(current_brush)
        corner_radius = 5.0
        painter.drawRoundedRect(self.rect(), corner_radius, corner_radius)

        if option.state & QStyle.StateFlag.State_Selected and not self.is_suggestion:
            handle_length = self.handleSize * 0.8
            handle_pen = QPen(current_pen.color(), current_pen.widthF() * 1.2)
            handle_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(handle_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = self.rect()
            topLeft = r.topLeft()
            topRight = r.topRight()
            bottomLeft = r.bottomLeft()
            bottomRight = r.bottomRight()
            # Top-Left Bracket
            painter.drawLine(QPointF(topLeft.x(), topLeft.y() + handle_length), topLeft)
            painter.drawLine(topLeft, QPointF(topLeft.x() + handle_length, topLeft.y()))
            # Top-Right Bracket
            painter.drawLine(
                QPointF(topRight.x() - handle_length, topRight.y()), topRight
            )
            painter.drawLine(
                topRight, QPointF(topRight.x(), topRight.y() + handle_length)
            )
            # Bottom-Left Bracket
            painter.drawLine(
                QPointF(bottomLeft.x(), bottomLeft.y() - handle_length), bottomLeft
            )
            painter.drawLine(
                bottomLeft, QPointF(bottomLeft.x() + handle_length, bottomLeft.y())
            )
            # Bottom-Right Bracket
            painter.drawLine(
                QPointF(bottomRight.x() - handle_length, bottomRight.y()), bottomRight
            )
            painter.drawLine(
                bottomRight, QPointF(bottomRight.x(), bottomRight.y() - handle_length)
            )

        # Text label (child item) paints itself automatically

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):
        """Handle changes to the item's state or position."""
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            QTimer.singleShot(0, self.update_visuals)
        elif (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and not self.is_suggestion
        ):
            if self.scene() and hasattr(self.scene(), "annotationsModified"):
                self.scene().annotationsModified.emit()
        return super().itemChange(change, value)

    # ADDED: Method to convert suggestion to regular annotation
    def convert_to_annotation(self):
        """Converts this item from a suggestion to a regular annotation."""
        if not self.is_suggestion:
            logger_gui.debug("Item is already a regular annotation.")
            return
        logger_gui.info(f"Converting suggestion '{self.class_label}' to annotation.")
        self.is_suggestion = False
        self.class_label = self._original_label
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.update_visuals()
        if self.scene() and hasattr(self.scene(), "annotationsModified"):
            self.scene().annotationsModified.emit()

    def get_annotation_data(self, image_width: int, image_height: int) -> dict | None:
        """Converts the item's scene coordinates to image pixel coordinates."""
        if self.is_suggestion:
            return None
        scene = self.scene()
        if not scene or not hasattr(scene, "image_item"):
            logger_gui.error(
                "Cannot get annotation data: Scene or scene.image_item missing."
            )
            return None
        img_item = scene.image_item
        if not img_item or img_item.pixmap().isNull():
            logger_gui.error("Cannot get annotation data: Invalid image item in scene.")
            return None
        scene_rect = self.sceneBoundingRect()
        try:
            pixel_rect = img_item.mapRectFromScene(scene_rect)
        except Exception as map_err:
            logger_gui.error(
                f"Error mapping scene rect to pixel rect: {map_err}", exc_info=True
            )
            return None
        x1 = max(0.0, pixel_rect.left())
        y1 = max(0.0, pixel_rect.top())
        x2 = min(float(image_width), pixel_rect.right())
        y2 = min(float(image_height), pixel_rect.bottom())
        pw = x2 - x1
        ph = y2 - y1
        if pw >= 1.0 and ph >= 1.0:
            return {
                "rect": [round(x1), round(y1), round(pw), round(ph)],
                "class": self.class_label,
            }
        else:
            logger_gui.warning(
                f"Item '{self.class_label}' resulted in invalid pixel coords: w={pw:.2f}, h={ph:.2f}. Skipping."
            )
            return None

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
        """
        Convert suggestion to annotation on double-click,
        or allow changing class label for existing annotations.
        """
        if self.is_suggestion:
            logger_gui.debug("Double-click on suggestion: Converting to annotation.")
            self.convert_to_annotation()
            event.accept()
            return

        parent_window = (
            self.scene().parent_window
            if self.scene() and hasattr(self.scene(), "parent_window")
            else None
        )
        if (
            parent_window
            and hasattr(parent_window, "state")
            and parent_window.state
            and hasattr(parent_window.state, "class_list")
        ):
            available_classes = getattr(parent_window.state, "class_list", [])
            if not available_classes:
                logger_gui.warning("Double-clicked box, but no classes defined.")
                QMessageBox.warning(
                    parent_window, "No Classes", "No annotation classes defined."
                )
                super().mouseDoubleClickEvent(event)
                return

            current_index = -1
            try:
                current_index = available_classes.index(self.class_label)
            except ValueError:
                logger_gui.warning(
                    f"Current label '{self.class_label}' not in available classes: {available_classes}."
                )

            new_label, ok = QInputDialog.getItem(
                parent_window,
                "Change Class",
                "Select new class:",
                available_classes,
                current_index if current_index != -1 else 0,
                False,
            )

            if ok and new_label:
                if new_label != self.class_label:
                    logger_gui.info(
                        f"Changing label from '{self.class_label}' to '{new_label}'."
                    )
                    self.class_label = new_label
                    self.textItem.setPlainText(self.class_label)
                    self._updateTextPosition()
                    self.update()
                    if self.scene() and hasattr(self.scene(), "annotationsModified"):
                        self.scene().annotationsModified.emit()
                else:
                    logger_gui.debug("Class label unchanged.")
            else:
                logger_gui.debug("Class change cancelled.")
        else:
            logger_gui.warning("Could not get class list for double-click event.")
        super().mouseDoubleClickEvent(event)


# --- End of Modified ResizableRectItem Class ---


# --- AnnotationScene Class (Minor Changes for Suggestions) ---
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
        """Loads or clears the background image."""
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
                        f"Failed load (Pixmap fallback failed): {image_path}"
                    )
                    self.image_item.setPixmap(QPixmap())
                    self.setSceneRect(QRectF(0, 0, 1, 1))
                    return False
                else:
                    self.image_item.setPixmap(pixmap)
                    self.setSceneRect(self.image_item.boundingRect())
                    logger_gui.info(
                        f"Image loaded (via Pixmap fallback): {os.path.basename(image_path)}"
                    )
                    return True

            original_size = reader.size()
            max_dim = 4096
            if original_size.width() > max_dim or original_size.height() > max_dim:
                scale_factor = min(
                    max_dim / original_size.width(), max_dim / original_size.height()
                )
                new_width = int(original_size.width() * scale_factor)
                new_height = int(original_size.height() * scale_factor)
                reader.setScaledSize(QSize(new_width, new_height))
                logger_gui.info(
                    f"Scaled image from {original_size.width()}x{original_size.height()} to {new_width}x{new_height}"
                )

            image = reader.read()
            if image.isNull():
                logger_gui.error(
                    f"Failed read image data: {image_path}, Error: {reader.errorString()}"
                )
                self.image_item.setPixmap(QPixmap())
                self.setSceneRect(QRectF(0, 0, 1, 1))
                return False

            pixmap = QPixmap.fromImage(image)
            self.image_item.setPixmap(pixmap)
            self.setSceneRect(self.image_item.boundingRect())
            logger_gui.info(f"Image loaded into scene: {os.path.basename(image_path)}")
            return True

        except Exception as e:
            logger_gui.error(
                f"Exception loading image {image_path}: {e}", exc_info=True
            )
            self.image_item.setPixmap(QPixmap())
            self.setSceneRect(QRectF(0, 0, 1, 1))
            return False

    def get_image_size(self):
        """Returns the dimensions (width, height) of the loaded image."""
        if self.image_item and not self.image_item.pixmap().isNull():
            size = self.image_item.pixmap().size()
            return size.width(), size.height()
        return 0, 0

    def set_tool(self, tool_name):
        """Sets the active interaction tool (e.g., 'bbox' for drawing)."""
        if tool_name in ["select", "bbox"]:
            self.selection_tool = tool_name
        self.cancel_drawing()
        logger_gui.info(f"Scene tool set to: {tool_name}")
        view = self.views()[0] if self.views() else None
        if view:
            cursor_shape = (
                Qt.CursorShape.CrossCursor
                if tool_name == "bbox"
                else Qt.CursorShape.ArrowCursor
            )
            view.setCursor(cursor_shape)
        else:
            logger_gui.warning(f"Attempted to set unknown tool: {tool_name}")

    def cancel_drawing(self):
        """Removes the temporary rectangle item if drawing is cancelled."""
        if self.current_rect_item and self.drawing:
            self.removeItem(self.current_rect_item)
            logger_gui.debug("Canceled drawing operation.")
        self.drawing = False
        self.current_rect_item = None
        view = self.views()[0] if self.views() else None
        if view and self.selection_tool != "bbox":
            view.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        """Handles mouse press events, starting bbox drawing if applicable."""
        item = self.itemAt(
            event.scenePos(),
            self.views()[0].transform() if self.views() else QTransform(),
        )
        is_suggestion_item = isinstance(item, ResizableRectItem) and item.is_suggestion
        if is_suggestion_item:
            super().mousePressEvent(event)
            return
        super().mousePressEvent(event)
        if event.isAccepted():
            return
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.selection_tool == "bbox"
            and self.image_item
            and not self.image_item.pixmap().isNull()
        ):
            self.start_point = event.scenePos()
            img_rect = self.image_item.sceneBoundingRect()
            self.start_point.setX(
                max(img_rect.left(), min(self.start_point.x(), img_rect.right()))
            )
            self.start_point.setY(
                max(img_rect.top(), min(self.start_point.y(), img_rect.bottom()))
            )
            self.drawing = True
            self.current_rect_item = QGraphicsRectItem(
                QRectF(self.start_point, self.start_point)
            )
            self.current_rect_item.setPen(
                QPen(QColor(0, 255, 255), 2, Qt.PenStyle.DashLine)
            )
            self.addItem(self.current_rect_item)
            logger_gui.debug("Started drawing new bounding box.")
            event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        """Handles mouse move events, resizing the temporary box while drawing."""
        if self.drawing and self.current_rect_item and self.selection_tool == "bbox":
            if not self.image_item or self.image_item.pixmap().isNull():
                self.cancel_drawing()
                return
            current_pos = event.scenePos()
            img_rect = self.image_item.sceneBoundingRect()
            current_pos.setX(
                max(img_rect.left(), min(current_pos.x(), img_rect.right()))
            )
            current_pos.setY(
                max(img_rect.top(), min(current_pos.y(), img_rect.bottom()))
            )
            rect = QRectF(self.start_point, current_pos).normalized()
            self.current_rect_item.setRect(rect)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        """Handles mouse release events, finalizing bbox drawing."""
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.drawing
            and self.selection_tool == "bbox"
            and self.current_rect_item
        ):
            final_rect_scene = self.current_rect_item.rect()
            self.removeItem(self.current_rect_item)
            self.current_rect_item = None
            self.drawing = False

            rect_item_class = globals().get("ResizableRectItem")
            is_dummy_item = (
                rect_item_class is None
                or rect_item_class.__name__ == "DummyResizableRectItem"
            )

            if (
                final_rect_scene.width() > 5
                and final_rect_scene.height() > 5
                and not is_dummy_item
            ):
                label, ok = self.prompt_for_label()
                if ok and label:
                    resizable_rect = rect_item_class(
                        final_rect_scene, label, is_suggestion=False
                    )
                    self.addItem(resizable_rect)
                    logger_gui.info(f"Added new bounding box: {label}")
                    self.annotationsModified.emit()
                elif not ok:
                    logger_gui.debug("Label entry canceled by user.")
            elif is_dummy_item:
                logger_gui.error("Cannot add annotation: Using DummyResizableRectItem.")
            else:
                logger_gui.debug("Finished drawing, but box was too small. Not added.")

            logger_gui.debug("Finished drawing mode.")
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        """Handles key presses, like Escape for cancelling or Delete for removing items."""
        if event.key() == Qt.Key.Key_Escape:
            if self.drawing:
                logger_gui.debug("Escape pressed: Cancelling drawing.")
                self.cancel_drawing()
                event.accept()
            else:
                selected = self.selectedItems()
                if selected:
                    logger_gui.debug(
                        f"Escape pressed: Deselecting {len(selected)} items."
                    )
                    for item in selected:
                        item.setSelected(False)
                    event.accept()
                else:
                    super().keyPressEvent(event)
        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            rect_item_class = globals().get("ResizableRectItem")
            is_dummy_item = (
                rect_item_class is None
                or rect_item_class.__name__ == "DummyResizableRectItem"
            )
            if is_dummy_item:
                logger_gui.warning("Delete key ignored: Using DummyResizableRectItem.")
                event.accept()
                return
            items_to_delete = self.selectedItems()
            deleted_items_info = []
            deleted_suggestions = False  # Flag if suggestions were deleted
            if items_to_delete:
                for item in items_to_delete:
                    if isinstance(item, rect_item_class):
                        label = getattr(item, "class_label", "Unknown")
                        if getattr(item, "is_suggestion", False):
                            deleted_suggestions = True
                        self.removeItem(item)
                        deleted_items_info.append(label)
                if deleted_items_info:
                    log_msg = f"Deleted selected items: {deleted_items_info}"
                    logger_gui.info(log_msg)
                    if not deleted_suggestions:
                        self.annotationsModified.emit()
                event.accept()
            else:
                super().keyPressEvent(event)
        elif event.key() == Qt.Key.Key_C:
            logger_gui.debug("Key 'C' pressed: Requesting paste last box.")
            if hasattr(self.parent_window, "paste_last_box"):
                self.parent_window.paste_last_box()
                event.accept()
            else:
                logger_gui.warning(
                    "Parent window does not have 'paste_last_box' method."
                )
                super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    def prompt_for_label(self):
        """Prompts the user to select or enter a class label."""
        parent_widget = self.views()[0] if self.views() else None
        available_classes = []
        label_to_return = None
        ok_status = False

        if (
            hasattr(self, "parent_window")
            and self.parent_window
            and hasattr(self.parent_window, "state")
            and self.parent_window.state
            and hasattr(self.parent_window.state, "class_list")
        ):
            available_classes = getattr(self.parent_window.state, "class_list", [])

        try:
            if available_classes:
                label, ok = QInputDialog.getItem(
                    parent_widget,
                    "Select Label",
                    "Class:",
                    available_classes,
                    0,
                    False,
                )
            else:
                logging.warning("No classes defined, prompting for text label.")
                label, ok = QInputDialog.getText(parent_widget, "Enter Label", "Label:")
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
            logging.error(f"Error during QInputDialog prompt: {e}", exc_info=True)
            ok_status = False
        return label_to_return, ok_status

    def add_annotation_item_from_data(self, annotation_data, image_width, image_height):
        """Creates and adds a ResizableRectItem from saved annotation data."""
        try:
            if "rect" not in annotation_data or "class" not in annotation_data:
                raise KeyError("Annotation data missing 'rect' or 'class' key.")
            x, y, w, h = map(float, annotation_data["rect"])
            label = str(annotation_data["class"]).strip()
            if w <= 0 or h <= 0:
                logger_gui.warning(
                    f"Skipping annotation with non-positive dimensions: {annotation_data}"
                )
                return False
            if not label:
                logger_gui.warning(
                    f"Skipping annotation with empty label: {annotation_data}"
                )
                return False
            rect_item_class = globals().get("ResizableRectItem")
            if rect_item_class and rect_item_class.__name__ != "DummyResizableRectItem":
                if not self.image_item or self.image_item.pixmap().isNull():
                    logger_gui.error(
                        "Cannot add annotation item: Image item is invalid."
                    )
                    return False
                pixel_qrect = QRectF(x, y, w, h)
                scene_qrect = self.image_item.mapRectToScene(pixel_qrect)
                item = rect_item_class(scene_qrect, label, is_suggestion=False)
                self.addItem(item)
                return True
            else:
                logger_gui.error(
                    "Cannot add annotation item: ResizableRectItem class unavailable or dummy."
                )
                return False
        except KeyError as e:
            logger_gui.error(f"Missing key {e} in annotation data: {annotation_data}")
            return False
        except (ValueError, TypeError) as e:
            logger_gui.error(
                f"Invalid value/type in annotation data {annotation_data}: {e}"
            )
            return False
        except Exception as e:
            logger_gui.error(
                f"Unexpected error adding item from data {annotation_data}: {e}",
                exc_info=True,
            )
            return False

    def clear_annotations(self):
        """Removes all ResizableRectItem instances from the scene."""
        rect_item_class = globals().get("ResizableRectItem")
        if not rect_item_class or rect_item_class.__name__ == "DummyResizableRectItem":
            logger_gui.warning(
                "Cannot clear annotations: ResizableRectItem class unavailable or dummy."
            )
            return
        items_to_remove = [
            item for item in self.items() if isinstance(item, rect_item_class)
        ]
        if items_to_remove:
            logger_gui.debug(
                f"Clearing {len(items_to_remove)} annotation/suggestion items."
            )
            for item in items_to_remove:
                self.removeItem(item)
        else:
            logger_gui.debug("ClearAnnotations called: No items found.")

    def get_all_annotations(self):
        """Retrieves annotation data (pixel coords) from all NON-SUGGESTION boxes."""
        annotations = []
        img_w, img_h = self.get_image_size()
        if img_w <= 0 or img_h <= 0:
            logger_gui.error("Cannot get annotations: Image invalid.")
            return []
        rect_item_class = globals().get("ResizableRectItem")
        if not rect_item_class or rect_item_class.__name__ == "DummyResizableRectItem":
            logger_gui.error(
                "Cannot get annotations: ResizableRectItem class unavailable or dummy."
            )
            return []
        for item in self.items():
            if isinstance(item, rect_item_class) and not item.is_suggestion:
                if hasattr(item, "get_annotation_data"):
                    data = item.get_annotation_data(img_w, img_h)
                    if data:
                        annotations.append(data)
                else:
                    logger_gui.warning(
                        "Found ResizableRectItem instance lacking get_annotation_data method."
                    )
        logger_gui.debug(
            f"get_all_annotations found {len(annotations)} valid annotation items."
        )
        return annotations


# --- AnnotatorGraphicsView Class (No changes needed) ---
class AnnotatorGraphicsView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._zoom = 0
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setStyleSheet("background-color: #333333; border: 1px solid #555;")
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate
        )
        logger_gui.info(
            f"Graphics Viewport Update Mode set to: {self.viewportUpdateMode().name}"
        )

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
            if zoom_range[0] < self._zoom < zoom_range[1]:
                self.scale(zoomFactor, zoomFactor)
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            fake_event = QMouseEvent(
                event.type(),
                event.position(),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                event.modifiers(),
            )
            super().mousePressEvent(fake_event)
            event.accept()
        else:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            fake_event = QMouseEvent(
                event.type(),
                event.position(),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton,
                event.modifiers(),
            )
            super().mouseReleaseEvent(fake_event)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


# --- SettingsDialog Class (No changes needed) ---
class SettingsDialog(QDialog):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        if not state or not hasattr(state, "get_setting"):
            logger_gui.error(
                "SettingsDialog initialized with invalid state manager object."
            )
            self.state = None
        else:
            self.state = state

        self.setWindowTitle("Legacy Settings")
        self.setModal(True)
        layout = QFormLayout(self)

        self.conf_thresh_spin = QDoubleSpinBox()
        self.conf_thresh_spin.setRange(0.0, 1.0)
        self.conf_thresh_spin.setSingleStep(0.05)
        self.conf_thresh_spin.setDecimals(2)
        default_conf = config.DEFAULT_CONFIDENCE_THRESHOLD
        current_conf = default_conf
        if self.state:
            conf_key = config.SETTING_KEYS.get("confidence_threshold")
            current_conf = (
                self.state.get_setting(conf_key, default_conf)
                if conf_key
                else default_conf
            )
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
            self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

    def accept(self):
        if not self.state:
            logger_gui.error(
                "Accept called on SettingsDialog with invalid state manager."
            )
            super().reject()
            return
        try:
            conf_key = config.SETTING_KEYS.get("confidence_threshold")
            if conf_key and hasattr(self.state, "set_setting"):
                self.state.set_setting(conf_key, self.conf_thresh_spin.value())
                logger_gui.info("Legacy settings updated via dialog.")
                super().accept()
            else:
                logger_gui.error(
                    "Failed save legacy settings: Key missing or state manager lacks 'set_setting'."
                )
                QMessageBox.critical(
                    self, "Error", "Could not save settings (Internal error)."
                )
        except ValueError as e:
            QMessageBox.warning(self, "Input Error", f"Invalid numeric value: {e}")
        except Exception as e:
            logger_gui.error(f"Error saving legacy settings: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Could not save settings: {e}")


# --- TrainingDashboard Class (MODIFIED) ---
class TrainingDashboard(QDialog):
    DARK_BG_COLOR = "#2E2E2E"
    LIGHT_TEXT_COLOR = "#FFFFFF"
    GRID_COLOR = "#666666"
    MAP_COLOR = "#00FFFF"
    LOSS_COLOR_TRAIN = "#FFA500"
    LOSS_COLOR_VAL = "#FF00FF"

    def __init__(self, state_manager, parent=None):
        super().__init__(parent)
        if not state_manager or not hasattr(state_manager, "get_setting"):
            logger_gui.error("TrainingDashboard received invalid state_manager object.")
            QMessageBox.critical(
                self, "Init Error", "Cannot open dashboard: Invalid state manager."
            )
            self.state_manager = None
        else:
            self.state_manager = state_manager

        self.setWindowTitle("Training Dashboard & Settings")
        self.setMinimumWidth(600)
        layout = QVBoxLayout(self)

        param_group = QGroupBox(
            "Training Parameters & Triggers"
        )  # MODIFIED: Group title
        param_layout = QFormLayout(param_group)

        # Helper function to safely get settings
        def _get_setting(key_name, default_val):
            if not self.state_manager:
                return default_val
            key = config.SETTING_KEYS.get(key_name)
            return (
                self.state_manager.get_setting(key, default_val)
                if key and hasattr(self.state_manager, "get_setting")
                else default_val
            )

        # -- Epochs and Learning Rate Inputs --
        self.epochs_20_spin = QSpinBox()
        self.epochs_20_spin.setRange(1, 1000)
        self.epochs_20_spin.setValue(
            _get_setting("epochs_20", config.DEFAULT_EPOCHS_20)
        )
        param_layout.addRow("Epochs (20 Img Trigger):", self.epochs_20_spin)
        self.lr_20_spin = QDoubleSpinBox()
        self.lr_20_spin.setRange(0.000001, 0.1)
        self.lr_20_spin.setDecimals(6)
        self.lr_20_spin.setSingleStep(0.0001)
        self.lr_20_spin.setValue(_get_setting("lr_20", config.DEFAULT_LR_20))
        param_layout.addRow("Learning Rate (20 Img):", self.lr_20_spin)
        self.epochs_100_spin = QSpinBox()
        self.epochs_100_spin.setRange(1, 1000)
        self.epochs_100_spin.setValue(
            _get_setting("epochs_100", config.DEFAULT_EPOCHS_100)
        )
        param_layout.addRow("Epochs (100 Img Trigger):", self.epochs_100_spin)
        self.lr_100_spin = QDoubleSpinBox()
        self.lr_100_spin.setRange(0.000001, 0.1)
        self.lr_100_spin.setDecimals(6)
        self.lr_100_spin.setSingleStep(0.0001)
        self.lr_100_spin.setValue(_get_setting("lr_100", config.DEFAULT_LR_100))
        param_layout.addRow("Learning Rate (100 Img):", self.lr_100_spin)

        # --- <<< ADDED: Training Trigger Checkboxes >>> ---
        param_layout.addRow(
            QLabel("--- Automatic Training Triggers ---")
        )  # Optional separator
        self.trigger_20_checkbox = QCheckBox("Enable 20 Image Trigger")
        self.trigger_20_checkbox.setToolTip(
            "Automatically start training when 20, 40, 60... approved images are reached."
        )
        self.trigger_20_checkbox.setChecked(
            _get_setting(
                "training.trigger_20_enabled", config.DEFAULT_TRAIN_TRIGGER_20_ENABLED
            )
        )
        param_layout.addRow(self.trigger_20_checkbox)
        self.trigger_100_checkbox = QCheckBox("Enable 100 Image Trigger")
        self.trigger_100_checkbox.setToolTip(
            "Automatically start training when 100, 200, 300... approved images are reached."
        )
        self.trigger_100_checkbox.setChecked(
            _get_setting(
                "training.trigger_100_enabled", config.DEFAULT_TRAIN_TRIGGER_100_ENABLED
            )
        )
        param_layout.addRow(self.trigger_100_checkbox)
        # --- <<< END ADDED >>> ---

        # -- Augmentation Inputs --
        param_layout.addRow(QLabel("--- Augmentations ---"))
        self.flipud_spin = QDoubleSpinBox()
        self.flipud_spin.setRange(0.0, 1.0)
        self.flipud_spin.setDecimals(2)
        self.flipud_spin.setSingleStep(0.05)
        self.flipud_spin.setValue(_get_setting("aug_flipud", config.DEFAULT_AUG_FLIPUD))
        param_layout.addRow("Vertical Flip Prob:", self.flipud_spin)
        self.fliplr_spin = QDoubleSpinBox()
        self.fliplr_spin.setRange(0.0, 1.0)
        self.fliplr_spin.setDecimals(2)
        self.fliplr_spin.setSingleStep(0.05)
        self.fliplr_spin.setValue(_get_setting("aug_fliplr", config.DEFAULT_AUG_FLIPLR))
        param_layout.addRow("Horizontal Flip Prob:", self.fliplr_spin)
        self.degrees_spin = QDoubleSpinBox()
        self.degrees_spin.setRange(0.0, 180.0)
        self.degrees_spin.setDecimals(1)
        self.degrees_spin.setSingleStep(5.0)
        self.degrees_spin.setValue(
            _get_setting("aug_degrees", config.DEFAULT_AUG_DEGREES)
        )
        param_layout.addRow("Rotation Degrees (+/-):", self.degrees_spin)

        layout.addWidget(param_group)

        # --- Training Results Graph Group ---
        results_group = QGroupBox("Latest Training Run Results (from results.csv)")
        results_layout = QVBoxLayout(results_group)
        self.figure = plt.figure()
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setMinimumSize(550, 350)
        results_layout.addWidget(self.canvas)
        self.open_folder_button = QPushButton("Open Last Run Folder")
        self.open_folder_button.clicked.connect(self.open_last_run_folder)
        results_layout.addWidget(self.open_folder_button)
        layout.addWidget(results_group)

        # --- Dialog Buttons (Apply/Close) ---
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Close
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self.apply_settings
        )
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.load_initial_graph()
        if not self.state_manager:
            param_group.setEnabled(False)
            results_group.setEnabled(False)
            self.button_box.button(QDialogButtonBox.StandardButton.Apply).setEnabled(
                False
            )

    def load_initial_graph(self):
        last_run_dir = None
        if self.state_manager and hasattr(self.state_manager, "get_last_run_path"):
            try:
                last_run_dir = self.state_manager.get_last_run_path()
                logger_gui.info(f"Dashboard init: Load graph from: {last_run_dir}")
            except Exception as e:
                logger_gui.error(f"Error calling get_last_run_path: {e}")
        else:
            logger_gui.warning("State manager or 'get_last_run_path' unavailable.")
        self.update_graph(last_run_dir)

    def apply_settings(self):
        if not self.state_manager:
            logger_gui.error("Apply settings ignored: Invalid state manager.")
            return
        if not hasattr(self.state_manager, "set_setting"):
            logger_gui.error(
                "Apply settings failed: State manager missing 'set_setting'."
            )
            QMessageBox.critical(self, "Internal Error", "Cannot save settings.")
            return

        def _set_setting(key_name, value):
            key = config.SETTING_KEYS.get(key_name)
            if key:
                self.state_manager.set_setting(key, value)
            else:
                logger_gui.error(
                    f"Configuration key '{key_name}' not found in config.SETTING_KEYS."
                )

        try:
            _set_setting("epochs_20", self.epochs_20_spin.value())
            _set_setting("lr_20", self.lr_20_spin.value())
            _set_setting("epochs_100", self.epochs_100_spin.value())
            _set_setting("lr_100", self.lr_100_spin.value())
            # --- <<< ADDED: Save Training Trigger Settings >>> ---
            _set_setting(
                "training.trigger_20_enabled", self.trigger_20_checkbox.isChecked()
            )
            _set_setting(
                "training.trigger_100_enabled", self.trigger_100_checkbox.isChecked()
            )
            # --- <<< END ADDED >>> ---
            _set_setting("aug_flipud", self.flipud_spin.value())
            _set_setting("aug_fliplr", self.fliplr_spin.value())
            _set_setting("aug_degrees", self.degrees_spin.value())
            logger_gui.info(
                "Training/augmentation/trigger params applied via dashboard."
            )
        except ValueError as e:
            QMessageBox.warning(self, "Input Error", f"Invalid numeric value: {e}")
        except Exception as e:
            logger_gui.error(f"Error applying settings: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Could not apply settings: {e}")

    def open_last_run_folder(self):
        last_run_path = None
        if self.state_manager and hasattr(self.state_manager, "get_last_run_path"):
            try:
                last_run_path = self.state_manager.get_last_run_path()
            except Exception as e:
                logger_gui.error(f"Error calling get_last_run_path: {e}")
        if last_run_path and os.path.isdir(last_run_path):
            try:
                logger_gui.info(f"Opening training run folder: {last_run_path}")
                QDesktopServices.openUrl(QUrl.fromLocalFile(last_run_path))
            except Exception as e:
                logger_gui.error(f"Failed to open folder {last_run_path}: {e}")
                QMessageBox.warning(
                    self,
                    "Error",
                    f"Could not open folder:\n{last_run_path}\n\nError: {e}",
                )
        elif last_run_path:
            QMessageBox.warning(
                self, "Not Found", f"Last run folder not valid:\n{last_run_path}"
            )
        else:
            QMessageBox.information(
                self, "No Run Data", "No training run folder recorded."
            )

    def update_graph(self, run_dir_path):
        """Updates the Matplotlib graph using data from results.csv in the specified run directory."""
        logger_gui.debug(f"Dashboard updating graph from: {run_dir_path}")
        self.figure.clear()
        self.figure.patch.set_facecolor(self.DARK_BG_COLOR)
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(self.DARK_BG_COLOR)

        display_message = None
        dataframe = None

        # --- Load Data ---
        if run_dir_path and os.path.isdir(run_dir_path):
            csv_path = os.path.join(run_dir_path, "results.csv")
            if os.path.exists(csv_path):
                try:
                    dataframe = pd.read_csv(csv_path)
                    dataframe.columns = dataframe.columns.str.strip()
                    logger_gui.info(f"Loaded results.csv from {run_dir_path}")
                    logger_gui.debug(f"CSV Columns found: {list(dataframe.columns)}")
                except pd.errors.EmptyDataError:
                    display_message = "results.csv is empty."
                    logger_gui.warning(f"Empty results.csv found in {run_dir_path}")
                except FileNotFoundError:
                    display_message = "results.csv not found."
                    logger_gui.warning(
                        f"results.csv not found at {csv_path} (unexpected)."
                    )
                except Exception as e:
                    display_message = f"Error reading CSV:\n{e}"
                    logger_gui.error(
                        f"Error reading {csv_path}: {e}\n{traceback.format_exc()}"
                    )
            else:
                display_message = "results.csv not found in run directory."
                logger_gui.warning(f"results.csv not found in {run_dir_path}")
        elif run_dir_path:
            display_message = "Invalid run directory path provided."
            logger_gui.warning(
                f"Invalid run directory path provided to update_graph: {run_dir_path}"
            )
        else:
            display_message = "No training run data available to display."
            logger_gui.info("No run directory path provided for plotting.")

        # --- Plot Data ---
        plot_success = False
        if dataframe is not None:
            try:
                epoch_col = "epoch"
                map_col = "metrics/mAP50-95(B)"  # Common mAP metric
                val_loss_col = "val/box_loss"  # Validation box loss
                train_loss_col = "train/box_loss"  # Training box loss

                required_cols = [epoch_col, map_col]
                if not all(col in dataframe.columns for col in required_cols):
                    missing = [c for c in required_cols if c not in dataframe.columns]
                    raise KeyError(
                        f"Missing required columns in results.csv: {missing}"
                    )

                ax.plot(
                    dataframe[epoch_col],
                    dataframe[map_col],
                    color=self.MAP_COLOR,
                    marker="o",
                    linestyle="-",
                    linewidth=1.5,
                    markersize=4,
                    label="mAP50-95",
                )
                ax.set_ylabel("mAP 50-95", color=self.LIGHT_TEXT_COLOR)
                ax.tick_params(axis="y", labelcolor=self.LIGHT_TEXT_COLOR)

                plot_loss = True  # Flag to enable loss plotting
                loss_cols_exist = all(
                    col in dataframe.columns for col in [val_loss_col, train_loss_col]
                )
                if plot_loss and loss_cols_exist:
                    ax2 = ax.twinx()
                    ax2.plot(
                        dataframe[epoch_col],
                        dataframe[train_loss_col],
                        color=self.LOSS_COLOR_TRAIN,
                        marker=".",
                        linestyle="--",
                        linewidth=1,
                        markersize=3,
                        label="Train Loss (Box)",
                    )
                    ax2.plot(
                        dataframe[epoch_col],
                        dataframe[val_loss_col],
                        color=self.LOSS_COLOR_VAL,
                        marker=".",
                        linestyle=":",
                        linewidth=1,
                        markersize=3,
                        label="Val Loss (Box)",
                    )
                    ax2.set_ylabel("Loss", color=self.LIGHT_TEXT_COLOR)
                    ax2.tick_params(axis="y", labelcolor=self.LIGHT_TEXT_COLOR)
                    lines, labels = ax.get_legend_handles_labels()
                    lines2, labels2 = ax2.get_legend_handles_labels()
                    ax2.legend(
                        lines + lines2,
                        labels + labels2,
                        loc="best",
                        fontsize="small",
                        frameon=False,
                        labelcolor=self.LIGHT_TEXT_COLOR,
                    )
                    for spine in ax2.spines.values():
                        spine.set_edgecolor(self.GRID_COLOR)
                elif ax.get_legend_handles_labels()[1]:
                    ax.legend(
                        loc="best",
                        fontsize="small",
                        frameon=False,
                        labelcolor=self.LIGHT_TEXT_COLOR,
                    )

                ax.set_xlabel("Epoch", color=self.LIGHT_TEXT_COLOR)
                ax.set_title(
                    "Training Metrics", color=self.LIGHT_TEXT_COLOR, fontsize=12
                )
                ax.grid(True, color=self.GRID_COLOR, linestyle=":", linewidth=0.5)
                ax.tick_params(axis="x", colors=self.LIGHT_TEXT_COLOR)
                for spine in ax.spines.values():
                    spine.set_edgecolor(self.GRID_COLOR)

                plot_success = True
            except KeyError as e:
                display_message = f"Missing expected column in results.csv:\n{e}"
                logger_gui.error(f"Plotting failed due to missing column: {e}")
            except Exception as e:
                display_message = f"Error during plotting:\n{e}"
                logger_gui.error(
                    f"Error plotting data from {run_dir_path}: {e}\n{traceback.format_exc()}"
                )

        # --- Display Message on Failure ---
        if not plot_success:
            ax.text(
                0.5,
                0.5,
                display_message or "Unknown error plotting data",
                ha="center",
                va="center",
                color=self.LIGHT_TEXT_COLOR,
                fontsize=10,
                wrap=True,
                transform=ax.transAxes,
            )
            ax.axis("off")

        # --- Final Canvas Draw ---
        try:
            self.figure.tight_layout()
            self.canvas.draw()
            logger_gui.debug("Dashboard canvas redrawn after plotting attempt.")
        except Exception as draw_err:
            logger_gui.error(
                f"Error finalizing or drawing dashboard canvas: {draw_err}",
                exc_info=True,
            )
            try:
                self.figure.clear()
                ax_err = self.figure.add_subplot(111)
                ax_err.set_facecolor(self.DARK_BG_COLOR)
                ax_err.text(
                    0.5, 0.5, "Canvas Draw Error", ha="center", va="center", color="red"
                )
                ax_err.axis("off")
                self.canvas.draw()
            except Exception:
                pass


# --- End of gui.py Modifications ---
