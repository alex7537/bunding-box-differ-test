# # # # 亮度滑块
# # # self.brightness_slider = QSlider(Qt.Horizontal, self)
# # # self.brightness_slider.setRange(0, 200)
# # # self.brightness_slider.setValue(100)
# # # self.brightness_slider.valueChanged.connect(self.updateImage)
# # #
# # # # 对比度滑块
# # # self.contrast_slider = QSlider(Qt.Horizontal, self)
# # # self.contrast_slider.setRange(0, 200)
# # # self.contrast_slider.setValue(100)
# # # self.contrast_slider.valueChanged.connect(self.updateImage)
# # #
# # # # # 同步色阶滑块
# # # self.sync_levels_slider = QSlider(Qt.Horizontal, self)
# # # self.sync_levels_slider.setRange(1, 200)
# # # self.sync_levels_slider.setValue(100)
# # # self.sync_levels_slider.valueChanged.connect(self.syncColorLevels)
# # #
# # # # 红色色阶滑块（单独调节）
# # # self.red_levels_slider = QSlider(Qt.Horizontal, self)
# # # self.red_levels_slider.setRange(1, 200)
# # # self.red_levels_slider.setValue(100)
# # # self.red_levels_slider.valueChanged.connect(self.updateImage)
# # #
# # # # 绿色色阶滑块（单独调节）
# # # self.green_levels_slider = QSlider(Qt.Horizontal, self)
# # # self.green_levels_slider.setRange(1, 200)
# # # self.green_levels_slider.setValue(100)
# # # self.green_levels_slider.valueChanged.connect(self.updateImage)
# # #
# # # # 蓝色色阶滑块（单独调节）
# # # self.blue_levels_slider = QSlider(Qt.Horizontal, self)
# # # self.blue_levels_slider.setRange(1, 200)
# # # self.blue_levels_slider.setValue(100)
# # # self.blue_levels_slider.valueChanged.connect(self.updateImage)
# #
# # # hbox = QHBoxLayout()
# #
# # # list_layout.addWidget(self.label)
# # # list_layout.addWidget(QLabel('亮度'))
# # # list_layout.addWidget(self.brightness_slider)
# # # list_layout.addWidget(QLabel('对比度'))
# # # list_layout.addWidget(self.contrast_slider)
# # # list_layout.addWidget(QLabel('同步色阶'))
# # # list_layout.addWidget(self.sync_levels_slider)
# # # list_layout.addWidget(QLabel('红色色阶'))
# # # list_layout.addWidget(self.red_levels_slider)
# # # list_layout.addWidget(QLabel('绿色色阶'))
# # # list_layout.addWidget(self.green_levels_slider)
# # # list_layout.addWidget(QLabel('蓝色色阶'))
# # # list_layout.addWidget(self.blue_levels_slider)
# # # layout.addLayout(hbox)
# # # self.setLayout(layout)
# # # self.setWindowTitle('图片查看器')
# #
# #
# #
# #
# #
# # def import_dir_images(self, dir_path):
# #     """导入目录中的所有图片并初始化状态"""
# #     if not self.may_continue() or not dir_path:
# #         print("无法继续或路径无效")
# #         return
# #
# #     # 清理之前的数据
# #     self.last_open_dir = dir_path
# #     self.dir_name = dir_path
# #     self.file_path = None
# #     self.file_list_widget.clear()
# #     self.m_img_list = self.scan_all_images(dir_path)  # 扫描目录中的图片
# #     self.img_count = len(self.m_img_list)
# #
# #     if self.img_count == 0:
# #         print("没有找到任何图片")
# #         return
# #
# #     # 初始化为第一张图片，并更新界面
# #     self.cur_img_idx = 0
# #     self.update_file_list_widget()
# #     self.open_image_at_index(self.cur_img_idx)
# #
# # def update_file_list_widget(self):
# #     """更新图片路径列表到界面组件"""
# #     for imgPath in self.m_img_list:
# #         item = QListWidgetItem(imgPath)
# #         self.file_list_widget.addItem(item)
# #
# # def loadImage(self):
# #     QTimer.singleShot(0, self._loadImage)
# #
# # # def loadImage(self):
# # #     """加载当前图片并应用全局调整"""
# # #     if self.cur_img_idx < 0 or self.cur_img_idx >= len(self.m_img_list):
# # #         print("图片索引无效")
# # #         return
# # #
# # #     self.file_path = self.m_img_list[self.cur_img_idx]
# # #     print(f"加载图片: {self.file_path}")
# # #
# # #     try:
# # #         self.original_image = Image.open(self.file_path).convert('RGB')
# # #     except Exception as e:
# # #         print(f"无法加载图片: {e}")
# # #         return
# # #
# # #     # 应用全局参数到图片
# # #     self.applyAdjustments()
# #
# # def _loadImage(self):
# #     if self.cur_img_idx < 0 or self.cur_img_idx >= len(self.m_img_list):
# #         print("图片索引无效")
# #         return
# #
# #     self.file_path = self.m_img_list[self.cur_img_idx]
# #     print(f"加载图片: {self.file_path}")
# #
# #     try:
# #         self.original_image = Image.open(self.file_path).convert('RGB')
# #     except Exception as e:
# #         print(f"无法加载图片: {e}")
# #         return
# #
# #     self.applyAdjustments()
# #
# # def applyAdjustments(self):
# #     """根据全局参数应用调整并更新画布"""
# #     if not hasattr(self, 'original_image') or self.original_image is None:
# #         print("没有原始图片可调整")
# #         return
# #
# #     # 复制原始图片
# #     image = self.original_image.copy()
# #
# #     # 获取当前的滑块值
# #     brightness = self.current_adjustments['brightness'] / 100.0
# #     contrast = self.current_adjustments['contrast'] / 100.0
# #     gamma_r = self.current_adjustments['red_levels'] / 100.0
# #     gamma_g = self.current_adjustments['green_levels'] / 100.0
# #     gamma_b = self.current_adjustments['blue_levels'] / 100.0
# #
# #     # 应用亮度和对比度
# #     image = ImageEnhance.Brightness(image).enhance(brightness)
# #     image = ImageEnhance.Contrast(image).enhance(contrast)
# #
# #     # 应用 RGB 通道伽马校正
# #     r, g, b = image.split()
# #     r = self.adjustGamma(r, gamma_r)
# #     g = self.adjustGamma(g, gamma_g)
# #     b = self.adjustGamma(b, gamma_b)
# #
# #     # 合并调整后的通道
# #     image = Image.merge("RGB", (r, g, b))
# #
# #     # 更新画布中的图片
# #     self.updateCanvas(image)
# #
# # def updateCanvas(self, image):
# #     """将 PIL 图像转换为 QPixmap 并显示在画布上"""
# #     data = image.convert('RGB').tobytes()
# #     qimage = QImage(data, image.width, image.height, QImage.Format_RGB888)
# #     pixmap = QPixmap.fromImage(qimage)
# #
# #     self.canvas.load_pixmap(pixmap)
# #     self.canvas.repaint()  # 强制重绘画布
# #
# # def adjustGamma(self, channel, gamma):
# #     """应用伽马校正"""
# #     inv_gamma = 1.0 / gamma
# #     table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype('uint8')
# #     return channel.point(table)
# #
# #
# #
# # def updateImage(self):
# #     """滑块值变化时更新全局参数并应用调整"""
# #     if not self.file_path:
# #         return
# #
# #     # 更新全局调整参数
# #     self.current_adjustments = {
# #         'brightness': self.brightness_slider.value(),
# #         'contrast': self.contrast_slider.value(),
# #         'red_levels': self.red_levels_slider.value(),
# #         'green_levels': self.green_levels_slider.value(),
# #         'blue_levels': self.blue_levels_slider.value()
# #     }
# #
# #     # 应用新的调整
# #     self.applyAdjustments()
# # def syncColorLevels(self):
# #     """同步RGB色阶滑块"""
# #     value = self.sync_levels_slider.value()
# #     self.red_levels_slider.setValue(value)
# #     self.green_levels_slider.setValue(value)
# #     self.blue_levels_slider.setValue(value)
# #     self.updateImage()
# #
# #
# #
# #
# #
# # def open_image_at_index(self, index):
# #     """根据索引加载指定的图片"""
# #     if 0 <= index < len(self.m_img_list):
# #         self.cur_img_idx = index
# #         self.loadImage()
# #         self.file_list_widget.setCurrentRow(self.cur_img_idx)
# #
# # def open_prev_image(self, _value=False):
# #     """打开上一张图片"""
# #     if self.cur_img_idx > 0:
# #         self.cur_img_idx -= 1
# #         self.open_image_at_index(self.cur_img_idx)
# #     else:
# #         print("已经是第一张图片")
# #
# # def open_next_image(self, _value=False):
# #     """打开下一张图片"""
# #     if self.cur_img_idx + 1 < len(self.m_img_list):
# #         self.cur_img_idx += 1
# #         self.open_image_at_index(self.cur_img_idx)
# #     else:
# #         print("已经是最后一张图片")
#
#
# def load_file(self, file_path=None):
#     """Load the specified file, or the last opened file if None."""
#     self.reset_state()
#     self.canvas.setEnabled(False)
#     if file_path is None:
#         file_path = self.settings.get(SETTING_FILENAME)
#
#     # Make sure that filePath is a regular python string, rather than QString
#     file_path = ustr(file_path)
#     print('file_path', file_path)
#     # Fix bug: An  index error after select a directory when open a new file.
#     unicode_file_path = ustr(file_path)
#     unicode_file_path = os.path.abspath(unicode_file_path)
#     # Tzutalin 20160906 : Add file list and dock to move faster
#     # Highlight the file item
#     if unicode_file_path and self.file_list_widget.count() > 0:
#         if unicode_file_path in self.m_img_list:
#             index = self.m_img_list.index(unicode_file_path)
#             file_widget_item = self.file_list_widget.item(index)
#             file_widget_item.setSelected(True)
#         else:
#             self.file_list_widget.clear()
#             self.m_img_list.clear()
#
#     if unicode_file_path and os.path.exists(unicode_file_path):
#         print('unicode_file_path', unicode_file_path)
#         if LabelFile.is_label_file(unicode_file_path):
#             try:
#                 self.label_file = LabelFile(unicode_file_path)
#             except LabelFileError as e:
#                 self.error_message(u'Error opening file',
#                                    (u"<p><b>%s</b></p>"
#                                     u"<p>Make sure <i>%s</i> is a valid label file.")
#                                    % (e, unicode_file_path))
#                 # self.status("Error reading %s" % unicode_file_path)
#                 return False
#             self.image_data = self.label_file.image_data
#             self.line_color = QColor(*self.label_file.lineColor)
#             self.fill_color = QColor(*self.label_file.fillColor)
#             self.canvas.verified = self.label_file.verified
#         else:
#             # Load image:
#             # read data first and store for saving into label file.
#             self.image_data = read(unicode_file_path, None)
#             self.label_file = None
#             self.canvas.verified = False
#
#         if isinstance(self.image_data, QImage):
#             image = self.image_data
#         else:
#             image = QImage.fromData(self.image_data)
#         if image.isNull():
#             self.error_message(u'Error opening file',
#                                u"<p>Make sure <i>%s</i> is a valid image file." % unicode_file_path)
#             # self.status("Error reading %s" % unicode_file_path)
#             return False
#
#         self.original_image = Image.open(unicode_file_path).convert('RGB')
#
#         self.applyAdjustments()  # 应用调整后更新画布
#         self.status("Loaded %s" % os.path.basename(unicode_file_path))
#         self.image = image
#         self.file_path = unicode_file_path
#         self.canvas.load_pixmap(QPixmap.fromImage(image))
#         if self.label_file:
#             self.load_labels(self.label_file.shapes)
#         self.set_clean()
#         self.canvas.setEnabled(True)
#         # self.adjust_scale(initial=True)
#         self.set_zoom_by_cache()
#         self.paint_canvas()
#         self.add_recent_file(self.file_path)
#         self.toggle_actions(True)
#
#         try:
#             self.show_bounding_box_from_annotation_file(file_path)
#         except Exception as e:
#             logger.debug(str(e))
#
#         self.canvas.setFocus(True)
#         return True
#     return False
#
#
# def applyAdjustments(self):
#     """根据滑块值应用调整，并更新画布，同时保留标注框。"""
#     if not hasattr(self, 'original_image') or self.original_image is None:
#         print("没有原始图片可调整")
#         return
#
#     if not hasattr(self, 'current_adjustments') or not self.current_adjustments:
#         print("滑块值未初始化")
#         return
#
#     try:
#         # 保存当前的标注框数据
#         saved_shapes = self.canvas.shapes.copy()
#
#         # 复制图片进行调整
#         image = self.original_image.copy()
#
#         # 获取滑块值
#         brightness = self.current_adjustments.get('brightness', 100) / 100.0
#         contrast = self.current_adjustments.get('contrast', 100) / 100.0
#         gamma_r = self.current_adjustments.get('red_levels', 100) / 100.0
#         gamma_g = self.current_adjustments.get('green_levels', 100) / 100.0
#         gamma_b = self.current_adjustments.get('blue_levels', 100) / 100.0
#
#         # 应用亮度和对比度调整
#         image = ImageEnhance.Brightness(image).enhance(brightness)
#         image = ImageEnhance.Contrast(image).enhance(contrast)
#
#         # 拆分RGB通道并应用伽马校正
#         r, g, b = image.split()
#         r = self.adjustGamma(r, gamma_r)
#         g = self.adjustGamma(g, gamma_g)
#         b = self.adjustGamma(b, gamma_b)
#
#         # 合并调整后的通道
#         adjusted_image = Image.merge("RGB", (r, g, b))
#
#         # 更新画布并重新加载标注框
#         self.updateCanvas(adjusted_image, saved_shapes)
#
#     except Exception as e:
#         print(f"应用调整时出现错误: {e}")
#
#
# def updateImage(self):
#     """当滑块值变化时更新调整参数并应用调整。"""
#     if not hasattr(self, 'original_image') or self.original_image is None:
#         print("未加载图片，无法更新")
#         return
#
#     # 确保滑块对象存在
#     try:
#         self.current_adjustments = {
#             'brightness': self.brightness_slider.value(),
#             'contrast': self.contrast_slider.value(),
#             'red_levels': self.red_levels_slider.value(),
#             'green_levels': self.green_levels_slider.value(),
#             'blue_levels': self.blue_levels_slider.value()
#         }
#     except Exception as e:
#         print(f"获取滑块值时出现错误: {e}")
#         return
#
#     # 应用新的调整
#     self.applyAdjustments()
#
#
# def syncColorLevels(self):
#     """同步RGB色阶滑块"""
#     value = self.sync_levels_slider.value()
#     self.red_levels_slider.setValue(value)
#     self.green_levels_slider.setValue(value)
#     self.blue_levels_slider.setValue(value)
#     self.updateImage()
#
#
# def updateCanvas(self, image, shapes=None):
#     """将调整后的图像显示在画布上，并保留标注框。"""
#     try:
#         # 将 PIL 图像转换为 QImage
#         data = image.tobytes('raw', 'RGB')
#         qimage = QImage(data, image.width, image.height, QImage.Format_RGB888)
#         pixmap = QPixmap.fromImage(qimage)
#
#         # 加载新图像到画布
#         self.canvas.load_pixmap(pixmap)
#
#         # 如果提供了标注框数据，则加载
#         if shapes:
#             self.canvas.load_shapes(shapes)
#
#         # 强制触发重绘，确保画布更新
#         self.canvas.update()
#         self.canvas.repaint()  # 添加 repaint() 确保强制重绘
#     except Exception as e:
#         print(f"更新画布时出错: {e}")
#
#
# def adjustGamma(self, channel, gamma):
#     """应用伽马校正。"""
#     inv_gamma = 1.0 / gamma if gamma > 0 else 1.0
#     table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)], dtype='uint8')
#     return channel.point(table)
