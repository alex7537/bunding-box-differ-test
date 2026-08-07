import os
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from watchdog.events import *
from watchdog.utils.dirsnapshot import DirectorySnapshot, DirectorySnapshotDiff
from PyQt5.QtGui import QImageReader
import time

# images
extensions = ['.%s' % fmt.data().decode("ascii").lower() for fmt in QImageReader.supportedImageFormats()]

logger = logging.getLogger('mylogger')
logger.setLevel(logging.DEBUG)


class FileEventHandler(FileSystemEventHandler):
    def __init__(self, main_window, aim_path):
        FileSystemEventHandler.__init__(self)
        self.aim_path = aim_path
        self.timer = None
        self.snapshot = DirectorySnapshot(self.aim_path)
        self.main_window = main_window
        self.last_timestamp = 0

    def on_any_event(self, event):
        '''
            check the difference of the dir every 0.2 seconds.
        Args:
            event:

        Returns:

        '''
        #        print('IN on any event')
        #        print(event)
        logger.debug(f'File Event Alive : IN on_any_event {event}')
        # 超过5秒,强制刷新
        if (time.time() - self.last_timestamp) * 1000 > 5000:
            logger.debug('DO self.checkSnapshot()')
            self.checkSnapshot()
            self.last_timestamp = time.time()

        # if event.event_type == "created" or event.event_type == "deleted":
        # 2秒内有新事件，先不刷新
        logger.debug(f'past time = {(time.time() - self.last_timestamp) * 1000}ms')
        if self.timer:
            self.timer.cancel()

        self.timer = threading.Timer(3, self.checkSnapshot)
        logger.debug(f'threading timer start now')
        self.timer.start()
        # else:
        #     pass

    def checkSnapshot(self):
        logger.debug('IN check Snapshot')

        snapshot = DirectorySnapshot(self.aim_path)
        diff = DirectorySnapshotDiff(self.snapshot, snapshot)
        self.snapshot = snapshot
        self.timer = None

        t = time.time()
        self.update_created_files(diff.files_created)
        logger.debug(f'file created {len(diff.files_created)}, using {(time.time() - t) * 1000} ms')

        logger.debug("files_deleted")
        self.update_deleted_files(diff.files_deleted)

        print("files_modified:", diff.files_modified)
        print("files_moved:", diff.files_moved)

        logger.debug(f'Check Snapshot:{(time.time() - t) * 1000} ms')

    def update_created_files(self, files):
        # filter extensions
        filter_files = []
        if files:
            for file in files:
                if file.lower().endswith(tuple(extensions)):
                    filter_files.append(file)
            filter_files.sort()
        if filter_files:
            self.main_window.insert_images(filter_files)

    def update_deleted_files(self, files):
        # filter extensions
        filter_files = []
        if files:
            for file in files:
                if file.lower().endswith(tuple(extensions)):
                    filter_files.append(file)
        if filter_files:
            self.main_window.delete_images(filter_files)
