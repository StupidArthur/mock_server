"""
OPCUA Server工具
根据CSV数据文件构建OPCUA Server，按时间顺序轮询数据值
"""
import sys
import os
import csv
import ast
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# 添加项目根目录到Python路径
SCRIPT_DIR = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(SCRIPT_DIR))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QGroupBox, QFileDialog,
    QMessageBox, QProgressBar, QTextEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont

# asyncua相关导入
from asyncua import Server, ua


class OPCUAServerThread(QThread):
    """OPCUA Server运行线程"""
    
    # 信号：进度更新
    progress_updated = pyqtSignal(float, int, str)  # (进度百分比, 当前索引, 当前时间)
    # 信号：状态更新
    status_updated = pyqtSignal(str)  # 状态消息
    # 信号：完成
    finished = pyqtSignal()
    # 信号：错误
    error_occurred = pyqtSignal(str)  # 错误消息
    
    def __init__(self, data_records: List[Dict[str, Any]], port: int):
        """
        初始化OPCUA Server线程
        
        Args:
            data_records: 数据记录列表
            port: OPCUA Server端口
        """
        super().__init__()
        self.data_records = data_records
        self.port = port
        self._running = False
        self._server = None
        self._nodes = {}  # 存储节点：参数名 -> 节点对象
        self._loop = None
        self._current_index = 0
        
    def stop(self):
        """停止服务器"""
        self._running = False
    
    def run(self):
        """运行OPCUA Server和数据轮询"""
        try:
            # 创建新的事件循环
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            
            # 运行异步任务
            self._loop.run_until_complete(self._run_server())
            
        except Exception as e:
            self.error_occurred.emit(f"服务器运行错误: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            if self._loop:
                self._loop.close()
    
    async def _run_server(self):
        """运行OPCUA Server"""
        try:
            # 初始化服务器
            await self._init_server()
            
            # 创建节点
            await self._create_nodes()
            
            # 启动服务器
            self._running = True
            self.status_updated.emit(f"OPCUA Server已启动，端口: {self.port}")
            
            # 启动数据轮询任务
            asyncio.create_task(self._poll_data())
            
            # 运行服务器（阻塞）
            async with self._server:
                while self._running:
                    await asyncio.sleep(0.1)
            
        except Exception as e:
            self.error_occurred.emit(f"服务器初始化错误: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            if self._server:
                try:
                    await self._server.stop()
                except:
                    pass
            self.finished.emit()
    
    async def _init_server(self):
        """初始化OPCUA Server"""
        self.status_updated.emit("正在初始化OPCUA Server...")
        
        # 创建Server
        self._server = Server()
        await self._server.init()
        
        # 设置安全策略
        try:
            self._server.set_security_policy([
                ua.SecurityPolicyType.NoSecurity
            ])
        except Exception as e:
            self.status_updated.emit(f"安全策略设置警告: {e}")
        
        # 设置端点
        self._server.set_endpoint(f"opc.tcp://0.0.0.0:{self.port}")
        
        # 设置服务器名称
        self._server.set_server_name("CSV Data OPCUA Server")
        
        self.status_updated.emit("OPCUA Server初始化完成")
    
    async def _create_nodes(self):
        """创建OPCUA节点"""
        if not self.data_records:
            return
        
        self.status_updated.emit("正在创建OPCUA节点...")
        
        # 获取所有参数名（除了sim_time）
        param_names = set()
        for record in self.data_records:
            param_names.update(record.keys())
        param_names.discard('sim_time')
        param_names = sorted(param_names)
        
        # 获取Objects节点
        objects = self._server.get_objects_node()
        
        # 创建PLC对象（namespace=1）
        namespace_idx = 1
        plc_obj = await objects.add_object(
            namespace_idx,
            "PLC",
            ua.ObjectIds.BaseObjectType
        )
        
        # 为每个参数创建变量节点
        for param_name in param_names:
            try:
                # 获取第一个记录的值作为初始值
                initial_value = self.data_records[0].get(param_name, 0.0)
                
                # 尝试转换为数值
                if isinstance(initial_value, str):
                    try:
                        # 尝试解析字符串（可能是字典或列表）
                        parsed = ast.literal_eval(initial_value)
                        if isinstance(parsed, dict):
                            # 如果是字典，取第一个值
                            initial_value = list(parsed.values())[0] if parsed else 0.0
                        elif isinstance(parsed, list):
                            # 如果是列表，取第一个值
                            initial_value = parsed[0] if parsed else 0.0
                        else:
                            initial_value = float(parsed) if isinstance(parsed, (int, float)) else 0.0
                    except:
                        try:
                            initial_value = float(initial_value)
                        except:
                            initial_value = 0.0
                
                # 确保是数值类型
                if not isinstance(initial_value, (int, float)):
                    initial_value = 0.0
                
                # 创建变量节点（使用string类型的NodeId，值为位号名）
                var_node = await plc_obj.add_variable(
                    namespace_idx,
                    param_name,  # NodeId使用string类型，值为位号名
                    initial_value,
                    varianttype=ua.VariantType.Double
                )
                
                # 设置节点属性
                await var_node.set_writable(False)  # 只读
                
                # 存储节点
                self._nodes[param_name] = var_node
                
            except Exception as e:
                self.status_updated.emit(f"创建节点 {param_name} 失败: {str(e)}")
        
        self.status_updated.emit(f"已创建 {len(self._nodes)} 个节点")
    
    async def _poll_data(self):
        """按时间顺序轮询数据"""
        if not self.data_records:
            return
        
        # 计算时间间隔（从数据中获取）
        time_intervals = []
        for i in range(1, len(self.data_records)):
            prev_time = self.data_records[i-1]['sim_time']
            curr_time = self.data_records[i]['sim_time']
            interval = curr_time - prev_time
            time_intervals.append(interval)
        
        # 如果没有时间间隔，使用默认值0.5秒
        if not time_intervals:
            default_interval = 0.5
        else:
            # 使用第一个时间间隔作为默认值
            default_interval = time_intervals[0] if time_intervals else 0.5
        
        self.status_updated.emit(f"开始数据轮询，时间间隔: {default_interval}秒")
        
        # 从第一个记录开始
        self._current_index = 0
        
        while self._running and self._current_index < len(self.data_records):
            record = self.data_records[self._current_index]
            
            # 更新所有节点的值
            for param_name, node in self._nodes.items():
                try:
                    value = record.get(param_name)
                    
                    # 处理字符串值（可能是字典或列表）
                    if isinstance(value, str):
                        try:
                            parsed = ast.literal_eval(value)
                            if isinstance(parsed, dict):
                                # 如果是字典，取第一个值
                                value = list(parsed.values())[0] if parsed else 0.0
                            elif isinstance(parsed, list):
                                # 如果是列表，取第一个值
                                value = parsed[0] if parsed else 0.0
                            else:
                                value = float(parsed) if isinstance(parsed, (int, float)) else 0.0
                        except:
                            try:
                                value = float(value)
                            except:
                                value = 0.0
                    
                    # 确保是数值类型
                    if not isinstance(value, (int, float)):
                        value = 0.0
                    
                    # 更新节点值
                    await node.write_value(value)
                    
                except Exception as e:
                    self.status_updated.emit(f"更新节点 {param_name} 失败: {str(e)}")
            
            # 更新进度
            progress = (self._current_index + 1) / len(self.data_records) * 100
            sim_time = record.get('sim_time', 0)
            self.progress_updated.emit(progress, self._current_index + 1, f"{sim_time:.1f}s")
            
            # 移动到下一个记录
            self._current_index += 1
            
            # 如果还有下一个记录，等待相应的时间间隔
            if self._current_index < len(self.data_records):
                # 计算到下一个记录的时间间隔
                if self._current_index < len(time_intervals):
                    interval = time_intervals[self._current_index - 1]
                else:
                    interval = default_interval
                
                # 等待时间间隔
                await asyncio.sleep(interval)
            else:
                # 数据轮询完成
                self.status_updated.emit("数据轮询完成")
                break
        
        # 停止服务器
        self._running = False


class OPCUAServerWindow(QMainWindow):
    """OPCUA Server工具主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OPCUA Server工具 - CSV数据轮询")
        self.setGeometry(100, 100, 800, 600)
        
        # 数据存储
        self.data_records: List[Dict[str, Any]] = []
        self.server_thread: Optional[OPCUAServerThread] = None
        
        # 创建主界面
        self._create_ui()
    
    def _create_ui(self):
        """创建用户界面"""
        # 主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # 主布局
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        
        # 文件加载区域
        file_group = QGroupBox("数据文件")
        file_layout = QHBoxLayout()
        
        self.file_path_label = QLabel("未选择文件")
        self.file_path_label.setStyleSheet("border: 1px solid gray; padding: 5px;")
        file_layout.addWidget(self.file_path_label, stretch=1)
        
        self.load_button = QPushButton("加载数据文件")
        self.load_button.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 8px;")
        self.load_button.clicked.connect(self.load_data_file)
        file_layout.addWidget(self.load_button)
        
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)
        
        # 服务器配置区域
        server_group = QGroupBox("OPCUA服务器配置")
        server_layout = QGridLayout()
        
        server_layout.addWidget(QLabel("端口:"), 0, 0)
        self.port_input = QLineEdit()
        self.port_input.setText("18951")
        server_layout.addWidget(self.port_input, 0, 1)
        
        server_group.setLayout(server_layout)
        main_layout.addWidget(server_group)
        
        # 控制按钮区域
        control_layout = QHBoxLayout()
        
        self.start_button = QPushButton("开始")
        self.start_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
        self.start_button.clicked.connect(self.start_server)
        self.start_button.setEnabled(False)
        control_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton("停止")
        self.stop_button.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; padding: 8px;")
        self.stop_button.clicked.connect(self.stop_server)
        self.stop_button.setEnabled(False)
        control_layout.addWidget(self.stop_button)
        
        control_layout.addStretch()
        main_layout.addLayout(control_layout)
        
        # 进度显示区域
        progress_group = QGroupBox("数据轮询进度")
        progress_layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel("等待开始...")
        progress_layout.addWidget(self.progress_label)
        
        progress_group.setLayout(progress_layout)
        main_layout.addWidget(progress_group)
        
        # 状态显示区域
        status_group = QGroupBox("状态信息")
        status_layout = QVBoxLayout()
        
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(150)
        status_layout.addWidget(self.status_text)
        
        status_group.setLayout(status_layout)
        main_layout.addWidget(status_group)
        
        # 添加弹性空间
        main_layout.addStretch()
    
    def load_data_file(self):
        """加载CSV数据文件"""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择CSV数据文件",
            "",
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if not filename:
            return
        
        try:
            # 读取CSV文件
            self.data_records = []
            with open(filename, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    record = {}
                    for key, value in row.items():
                        if key == 'sim_time':
                            record[key] = float(value)
                        else:
                            # 尝试转换为数值，如果失败则保持字符串
                            try:
                                # 先尝试直接转换为float
                                record[key] = float(value)
                            except ValueError:
                                # 如果失败，保持字符串（可能是字典或列表的字符串表示）
                                record[key] = value
                    self.data_records.append(record)
            
            # 更新UI
            self.file_path_label.setText(filename)
            self.status_text.append(f"已加载数据文件: {filename}")
            self.status_text.append(f"数据记录数: {len(self.data_records)}")
            
            # 显示参数列表
            if self.data_records:
                param_names = [k for k in self.data_records[0].keys() if k != 'sim_time']
                self.status_text.append(f"参数数量: {len(param_names)}")
                self.status_text.append(f"参数列表: {', '.join(param_names[:10])}{'...' if len(param_names) > 10 else ''}")
            
            # 启用开始按钮
            self.start_button.setEnabled(True)
            
            QMessageBox.information(self, "成功", f"数据文件加载成功！\n记录数: {len(self.data_records)}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载数据文件失败: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def start_server(self):
        """启动OPCUA Server"""
        if not self.data_records:
            QMessageBox.warning(self, "警告", "请先加载数据文件！")
            return
        
        try:
            port = int(self.port_input.text() or "18951")
        except ValueError:
            QMessageBox.warning(self, "警告", "端口号必须是数字！")
            return
        
        # 禁用开始按钮，启用停止按钮
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        
        # 重置进度
        self.progress_bar.setValue(0)
        self.progress_label.setText("正在启动服务器...")
        
        # 创建并启动服务器线程
        self.server_thread = OPCUAServerThread(
            data_records=self.data_records,
            port=port
        )
        self.server_thread.progress_updated.connect(self._on_progress_updated)
        self.server_thread.status_updated.connect(self._on_status_updated)
        self.server_thread.finished.connect(self._on_server_finished)
        self.server_thread.error_occurred.connect(self._on_error_occurred)
        self.server_thread.start()
        
        self.status_text.append(f"正在启动OPCUA Server，端口: {port}")
    
    def stop_server(self):
        """停止OPCUA Server"""
        if self.server_thread:
            self.server_thread.stop()
            self.status_text.append("正在停止服务器...")
    
    def _on_progress_updated(self, progress: float, current_index: int, sim_time: str):
        """进度更新回调"""
        self.progress_bar.setValue(int(progress))
        self.progress_label.setText(f"进度: {current_index}/{len(self.data_records)} ({progress:.1f}%) - 模拟时间: {sim_time}")
    
    def _on_status_updated(self, message: str):
        """状态更新回调"""
        self.status_text.append(message)
        # 自动滚动到底部
        self.status_text.verticalScrollBar().setValue(
            self.status_text.verticalScrollBar().maximum()
        )
    
    def _on_server_finished(self):
        """服务器完成回调"""
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_text.append("服务器已停止")
    
    def _on_error_occurred(self, error_message: str):
        """错误回调"""
        QMessageBox.critical(self, "错误", error_message)
        self._on_server_finished()


def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    window = OPCUAServerWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

