import collections
import cv2
import fcntl
import json
import os
import threading
import time


# "optical_detection/P/50.jpg": {
#         "data-properties": {
#           "height": 768,
#           "width": 1024
#         },
#         "label": {
#           "classification": -1,
#           "detection": [
#             {
#               "bbox": [
#                 636.7938842773438,
#                 295.9556579589844,
#                 888.2864990234375,
#                 295.9556579589844,
#                 888.2864990234375,
#                 479.9924621582031,
#                 636.7938842773438,
#                 479.9924621582031
#               ],
#               "classification": 1,
#               "confidence": 0.4104676842689514,
#               "id": 0,
#               "is manual label": false
#             }
#           ],
#           "is manual label": false
#         },
#         "other information": {},
#         "sample source": "simulation",
#         "sample source description": "\u4eff\u771f\u5668\u6837\u672c.",
#         "set": "train",
#         "version": "0.3.0"
#       }

def get_classes_index(classes, label):
    for index, c in enumerate(classes):
        if c == label:
            return index
    return -1


def get_sample(shapes, classes, filename, manual=True):
    d = dict()
    # d['data-properties'] = dict(height=1024, width=768)
    if filename:
        img = cv2.imread(filename)
        h, w, _ = img.shape
    else:
        h, w = 768, 1024
    d['data-properties'] = dict(height=h, width=w)
    d['other information'] = {}
    d['sample source'] = "simulation"
    d['sample source description'] = "仿真器样本."
    d['set'] = "train"
    d["version"] = "0.3.0"
    d['label'] = dict()
    d['label']['classification'] = -1
    d['label']['detection'] = []
    d['label']['is manual label'] = manual

    # "other information": {},
    #            "sample source": "simulation",
    #            "sample source description": "仿真器样本.",
    #            "set": "train",
    #            "version": "0.3.0"

    id_count = 0
    for shape in shapes:
        detection_instance = {}
        detection_instance['bbox'] = []  # shape["points"]
        for p in shape["points"]:
            detection_instance['bbox'].append(p[0])
            detection_instance['bbox'].append(p[1])

        detection_instance['classification'] = get_classes_index(classes=classes, label=shape["label"])
        detection_instance['confidence'] = 1
        detection_instance['id'] = id_count
        detection_instance['is manual label'] = manual
        d['label']['detection'].append(detection_instance)
        id_count += 1
    return d


def get_init_json(dataset_name, classes):
    d = dict()
    d["dataset-description"] = "relearning"
    d["dataset-format"] = "relearning"
    d["dataset-name"] = dataset_name  # "relearning-sar-detection-2023",
    d["dataset-version"] = "0.0.1"
    d["label-description"] = {}
    d["label-description"]["bbox"] = "目标检测框"
    d["label-description"]["classification"] = {}
    for label in classes:
        index = get_classes_index(classes, label)
        d["label-description"]["classification"][str(index)] = label
    d["samples"] = collections.OrderedDict()
    return d

def update_classes_mem(desp_json, classes):
    d = desp_json
    for label in classes:
        index = get_classes_index(classes, label)
        d["label-description"]["classification"][str(index)] = label
    return d.copy()

def is_samples_empty(f, count):
    if f.tell() > 500:
        return False
    i = -1
    while (True):
        f.seek(i, 2)
        # print(f.tell())
        s = f.read().decode('utf-8')
        # print(s)
        # print(s.count('}'))
        if s.startswith("samples") and s.count('}') == count:
            return True
        i = i - 1
        if i < -200:
            break
    return False


def get_off_set(f, count=2):
    i = -1
    while (True):
        f.seek(i, 2)
        # print(f.tell())
        s = f.read().decode('utf-8')
        # print(s)
        # print(s.count('}'))
        if s.count('}') == count:
            break
        i = i - 1
    return i


def append_json(json_path, filename, abs_filename, shapes, classes, first_sample):
    with open(json_path, 'rb+') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        print('fcntl LOCKEX')
        lock = threading.Lock()
        with lock:
            print('threading lock')
            # data = json.load(f)
            off_set = get_off_set(f, 2)
            d = get_sample(shapes=shapes, classes=classes, filename=abs_filename, manual=True)
            d_json = json.dumps(d)
            # print(d_json)
            if is_samples_empty(f, 2):
                d_json = "\"" + filename + "\":" + d_json + "}}"
            else:
                d_json = ",\"" + filename + "\":" + d_json + "}}"
            f.seek(off_set, 2)
            f.write(d_json.encode('utf-8'))
        print('threading lock released')
    print('fcntl LOCKUN')


def write_desp_json(desp_json, json_path):
    with open(json_path, 'wb') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        print('fcntl LOCKEX')
        lock = threading.Lock()
        with lock:
            d_json = json.dumps(desp_json)
            f.write(d_json.encode('utf-8'))
        print('threading lock released')
    print('fcntl LOCKUN')


def append_json_mem(filename, abs_filename, shapes, classes):
    d = get_sample(shapes=shapes, classes=classes, filename=abs_filename, manual=True)
    return d.copy()


def init_json(json_path, classes):
    with open(json_path, 'wb') as f:
        f.seek(0, 0)
        d = get_init_json('sar_dataset', classes=classes)
        d_json = json.dumps(d).encode('utf-8')
        f.write(d_json)
    print('Init json succesfully')
    return True


def init_json_mem(classes):
    d = get_init_json('sar_dataset', classes=classes)
    return d.copy()


def generate_sample_numbers_json(des_path, sample_numbers):
    print(des_path)
    json_file_path = os.path.join(des_path, "sample_numbers.json")
    data = {"sample_numbers": sample_numbers}
    with open(json_file_path, 'w') as f:
        json.dump(data, f)


def update_sample_numbers_from_json(des_path, sample_number):
    # 更新sample_numbers.json
    generate_sample_numbers_json(des_path, sample_number)
    print("sample_numbers:", sample_number)
