import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QAction, QFileDialog
from PIL import Image
from images_edit  import ImageEditorWidget  # 导入图片编辑模块

class MainWindow(QMainWindow):
    """主窗口，包含菜单栏和图片编辑器。"""

    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        # 设置主窗口标题和大小
        self.setWindowTitle('图片编辑器')
        self.setGeometry(100, 100, 800, 600)

        # 创建菜单栏和"文件"菜单
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu('文件')

        # 添加"打开图片"菜单项
        open_action = QAction('打开图片', self)
        open_action.triggered.connect(self.open_image)
        file_menu.addAction(open_action)

        # 创建图片编辑器，并设置为中央部件
        self.image_editor = ImageEditorWidget()
        self.setCentralWidget(self.image_editor)

    def open_image(self):
        """打开图片文件并传递给编辑器。"""
        file_name, _ = QFileDialog.getOpenFileName(self, '打开图片', '', 'Images (*.png *.jpg *.jpeg *.bmp)')
        if file_name:
            image = Image.open(file_name)  # 使用 PIL 打开图片
            self.image_editor.set_image(image)  # 将图片传递给编辑器

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
