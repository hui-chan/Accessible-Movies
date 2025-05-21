import csv
import os
import platform
import shutil
import subprocess
import sys
import threading
import time

from PyQt6.QtCore import QSize, Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QDialog, QFileDialog,
                             QFrame, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QMainWindow, QMessageBox,
                             QProgressBar, QPushButton, QRadioButton,
                             QScrollArea, QSplitter, QStackedWidget,
                             QTabWidget, QTextEdit, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout, QWidget)

import AD
import crawler
import tts_with_emo


class WorkerThread(QThread):
    """通用工作线程，用于执行耗时操作"""
    finished = pyqtSignal(bool, str, object)  # 成功/失败, 错误消息, 结果对象
    progress = pyqtSignal(int, str)  # 进度百分比, 状态消息

    def __init__(self, task_func, *args, **kwargs):
        super().__init__()
        self.task_func = task_func
        self.args = args
        self.kwargs = kwargs
        
    def run(self):
        try:
            result = self.task_func(*self.args, **self.kwargs)
            self.finished.emit(True, "", result)
        except Exception as e:
            self.finished.emit(False, str(e), None)

class StartPage(QWidget):
    """开始页面，显示在主应用程序之前"""
    start_clicked = pyqtSignal()  # 开始按钮点击信号

    def __init__(self):
        super().__init__()
        self.background_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),"background.png") # 默认背景图片路径
        self.setup_ui()

    def setup_ui(self):
        # 主垂直布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 背景图层
        self.bg_label = QLabel()
        self.bg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bg_label.setStyleSheet("background-color: #f0f0f0;")
        self.load_background()

        # 创建覆盖层
        overlay = QWidget()
        overlay.setStyleSheet("background-color: rgba(255, 255, 255, 0);")  # 完全透明
        overlay_layout = QVBoxLayout(overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setSpacing(0)

        # 📦 创建左侧内容布局
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(60, 80, 0, 0)  # 左上角留白
        left_layout.setSpacing(20)

        # 🚩白色块包裹标题与副标题，避免半透明背景
        title_container = QWidget()
        title_container.setStyleSheet("background-color: white; border-radius: 10px;")
        title_container.setMaximumWidth(480)
        title_layout = QVBoxLayout(title_container)
        title_layout.setContentsMargins(20, 20, 20, 20)
        title_layout.setSpacing(10)
        # 标题
        title_label = QLabel("无障碍电影制作工具")
        title_label.setStyleSheet("""
            font-size: 36px;
            font-weight: bold;
            color: purple;
            background-color: rgba(255, 255, 255, 0);  /* 半透明白背景 */
            padding: 10px 2px;
            border-radius: 10px;
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # 副标题
        subtitle_label = QLabel("让每个人都能平等地享受电影艺术")
        subtitle_label.setStyleSheet("""
            font-size: 18px;
            color: purple;
            background-color: rgba(255, 255, 255, 0);  /* 同样加淡背景 */
            padding: 6px 60px;
            border-radius: 8px;
        """)
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        title_layout.addWidget(title_label)
        title_layout.addWidget(subtitle_label)

        # ➕ 添加白色标题块到左布局
        left_layout.addWidget(title_container)

        # 🔽 添加一点按钮与标题之间的垂直距离
        left_layout.addSpacing(200)

        # “开始使用”按钮
        start_button = QPushButton("开始使用")
        start_button.setStyleSheet("""
            QPushButton {
                background-color: #8a56e8;
                color: white;
                border: none;
                border-radius: 30px;
                padding: 20px 60px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7546d8;
            }
        """)
        start_button.setFixedSize(240, 60)
        start_button.clicked.connect(self.start_clicked.emit)

        left_layout.addWidget(start_button, alignment=Qt.AlignmentFlag.AlignLeft)

        # 添加左侧布局到覆盖层
        overlay_layout.addLayout(left_layout)
        overlay_layout.addStretch()

        # 将背景和覆盖层添加到主布局
        layout.addWidget(self.bg_label)
        self.bg_label.setLayout(overlay_layout)

    def load_background(self):
        """加载背景图片"""
        try:
            if os.path.exists(self.background_path):
                pixmap = QPixmap(self.background_path)
                if not pixmap.isNull():
                    self.bg_label.setPixmap(pixmap.scaled(
                        self.size(),
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation
                    ))
                    return

            self.bg_label.clear()
            self.bg_label.setStyleSheet("background-color: #3a3a3a;")
            print(f"背景图片 '{self.background_path}' 不存在或无法加载，使用默认背景色")
        except Exception as e:
            print(f"加载背景图片时出错: {e}")
            self.bg_label.clear()
            self.bg_label.setStyleSheet("background-color: #3a3a3a;")

    def resizeEvent(self, event):
        """窗口大小改变时重新调整背景图片"""
        super().resizeEvent(event)
        self.load_background()
class VideoProcessorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("无障碍电影制作工具")
        self.setMinimumSize(960, 720)
        self.resize(900, 750)
        
        # --- 状态变量 ---
        self.video_path = ""
        self.character_library = []  # 存储 (source_path, target_path, char_name)
        self.csv_data = []
        self.csv_headers = []
        self.final_video_path = ""
        self.is_csv_edited = False
        self.video_name_no_ext = None
        
        # --- Step 2 特有状态 ---
        self.step2_mode = "manual"  # 'manual' 或 'scraper'
        self.char_img_path = ""
        self.char_name = ""
        self.movie_title = ""
        self.scraper_results = []  # 存储爬虫结果
        self.driver = None
        
        # --- 动态路径变量 ---
        self.original_video_path = None
        self.base_path = None
        self.character_image_dir = None  # 这是角色图片的最终存储目录 (photos)
        self.zh_txt_path = None
        self.intermediate_csv_dir = None
        self.intermediate_csv_path = None
        
        # --- 创建主堆叠窗口 ---
        self.main_stack = QStackedWidget(self)
        self.setCentralWidget(self.main_stack)
        
        # --- 创建开始页面 ---
        self.start_page = StartPage()
        self.start_page.start_clicked.connect(self.show_main_app)
        
        # --- 创建主应用页面 ---
        self.main_app_widget = QWidget()
        
        # --- 设置UI ---
        self.setup_ui()
        
        # --- 添加页面到堆叠窗口 ---
        self.main_stack.addWidget(self.start_page)
        self.main_stack.addWidget(self.main_app_widget)
        
        # --- 默认显示开始页面 ---
        self.main_stack.setCurrentIndex(0)
        
    def show_main_app(self):
        """显示主应用程序界面"""
        self.main_stack.setCurrentIndex(1)
        
    def setup_ui(self):
        # 主布局
        main_layout = QVBoxLayout(self.main_app_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 顶部标题栏
        self.create_header()
        main_layout.addWidget(self.header_widget)
        
        # 步骤指示器
        self.create_step_indicator()
        main_layout.addWidget(self.step_indicator)
        
        # 主内容区域 - 使用堆叠窗口部件
        self.content_stack = QStackedWidget()
        main_layout.addWidget(self.content_stack)
        
        # 创建各步骤页面
        self.create_step1_page()
        self.create_step2_page()
        self.create_step3_page()
        self.create_step4_page()
        
        # 添加页面到堆叠窗口
        self.content_stack.addWidget(self.step1_page)
        self.content_stack.addWidget(self.step2_page)
        self.content_stack.addWidget(self.step3_page)
        self.content_stack.addWidget(self.step4_page)
        
        # 状态栏
        self.statusBar().setStyleSheet("background-color: #f0f0f0; color: #333;")
        self.set_status("请先选择视频文件")
        
        # 显示第一步
        self.content_stack.setCurrentIndex(0)
        self.update_step_indicator(0)
        
    def create_header(self):
        self.header_widget = QWidget()
        self.header_widget.setObjectName("headerWidget")
        self.header_widget.setStyleSheet("""
            #headerWidget {
                background-color: #f8f9fa;
                border-bottom: 1px solid #e0e0e0;
            }
        """)
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(20, 15, 20, 15)
        
        # 左侧标题和图标
        left_layout = QHBoxLayout()
        
        # 创建圆形头像标签
        avatar_label = QLabel()
        avatar_label.setStyleSheet("""
            background-color: #8a56e8;
            border-radius: 20px;
            min-width: 40px;
            min-height: 40px;
            max-width: 40px;
            max-height: 40px;
        """)
        
        # 标题和副标题
        title_layout = QVBoxLayout()
        title_label = QLabel("无障碍电影制作工具")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #8a56e8;")
        subtitle_label = QLabel("让每个人都能平等地享受电影艺术")
        subtitle_label.setStyleSheet("font-size: 12px; color: #666;")
        
        title_layout.addWidget(title_label)
        title_layout.addWidget(subtitle_label)
        
        left_layout.addWidget(avatar_label)
        left_layout.addSpacing(10)
        left_layout.addLayout(title_layout)
        
        # 右侧按钮
        about_button = QPushButton("关于项目")
        about_button.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 5px 15px;
                color: #333;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        about_button.clicked.connect(self.show_about_dialog)
        
        header_layout.addLayout(left_layout)
        header_layout.addStretch()
        header_layout.addWidget(about_button)
        
    def create_step_indicator(self):
        self.step_indicator = QWidget()
        self.step_indicator.setObjectName("stepIndicator")
        self.step_indicator.setStyleSheet("""
            #stepIndicator {
                background-color: #fff;
                border-bottom: 1px solid #e0e0e0;
            }
        """)
        step_layout = QHBoxLayout(self.step_indicator)
        step_layout.setContentsMargins(20, 15, 20, 15)
        
        # 创建4个步骤指示器
        self.step_widgets = []
        step_titles = ["选择视频", "管理角色库", "编辑音频描述", "生成无障碍视频"]
        step_descriptions = [
            "选择需要添加无障碍音轨的视频文件",
            "添加或管理视频中的角色信息",
            "编辑自动生成的音频描述",
            "生成并查看最终的无障碍视频"
        ]
        
        for i in range(4):
            step_widget = QWidget()
            step_widget.setObjectName(f"step{i+1}")
            step_layout_inner = QVBoxLayout(step_widget)
            step_layout_inner.setContentsMargins(0, 0, 0, 0)
            
            # 步骤数字
            number_label = QLabel(str(i+1))
            number_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            number_label.setObjectName(f"stepNumber{i+1}")
            number_label.setStyleSheet("""
                background-color: #d8d8d8;
                color: #666;
                border-radius: 15px;
                min-width: 30px;
                min-height: 30px;
                max-width: 30px;
                max-height: 30px;
                font-weight: bold;
                font-size: 14px;
            """)
            
            # 步骤标题
            title_label = QLabel(step_titles[i])
            title_label.setObjectName(f"stepTitle{i+1}")
            title_label.setStyleSheet("font-weight: bold; color: #666; margin-top: 5px;")
            title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # 步骤描述
            desc_label = QLabel(step_descriptions[i])
            desc_label.setObjectName(f"stepDesc{i+1}")
            desc_label.setStyleSheet("font-size: 11px; color: #888;")
            desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            desc_label.setWordWrap(True)
            
            step_layout_inner.addWidget(number_label, 0, Qt.AlignmentFlag.AlignCenter)
            step_layout_inner.addWidget(title_label)
            step_layout_inner.addWidget(desc_label)
            
            self.step_widgets.append({
                'widget': step_widget,
                'number': number_label,
                'title': title_label,
                'desc': desc_label
            })
            
            step_layout.addWidget(step_widget)
            
            # 添加连接线，除了最后一个步骤
            if i < 3:
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFrameShadow(QFrame.Shadow.Sunken)
                line.setStyleSheet("background-color: #d8d8d8; max-height: 1px;")
                step_layout.addWidget(line)
        
    def update_step_indicator(self, current_step):
        """更新步骤指示器的样式，高亮当前步骤"""
        for i, step_dict in enumerate(self.step_widgets):
            if i == current_step:
                # 当前步骤
                step_dict['number'].setStyleSheet("""
                    background-color: #8a56e8;
                    color: white;
                    border-radius: 15px;
                    min-width: 30px;
                    min-height: 30px;
                    max-width: 30px;
                    max-height: 30px;
                    font-weight: bold;
                    font-size: 14px;
                """)
                step_dict['title'].setStyleSheet("font-weight: bold; color: #8a56e8; margin-top: 5px;")
                step_dict['desc'].setStyleSheet("font-size: 11px; color: #555;")
            elif i < current_step:
                # 已完成步骤
                step_dict['number'].setStyleSheet("""
                    background-color: #a8d5ba;
                    color: white;
                    border-radius: 15px;
                    min-width: 30px;
                    min-height: 30px;
                    max-width: 30px;
                    max-height: 30px;
                    font-weight: bold;
                    font-size: 14px;
                """)
                step_dict['title'].setStyleSheet("font-weight: bold; color: #666; margin-top: 5px;")
                step_dict['desc'].setStyleSheet("font-size: 11px; color: #888;")
            else:
                # 未开始步骤
                step_dict['number'].setStyleSheet("""
                    background-color: #d8d8d8;
                    color: #666;
                    border-radius: 15px;
                    min-width: 30px;
                    min-height: 30px;
                    max-width: 30px;
                    max-height: 30px;
                    font-weight: bold;
                    font-size: 14px;
                """)
                step_dict['title'].setStyleSheet("font-weight: bold; color: #666; margin-top: 5px;")
                step_dict['desc'].setStyleSheet("font-size: 11px; color: #888;")
    
    def create_step1_page(self):
        self.step1_page = QWidget()
        layout = QVBoxLayout(self.step1_page)
        layout.setContentsMargins(30, 20, 30, 20)
        
        # 欢迎区域
        welcome_widget = QWidget()
        welcome_widget.setObjectName("welcomeWidget")
        welcome_widget.setStyleSheet("""
            #welcomeWidget {
                background-color: #f0f0ff;
                border-radius: 8px;
                padding: 20px;
            }
        """)
        welcome_layout = QHBoxLayout(welcome_widget)
        
        # 左侧头像
        avatar_label = QLabel()
        avatar_label.setStyleSheet("""
            background-color: #8a56e8;
            border-radius: 25px;
            min-width: 50px;
            min-height: 50px;
            max-width: 50px;
            max-height: 50px;
        """)
        
        # 右侧文本
        welcome_text_layout = QVBoxLayout()
        welcome_title = QLabel("欢迎使用无障碍电影制作工具")
        welcome_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #8a56e8;")
        welcome_desc = QLabel("本工具旨在帮助为视障人士制作无障碍电影，让电影艺术不再有障碍。\n请选择您想要处理的视频文件，开始制作之旅。")
        welcome_desc.setStyleSheet("font-size: 13px; color: #555; margin-top: 5px;")
        welcome_desc.setWordWrap(True)
        
        welcome_text_layout.addWidget(welcome_title)
        welcome_text_layout.addWidget(welcome_desc)
        
        welcome_layout.addWidget(avatar_label)
        welcome_layout.addSpacing(15)
        welcome_layout.addLayout(welcome_text_layout)
        welcome_layout.addStretch()
        
        # 步骤标题
        step_title = QLabel("步骤 1: 选择视频文件")
        step_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #333; margin: 20px 0;")
        
        # 文件选择区域
        file_select_widget = QWidget()
        file_select_widget.setObjectName("fileSelectWidget")
        file_select_widget.setStyleSheet("""
            #fileSelectWidget {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 20px;
            }
        """)
        file_select_layout = QVBoxLayout(file_select_widget)
        
        # 文件选择行
        file_row_layout = QHBoxLayout()
        file_label = QLabel("视频文件:")
        file_label.setStyleSheet("font-size: 14px; color: #333;")
        
        self.video_path_edit = QLineEdit()
        self.video_path_edit.setReadOnly(True)
        self.video_path_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 8px;
                background-color: #f9f9f9;
            }
        """)
        
        browse_button = QPushButton("浏览...")
        browse_button.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px 15px;
                color: #333;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        browse_button.clicked.connect(self.select_video)
        
        file_row_layout.addWidget(file_label)
        file_row_layout.addWidget(self.video_path_edit, 1)
        file_row_layout.addWidget(browse_button)
        
        # 为什么无障碍电影很重要
        importance_widget = QWidget()
        importance_widget.setObjectName("importanceWidget")
        importance_widget.setStyleSheet("""
            #importanceWidget {
                background-color: #f8f8f8;
                border-radius: 8px;
                padding: 15px;
                margin-top: 20px;
            }
        """)
        importance_layout = QVBoxLayout(importance_widget)
        
        importance_title = QLabel("为什么无障碍电影很重要?")
        importance_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #8a56e8;")
        
        importance_text = QLabel(
            "在中国，有超过1700万视力障碍者，他们同样渴望欣赏电影艺术。\n"
            "无障碍电影通过添加专业的音频描述，帮助视障人士理解电影中的视觉元素，如场景、人物动作、表情等非对话内容。\n"
            "您的参与将帮助更多人平等地享受电影的魅力。"
        )
        importance_text.setStyleSheet("font-size: 13px; color: #555; line-height: 150%;")
        importance_text.setWordWrap(True)
        
        importance_layout.addWidget(importance_title)
        importance_layout.addWidget(importance_text)
        
        # 下一步按钮
        self.step1_next_button = QPushButton("下一步：设置角色库")
        self.step1_next_button.setEnabled(False)
        self.step1_next_button.setStyleSheet("""
            QPushButton {
                background-color: #8a56e8;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-size: 14px;
                margin-top: 20px;
            }
            QPushButton:hover {
                background-color: #7546d8;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
        """)
        self.step1_next_button.clicked.connect(self.goto_step2)
        
        # 添加所有组件到布局
        file_select_layout.addLayout(file_row_layout)
        
        layout.addWidget(welcome_widget)
        layout.addWidget(step_title)
        layout.addWidget(file_select_widget)
        layout.addWidget(importance_widget)
        layout.addWidget(self.step1_next_button, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        
    def create_step2_page(self):
        self.step2_page = QWidget()
        layout = QVBoxLayout(self.step2_page)
        layout.setContentsMargins(30, 20, 30, 20)
        
        # 步骤标题
        step_title = QLabel("步骤 2: 管理角色库")
        step_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #333; margin-bottom: 20px;")
        
        # 模式选择区域
        mode_group = QGroupBox("选择添加方式")
        mode_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        mode_layout = QHBoxLayout(mode_group)
        
        # 单选按钮
        self.scraper_radio = QRadioButton("爬虫获取")
        self.scraper_radio.setChecked(True)
        self.manual_radio = QRadioButton("手动添加")
        
        mode_layout.addWidget(self.scraper_radio)
        mode_layout.addWidget(self.manual_radio)
        mode_layout.addStretch()
        
        # 创建按钮组并连接信号
        mode_button_group = QButtonGroup(self)
        mode_button_group.addButton(self.scraper_radio, 1)
        mode_button_group.addButton(self.manual_radio, 2)
        mode_button_group.buttonClicked.connect(self.toggle_step2_mode)
        
        # 创建堆叠窗口用于切换手动/爬虫模式
        self.step2_stack = QStackedWidget()
        
        # 手动添加页面
        manual_page = QWidget()
        manual_layout = QVBoxLayout(manual_page)
        
        manual_group = QGroupBox("手动添加角色信息")
        manual_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        manual_inner_layout = QVBoxLayout(manual_group)
        
        # 图片选择行
        img_row_layout = QHBoxLayout()
        img_label = QLabel("选择图片:")
        
        self.char_img_edit = QLineEdit()
        self.char_img_edit.setReadOnly(True)
        self.char_img_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 8px;
                background-color: #f9f9f9;
            }
        """)
        
        img_browse_button = QPushButton("浏览...")
        img_browse_button.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px 15px;
                color: #333;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        img_browse_button.clicked.connect(self.select_character_image)
        
        img_row_layout.addWidget(img_label)
        img_row_layout.addWidget(self.char_img_edit, 1)
        img_row_layout.addWidget(img_browse_button)
        
        # 角色名称行
        name_row_layout = QHBoxLayout()
        name_label = QLabel("角色名称:")
        
        self.char_name_edit = QLineEdit()
        self.char_name_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        
        add_char_button = QPushButton("添加角色")
        add_char_button.setStyleSheet("""
            QPushButton {
                background-color: #8a56e8;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 15px;
            }
            QPushButton:hover {
                background-color: #7546d8;
            }
        """)
        add_char_button.clicked.connect(self.add_character)
        
        name_row_layout.addWidget(name_label)
        name_row_layout.addWidget(self.char_name_edit, 1)
        name_row_layout.addWidget(add_char_button)
        
        manual_inner_layout.addLayout(img_row_layout)
        manual_inner_layout.addLayout(name_row_layout)
        
        manual_layout.addWidget(manual_group)
        manual_layout.addStretch()
        
        # 爬虫获取页面
        scraper_page = QWidget()
        scraper_layout = QVBoxLayout(scraper_page)
        
        scraper_group = QGroupBox("爬虫获取角色信息")
        scraper_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        scraper_inner_layout = QVBoxLayout(scraper_group)
        
        # 电影名称搜索行
        search_row_layout = QHBoxLayout()
        search_label = QLabel("电影名称:")
        
        self.movie_title_edit = QLineEdit()
        self.movie_title_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        
        search_button = QPushButton("搜索")
        search_button.setStyleSheet("""
            QPushButton {
                background-color: #8a56e8;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 15px;
            }
            QPushButton:hover {
                background-color: #7546d8;
            }
        """)
        search_button.clicked.connect(self.start_search_movie_characters)
        
        search_row_layout.addWidget(search_label)
        search_row_layout.addWidget(self.movie_title_edit, 1)
        search_row_layout.addWidget(search_button)
        
        # 搜索结果列表
        results_group = QGroupBox("搜索结果候选")
        results_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        results_layout = QVBoxLayout(results_group)
        
        self.scraper_results_list = QListWidget()
        self.scraper_results_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: #e0e0ff;
                color: #333;
            }
        """)
        
        results_layout.addWidget(self.scraper_results_list)
        
        # 爬取按钮
        self.download_button = QPushButton("从选中链接中爬取角色信息")
        self.download_button.setEnabled(False)
        self.download_button.setStyleSheet("""
            QPushButton {
                background-color: #8a56e8;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 15px;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #7546d8;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
        """)
        self.download_button.clicked.connect(self.start_download_selected_characters)
        
        results_layout.addWidget(self.download_button)
        
        scraper_inner_layout.addLayout(search_row_layout)
        scraper_inner_layout.addWidget(results_group)
        
        scraper_layout.addWidget(scraper_group)
        scraper_layout.addStretch()
        
        # 添加两个页面到堆叠窗口
        self.step2_stack.addWidget(manual_page)
        self.step2_stack.addWidget(scraper_page)
        
        # 角色列表区域
        char_list_group = QGroupBox("当前角色库 (保存在 photos 文件夹)")
        char_list_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        char_list_layout = QVBoxLayout(char_list_group)
        
        self.char_listbox = QListWidget()
        self.char_listbox.setStyleSheet("""
            QListWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 5px;
            }
            QListWidget::item:selected {
                background-color: #e0e0ff;
                color: #333;
            }
        """)
        
        char_list_layout.addWidget(self.char_listbox)
        
        # 删除按钮
        self.remove_char_button = QPushButton("删除库中选中角色")
        self.remove_char_button.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px 15px;
                color: #333;
                margin-top: 10px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        self.remove_char_button.clicked.connect(self.remove_selected_character)
        
        char_list_layout.addWidget(self.remove_char_button)
        
        # 提交按钮
        self.submit_library_button = QPushButton("保存角色库并生成音频描述")
        self.submit_library_button.setStyleSheet("""
            QPushButton {
                background-color: #8a56e8;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-size: 14px;
                margin-top: 20px;
            }
            QPushButton:hover {
                background-color: #7546d8;
            }
        """)
        self.submit_library_button.clicked.connect(self.submit_character_library)
        
        # 添加所有组件到布局
        layout.addWidget(step_title)
        layout.addWidget(mode_group)
        layout.addWidget(self.step2_stack)
        layout.addWidget(char_list_group)
        layout.addWidget(self.submit_library_button, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        
    def create_step3_page(self):
        self.step3_page = QWidget()
        layout = QVBoxLayout(self.step3_page)
        layout.setContentsMargins(30, 20, 30, 20)
        
        # 步骤标题
        step_title = QLabel("步骤 3: 查看和修改旁白脚本")
        step_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #333; margin-bottom: 20px;")
        
        # 树形视图
        self.tree = QTreeWidget()
        self.tree.setStyleSheet("""
            QTreeWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 5px;
            }
            QTreeWidget::item {
                padding: 5px;
            }
            QTreeWidget::item:selected {
                background-color: #e0e0ff;
                color: #333;
            }
            QTreeWidget QHeaderView::section {
                background-color: #f0f0f0;
                padding: 5px;
                border: 1px solid #ccc;
                font-weight: bold;
            }
        """)
        self.tree.setAlternatingRowColors(True)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.edit_button = QPushButton("编辑选中行")
        self.edit_button.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px 15px;
                color: #333;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        self.edit_button.clicked.connect(self.edit_selected_row)
        
        self.submit_csv_button = QPushButton("保存修改并生成最终视频")
        self.submit_csv_button.setStyleSheet("""
            QPushButton {
                background-color: #8a56e8;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 15px;
            }
            QPushButton:hover {
                background-color: #7546d8;
            }
        """)
        self.submit_csv_button.clicked.connect(self.submit_csv_for_final_processing)
        
        button_layout.addWidget(self.edit_button)
        button_layout.addStretch()
        button_layout.addWidget(self.submit_csv_button)
        
        # 添加所有组件到布局
        layout.addWidget(step_title)
        layout.addWidget(self.tree)
        layout.addLayout(button_layout)
        
    def create_step4_page(self):
        self.step4_page = QWidget()
        layout = QVBoxLayout(self.step4_page)
        layout.setContentsMargins(30, 20, 30, 20)
        
        # 步骤标题
        step_title = QLabel("步骤 4: 查看最终生成的视频")
        step_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #333; margin-bottom: 20px;")
        
        # 视频路径显示
        path_group = QGroupBox("最终视频文件")
        path_group.setStyleSheet("""
            QGroupBox {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                font-size: 14px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        path_layout = QVBoxLayout(path_group)
        
        self.final_video_path_edit = QLineEdit()
        self.final_video_path_edit.setReadOnly(True)
        self.final_video_path_edit.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 8px;
                background-color: #f9f9f9;
            }
        """)
        
        path_layout.addWidget(self.final_video_path_edit)
        
        # 播放按钮
        self.play_button = QPushButton("▶ 播放视频 (系统默认播放器)")
        self.play_button.setStyleSheet("""
            QPushButton {
                background-color: #8a56e8;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-size: 14px;
                margin: 20px 0;
            }
            QPushButton:hover {
                background-color: #7546d8;
            }
        """)
        self.play_button.clicked.connect(self.play_video)
        
        # 操作按钮
        action_layout = QHBoxLayout()
        
        self.back_to_edit_button = QPushButton("返回编辑旁白脚本")
        self.back_to_edit_button.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px 15px;
                color: #333;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        self.back_to_edit_button.clicked.connect(self.goto_step3_from_step4)
        
        self.full_restart_button = QPushButton("处理新视频 (完全重启)")
        self.full_restart_button.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 8px 15px;
                color: #333;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)
        self.full_restart_button.clicked.connect(self.restart_process)
        
        action_layout.addWidget(self.back_to_edit_button)
        action_layout.addWidget(self.full_restart_button)
        
        # 添加所有组件到布局
        layout.addWidget(step_title)
        layout.addWidget(path_group)
        layout.addWidget(self.play_button, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(action_layout)
        layout.addStretch()
        
    def set_status(self, message):
        """设置状态栏消息"""
        self.statusBar().showMessage(message)
        QApplication.processEvents()  # 确保UI更新
        
    def show_about_dialog(self):
        """显示关于对话框"""
        QMessageBox.about(self, "关于项目", 
                         "无障碍电影制作工具\n\n"
                         "版本: 1.0\n"
                         "本工具旨在帮助为视障人士制作无障碍电影，让电影艺术不再有障碍。\n\n"
                         "通过AI技术自动生成视觉内容的音频描述，帮助视障人士更好地理解电影。")
        
    # --- 步骤 1 功能 ---
    def select_video(self):
        """选择视频文件"""
        filetypes = "视频文件 (*.mp4 *.avi *.mov *.mkv);;所有文件 (*.*)"
        filepath, _ = QFileDialog.getOpenFileName(self, "选择视频文件", "", filetypes)
        
        if filepath:
            self.video_path = filepath
            self.video_path_edit.setText(filepath)
            self.original_video_path = filepath
            
            try:
                video_filename = os.path.basename(filepath)
                self.video_name_no_ext, _ = os.path.splitext(video_filename)
                if not self.video_name_no_ext:
                    QMessageBox.critical(self, "错误", "视频文件名无效，无法处理。")
                    self.step1_next_button.setEnabled(False)
                    self.set_status("错误：视频文件名无效")
                    return
                
                # 使用AppData/Local目录
                local_appdata = os.getenv('LOCALAPPDATA', os.path.join(os.path.expanduser('~'), 'AppData', 'Local'))
                program_base_dir = os.path.join(local_appdata, 'ADTool')
                
                self.base_path = os.path.join(program_base_dir, self.video_name_no_ext)
                self.character_image_dir = os.path.join(self.base_path, 'photos')
                self.zh_txt_path = os.path.join(self.character_image_dir, 'zh.txt')
                self.intermediate_csv_dir = os.path.join(self.base_path, 'video_seg')
                self.intermediate_csv_path = os.path.join(self.intermediate_csv_dir, 'merged_AD_scripts.csv')
                self.final_video_path = os.path.join(self.base_path, f'{self.video_name_no_ext}_processed.mp4')
                
                os.makedirs(self.base_path, exist_ok=True)
                os.makedirs(self.character_image_dir, exist_ok=True)
                os.makedirs(self.intermediate_csv_dir, exist_ok=True)
                
                print(f"视频处理基础路径设置为: {self.base_path}")
                print(f"角色图片目录: {self.character_image_dir}")
                
                self.step1_next_button.setEnabled(True)
                self.set_status(f"已选择: {video_filename} | 工作目录: {self.base_path}")
                
            except Exception as e:
                QMessageBox.critical(self, "路径错误", f"计算或创建工作路径时出错:\n{e}")
                self.set_status("路径设置失败")
                self.step1_next_button.setEnabled(False)
                self.reset_paths()
                self.video_path_edit.setText("")
    
    def reset_paths(self):
        """重置所有路径变量"""
        self.original_video_path = None
        self.base_path = None
        self.character_image_dir = None
        self.zh_txt_path = None
        self.intermediate_csv_dir = None
        self.intermediate_csv_path = None
        self.final_video_path = None
        self.final_video_path_edit.setText("")
    
    def goto_step2(self):
        """转到步骤2"""
        if not self.original_video_path or not self.base_path:
            QMessageBox.critical(self, "错误", "请先成功选择一个视频文件！")
            return
            
        if self.character_image_dir:
            os.makedirs(self.character_image_dir, exist_ok=True)
        else:
            QMessageBox.critical(self, "错误", "角色图片目录未设置。请返回步骤1。")
            return
            
        self.preload_character_library()
        self.toggle_step2_mode()  # 确保根据默认模式显示正确的Frame
        self.content_stack.setCurrentIndex(1)  # 显示步骤2
        self.update_step_indicator(1)
        self.set_status("步骤 2: 管理角色库 - 选择模式或添加角色")
    
    # --- 步骤 2 功能 ---
    def toggle_step2_mode(self):
        """切换步骤2的模式（手动/爬虫）"""
        if self.manual_radio.isChecked():
            self.step2_mode = "manual"
            self.step2_stack.setCurrentIndex(0)
            self.set_status("请手动选择角色图片和输入名称")
        else:
            self.step2_mode = "scraper"
            self.step2_stack.setCurrentIndex(1)
            self.set_status("请输入电影名称进行搜索")
    
    def select_character_image(self):
        """选择角色图片"""
        if not self.character_image_dir or not os.path.exists(self.character_image_dir):
            QMessageBox.critical(self, "错误", "角色图片目录 'photos' 未找到或未设置。请返回步骤1。")
            return
            
        filetypes = "图片文件 (*.jpg *.jpeg *.png *.bmp);;所有文件 (*.*)"
        filepath, _ = QFileDialog.getOpenFileName(self, "选择角色图片", "", filetypes)
        
        if filepath:
            self.char_img_path = filepath
            self.char_img_edit.setText(filepath)
    
    def add_character(self):
        """添加角色到库中"""
        if not self.character_image_dir or not os.path.exists(self.character_image_dir):
            QMessageBox.critical(self, "错误", "角色图片目录 'photos' 未找到或未设置。请返回步骤1。")
            return
            
        img_path = self.char_img_path
        char_name = self.char_name_edit.text().strip()
        
        if not img_path or not char_name:
            QMessageBox.warning(self, "提示", "请选择图片并输入角色名称。")
            return
            
        # 目标路径是在photos文件夹下
        base_filename = os.path.basename(img_path)
        target_path = os.path.join(self.character_image_dir, base_filename)
        
        # 检查是否重复
        if any(tp == target_path and name == char_name for _, tp, name in self.character_library):
            QMessageBox.warning(self, "重复", f"角色 '{char_name}' 使用图片 '{base_filename}' 已在库中。")
            return
            
        # 添加到内存列表
        self.character_library.append((img_path, target_path, char_name))
        self.char_listbox.addItem(f"角色: {char_name} (文件: {base_filename})")
        
        self.char_img_path = ""
        self.char_img_edit.setText("")
        self.char_name_edit.setText("")
        self.char_name_edit.setFocus()
        self.set_status(f"已添加角色到列表: {char_name}")
    
    def remove_selected_character(self):
        """从库中删除选中的角色"""
        selected_items = self.char_listbox.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "提示", "请在下面的角色库列表中选择要删除的角色。")
            return
            
        if not QMessageBox.question(self, "确认删除", 
                                   f"确定要从角色库列表中删除选中的 {len(selected_items)} 个角色吗？\n"
                                   "（注意：这不会删除 photos 文件夹中的实际图片文件）",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            return
            
        deleted_count = 0
        # 从后往前删，避免索引变化问题
        for item in reversed(selected_items):
            try:
                item_text = item.text()
                print(f"准备删除: {item_text}")
                
                # 从character_library中找到并删除对应项
                try:
                    parts = item_text.split('(文件: ')
                    name_part = parts[0].replace('角色: ', '').strip()
                    filename_part = parts[1].replace(')', '').strip()
                    target_path_to_remove = os.path.join(self.character_image_dir, filename_part)
                    
                    found_in_lib = False
                    for j, (src, target, name) in enumerate(self.character_library):
                        if target == target_path_to_remove and name == name_part:
                            print(f"  > 在 character_library 中找到匹配项，索引 {j}")
                            del self.character_library[j]
                            found_in_lib = True
                            break
                    if not found_in_lib:
                        print(f"  > 警告：在 character_library 中未找到与 '{item_text}' 完全匹配的项。")
                        
                except Exception as e:
                    print(f"  > 解析列表项 '{item_text}' 时出错: {e}. 无法从 character_library 中移除。")
                
                # 从列表中删除
                row = self.char_listbox.row(item)
                self.char_listbox.takeItem(row)
                deleted_count += 1
                
            except Exception as e:
                print(f"删除列表项时出错: {e}")
        
        self.set_status(f"已从角色库列表中删除 {deleted_count} 个角色。")
    
    def preload_character_library(self):
        """从zh.txt加载角色库"""
        self.character_library = []
        self.char_listbox.clear()
        
        if not self.zh_txt_path:
            print("警告: zh.txt 路径未设置，无法预加载。")
            return
        if not self.character_image_dir:
            print("警告: 角色图片目录未设置，无法验证图片。")
            
        if os.path.exists(self.zh_txt_path):
            try:
                count = 0
                with open(self.zh_txt_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and ',' in line:
                            parts = line.split(',', 1)
                            img_filename_no_ext = parts[0].strip()
                            char_name = parts[1].strip()
                            
                            if img_filename_no_ext and char_name:
                                # 尝试在photos目录找到实际图片文件
                                found_img_path = None
                                target_filename = ""
                                if self.character_image_dir:
                                    target_path_base = os.path.join(self.character_image_dir, img_filename_no_ext)
                                    for ext in ['.jpg', '.jpeg', '.png', '.bmp']:
                                        potential_path = target_path_base + ext
                                        if os.path.exists(potential_path):
                                            found_img_path = potential_path
                                            target_filename = os.path.basename(found_img_path)
                                            break
                                else:
                                    target_filename = f"{img_filename_no_ext}.???"
                                
                                if found_img_path:
                                    self.character_library.append((found_img_path, found_img_path, char_name))
                                    self.char_listbox.addItem(f"角色: {char_name} (文件: {target_filename})")
                                    count += 1
                                else:
                                    print(f"警告: 角色 '{char_name}' 的图片文件 '{img_filename_no_ext}.*' 在目录 {self.character_image_dir} 中未找到。仍在库中记录。")
                                    missing_target_path = os.path.join(self.character_image_dir or "", img_filename_no_ext + ".???")
                                    self.character_library.append((None, missing_target_path, char_name))
                                    self.char_listbox.addItem(f"角色: {char_name} (文件: {img_filename_no_ext}.??? - 未找到)")
                                    count += 1
                
                if count > 0:
                    self.set_status(f"已从 {os.path.basename(self.zh_txt_path)} 加载 {count} 个角色记录。")
                else:
                    self.set_status(f"{os.path.basename(self.zh_txt_path)} 存在但未加载任何有效角色。")
                    
            except Exception as e:
                QMessageBox.critical(self, "加载错误", f"从 zh.txt 加载角色库时出错: {e}")
                self.character_library = []
                self.char_listbox.clear()
                self.set_status("加载 zh.txt 失败")
        else:
            self.set_status("未找到现有的角色库 (zh.txt)。请添加新角色。")
    
    # --- 爬虫相关方法 ---
    def start_search_movie_characters(self):
        """启动搜索电影角色的线程"""
        movie_title = self.movie_title_edit.text().strip()
        if not movie_title:
            QMessageBox.warning(self, "提示", "请输入电影名称。")
            return
            
        self.set_status(f"正在搜索电影 '{movie_title}' ...")
        self.movie_title_edit.setEnabled(False)
        self.download_button.setEnabled(False)
        self.scraper_results_list.clear()
        
        # 创建并启动工作线程
        def search_task():
            self.driver = crawler.setup_browser()
            return crawler.baidu_search(self.driver, movie_title)
            
        self.search_thread = WorkerThread(search_task)
        self.search_thread.finished.connect(self.on_search_complete)
        self.search_thread.start()
    
    def on_search_complete(self, success, error_message, results):
        """搜索完成后的回调"""
        self.movie_title_edit.setEnabled(True)
        
        if not success or results is None:
            self.set_status("未找到相关电影信息。")
            QMessageBox.information(self, "无结果", f"未能找到与该电影相关的信息。{error_message}")
            self.download_button.setEnabled(False)
        else:
            self.scraper_results = results
            self.scraper_results_list.clear()
            for idx, title, href in results:
                display_text = f"[{idx}] {title[:40]} -> {href}"
                self.scraper_results_list.addItem(display_text)
            self.set_status(f"找到 {len(results)} 个候选结果，请在上方列表选择后下载。")
            self.download_button.setEnabled(True)
    
    def start_download_selected_characters(self):
        """启动从选中链接中爬取角色信息的线程"""
        selected_items = self.scraper_results_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "提示", "请选择一个搜索结果。")
            return
            
        selected_index = self.scraper_results_list.row(selected_items[0])
        if selected_index < 0 or selected_index >= len(self.scraper_results):
            QMessageBox.warning(self, "错误", "选择的项目无效。")
            return
            
        url = self.scraper_results[selected_index][2]
        if not url:
            QMessageBox.warning(self, "错误", "没有有效词条可用")
            return
            
        self.set_status(f"正在从 {url} 爬取角色信息...")
        self.download_button.setEnabled(False)
        
        # 创建并启动工作线程
        def download_task():
            crawler.crawl_baike_roles_images(self.driver, self.character_image_dir, url,False)
            crawler.crawl_baike_roles_images(self.driver, self.character_image_dir, url,True)
            if self.driver:
                self.driver.quit()
                self.driver = None
            return True
            
        self.download_thread = WorkerThread(download_task)
        self.download_thread.finished.connect(self.on_download_complete)
        self.download_thread.start()
    
    def on_download_complete(self, success, error_message, _):
        """下载完成后的回调"""
        self.download_button.setEnabled(True)
        
        if not success:
            QMessageBox.warning(self, "下载错误", f"爬取角色信息时出错: {error_message}")
            self.set_status(f"爬取失败: {error_message}")
        else:
            self.set_status("角色信息爬取完成，正在刷新角色库...")
            self.preload_character_library()
    
    def submit_character_library(self):
        """提交角色库并开始处理"""
        if not self.character_image_dir or not self.zh_txt_path or not self.intermediate_csv_path:
            QMessageBox.critical(self, "错误", "工作路径未设置或不完整。请返回步骤1。")
            return
            
        if not self.character_library:
            if not QMessageBox.question(self, "确认", 
                                      "角色库当前为空，确定要继续吗？\n"
                                      "（将生成空的 zh.txt 文件并开始处理视频）",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                return
            self.set_status("角色库为空，继续处理...")
        else:
            self.set_status("正在保存角色库...")
            
        try:
            os.makedirs(self.character_image_dir, exist_ok=True)
            copied_files_count = 0
            missing_source_files = []
            written_to_zh_txt = []
            
            # 写入zh.txt并复制图片
            with open(self.zh_txt_path, 'w', encoding='utf-8') as f:
                processed_targets = set()  # 防止重复写入zh.txt
                for source_path, target_path, char_name in self.character_library:
                    # 从target_path推导zh.txt中的图片名(无扩展名)
                    target_filename = os.path.basename(target_path)
                    image_name_no_ext, _ = os.path.splitext(target_filename)
                    
                    # 防止因列表重复导致zh.txt重复写入同一角色
                    unique_key = (image_name_no_ext, char_name)
                    if unique_key in processed_targets:
                        continue
                    processed_targets.add(unique_key)
                    
                    # 写入zh.txt
                    f.write(f"{image_name_no_ext},{char_name}\n")
                    written_to_zh_txt.append(f"{image_name_no_ext},{char_name}")
                    
                    # 处理图片复制或验证
                    if source_path and os.path.exists(source_path):
                        # 如果源路径和目标路径不同(通常是手动添加的情况)
                        if source_path != target_path:
                            try:
                                print(f"需要复制: {source_path} -> {target_path}")
                                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                                shutil.copy2(source_path, target_path)  # copy2保留元数据
                                print(f"  > 已复制。")
                                copied_files_count += 1
                            except shutil.SameFileError:
                                print(f"  > 信息：源文件和目标文件相同。")
                            except Exception as copy_err:
                                QMessageBox.warning(self, "复制错误", 
                                                  f"无法复制图片 '{os.path.basename(source_path)}' 到 '{self.character_image_dir}':\n"
                                                  f"{copy_err}\n\nzh.txt 已记录此角色，但处理可能因缺少图片失败。")
                    elif not os.path.exists(target_path):
                        # 源路径无效且目标路径也不存在
                        missing_source_files.append(target_filename)
                        print(f"警告: 角色 '{char_name}' 的图片 '{target_filename}' 在源路径和目标路径均未找到。")
            
            status_msg = f"角色库信息 ({len(written_to_zh_txt)} 条) 已写入 {os.path.basename(self.zh_txt_path)}."
            if copied_files_count > 0:
                status_msg += f" {copied_files_count} 张新图片已复制到 photos 文件夹。"
            if missing_source_files:
                QMessageBox.warning(self, "缺少图片", 
                                   f"以下图片文件在 'photos' 目录中缺失，且无法从源路径复制或找到：\n" + 
                                   "\n".join(missing_source_files) + 
                                   "\n\n处理可能会失败或不准确。")
            print(status_msg)
            
            # 启动后台处理
            self.set_status("保存完毕，正在启动音频描述生成 (可能需要较长时间)...")
            # 禁用所有Step 2的交互按钮
            self.disable_step2_controls()
            
            # 创建并启动工作线程
            def processing_task():
                try:
                    print(f"Starting AD processing for video: {self.video_name_no_ext}")
                    start_time = time.time()
                    AD.AD(self.base_path, self.video_name_no_ext, self.original_video_path)
                    end_time = time.time()
                    print(f"AD processing finished in {end_time - start_time:.2f} seconds.")
                    
                    if not os.path.exists(self.intermediate_csv_path):
                        raise FileNotFoundError(f"AD process completed but did not generate the expected CSV file: {self.intermediate_csv_path}")
                    return True
                except Exception as e:
                    print(f"Error during AD processing: {e}")
                    raise
            
            self.processing_thread = WorkerThread(processing_task)
            self.processing_thread.finished.connect(self.on_initial_processing_complete)
            self.processing_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "处理错误", f"保存角色库或启动处理时出错: {e}")
            self.set_status(f"错误: {e}")
            self.enable_step2_controls()  # 出错时恢复按钮
    
    def disable_step2_controls(self):
        """禁用Step 2的所有交互控件"""
        self.manual_radio.setEnabled(False)
        self.scraper_radio.setEnabled(False)
        
        # 手动区
        self.char_img_edit.setEnabled(False)
        for child in self.step2_stack.widget(0).findChildren(QPushButton):
            child.setEnabled(False)
        self.char_name_edit.setEnabled(False)
        
        # 爬虫区
        self.movie_title_edit.setEnabled(False)
        for child in self.step2_stack.widget(1).findChildren(QPushButton):
            child.setEnabled(False)
        self.scraper_results_list.setEnabled(False)
        
        # 列表和提交区
        self.char_listbox.setEnabled(False)
        self.remove_char_button.setEnabled(False)
        self.submit_library_button.setEnabled(False)
    
    def enable_step2_controls(self):
        """恢复Step 2的交互控件状态"""
        self.manual_radio.setEnabled(True)
        self.scraper_radio.setEnabled(True)
        
        # 手动区
        self.char_img_edit.setEnabled(True)
        for child in self.step2_stack.widget(0).findChildren(QPushButton):
            child.setEnabled(True)
        self.char_name_edit.setEnabled(True)
        
        # 爬虫区
        self.movie_title_edit.setEnabled(True)
        for child in self.step2_stack.widget(1).findChildren(QPushButton):
            if child != self.download_button:  # 下载按钮状态取决于是否有结果
                child.setEnabled(True)
        self.scraper_results_list.setEnabled(True)
        if self.scraper_results_list.count() > 0:
            self.download_button.setEnabled(True)
        
        # 列表和提交区
        self.char_listbox.setEnabled(True)
        self.remove_char_button.setEnabled(True)
        self.submit_library_button.setEnabled(True)
    
    def on_initial_processing_complete(self, success, error_message, _):
        """初始处理完成后的回调"""
        # 恢复Step 2按钮状态
        self.enable_step2_controls()
        
        if not success:
            err_msg = f"音频描述生成失败: {error_message}"
            QMessageBox.critical(self, "处理失败", err_msg)
            self.set_status(f"错误: {error_message}")
            return
        
        self.set_status(f"音频描述生成完成! CSV: {os.path.basename(self.intermediate_csv_path)}")
        self.load_and_display_csv(self.intermediate_csv_path)
        self.is_csv_edited = False
        self.goto_step3()
    
    # --- 步骤 3 功能 ---
    def load_and_display_csv(self, csv_path):
        """加载并显示CSV数据"""
        self.csv_data = []
        self.csv_headers = []
        
        # 清空现有树内容和列
        self.tree.clear()
        self.tree.setHeaderLabels([])
        
        if not csv_path or not os.path.exists(csv_path):
            QMessageBox.critical(self, "错误", f"找不到CSV文件: {csv_path or '路径未定义'}")
            self.set_status("加载CSV失败：文件不存在")
            return
        
        try:
            with open(csv_path, 'r', newline='', encoding='utf-8-sig') as f:
                reader = csv.reader(f)
                try:
                    self.csv_headers = next(reader)
                except StopIteration:
                    QMessageBox.information(self, "空文件", f"CSV文件 '{os.path.basename(csv_path)}' 是空的或只有一行（可能只有表头）。")
                    if self.csv_headers:
                        self.tree.setHeaderLabels(self.csv_headers)
                    return
                
                # 读取数据行
                self.csv_data = list(reader)
                if not self.csv_data:
                    QMessageBox.information(self, "无数据", f"CSV文件 '{os.path.basename(csv_path)}' 包含表头但没有数据行。")
        
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法加载CSV文件 '{os.path.basename(csv_path)}': {e}")
            self.set_status(f"加载CSV失败: {e}")
            return
        
        # 设置树形视图的列和标题
        if self.csv_headers:
            self.tree.setHeaderLabels(self.csv_headers)
            for i, col in enumerate(self.csv_headers):
                # 设置列宽
                col_width = 150
                if "script" in col.lower() or "text" in col.lower():
                    col_width = 300  # 文本列更宽
                elif "time" in col.lower():
                    col_width = 100
                self.tree.setColumnWidth(i, col_width)
        
        # 填充数据
        for i, row in enumerate(self.csv_data):
            # 确保行有相同数量的元素(必要时填充)
            full_row = row[:]
            expected_len = len(self.csv_headers) if self.csv_headers else 0
            if len(full_row) < expected_len:
                full_row.extend([''] * (expected_len - len(full_row)))
            elif len(full_row) > expected_len:
                full_row = full_row[:expected_len]  # 截断多余列
            
            item = QTreeWidgetItem(self.tree, full_row)
            item.setData(0, Qt.ItemDataRole.UserRole, i)  # 存储原始行索引
        
        self.is_csv_edited = False
        self.edit_button.setEnabled(True)
        self.set_status(f"已加载CSV: {os.path.basename(csv_path)}. 共 {len(self.csv_data)} 行数据。")
    
    def edit_selected_row(self):
        """编辑选中的行"""
        selected_items = self.tree.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "提示", "请先在表格中选择要编辑的行。")
            return
        if len(selected_items) > 1:
            QMessageBox.information(self, "提示", "一次只能编辑一行。")
            return
        
        item = selected_items[0]
        row_index = item.data(0, Qt.ItemDataRole.UserRole)
        
        try:
            if not (0 <= row_index < len(self.csv_data)):
                raise IndexError("选中的行索引与内部数据不匹配")
            
            if not self.csv_headers:
                raise ValueError("没有表头信息，无法编辑")
            
            current_values = self.csv_data[row_index][:]  # 获取副本
            if len(current_values) < len(self.csv_headers):
                current_values.extend([''] * (len(self.csv_headers) - len(current_values)))
            
            self.open_edit_dialog(row_index, current_values[:len(self.csv_headers)], item)
        
        except (ValueError, IndexError) as e:
            QMessageBox.critical(self, "编辑错误", f"无法准备编辑选中的行: {e}")
            print(f"Edit error: {e}")
    
    def open_edit_dialog(self, row_index, current_values, tree_item):
        """打开编辑对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"编辑第 {row_index + 1} 行")
        dialog.setMinimumSize(550, 450)
        dialog.resize(600, 500)
        
        layout = QVBoxLayout(dialog)
        
        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        
        # 编辑字段
        field_widgets = []
        
        for i, header in enumerate(self.csv_headers):
            field_group = QGroupBox(header)
            field_layout = QVBoxLayout(field_group)
            
            # 使用文本框或行编辑
            if "script" in header.lower() or "text" in header.lower() or len(str(current_values[i])) > 80:
                field = QTextEdit()
                field.setPlainText(current_values[i])
                field.setMinimumHeight(100)
            else:
                field = QLineEdit()
                field.setText(current_values[i])
            
            field_layout.addWidget(field)
            scroll_layout.addWidget(field_group)
            field_widgets.append((header, field))
        
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(dialog.reject)
        
        save_button = QPushButton("保存")
        save_button.setStyleSheet("""
            QPushButton {
                background-color: #8a56e8;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 15px;
            }
            QPushButton:hover {
                background-color: #7546d8;
            }
        """)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(save_button)
        layout.addLayout(button_layout)
        
        # 连接保存按钮
        def save_changes():
            new_values = []
            for _, widget in field_widgets:
                if isinstance(widget, QTextEdit):
                    value = widget.toPlainText()
                else:
                    value = widget.text()
                new_values.append(value)
            
            # 更新内部数据
            self.csv_data[row_index] = new_values
            
            # 更新树形视图项
            for i, value in enumerate(new_values):
                tree_item.setText(i, value)
            
            self.is_csv_edited = True
            self.set_status(f"第 {row_index + 1} 行已在内存中更新。点击保存并生成以应用到CSV。")
            dialog.accept()
        
        save_button.clicked.connect(save_changes)
        
        # 显示对话框
        dialog.exec()
    
    def goto_step3(self):
        """转到步骤3"""
        can_process = True
        if not self.intermediate_csv_path:
            self.set_status("错误: CSV文件路径未设置，无法编辑或提交。")
            can_process = False
        elif not os.path.exists(self.intermediate_csv_path):
            self.set_status(f"警告: CSV文件 {os.path.basename(self.intermediate_csv_path)} 不存在。")
            can_process = False
            self.load_and_display_csv(self.intermediate_csv_path)
        
        # 启用/禁用按钮
        self.edit_button.setEnabled(can_process)
        self.submit_csv_button.setEnabled(can_process)
        
        if can_process:
            self.set_status("步骤 3: 查看或修改CSV数据。选择行并点击编辑。")
        
        self.content_stack.setCurrentIndex(2)  # 显示步骤3
        self.update_step_indicator(2)
    
    def submit_csv_for_final_processing(self):
        """提交CSV进行最终处理"""
        if not self.intermediate_csv_path or not self.final_video_path or not self.original_video_path:
            QMessageBox.critical(self, "路径错误", "需要 CSV路径、最终视频输出路径和原始视频路径才能继续。请返回步骤1检查。")
            return
        
        if not os.path.exists(self.intermediate_csv_path):
            QMessageBox.critical(self, "文件丢失", f"CSV文件 '{os.path.basename(self.intermediate_csv_path)}' 已不存在，无法提交。请返回步骤2重新生成。")
            return
        
        confirm_action = "保存修改并" if self.is_csv_edited else "使用当前CSV"
        if not QMessageBox.question(self, "确认生成", 
                                  f"确定要{confirm_action}生成最终的无障碍视频吗？\n"
                                  f"（{('修改将覆盖原CSV文件' if self.is_csv_edited else '将使用当前CSV内容')}）",
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.set_status("最终视频生成已取消。")
            return
        
        try:
            # 保存当前数据到CSV
            self.set_status("正在保存CSV文件...")
            QApplication.processEvents()
            with open(self.intermediate_csv_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                if self.csv_headers:
                    writer.writerow(self.csv_headers)
                writer.writerows(self.csv_data)
            print(f"CSV数据已{'更新并' if self.is_csv_edited else ''}保存至: {self.intermediate_csv_path}")
            self.is_csv_edited = False
            
            # 启动最终处理线程
            self.set_status("CSV保存完成，正在启动最终视频生成 (这可能需要很长时间)...")
            self.submit_csv_button.setEnabled(False)
            self.edit_button.setEnabled(False)
            
            # 创建并启动工作线程
            def final_processing_task():
                try:
                    print(f"Starting final video processing (TTS and merge) using CSV: {os.path.basename(self.intermediate_csv_path)}")
                    start_time = time.time()
                    tts_with_emo.T2S(self.intermediate_csv_path, self.final_video_path, self.original_video_path)
                    end_time = time.time()
                    print(f"Final video processing finished in {end_time - start_time:.2f} seconds.")
                    
                    if not os.path.exists(self.final_video_path):
                        raise FileNotFoundError(f"tts_with_emo process completed but did not generate the expected video file: {self.final_video_path}")
                    return True
                except Exception as e:
                    print(f"Error during final processing: {e}")
                    raise
            
            self.final_processing_thread = WorkerThread(final_processing_task)
            self.final_processing_thread.finished.connect(self.on_final_processing_complete)
            self.final_processing_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "提交错误", f"保存CSV或启动最终处理时出错: {e}")
            self.set_status(f"错误: {e}")
            self.submit_csv_button.setEnabled(True)
            self.edit_button.setEnabled(True)
    
    def on_final_processing_complete(self, success, error_message, _):
        """最终处理完成后的回调"""
        # 恢复按钮状态
        self.submit_csv_button.setEnabled(True)
        self.edit_button.setEnabled(True)
        
        if not success:
            err_msg = f"最终视频生成失败: {error_message}"
            QMessageBox.critical(self, "生成失败", err_msg)
            self.set_status(f"错误: {error_message}")
            return
        
        abs_video_path = os.path.abspath(self.final_video_path)
        self.final_video_path_edit.setText(abs_video_path)
        self.set_status("最终视频生成完成！")
        QMessageBox.information(self, "完成", f"无障碍视频已生成:\n{abs_video_path}")
        self.goto_step4()
    
    # --- 步骤 4 功能 ---
    def goto_step4(self):
        """转到步骤4"""
        self.content_stack.setCurrentIndex(3)  # 显示步骤4
        self.update_step_indicator(3)
        final_path = self.final_video_path_edit.text()
        if final_path:
            self.set_status(f"步骤 4: 处理完成。最终视频: {final_path}")
        else:
            self.set_status("步骤 4: 查看最终视频 (路径未找到?)")
    
    def play_video(self):
        """播放生成的视频"""
        video_path = self.final_video_path_edit.text()
        if not video_path:
            QMessageBox.warning(self, "无文件", "最终视频文件路径未设置。")
            return
        
        abs_video_path = os.path.abspath(video_path)
        if not os.path.exists(abs_video_path):
            QMessageBox.critical(self, "错误", f"找不到视频文件:\n{abs_video_path}")
            return
        
        try:
            self.set_status(f"尝试使用系统播放器打开: {os.path.basename(abs_video_path)}...")
            system = platform.system()
            if system == "Windows":
                os.startfile(abs_video_path)
            elif system == "Darwin":  # macOS
                subprocess.run(['open', abs_video_path], check=True)
            else:  # Linux and other Unix-like
                subprocess.run(['xdg-open', abs_video_path], check=True)
            
            # 延迟更新状态消息
            QApplication.processEvents()
            self.set_status(f"已尝试播放 {os.path.basename(abs_video_path)}")
            
        except FileNotFoundError as fnf_err:
            cmd = 'startfile' if system == "Windows" else ('open' if system == "Darwin" else 'xdg-open')
            QMessageBox.critical(self, "播放错误", f"无法找到用于打开视频的命令 ('{cmd}' 或系统关联)。\n请确保已安装视频播放器。")
            print(f"Error playing video (command not found?): {fnf_err}")
            self.set_status(f"播放失败：找不到命令 '{cmd}'")
        except Exception as e:
            QMessageBox.critical(self, "播放错误", f"无法播放视频:\n{e}")
            print(f"Error playing video: {e}")
            self.set_status(f"播放视频时出错: {e}")
    
    def goto_step3_from_step4(self):
        """从步骤4返回步骤3"""
        if self.intermediate_csv_path and os.path.exists(self.intermediate_csv_path):
            self.load_and_display_csv(self.intermediate_csv_path)
        else:
            self.edit_button.setEnabled(False)
            self.submit_csv_button.setEnabled(False)
        
        self.goto_step3()
    
    def restart_process(self):
        """重启整个处理过程"""
        if not QMessageBox.question(self, "确认重启", 
                                  "确定要处理一个全新的视频吗？\n\n"
                                  "当前所有进度（视频选择、角色库、CSV修改、处理状态）都将被清除。",
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            return
        
        # 重置状态变量
        self.video_path = ""
        self.video_path_edit.setText("")
        self.character_library = []
        self.csv_data = []
        self.csv_headers = []
        self.is_csv_edited = False
        self.video_name_no_ext = None
        
        # 重置Step 2特有状态
        self.step2_mode = "manual"
        self.manual_radio.setChecked(True)
        self.char_img_path = ""
        self.char_img_edit.setText("")
        self.char_name_edit.setText("")
        self.movie_title_edit.setText("")
        self.scraper_results = []
        
        # 重置动态路径
        self.reset_paths()
        
        # 清空UI元素
        self.char_listbox.clear()
        self.scraper_results_list.clear()
        self.tree.clear()
        
        # 重置按钮状态
        self.step1_next_button.setEnabled(False)
        self.enable_step2_controls()
        self.edit_button.setEnabled(False)
        self.submit_csv_button.setEnabled(False)
        
        # 导航到步骤1
        self.toggle_step2_mode()
        self.content_stack.setCurrentIndex(0)
        self.update_step_indicator(0)
        self.set_status("已重置，请重新选择视频文件")


def main():
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyle("Fusion")
    
    # 创建并显示主窗口
    window = VideoProcessorApp()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
