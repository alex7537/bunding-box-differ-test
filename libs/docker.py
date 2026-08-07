import sys
import threading
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QInputDialog, \
    QListWidget, QMessageBox, QLineEdit
import subprocess


class DockerManagerApp(QWidget):
    def __init__(self):
        super().__init__()

        self.password = None  # 用于存储输入的密码

        self.setWindowTitle('Docker管理')
        self.setGeometry(100, 100, 2200, 1100)

        self.layout = QVBoxLayout(self)

        # 上方布局
        self.top_layout = QVBoxLayout()
        self.right_list = QListWidget(self)
        self.top_layout.addWidget(self.right_list)

        # 下方布局
        self.bottom_layout = QHBoxLayout()

        # 左侧错误信息输出窗口
        self.left_list = QListWidget(self)
        self.bottom_layout.addWidget(self.left_list)

        # 右侧按钮布局
        self.button_layout = QVBoxLayout()
        self.show_images_btn = QPushButton('显示Docker镜像', self)
        self.create_container_btn = QPushButton('新建Docker容器', self)
        self.show_containers_btn = QPushButton('显示Docker容器', self)
        self.start_btn = QPushButton('启动Docker容器', self)
        self.stop_btn = QPushButton('停止Docker容器', self)
        self.monitor_btn = QPushButton('监控Docker容器', self)
        self.button_layout.addWidget(self.show_images_btn)
        self.button_layout.addWidget(self.create_container_btn)
        self.button_layout.addWidget(self.show_containers_btn)
        self.button_layout.addWidget(self.start_btn)
        self.button_layout.addWidget(self.stop_btn)
        self.button_layout.addWidget(self.monitor_btn)

        # 将左侧和右侧的布局添加到主布局中
        self.bottom_layout.addLayout(self.button_layout)
        self.layout.addLayout(self.top_layout)
        self.layout.addLayout(self.bottom_layout)

        self.show_images_btn.clicked.connect(self.show_docker_images)
        self.create_container_btn.clicked.connect(self.create_docker_container)
        self.show_containers_btn.clicked.connect(self.show_docker_containers)
        self.start_btn.clicked.connect(self.start_docker_container)
        self.stop_btn.clicked.connect(self.stop_docker_container)
        self.monitor_btn.clicked.connect(self.monitor_docker_container)
        self.right_list.itemClicked.connect(self.update_info_text)

    def get_password(self):
        if not self.password:  # 只在密码未输入时提示用户输入
            password, ok = QInputDialog.getText(self, '密码输入', '输入主机密码:', QLineEdit.Password)
            if ok:
                self.password = password  # 保存密码
        return self.password

    def show_docker_images(self):
        password = self.get_password()
        if password:
            self.get_all_images(password)

    def create_docker_container(self):
        password = self.get_password()
        if password:
            selected_item = self.right_list.currentItem()
            if selected_item:
                image_name = (selected_item.text().split()[0] + ":" + selected_item.text().split()[1])
                container_name, ok = QInputDialog.getText(self, '输入容器名称', '输入新容器的名称:')
                if ok and container_name:
                    self.execute_docker_command(
                        f"sudo -S docker run  -d --gpus all -p 50:5000 --name {container_name} {image_name} bash -c 'source /home/miniconda3/etc/profile.d/conda.sh && conda activate ptpy37 && python /home/longqi/codebase/pytracking/pytracking/server_api.py'",
                        password)

    def show_docker_containers(self):
        password = self.get_password()
        if password:
            self.get_all_containers(password)

    def start_docker_container(self):
        password = self.get_password()
        if password:
            selected_item = self.left_list.currentItem()
            if selected_item:
                container_id = selected_item.text().split()[0]
                self.execute_docker_command(f"sudo -S docker start {container_id}", password)

    def stop_docker_container(self):
        password = self.get_password()
        if password:
            selected_item = self.left_list.currentItem()
            if selected_item:
                container_id = selected_item.text().split()[0]
                self.execute_docker_command(f"sudo -S docker stop {container_id}", password)

    def monitor_docker_container(self):
        password = self.get_password()
        if password:
            selected_item = self.left_list.currentItem()
            if selected_item:
                container_id = selected_item.text().split()[0]
                self.execute_docker_command(f"sudo -S docker stats --no-stream {container_id}", password)

    def get_all_images(self, password):
        self.execute_docker_command(f"sudo -S docker images", password)

    def get_all_containers(self, password):
        self.execute_docker_command(f"sudo -S docker ps -a", password)

    def execute_docker_command(self, command, password):
        try:
            result = {'output': None, 'error': None}

            def run_command():
                nonlocal result
                try:
                    process = subprocess.Popen(['bash', '-c', f'echo {password} | {command}'], stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE)
                    output, error = process.communicate()

                    result = {'output': output.decode('utf-8'), 'error': error.decode('utf-8')}
                except Exception as e:
                    result = {'output': None, 'error': f"发生错误: {str(e)}"}

            # 创建线程来运行命令
            thread = threading.Thread(target=run_command)
            thread.start()
            thread.join()  # 等待线程完成

            if result['output'] is not None:
                if 'docker ps -a' in command:
                    self.display_list_left(result['output'].split('\n'))
                else:
                    self.display_list_right(result['output'].split('\n'))
            elif result['error'] is not None:
                self.display_list_left(result['error'].split('\n'))
                QMessageBox.critical(self, '错误', f"执行命令失败\n")

        except Exception as e:
            QMessageBox.critical(self, '错误', f"发生错误: {str(e)}")

    def display_list_left(self, info_list):
        self.left_list.clear()
        for item in info_list:
            self.left_list.addItem(item)
            self.left_list.setCurrentRow(0)

    def display_list_right(self, info_list):
        self.right_list.clear()
        for item in info_list:
            self.right_list.addItem(item)
            self.right_list.setCurrentRow(0)

    def update_info_text(self):
        selected_item = self.right_list.currentItem()
        if selected_item and selected_item.text():
            container_id = selected_item.text().split()[0]
            print(container_id)
        else:
            QMessageBox.warning(self, '警告', '未选择任何容器，请选择一个容器。')


def show_docker_manager_window():
    app = QApplication(sys.argv)
    ex = DockerManagerApp()
    ex.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    show_docker_manager_window()
