#!/usr/bin/python
# -*- coding: utf-8 -*-
import math

from PyQt5.QtWidgets import QGraphicsRectItem

try:
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
except ImportError:
    from PyQt4.QtGui import *
    from PyQt4.QtCore import *

import sys

from libs.utils import distance

# DEFAULT_LINE_COLOR = QColor(0, 255, 0, 230)
# DEFAULT_FILL_COLOR = QColor(255, 0, 0, 128)
DEFAULT_LINE_COLOR = QColor(0, 255, 0, 255)  # 绿色，完全不透明
DEFAULT_FILL_COLOR = QColor(255, 0, 0, 255)  # 红色，完全不透明
DEFAULT_SELECT_LINE_COLOR = QColor(0, 255, 255, 255)
DEFAULT_SELECT_FILL_COLOR = QColor(0, 0, 155, 30)
DEFAULT_VERTEX_FILL_COLOR = QColor(0, 255, 0, 255)
DEFAULT_HVERTEX_FILL_COLOR = QColor(255, 0, 0)


class Shape(object):
    P_SQUARE, P_ROUND = range(2)

    MOVE_VERTEX, NEAR_VERTEX = range(2)

    # The following class variables influence the drawing
    # of _all_ shape objects.
    line_color = DEFAULT_LINE_COLOR
    fill_color = DEFAULT_FILL_COLOR
    select_line_color = DEFAULT_SELECT_LINE_COLOR
    select_fill_color = DEFAULT_SELECT_FILL_COLOR
    vertex_fill_color = DEFAULT_VERTEX_FILL_COLOR
    h_vertex_fill_color = DEFAULT_HVERTEX_FILL_COLOR
    point_type = P_ROUND
    point_size = 6
    scale = 1.0
    label_font_size = 8

    def __init__(self, label=None, line_color=None, difficult=False, paint_label=False):
        self.label = label
        self.points = []
        self.fill = False
        self.selected = False
        self.difficult = difficult
        self.paint_label = paint_label

        self._highlight_index = None
        self._highlight_mode = self.NEAR_VERTEX
        self._highlight_settings = {
            self.NEAR_VERTEX: (4, self.P_ROUND),
            self.MOVE_VERTEX: (1.5, self.P_SQUARE),
        }

        self._closed = False

        if line_color is not None:
            # Override the class line_color attribute
            # with an object attribute. Currently this
            # is used for drawing the pending line a different color.
            self.line_color = line_color

    def close(self):
        self._closed = True

    def reach_max_points(self):
        if len(self.points) >= 4:
            return True
        return False

    def add_point(self, point):
        if not self.reach_max_points():
            self.points.append(point)

    def pop_point(self):
        if self.points:
            return self.points.pop()
        return None

    def is_closed(self):
        return self._closed

    def set_open(self):
        self._closed = False

    def paint(self, painter):
        """绘制形状和标签文本。"""
        if not self.points:
            return  # 如果没有点则不绘制

        # 设置线条颜色和宽度
        color = self.select_line_color if self.selected else self.line_color
        pen = QPen(QColor(255, 0, 0), 1)
        # pen.setWidth(max(2, int(round(4.0 / self.scale))))  # 根据缩放比例调整线宽
        pen.setWidth(1)
        painter.setPen(pen)

        # 创建线条和顶点路径
        line_path = QPainterPath()
        vertex_path = QPainterPath()

        # 移动到第一个点并绘制路径
        line_path.moveTo(self.points[0])

        for i, p in enumerate(self.points):
            line_path.lineTo(p)
            self.draw_vertex(vertex_path, i)

        # 如果形状是闭合的，连接回起点
        if self.is_closed():
            line_path.lineTo(self.points[0])

        # 绘制路径和顶点
        painter.drawPath(line_path)
        painter.drawPath(vertex_path)
        painter.fillPath(vertex_path, self.vertex_fill_color)

        # 计算标签字体大小并绘制标签
        if self.paint_label:
            min_x = min(point.x() for point in self.points)
            min_y = min(point.y() for point in self.points)
            max_x = max(point.x() for point in self.points)
            max_y = max(point.y() for point in self.points)

            # 计算边界框的宽度和高度
            box_width = max_x - min_x
            box_height = max_y - min_y

            # 使用宽度和高度的最小值计算字体大小，并限制最大值
            font_size = min(max(1, int(min(box_width, box_height) / 4)), 15)  # 限制字体最大为 12
            font = QFont()
            font.setPointSize(font_size)
            font.setBold(True)
            painter.setFont(font)

            # 确保标签文本不为空
            label = self.label if self.label else ""

            # 设置固定偏移量，避免标签贴近框
            offset = 5  # 固定偏移 5 像素

            # 确保标签不会与顶点重叠，并适当调整标签位置
            label_x = min_x + offset
            label_y = min_y - offset if min_y > offset else min_y + font_size + offset

            # 设置标签颜色为红色
            painter.setPen(QColor(255, 0, 0))  # 红色标签

            # 绘制标签文本
            painter.drawText(label_x, label_y, label)

        # 根据选择状态填充形状
        if self.fill:
            fill_color = self.select_fill_color if self.selected else self.fill_color
            painter.fillPath(line_path, fill_color)

    def draw_vertex(self, path, i):
        d = self.point_size / self.scale
        shape = self.point_type
        point = self.points[i]
        if i == self._highlight_index:
            size, shape = self._highlight_settings[self._highlight_mode]
            d *= size
        if self._highlight_index is not None:
            self.vertex_fill_color = self.h_vertex_fill_color
        else:
            self.vertex_fill_color = Shape.vertex_fill_color
        if shape == self.P_SQUARE:
            path.addRect(point.x() - d / 2, point.y() - d / 2, d, d)
        elif shape == self.P_ROUND:
            path.addEllipse(point, d / 2.0, d / 2.0)
        else:
            assert False, "unsupported vertex shape"

    def nearest_vertex(self, point, epsilon):
        for i, p in enumerate(self.points):
            if distance(p - point) <= epsilon:
                return i
        return None

    def contains_point(self, point):
        return self.make_path().contains(point)

    def make_path(self):
        path = QPainterPath(self.points[0])
        for p in self.points[1:]:
            path.lineTo(p)
        return path

    def bounding_rect(self):
        return self.make_path().boundingRect()

    def move_by(self, offset):
        self.points = [p + offset for p in self.points]

    def move_vertex_by(self, i, offset):
        self.points[i] = self.points[i] + offset

    def highlight_vertex(self, i, action):
        self._highlight_index = i
        self._highlight_mode = action

    def highlight_clear(self):
        self._highlight_index = None

    def copy(self):
        shape = Shape("%s" % self.label)
        shape.points = [p for p in self.points]
        shape.fill = self.fill
        shape.selected = self.selected
        shape._closed = self._closed
        if self.line_color != Shape.line_color:
            shape.line_color = self.line_color
        if self.fill_color != Shape.fill_color:
            shape.fill_color = self.fill_color
        shape.difficult = self.difficult
        return shape

    def rotate(self, angle):
        """将形状绕中心点旋转指定角度（度数）。"""
        if not self.points or len(self.points) < 2:
            print("无法旋转：没有足够的点")
            return  # 避免旋转空的形状

        theta = math.radians(angle)  # 将角度转换为弧度

        # 计算质心（中心点）
        cx = sum(p.x() for p in self.points) / len(self.points)
        cy = sum(p.y() for p in self.points) / len(self.points)
        center = QPointF(cx, cy)

        # 应用旋转矩阵更新所有点的位置
        new_points = []
        for p in self.points:
            dx = p.x() - cx
            dy = p.y() - cy

            new_x = cx + (dx * math.cos(theta) - dy * math.sin(theta))
            new_y = cy + (dx * math.sin(theta) + dy * math.cos(theta))
            new_points.append(QPointF(new_x, new_y))

        # 更新形状的点
        self.points = new_points
        print(f"旋转完成：当前角度 {angle} 度")

    def __len__(self):
        return len(self.points)

    def __getitem__(self, key):
        return self.points[key]

    def __setitem__(self, key, value):
        self.points[key] = value
