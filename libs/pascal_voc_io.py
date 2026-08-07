# #!/usr/bin/env python
# # -*- coding: utf8 -*-
# import codecs
# import sys
# from lxml import etree
# from xml.etree import ElementTree
# from xml.etree.ElementTree import Element, SubElement
#
# from libs.constants import DEFAULT_ENCODING
# from libs.ustr import ustr
#
# XML_EXT = '.xml'
# ENCODE_METHOD = DEFAULT_ENCODING
#
#
# class PascalVocWriter:
#
#     def __init__(self, folder_name, filename, img_size, database_src='Unknown', local_img_path=None):
#         self.folder_name = folder_name
#         self.filename = filename
#         self.database_src = database_src
#         self.img_size = img_size
#         self.box_list = []
#         self.local_img_path = local_img_path
#         self.verified = False
#
#     def prettify(self, elem):
#         """
#             Return a pretty-printed XML string for the Element.
#         """
#         rough_string = ElementTree.tostring(elem, 'utf8')
#         root = etree.fromstring(rough_string)
#         return etree.tostring(root, pretty_print=True, encoding=ENCODE_METHOD).replace("  ".encode(), "\t".encode())
#         # minidom does not support UTF-8
#         # reparsed = minidom.parseString(rough_string)
#         # return reparsed.toprettyxml(indent="\t", encoding=ENCODE_METHOD)
#
#     def gen_xml(self):
#         """
#             Return XML root
#         """
#         # Check conditions
#         if self.filename is None or \
#                 self.folder_name is None or \
#                 self.img_size is None:
#             return None
#
#         top = Element('annotation')
#         if self.verified:
#             top.set('verified', 'yes')
#
#         folder = SubElement(top, 'folder')
#         folder.text = self.folder_name
#
#         filename = SubElement(top, 'filename')
#         filename.text = self.filename
#
#         if self.local_img_path is not None:
#             local_img_path = SubElement(top, 'path')
#             local_img_path.text = self.local_img_path
#
#         source = SubElement(top, 'source')
#         database = SubElement(source, 'database')
#         database.text = self.database_src
#
#         size_part = SubElement(top, 'size')
#         width = SubElement(size_part, 'width')
#         height = SubElement(size_part, 'height')
#         depth = SubElement(size_part, 'depth')
#         width.text = str(self.img_size[1])
#         height.text = str(self.img_size[0])
#         if len(self.img_size) == 3:
#             depth.text = str(self.img_size[2])
#         else:
#             depth.text = '1'
#
#         segmented = SubElement(top, 'segmented')
#         segmented.text = '0'
#         return top
#
#     def add_bnd_box(self, x_min, y_min, x_max, y_max, name, difficult):
#         bnd_box = {'xmin': x_min, 'ymin': y_min, 'xmax': x_max, 'ymax': y_max}
#         bnd_box['name'] = name
#         bnd_box['difficult'] = difficult
#         self.box_list.append(bnd_box)
#
#     def append_objects(self, top):
#         for each_object in self.box_list:
#             object_item = SubElement(top, 'object')
#             name = SubElement(object_item, 'name')
#             name.text = ustr(each_object['name'])
#             pose = SubElement(object_item, 'pose')
#             pose.text = "Unspecified"
#             truncated = SubElement(object_item, 'truncated')
#             if int(float(each_object['ymax'])) == int(float(self.img_size[0])) or (
#                     int(float(each_object['ymin'])) == 1):
#                 truncated.text = "1"  # max == height or min
#             elif (int(float(each_object['xmax'])) == int(float(self.img_size[1]))) or (
#                     int(float(each_object['xmin'])) == 1):
#                 truncated.text = "1"  # max == width or min
#             else:
#                 truncated.text = "0"
#             difficult = SubElement(object_item, 'difficult')
#             difficult.text = str(bool(each_object['difficult']) & 1)
#             bnd_box = SubElement(object_item, 'bndbox')
#             x_min = SubElement(bnd_box, 'xmin')
#             x_min.text = str(each_object['xmin'])
#             y_min = SubElement(bnd_box, 'ymin')
#             y_min.text = str(each_object['ymin'])
#             x_max = SubElement(bnd_box, 'xmax')
#             x_max.text = str(each_object['xmax'])
#             y_max = SubElement(bnd_box, 'ymax')
#             y_max.text = str(each_object['ymax'])
#
#     def save(self, target_file=None):
#         root = self.gen_xml()
#         self.append_objects(root)
#         out_file = None
#         if target_file is None:
#             out_file = codecs.open(
#                 self.filename + XML_EXT, 'w', encoding=ENCODE_METHOD)
#         else:
#             out_file = codecs.open(target_file, 'w', encoding=ENCODE_METHOD)
#
#         prettify_result = self.prettify(root)
#         out_file.write(prettify_result.decode('utf8'))
#         out_file.close()
#
#
# class PascalVocReader:
#
#     def __init__(self, file_path):
#         # shapes type:
#         # [labbel, [(x1,y1), (x2,y2), (x3,y3), (x4,y4)], color, color, difficult]
#         self.shapes = []
#         self.file_path = file_path
#         self.verified = False
#         try:
#             self.parse_xml()
#         except:
#             pass
#
#     def get_shapes(self):
#         return self.shapes
#
#     def add_shape(self, label, bnd_box, difficult):
#         x_min = int(float(bnd_box.find('xmin').text))
#         y_min = int(float(bnd_box.find('ymin').text))
#         x_max = int(float(bnd_box.find('xmax').text))
#         y_max = int(float(bnd_box.find('ymax').text))
#         points = [(x_min, y_min), (x_max, y_min), (x_max, y_max), (x_min, y_max)]
#         self.shapes.append((label, points, None, None, difficult))
#
#     def parse_xml(self):
#         assert self.file_path.endswith(XML_EXT), "Unsupported file format"
#         parser = etree.XMLParser(encoding=ENCODE_METHOD)
#         xml_tree = ElementTree.parse(self.file_path, parser=parser).getroot()
#         filename = xml_tree.find('filename').text
#         try:
#             verified = xml_tree.attrib['verified']
#             if verified == 'yes':
#                 self.verified = True
#         except KeyError:
#             self.verified = False
#
#         for object_iter in xml_tree.findall('object'):
#             bnd_box = object_iter.find("bndbox")
#             label = object_iter.find('name').text
#             # Add chris
#             difficult = False
#             if object_iter.find('difficult') is not None:
#                 difficult = bool(int(object_iter.find('difficult').text))
#             self.add_shape(label, bnd_box, difficult)
#         return True


#!/usr/bin/env python
# -*- coding: utf8 -*-
import codecs
import sys
from lxml import etree
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement

from libs.constants import DEFAULT_ENCODING
from libs.ustr import ustr

XML_EXT = '.xml'
ENCODE_METHOD = DEFAULT_ENCODING


class PascalVocWriter:

    def __init__(self, folder_name, filename, img_size, database_src='Unknown', local_img_path=None):
        self.folder_name = folder_name
        self.filename = filename
        self.database_src = database_src
        self.img_size = img_size
        self.box_list = []
        self.local_img_path = local_img_path
        self.verified = False

    def prettify(self, elem):
        """返回格式化后的 XML 字符串。"""
        rough_string = ElementTree.tostring(elem, 'utf8')
        root = etree.fromstring(rough_string)
        return etree.tostring(root, pretty_print=True, encoding=ENCODE_METHOD).replace("  ".encode(), "\t".encode())

    def gen_xml(self):
        """生成 XML 根节点并填充基本信息。"""
        if not (self.filename and self.folder_name and self.img_size):
            print("缺少必要的文件信息，无法生成 XML")
            return None

        top = Element('annotation')
        if self.verified:
            top.set('verified', 'yes')

        self._add_text_element(top, 'folder', self.folder_name)
        self._add_text_element(top, 'filename', self.filename)

        # 添加 source 信息
        source = SubElement(top, 'source')
        self._add_text_element(source, 'database', self.database_src)

        # 添加 owner 信息
        owner = SubElement(top, 'owner')
        self._add_text_element(owner, 'flickrid', "I do not know neither")

        # 添加图像尺寸信息
        size_part = SubElement(top, 'size')
        width, height, depth = self._get_image_size()
        self._add_text_element(size_part, 'width', str(width))
        self._add_text_element(size_part, 'height', str(height))
        self._add_text_element(size_part, 'depth', str(depth))

        self._add_text_element(top, 'segmented', '0')
        return top

    def _get_image_size(self):
        """确保返回图像的 (width, height, depth)。"""
        width, height = self.img_size[:2]
        depth = self.img_size[2] if len(self.img_size) == 3 else 1
        return width, height, depth

    def _add_text_element(self, parent, tag, text):
        """辅助函数，用于添加带文本的 XML 子元素。"""
        element = SubElement(parent, tag)
        element.text = text

    def add_bnd_box(self, coords, name, conf=0, difficult=0, label=0):
        """添加边界框信息。"""
        self.box_list.append({
            'name': name,
            'conf': conf,
            'difficult': difficult,
            'markitemtype': 0,
            'coordinates': coords,
            'label': label
        })

    def append_objects(self, top):
        """将所有边界框对象添加到 XML 中。"""
        for obj in self.box_list:
            obj_elem = SubElement(top, 'object')
            self._add_text_element(obj_elem, 'name', obj['name'])
            self._add_text_element(obj_elem, 'conf', str(obj['conf']))
            self._add_text_element(obj_elem, 'truncated', '0')
            self._add_text_element(obj_elem, 'difficult', str(obj['difficult']))
            self._add_text_element(obj_elem, 'markitemtype', str(obj['markitemtype']))

            # 添加边界框信息
            bnd_box = SubElement(obj_elem, 'bndbox')
            for i, (x, y) in enumerate(obj['coordinates'], start=1):
                self._add_text_element(bnd_box, f'x{i}', str(x))
                self._add_text_element(bnd_box, f'y{i}', str(y))
            self._add_text_element(bnd_box, 'label', str(obj['label']))

    def save(self, target_file=None):
        """保存 XML 文件到目标路径。"""
        root = self.gen_xml()
        self.append_objects(root)

        if target_file is None:
            target_file = self.filename + XML_EXT

        with codecs.open(target_file, 'w', encoding=ENCODE_METHOD) as out_file:
            prettify_result = self.prettify(root)
            out_file.write(prettify_result.decode('utf8'))


class PascalVocReader:

    def __init__(self, file_path):
        self.shapes = []
        self.file_path = file_path
        self.verified = False
        try:
            self.parse_xml()
        except Exception as e:
            print(f"解析 XML 时出错: {e}")

    def get_shapes(self):
        """返回解析后的形状列表。"""
        return self.shapes

    def add_shape(self, label, bnd_box, difficult):
        """将边界框添加到形状列表中。"""
        coordinates = [
            (float(bnd_box.find(f'x{i}').text), float(bnd_box.find(f'y{i}').text))
            for i in range(1, 5)
        ]
        self.shapes.append((label, coordinates, None, None, difficult))

    def parse_xml(self):
        """解析 XML 文件并提取信息。"""
        assert self.file_path.endswith(XML_EXT), "不支持的文件格式"
        parser = etree.XMLParser(encoding=ENCODE_METHOD)
        xml_tree = ElementTree.parse(self.file_path, parser=parser).getroot()

        filename = xml_tree.find('filename').text
        self.verified = xml_tree.get('verified', 'no') == 'yes'

        for obj in xml_tree.findall('object'):
            bnd_box = obj.find("bndbox")
            label = obj.find('name').text
            difficult = bool(int(obj.find('difficult').text)) if obj.find('difficult') is not None else False
            self.add_shape(label, bnd_box, difficult)

        return True
