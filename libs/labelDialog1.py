# try:
#     from PyQt5.QtGui import *
#     from PyQt5.QtCore import *
#     from PyQt5.QtWidgets import *
# except ImportError:
#     from PyQt4.QtGui import *
#     from PyQt4.QtCore import *
#
# from libs.utils import new_icon, label_validator, trimmed
#
# BB = QDialogButtonBox
#
#
# class LabelDialog(QDialog):
#
#     def __init__(self, text="Enter object label", parent=None, list_item=None):
#         super(LabelDialog, self).__init__(parent)
#
#         self.edit = QLineEdit()
#         self.edit.setText(text)
#         self.edit.setValidator(label_validator())
#         self.edit.editingFinished.connect(self.post_process)
#
#         model = QStringListModel()
#         model.setStringList(list_item)
#         completer = QCompleter()
#         completer.setModel(model)
#         self.edit.setCompleter(completer)
#
#         layout = QVBoxLayout()
#         layout.addWidget(self.edit)
#         self.button_box = bb = BB(BB.Ok | BB.Cancel, Qt.Horizontal, self)
#         bb.button(BB.Ok).setIcon(new_icon('done'))
#         bb.button(BB.Cancel).setIcon(new_icon('undo'))
#         bb.accepted.connect(self.validate)
#         bb.rejected.connect(self.reject)
#         layout.addWidget(bb)
#
#         if list_item is not None and len(list_item) > 0:
#             self.list_widget = QListWidget(self)
#             for item in list_item:
#                 self.list_widget.addItem(item)
#             self.list_widget.itemClicked.connect(self.list_item_click)
#             self.list_widget.itemDoubleClicked.connect(self.list_item_double_click)
#             layout.addWidget(self.list_widget)
#
#         self.setLayout(layout)
#
#     def validate(self):
#         if trimmed(self.edit.text()):
#             self.accept()
#
#     def post_process(self):
#         self.edit.setText(trimmed(self.edit.text()))
#
#     def pop_up(self, text='', move=True):
#         """
#         Shows the dialog, setting the current text to `text`, and blocks the caller until the user has made a choice.
#         If the user entered a label, that label is returned, otherwise (i.e. if the user cancelled the action)
#         `None` is returned.
#         """
#         self.edit.setText(text)
#         self.edit.setSelection(0, len(text))
#         self.edit.setFocus(Qt.PopupFocusReason)
#         if move:
#             cursor_pos = QCursor.pos()
#             parent_bottom_right = self.parentWidget().geometry()
#             max_x = parent_bottom_right.x() + parent_bottom_right.width() - self.sizeHint().width()
#             max_y = parent_bottom_right.y() + parent_bottom_right.height() - self.sizeHint().height()
#             max_global = self.parentWidget().mapToGlobal(QPoint(max_x, max_y))
#             if cursor_pos.x() > max_global.x():
#                 cursor_pos.setX(max_global.x())
#             if cursor_pos.y() > max_global.y():
#                 cursor_pos.setY(max_global.y())
#             self.move(cursor_pos)
#         return trimmed(self.edit.text()) if self.exec_() else None
#
#     def list_item_click(self, t_qlist_widget_item):
#         text = trimmed(t_qlist_widget_item.text())
#         self.edit.setText(text)
#
#     def list_item_double_click(self, t_qlist_widget_item):
#         self.list_item_click(t_qlist_widget_item)
#         self.validate()


# try:
#     from PyQt5.QtGui import *
#     from PyQt5.QtCore import *
#     from PyQt5.QtWidgets import *
# except ImportError:
#     from PyQt4.QtGui import *
#     from PyQt4.QtCore import *
#
# from libs.utils import new_icon, label_validator, trimmed
#
# BB = QDialogButtonBox
#
#
# class LabelDialog(QDialog):
#
#     def __init__(self, text="Enter object label", parent=None, list_item=None):
#         super(LabelDialog, self).__init__(parent)
#
#         self.edit = QLineEdit()
#         self.edit.setText(text)
#         self.edit.setValidator(label_validator())
#         self.edit.editingFinished.connect(self.post_process)
#
#         model = QStringListModel()
#         model.setStringList(list_item)
#         completer = QCompleter()
#         completer.setModel(model)
#         self.edit.setCompleter(completer)
#
#         layout = QVBoxLayout()
#         layout.addWidget(self.edit)
#         self.button_box = bb = BB(BB.Ok | BB.Cancel, Qt.Horizontal, self)
#         bb.button(BB.Ok).setIcon(new_icon('done'))
#         bb.button(BB.Cancel).setIcon(new_icon('undo'))
#         bb.accepted.connect(self.validate)
#         bb.rejected.connect(self.reject)
#         layout.addWidget(bb)
#
#         if list_item is not None and len(list_item) > 0:
#             self.list_widget = QListWidget(self)
#             for item in list_item:
#                 self.list_widget.addItem(item)
#             self.list_widget.itemClicked.connect(self.list_item_click)
#             self.list_widget.itemDoubleClicked.connect(self.list_item_double_click)
#             layout.addWidget(self.list_widget)
#
#         self.setLayout(layout)
#
#     def validate(self):
#         if trimmed(self.edit.text()):
#             self.accept()
#
#     def post_process(self):
#         self.edit.setText(trimmed(self.edit.text()))
#
#     def pop_up(self, text='', move=True):
#         """
#         Shows the dialog, setting the current text to `text`, and blocks the caller until the user has made a choice.
#         If the user entered a label, that label is returned, otherwise (i.e. if the user cancelled the action)
#         `None` is returned.
#         """
#         self.edit.setText(text)
#         self.edit.setSelection(0, len(text))
#         self.edit.setFocus(Qt.PopupFocusReason)
#
#         if move and self.parentWidget() is not None:
#             # 获取父窗口几何信息并计算中心位置
#             parent_geometry = self.parentWidget().geometry()
#             screen_geometry = QGuiApplication.screenAt(parent_geometry.center()).availableGeometry()
#
#             center_x = parent_geometry.x() + parent_geometry.width() // 2 - self.sizeHint().width() // 2
#             center_y = parent_geometry.y() + parent_geometry.height() // 2 - self.sizeHint().height() // 2
#
#             # 限制位置在屏幕范围内
#             center_x = max(screen_geometry.x(), min(center_x, screen_geometry.right() - self.sizeHint().width()))
#             center_y = max(screen_geometry.y(), min(center_y, screen_geometry.bottom() - self.sizeHint().height()))
#
#             self.move(QPoint(center_x, center_y))
#
#         return trimmed(self.edit.text()) if self.exec_() else None
#
#     def list_item_click(self, t_qlist_widget_item):
#         text = trimmed(t_qlist_widget_item.text())
#         self.edit.setText(text)
#
#     def list_item_double_click(self, t_qlist_widget_item):
#         self.list_item_click(t_qlist_widget_item)
#         self.validate()


# label_dialog.py
# try:
#     from PyQt5.QtGui import *
#     from PyQt5.QtCore import *
#     from PyQt5.QtWidgets import *
# except ImportError:
#     from PyQt4.QtGui import *
#     from PyQt4.QtCore import *
# import sys
# import yaml
# from libs.utils import new_icon, label_validator, trimmed
# from libs.stringBundle import StringBundle


# class LabelDialog(QDialog):
#     def __init__(self, parent=None, categories=None, text="Enter object label", list_item=None):
#         super(LabelDialog, self).__init__(parent)
#         self.string_bundle = StringBundle.get_bundle()
#         get_str = lambda str_id: self.string_bundle.get_string(str_id)
#         self.categories = categories if categories is not None else {}
#         self.setFixedSize(550, 200)
#         self.setWindowTitle("标签编辑")
#
#         # 现有的文本编辑框
#         self.edit = QLineEdit()
#         self.edit.setText(text)
#         self.edit.setValidator(label_validator())
#         self.edit.editingFinished.connect(self.post_process)
#
#         # 自动完成设置
#         if list_item is not None:
#             model = QStringListModel()
#             model.setStringList(list_item)
#             completer = QCompleter()
#             completer.setModel(model)
#             self.edit.setCompleter(completer)
#
#         # 创建“使用默认标签”相关控件
#         self.use_default_label_checkbox = QCheckBox(get_str('useDefaultLabel') or '使用默认标签')
#         self.use_default_label_checkbox.setChecked(False)
#
#         self.default_label_combo = QComboBox()
#         self.default_label_combo.addItem("")  # 第一行为空
#
#         self.subcategory_combo = QComboBox(self)
#
#         # 水平布局，将复选框和两个下拉菜单水平排列
#         use_default_label_layout = QHBoxLayout()
#         use_default_label_layout.addWidget(self.use_default_label_checkbox)
#         use_default_label_layout.addWidget(QLabel("一级:"))
#         use_default_label_layout.addWidget(self.default_label_combo)
#         use_default_label_layout.addWidget(QLabel("二级:"))
#         use_default_label_layout.addWidget(self.subcategory_combo)
#
#         # 创建容器并设置布局
#         use_default_label_container = QWidget()
#         use_default_label_container.setLayout(use_default_label_layout)
#
#         # 主布局
#         main_layout = QVBoxLayout()
#         main_layout.addWidget(QLabel("输入标签:"))
#         main_layout.addWidget(self.edit)
#         main_layout.addWidget(use_default_label_container)
#
#         # 添加列表部件（如果有）
#         if list_item is not None and len(list_item) > 0:
#             self.list_widget = QListWidget(self)
#             for item in list_item:
#                 self.list_widget.addItem(item)
#             self.list_widget.itemClicked.connect(self.list_item_click)
#             self.list_widget.itemDoubleClicked.connect(self.list_item_double_click)
#             main_layout.addWidget(self.list_widget)
#
#         # 添加确定和取消按钮
#         self.button_box = bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
#         bb.button(QDialogButtonBox.Ok).setIcon(new_icon('done'))
#         bb.button(QDialogButtonBox.Cancel).setIcon(new_icon('undo'))
#         bb.accepted.connect(self.validate)
#         bb.rejected.connect(self.reject)
#         main_layout.addWidget(self.button_box)
#
#         self.setLayout(main_layout)
#
#         # 信号与槽连接
#         self.default_label_combo.currentIndexChanged.connect(self.update_subcategories)
#         self.use_default_label_checkbox.stateChanged.connect(self.toggle_default_label_controls)
#
#         # 加载类别数据
#         # self.load_categories_into_combo()
#         self.load_categories_from_yaml('config/tags.yaml')
#         # 初始状态下禁用默认标签控件
#         self.toggle_default_label_controls(self.use_default_label_checkbox.isChecked())
#
#     def load_categories_from_yaml(self, yaml_file):
#         """从 YAML 文件加载数据，并填充到一级菜单中"""
#         with open(yaml_file, 'r', encoding='utf-8') as f:
#             data = yaml.safe_load(f)
#
#         self.categories = data.get('categories', {})
#         self.default_label_combo.addItems(self.categories.keys())
#
#     def load_categories_into_combo(self):
#         """
#         将类别数据加载到默认标签下拉菜单中。
#         """
#         self.default_label_combo.addItem("")  # 确保第一项为空
#         if self.categories:
#             self.default_label_combo.addItems(self.categories.keys())
#
#     def update_subcategories(self, index):
#         """
#         根据选择的标签更新子类别下拉菜单。
#         """
#         selected_label = self.default_label_combo.currentText()
#         self.subcategory_combo.clear()
#         if selected_label and selected_label in self.categories:
#             self.subcategory_combo.addItems(self.categories[selected_label])
#         else:
#             self.subcategory_combo.addItem("")  # 如果没有选择有效标签，添加一个空选项
#
#     def toggle_default_label_controls(self, checked):
#         """
#         根据复选框的状态启用或禁用默认标签相关控件。
#         """
#         self.default_label_combo.setEnabled(checked)
#         self.subcategory_combo.setEnabled(checked)
#         self.edit.setEnabled(not checked)  # 当使用默认标签时，禁用自定义编辑框
#         if not checked:
#             # 清空默认标签选择
#             self.default_label_combo.setCurrentIndex(0)
#             self.subcategory_combo.clear()
#             self.subcategory_combo.addItem("")
#         else:
#             # 禁用自定义标签编辑框并清空其内容
#             self.edit.clear()
#
#     def validate(self):
#         """
#         验证输入内容，如果有效则接受对话框。
#         """
#         if self.use_default_label_checkbox.isChecked():
#             # 使用默认标签时，确保选择了标签
#             selected_label = self.default_label_combo.currentText()
#             if not selected_label:
#                 # 未选择标签，提示错误
#                 QMessageBox.warning(self, "警告", "请选择一个默认标签。")
#                 return
#         else:
#             # 使用自定义标签时，确保输入了标签
#             if not trimmed(self.edit.text()):
#                 QMessageBox.warning(self, "警告", "请输入标签。")
#                 return
#         self.accept()
#
#     def post_process(self):
#         """
#         修剪编辑框中的文本。
#         """
#         self.edit.setText(trimmed(self.edit.text()))
#
#     def pop_up(self, text='', move=True):
#         """
#         显示对话框，设置标签和输入框的当前文本，
#         并阻塞调用者直到用户做出选择。
#         如果用户确认，则返回标签，否则返回 `None`。
#         """
#         if self.use_default_label_checkbox.isChecked():
#             # 如果使用默认标签，清空编辑框
#             self.edit.clear()
#         else:
#             self.edit.setText(text)
#             self.edit.setSelection(0, len(text))
#             self.edit.setFocus(Qt.PopupFocusReason)
#
#         if move and self.parentWidget() is not None:
#             # 获取父窗口几何信息并计算中心位置
#             parent_geometry = self.parentWidget().geometry()
#             screen_geometry = QGuiApplication.screenAt(parent_geometry.center()).availableGeometry()
#
#             center_x = parent_geometry.x() + parent_geometry.width() // 2 - self.sizeHint().width() // 2
#             center_y = parent_geometry.y() + parent_geometry.height() // 2 - self.sizeHint().height() // 2
#
#             # 限制位置在屏幕范围内
#             center_x = max(screen_geometry.x(), min(center_x, screen_geometry.right() - self.sizeHint().width()))
#             center_y = max(screen_geometry.y(), min(center_y, screen_geometry.bottom() - self.sizeHint().height()))
#
#             self.move(QPoint(center_x, center_y))
#
#         result = self.exec_()
#         if result:
#             if self.use_default_label_checkbox.isChecked():
#                 selected_label = self.default_label_combo.currentText().strip()
#                 selected_subcategory = self.subcategory_combo.currentText().strip()
#                 label = f"{selected_subcategory}" if selected_subcategory else selected_label
#             else:
#                 label = self.edit.text().strip()
#             return trimmed(label) if label else None
#         else:
#             return None
#
#     def list_item_click(self, t_qlist_widget_item):
#         """
#         当列表项被点击时，将其文本设置到编辑框中。
#         """
#         text = trimmed(t_qlist_widget_item.text())
#         self.edit.setText(text)
#
#     def list_item_double_click(self, t_qlist_widget_item):
#         """
#         当列表项被双击时，设置文本并验证。
#         """
#         self.list_item_click(t_qlist_widget_item)
#         self.validate()


# def trimmed(text):
#     return text.strip()
#
#
# def new_icon(icon_name):
#     # 这里只是一个示例方法，用于返回一个图标
#     return QIcon()
#
#
# class LabelDialog(QDialog):
#     def __init__(self,
#                  parent=None,
#                  categories=None,
#                  text="Enter object label",
#                  list_item=None,
#                  yaml_file="config/tags.yaml"):
#         super(LabelDialog, self).__init__(parent)
#
#         # =========================
#         #  1. 初始化数据和控件
#         # =========================
#
#         self.categories = categories if categories is not None else {}
#         self.setWindowTitle("标签编辑")
#
#         # 复选框：使用默认标签
#         self.use_default_label_checkbox = QCheckBox("使用默认标签", self)
#         self.use_default_label_checkbox.setChecked(True)
#
#         # 一级分类
#         self.default_label_combo = QComboBox(self)
#         self.default_label_combo.addItem("")  # 第一项为空
#
#         # 二级标签列表
#         self.subcategory_list = QListWidget(self)  # 新增QListWidget来显示二级标签
#         self.subcategory_list.setMinimumHeight(100)  # 设置列表的最小高度
#         self.subcategory_list.setSelectionMode(QAbstractItemView.SingleSelection)
#         self.subcategory_list.itemClicked.connect(self.list_item_click)  # 连接点击事件
#         self.subcategory_list.itemDoubleClicked.connect(self.list_item_double_click)  # 双击事件
#
#         # =========================
#         #  2. 布局
#         # =========================
#
#         # 主布局
#         main_layout = QVBoxLayout()
#
#         # 【1】使用默认标签 复选框 + 一级分类
#         default_label_layout = QHBoxLayout()
#         default_label_layout.addWidget(self.use_default_label_checkbox)
#         default_label_layout.addWidget(QLabel("一级:", self))
#         default_label_layout.addWidget(self.default_label_combo)
#         main_layout.addLayout(default_label_layout)
#
#         # 【2】二级标签列表
#         main_layout.addWidget(QLabel("二级标签:", self))
#         main_layout.addWidget(self.subcategory_list)
#
#         # 【3】按钮区 (Ok/Cancel)
#         self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
#                                            Qt.Horizontal, self)
#         self.button_box.button(QDialogButtonBox.Ok).setIcon(new_icon('done'))
#         self.button_box.button(QDialogButtonBox.Cancel).setIcon(new_icon('undo'))
#         self.button_box.accepted.connect(self.validate)
#         self.button_box.rejected.connect(self.reject)
#
#         main_layout.addWidget(self.button_box)
#
#         # 设置主布局
#         self.setLayout(main_layout)
#
#         # 允许布局根据内容自动调整大小（非常关键）
#         self.layout().setSizeConstraint(QLayout.SetFixedSize)
#         self.layout().setSizeConstraint(QLayout.SizeConstraint.SetDefaultConstraint)
#
#         # =========================
#         #  3. 信号与槽
#         # =========================
#         self.default_label_combo.currentIndexChanged.connect(self.update_subcategories)
#         self.use_default_label_checkbox.stateChanged.connect(self.toggle_default_label_controls)
#
#         # =========================
#         #  4. 加载类别数据
#         # =========================
#         self.load_categories_from_yaml(yaml_file)
#         self.toggle_default_label_controls(self.use_default_label_checkbox.isChecked())
#
#     # -------------------------
#     #    加载分类逻辑
#     # -------------------------
#     def load_categories_from_yaml(self, yaml_file):
#         """
#         从 YAML 文件加载数据，并填充到一级菜单和二级标签列表中。
#         """
#         try:
#             with open(yaml_file, 'r', encoding='utf-8') as f:
#                 data = yaml.safe_load(f)
#             self.categories = data.get('categories', {})
#
#             # 将分类名填入一级分类 combo box（先清空，再添加）
#             self.default_label_combo.clear()
#             self.default_label_combo.addItem("")  # 第一项为空
#             for cat_name in self.categories.keys():
#                 self.default_label_combo.addItem(cat_name)
#
#             # 更新二级标签列表
#             self.update_subcategories()  # 加载一级标签后，更新二级标签列表
#
#         except Exception as e:
#             print("加载 YAML 文件失败:", e)
#
#     def update_subcategories(self):
#         """
#         根据选择的一级分类，更新二级分类列表。
#         """
#         selected_label = self.default_label_combo.currentText()
#         self.subcategory_list.clear()  # 清空列表
#
#         if selected_label and selected_label in self.categories:
#             # 如果有二级分类列表，就添加
#             sub_list = self.categories[selected_label]
#             if isinstance(sub_list, list):
#                 self.subcategory_list.addItems(sub_list)
#             else:
#                 # 数据结构不符合预期，则添加一个空项
#                 self.subcategory_list.addItem("")
#
#     def toggle_default_label_controls(self, checked):
#         """
#         根据复选框状态 启用/禁用 默认标签相关控件。
#         """
#         self.default_label_combo.setEnabled(checked)
#         self.subcategory_list.setEnabled(checked)  # 启用/禁用二级标签列表
#
#     # -------------------------
#     #    弹窗逻辑
#     # -------------------------
#     def pop_up(self, text='', move=True):
#         """
#         显示对话框，设置标签和输入框的当前文本，阻塞调用者直到用户做出选择。
#         """
#         # 将对话框移动到父窗口中心
#         if move and self.parentWidget() is not None:
#             parent_geometry = self.parentWidget().geometry()
#             screen_geometry = QGuiApplication.screenAt(parent_geometry.center()).availableGeometry()
#
#             center_x = parent_geometry.x() + parent_geometry.width() // 2 - self.sizeHint().width() // 2
#             center_y = parent_geometry.y() + parent_geometry.height() // 2 - self.sizeHint().height() // 2
#
#             # 限制位置在屏幕范围内
#             center_x = max(screen_geometry.x(),
#                            min(center_x, screen_geometry.right() - self.sizeHint().width()))
#             center_y = max(screen_geometry.y(),
#                            min(center_y, screen_geometry.bottom() - self.sizeHint().height()))
#
#             self.move(QPoint(center_x, center_y))
#
#         # 弹出对话框
#         result = self.exec_()
#         if result == QDialog.Accepted:
#             if self.use_default_label_checkbox.isChecked():
#                 # 拼装默认标签或子分类
#                 selected_label = self.default_label_combo.currentText().strip()
#                 selected_subcategory = self.subcategory_list.currentItem().text().strip() if self.subcategory_list.currentItem() else ""
#                 # 如果子分类不为空，则使用子分类，否则只用一级分类
#                 final_label = selected_subcategory if selected_subcategory else selected_label
#             else:
#                 final_label = None  # 自定义标签可以在其他地方处理
#
#             return trimmed(final_label) if final_label else None
#         else:
#             return None
#
#     # -------------------------
#     #    验证与处理
#     # -------------------------
#     def validate(self):
#         """
#         验证输入内容，如果有效则接受对话框。
#         """
#         if self.use_default_label_checkbox.isChecked():
#             # 使用默认标签时，确保选择了标签
#             selected_label = self.default_label_combo.currentText()
#             if not selected_label:
#                 QMessageBox.warning(self, "警告", "请选择一个默认标签。")
#                 return
#         else:
#             # 自定义标签，这部分可以根据需求来补充
#             pass
#
#         # 如果一切通过，则接受
#         self.accept()
#
#     # -------------------------
#     #    列表交互事件
#     # -------------------------
#     def list_item_click(self, item):
#         """
#         当列表项被点击时，直接选择该标签。
#         """
#         # 更新当前选择的标签
#         selected_label = self.default_label_combo.currentText().strip()
#         selected_subcategory = item.text().strip()  # 获取选中的标签文本
#         final_label = selected_subcategory if selected_subcategory else selected_label
#
#         # 自动更新标签选择（这里可以根据需求进一步处理）
#         # print(f"选择的标签是: {final_label}")
#         # 更新对话框显示或其他处理...
#
#     def list_item_double_click(self, item):
#         """
#         当列表项被双击时，模拟点击 OK 按钮，直接选择标签并更新。
#         """
#         # 获取当前选中的标签
#         selected_label = self.default_label_combo.currentText().strip()
#
#         # 直接选择当前标签项
#         selected_subcategory = item.text().strip()  # 获取双击的标签文本
#         final_label = selected_subcategory if selected_subcategory else selected_label
#
#         # 自动更新标签
#         # print(f"双击选中的标签是: {final_label}")
#
#         # 直接确认并关闭对话框
#         self.accept()
