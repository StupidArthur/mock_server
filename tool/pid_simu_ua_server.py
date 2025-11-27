"""
统一工具：PID模拟 + OPCUA Server
整合PID回路模拟和OPCUA Server功能，可以在模拟完成后直接启动OPCUA Server
"""
import sys
import os
import ast
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional

# 添加项目根目录到Python路径
SCRIPT_DIR = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(SCRIPT_DIR))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QGroupBox,
    QMessageBox, QProgressBar, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

# matplotlib相关导入
import matplotlib
matplotlib.use('Qt5Agg')  # 使用Qt5后端
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

# asyncua相关导入
from asyncua import Server, ua

# 导入项目模块
from plc.clock import Clock
from module.cylindrical_tank import CylindricalTank
from module.valve import Valve
from algorithm.pid import PID


class SimulationThread(QThread):
    """模拟运行线程"""
    
    # 信号：进度更新
    progress_updated = pyqtSignal(float, int)  # (进度百分比, 记录数)
    # 信号：数据更新
    data_updated = pyqtSignal(dict)  # 单条数据记录
    # 信号：完成
    finished = pyqtSignal(list)  # 所有数据记录
    
    def __init__(self, tank_params: Dict[str, Any], valve_params: Dict[str, Any],
                 pid_params: Dict[str, Any], duration: float, sv_values: List[float],
                 cycle_time: float = 0.5):
        """
        初始化模拟线程
        
        Args:
            tank_params: 水箱参数
            valve_params: 阀门参数
            pid_params: PID参数
            duration: 模拟时长（秒）
            sv_values: SV设定值列表，会在模拟时长内均匀分布
            cycle_time: 运行周期（秒）
        """
        super().__init__()
        self.tank_params = tank_params
        self.valve_params = valve_params
        self.pid_params = pid_params
        self.duration = duration
        self.sv_values = sv_values
        self.cycle_time = cycle_time
        self._running = True
        
    def stop(self):
        """停止模拟"""
        self._running = False
    
    def run(self):
        """运行模拟"""
        try:
            # 初始化模型和算法
            tank = CylindricalTank(**self.tank_params)
            valve = Valve(**self.valve_params)
            pid = PID(**self.pid_params)
            
            # 初始化时钟
            clock = Clock(cycle_time=self.cycle_time)
            clock.start()
            
            # 数据记录
            data_records = []
            
            # 计算SV切换时间点
            # 将模拟时长均匀分成len(sv_values)段，每段使用一个SV值
            if len(self.sv_values) > 1:
                segment_duration = self.duration / len(self.sv_values)
                sv_switch_times = [i * segment_duration for i in range(len(self.sv_values))]
            else:
                sv_switch_times = [0.0]
                self.sv_values = [self.sv_values[0]]
            
            # 初始化参数值
            tank_level = tank.level
            valve_opening = valve.current_opening
            pid_pv = tank_level
            
            # 设置初始SV值
            current_sv_index = 0
            pid.input['sv'] = self.sv_values[current_sv_index]
            pid_sv = pid.input['sv']
            pid_mv = pid.output['mv']
            
            # 运行循环
            target_sim_time = self.duration
            
            while clock.current_time < target_sim_time and self._running:
                # 检查是否需要切换SV值
                if current_sv_index < len(self.sv_values) - 1:
                    next_switch_time = sv_switch_times[current_sv_index + 1]
                    if clock.current_time >= next_switch_time:
                        current_sv_index += 1
                        pid.input['sv'] = self.sv_values[current_sv_index]
                
                # 更新PID的PV（从水箱获取）
                pid.input['pv'] = tank_level
                
                # 执行PID算法
                pid.execute(input_params={'pv': tank_level, 'sv': pid.input['sv']})
                pid_mv = pid.output['mv']
                
                # PID输出 -> 阀门目标开度（通过属性设置）
                valve.target_opening = pid_mv
                valve_opening = valve.execute(step=self.cycle_time)
                
                # 阀门开度 -> 水箱输入（通过属性设置）
                tank.valve_opening = valve_opening
                tank_level = tank.execute(step=self.cycle_time)
                
                # 步进时钟
                clock.step()
                
                # 记录数据
                record = {
                    'sim_time': clock.current_time,
                    'pid.sv': pid.input['sv'],
                    'pid.pv': pid.input['pv'],
                    'pid.mv': pid.output['mv'],
                    'tank.level': tank_level,
                    'valve.current_opening': valve_opening
                }
                data_records.append(record)
                
                # 发送数据更新信号（每10个周期发送一次，避免UI阻塞）
                if len(data_records) % 10 == 0:
                    self.data_updated.emit(record)
                    progress = (clock.current_time / target_sim_time) * 100
                    self.progress_updated.emit(progress, len(data_records))
            
            clock.stop()
            
            # 发送完成信号
            self.finished.emit(data_records)
            
        except Exception as e:
            print(f"Simulation error: {e}")
            import traceback
            traceback.print_exc()
            self.finished.emit([])


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
    
    def __init__(self, data_records: List[Dict[str, Any]], port: int, instance_name: str = "PLC"):
        """
        初始化OPCUA Server线程
        
        Args:
            data_records: 数据记录列表
            port: OPCUA Server端口
            instance_name: 实例名称，用于生成节点ID前缀，如"PID_TEST_1"
        """
        super().__init__()
        self.data_records = data_records
        self.port = port
        self.instance_name = instance_name
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
            
            # 启动数据轮询任务（循环播放）
            asyncio.create_task(self._poll_data_loop())
            
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
        self._server.set_server_name("PID Simulation OPCUA Server")
        
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
                
                # 创建变量节点（使用string类型的NodeId，值为实例名.参数名）
                # 例如：如果instance_name="PID_TEST_1"，param_name="pid.mv"
                # 则NodeId为"PID_TEST_1.pid.mv"
                node_id = f"{self.instance_name}.{param_name}"
                var_node = await plc_obj.add_variable(
                    namespace_idx,
                    node_id,  # NodeId使用string类型，值为实例名.参数名
                    initial_value,
                    varianttype=ua.VariantType.Double
                )
                
                # 设置节点属性
                await var_node.set_writable(False)  # 只读
                
                # 存储节点
                self._nodes[param_name] = var_node
                
            except Exception as e:
                self.status_updated.emit(f"创建节点 {param_name} 失败: {str(e)}")
        
        self.status_updated.emit(f"已创建 {len(self._nodes)} 个节点（实例名: {self.instance_name}）")
    
    async def _poll_data_loop(self):
        """循环轮询数据"""
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
        
        self.status_updated.emit(f"开始数据轮询（循环播放），时间间隔: {default_interval}秒")
        
        # 循环播放数据
        cycle_count = 0
        while self._running:
            cycle_count += 1
            self.status_updated.emit(f"开始第 {cycle_count} 轮循环播放")
            
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
                
                # 更新进度（相对于当前循环）
                progress = (self._current_index + 1) / len(self.data_records) * 100
                sim_time = record.get('sim_time', 0)
                self.progress_updated.emit(progress, self._current_index + 1, f"{sim_time:.1f}s (第{cycle_count}轮)")
                
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
                    # 当前循环完成，等待一小段时间后开始下一轮
                    self.status_updated.emit(f"第 {cycle_count} 轮循环播放完成，准备开始下一轮...")
                    await asyncio.sleep(0.5)


class UnifiedToolWindow(QMainWindow):
    """统一工具主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PID模拟与OPCUA Server工具")
        self.setGeometry(100, 100, 1600, 900)
        
        # 数据存储
        self.data_records: List[Dict[str, Any]] = []
        self.simulation_thread: Optional[SimulationThread] = None
        self.server_thread: Optional[OPCUAServerThread] = None
        
        # 创建主界面
        self._create_ui()
        
        # 设置默认值
        self._set_default_values()
    
    def _create_ui(self):
        """创建用户界面"""
        # 主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # 主布局（垂直布局）
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        
        # 上半部分：PID模拟区域（水平布局：左侧配置 + 右侧图表）
        sim_layout = QHBoxLayout()
        
        # 左侧：参数配置区域
        left_panel = self._create_simulation_left_panel()
        sim_layout.addWidget(left_panel, stretch=1)
        
        # 右侧：图表区域
        right_panel = self._create_simulation_right_panel()
        sim_layout.addWidget(right_panel, stretch=2)
        
        main_layout.addLayout(sim_layout)
        
        # 添加分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setLineWidth(2)
        main_layout.addWidget(separator)
        
        # 下半部分：OPCUA Server区域
        server_panel = self._create_server_panel()
        main_layout.addWidget(server_panel)
    
    def _create_simulation_left_panel(self) -> QWidget:
        """创建模拟左侧参数配置面板"""
        panel = QWidget()
        layout = QVBoxLayout()
        panel.setLayout(layout)
        
        # 水箱参数配置
        tank_group = QGroupBox("水箱参数")
        tank_layout = QGridLayout()
        
        self.tank_height = QLineEdit()
        self.tank_radius = QLineEdit()
        self.tank_inlet_area = QLineEdit()
        self.tank_inlet_velocity = QLineEdit()
        self.tank_outlet_area = QLineEdit()
        self.tank_initial_level = QLineEdit()
        
        tank_layout.addWidget(QLabel("高度 (m):"), 0, 0)
        tank_layout.addWidget(self.tank_height, 0, 1)
        tank_layout.addWidget(QLabel("半径 (m):"), 1, 0)
        tank_layout.addWidget(self.tank_radius, 1, 1)
        tank_layout.addWidget(QLabel("入水口面积 (m²):"), 2, 0)
        tank_layout.addWidget(self.tank_inlet_area, 2, 1)
        tank_layout.addWidget(QLabel("入水速度 (m/s):"), 3, 0)
        tank_layout.addWidget(self.tank_inlet_velocity, 3, 1)
        tank_layout.addWidget(QLabel("出水口面积 (m²):"), 4, 0)
        tank_layout.addWidget(self.tank_outlet_area, 4, 1)
        tank_layout.addWidget(QLabel("初始水位 (m):"), 5, 0)
        tank_layout.addWidget(self.tank_initial_level, 5, 1)
        
        tank_group.setLayout(tank_layout)
        layout.addWidget(tank_group)
        
        # 阀门参数配置
        valve_group = QGroupBox("阀门参数")
        valve_layout = QGridLayout()
        
        self.valve_min_opening = QLineEdit()
        self.valve_max_opening = QLineEdit()
        self.valve_full_travel_time = QLineEdit()
        
        valve_layout.addWidget(QLabel("最小开度 (%):"), 0, 0)
        valve_layout.addWidget(self.valve_min_opening, 0, 1)
        valve_layout.addWidget(QLabel("最大开度 (%):"), 1, 0)
        valve_layout.addWidget(self.valve_max_opening, 1, 1)
        valve_layout.addWidget(QLabel("满行程时间 (s):"), 2, 0)
        valve_layout.addWidget(self.valve_full_travel_time, 2, 1)
        
        valve_group.setLayout(valve_layout)
        layout.addWidget(valve_group)
        
        # PID参数配置
        pid_group = QGroupBox("PID参数")
        pid_layout = QGridLayout()
        
        self.pid_kp = QLineEdit()
        self.pid_ti = QLineEdit()
        self.pid_td = QLineEdit()
        self.pid_sv = QLineEdit()  # 改为逗号分隔的多个值
        self.pid_pv = QLineEdit()
        self.pid_mv = QLineEdit()
        self.pid_h = QLineEdit()
        self.pid_l = QLineEdit()
        
        pid_layout.addWidget(QLabel("比例系数 (Kp):"), 0, 0)
        pid_layout.addWidget(self.pid_kp, 0, 1)
        pid_layout.addWidget(QLabel("积分时间 (Ti):"), 1, 0)
        pid_layout.addWidget(self.pid_ti, 1, 1)
        pid_layout.addWidget(QLabel("微分时间 (Td):"), 2, 0)
        pid_layout.addWidget(self.pid_td, 2, 1)
        pid_layout.addWidget(QLabel("设定值 (SV，逗号分隔):"), 3, 0)
        pid_layout.addWidget(self.pid_sv, 3, 1)
        pid_layout.addWidget(QLabel("过程值 (PV):"), 4, 0)
        pid_layout.addWidget(self.pid_pv, 4, 1)
        pid_layout.addWidget(QLabel("输出值 (MV):"), 5, 0)
        pid_layout.addWidget(self.pid_mv, 5, 1)
        pid_layout.addWidget(QLabel("输出上限 (H):"), 6, 0)
        pid_layout.addWidget(self.pid_h, 6, 1)
        pid_layout.addWidget(QLabel("输出下限 (L):"), 7, 0)
        pid_layout.addWidget(self.pid_l, 7, 1)
        
        pid_group.setLayout(pid_layout)
        layout.addWidget(pid_group)
        
        # 模拟时长配置
        duration_group = QGroupBox("模拟设置")
        duration_layout = QVBoxLayout()
        
        duration_input_layout = QHBoxLayout()
        duration_input_layout.addWidget(QLabel("模拟时长 (秒):"))
        self.duration_input = QLineEdit()
        duration_input_layout.addWidget(self.duration_input)
        duration_layout.addLayout(duration_input_layout)
        
        duration_group.setLayout(duration_layout)
        layout.addWidget(duration_group)
        
        # 控制按钮
        self.start_sim_button = QPushButton("开始模拟")
        self.start_sim_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
        self.start_sim_button.clicked.connect(self.start_simulation)
        layout.addWidget(self.start_sim_button)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 添加弹性空间
        layout.addStretch()
        
        return panel
    
    def _create_simulation_right_panel(self) -> QWidget:
        """创建模拟右侧图表面板"""
        panel = QWidget()
        layout = QVBoxLayout()
        panel.setLayout(layout)
        
        # 图表标题
        title_label = QLabel("PID控制曲线")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # matplotlib图表
        self.figure = Figure(figsize=(10, 6))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        
        # 初始化图表
        self._init_chart()
        
        return panel
    
    def _create_server_panel(self) -> QWidget:
        """创建OPCUA Server面板"""
        panel = QWidget()
        layout = QVBoxLayout()
        panel.setLayout(layout)
        
        # 服务器配置区域
        server_group = QGroupBox("OPCUA服务器配置")
        server_layout = QHBoxLayout()
        
        server_layout.addWidget(QLabel("实例名:"))
        self.instance_name_input = QLineEdit()
        self.instance_name_input.setText("PID_TEST_1")
        self.instance_name_input.setMaximumWidth(150)
        server_layout.addWidget(self.instance_name_input)
        
        server_layout.addWidget(QLabel("端口:"))
        self.port_input = QLineEdit()
        self.port_input.setText("18951")
        self.port_input.setMaximumWidth(100)
        server_layout.addWidget(self.port_input)
        
        server_layout.addStretch()
        
        # 控制按钮
        self.start_server_button = QPushButton("启动服务器")
        self.start_server_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
        self.start_server_button.clicked.connect(self.start_server)
        self.start_server_button.setEnabled(False)
        server_layout.addWidget(self.start_server_button)
        
        self.stop_server_button = QPushButton("停止服务器")
        self.stop_server_button.setStyleSheet("background-color: #f44336; color: white; font-weight: bold; padding: 8px;")
        self.stop_server_button.clicked.connect(self.stop_server)
        self.stop_server_button.setEnabled(False)
        server_layout.addWidget(self.stop_server_button)
        
        server_group.setLayout(server_layout)
        layout.addWidget(server_group)
        
        # 进度显示区域
        progress_group = QGroupBox("数据轮询进度")
        progress_layout = QVBoxLayout()
        
        self.server_progress_bar = QProgressBar()
        self.server_progress_bar.setMinimum(0)
        self.server_progress_bar.setMaximum(100)
        progress_layout.addWidget(self.server_progress_bar)
        
        self.progress_label = QLabel("等待开始...")
        progress_layout.addWidget(self.progress_label)
        
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        return panel
    
    def _init_chart(self):
        """初始化图表"""
        self.figure.clear()
        ax1 = self.figure.add_subplot(111)
        
        # 创建第二个y轴（用于MV）
        ax2 = ax1.twinx()
        
        # 设置标签和颜色
        ax1.set_xlabel('模拟时间 (秒)', fontsize=12)
        ax1.set_ylabel('SV / PV', fontsize=12, color='blue')
        ax1.tick_params(axis='y', labelcolor='blue')
        
        ax2.set_ylabel('MV', fontsize=12, color='orange')
        ax2.tick_params(axis='y', labelcolor='orange')
        
        ax1.grid(True, alpha=0.3)
        ax1.set_title('PID控制曲线', fontsize=14, fontweight='bold')
        
        self.ax1 = ax1
        self.ax2 = ax2
        
        self.canvas.draw()
    
    def _set_default_values(self):
        """设置默认参数值"""
        # 水箱默认值
        self.tank_height.setText("2.0")
        self.tank_radius.setText("0.5")
        self.tank_inlet_area.setText("0.06")
        self.tank_inlet_velocity.setText("3.0")
        self.tank_outlet_area.setText("0.001")
        self.tank_initial_level.setText("0.0")
        
        # 阀门默认值
        self.valve_min_opening.setText("0.0")
        self.valve_max_opening.setText("100.0")
        self.valve_full_travel_time.setText("5.0")
        
        # PID默认值
        self.pid_kp.setText("12.0")
        self.pid_ti.setText("30.0")
        self.pid_td.setText("0.15")
        self.pid_sv.setText("1.5,0.5,0")  # 默认多个SV值
        self.pid_pv.setText("0.0")
        self.pid_mv.setText("0.0")
        self.pid_h.setText("100.0")
        self.pid_l.setText("0.0")
        
        # 模拟时长默认值
        self.duration_input.setText("900.0")
        
        # 实例名默认值
        self.instance_name_input.setText("PID_TEST_1")
    
    def _get_tank_params(self) -> Dict[str, Any]:
        """获取水箱参数"""
        return {
            'height': float(self.tank_height.text() or "2.0"),
            'radius': float(self.tank_radius.text() or "0.5"),
            'inlet_area': float(self.tank_inlet_area.text() or "0.06"),
            'inlet_velocity': float(self.tank_inlet_velocity.text() or "3.0"),
            'outlet_area': float(self.tank_outlet_area.text() or "0.001"),
            'initial_level': float(self.tank_initial_level.text() or "0.0")
        }
    
    def _get_valve_params(self) -> Dict[str, Any]:
        """获取阀门参数"""
        return {
            'min_opening': float(self.valve_min_opening.text() or "0.0"),
            'max_opening': float(self.valve_max_opening.text() or "100.0"),
            'full_travel_time': float(self.valve_full_travel_time.text() or "5.0")
        }
    
    def _get_pid_params(self) -> Dict[str, Any]:
        """获取PID参数"""
        return {
            'kp': float(self.pid_kp.text() or "12.0"),
            'ti': float(self.pid_ti.text() or "30.0"),
            'td': float(self.pid_td.text() or "0.15"),
            'sv': float(self.pid_sv.text().split(',')[0] if self.pid_sv.text() else "0.0"),  # 使用第一个值作为初始值
            'pv': float(self.pid_pv.text() or "0.0"),
            'mv': float(self.pid_mv.text() or "0.0"),
            'h': float(self.pid_h.text() or "100.0"),
            'l': float(self.pid_l.text() or "0.0")
        }
    
    def _get_sv_values(self) -> List[float]:
        """获取SV设定值列表（逗号分隔）"""
        sv_text = self.pid_sv.text().strip()
        if not sv_text:
            return [0.0]
        
        try:
            # 按逗号分割并转换为浮点数列表
            sv_values = [float(x.strip()) for x in sv_text.split(',') if x.strip()]
            return sv_values if sv_values else [0.0]
        except ValueError:
            QMessageBox.warning(self, "警告", "SV设定值格式错误，请使用逗号分隔的数字，如：0,1.5,0")
            return [0.0]
    
    def start_simulation(self):
        """开始模拟"""
        try:
            # 获取参数
            tank_params = self._get_tank_params()
            valve_params = self._get_valve_params()
            pid_params = self._get_pid_params()
            duration = float(self.duration_input.text() or "900.0")
            sv_values = self._get_sv_values()
            
            if not sv_values:
                QMessageBox.warning(self, "警告", "请至少输入一个SV设定值！")
                return
            
            # 清空之前的数据
            self.data_records = []
            
            # 重置图表
            self._init_chart()
            
            # 禁用开始按钮
            self.start_sim_button.setEnabled(False)
            self.start_sim_button.setText("模拟中...")
            
            # 显示进度条
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            
            # 创建并启动模拟线程
            self.simulation_thread = SimulationThread(
                tank_params=tank_params,
                valve_params=valve_params,
                pid_params=pid_params,
                duration=duration,
                sv_values=sv_values
            )
            self.simulation_thread.progress_updated.connect(self._on_progress_updated)
            self.simulation_thread.data_updated.connect(self._on_data_updated)
            self.simulation_thread.finished.connect(self._on_simulation_finished)
            self.simulation_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动模拟失败: {str(e)}")
            self.start_sim_button.setEnabled(True)
            self.start_sim_button.setText("开始模拟")
            self.progress_bar.setVisible(False)
    
    def _on_progress_updated(self, progress: float, record_count: int):
        """进度更新回调"""
        self.progress_bar.setValue(int(progress))
    
    def _on_data_updated(self, record: Dict[str, Any]):
        """数据更新回调（实时更新图表）"""
        self.data_records.append(record)
        
        # 每50个记录更新一次图表（避免UI阻塞）
        if len(self.data_records) % 50 == 0:
            self._update_chart()
    
    def _on_simulation_finished(self, data_records: List[Dict[str, Any]]):
        """模拟完成回调"""
        self.data_records = data_records
        
        # 更新图表
        self._update_chart()
        
        # 恢复按钮状态
        self.start_sim_button.setEnabled(True)
        self.start_sim_button.setText("开始模拟")
        self.progress_bar.setVisible(False)
        
        # 启用启动服务器按钮
        self.start_server_button.setEnabled(True)
        
        QMessageBox.information(self, "完成", f"模拟完成！共生成 {len(data_records)} 条记录。")
    
    def _update_chart(self):
        """更新图表"""
        if not self.data_records:
            return
        
        # 清空图表
        self.ax1.clear()
        self.ax2.clear()
        
        # 提取数据
        sim_times = [r['sim_time'] for r in self.data_records]
        sv_values = [r.get('pid.sv', 0) for r in self.data_records]
        pv_values = [r.get('pid.pv', 0) for r in self.data_records]
        mv_values = [r.get('pid.mv', 0) for r in self.data_records]
        
        # 绘制SV和PV（左侧y轴）
        self.ax1.plot(sim_times, sv_values, label='SV', color='blue', linewidth=1.5, alpha=0.7)
        self.ax1.plot(sim_times, pv_values, label='PV', color='cyan', linewidth=1.5, alpha=0.7)
        
        # 绘制MV（右侧y轴）
        self.ax2.plot(sim_times, mv_values, label='MV', color='orange', linewidth=1.5, alpha=0.7, linestyle='--')
        
        # 设置标签和标题
        self.ax1.set_xlabel('模拟时间 (秒)', fontsize=12)
        self.ax1.set_ylabel('SV / PV', fontsize=12, color='blue')
        self.ax1.tick_params(axis='y', labelcolor='blue')
        self.ax1.grid(True, alpha=0.3)
        self.ax1.set_title('PID控制曲线', fontsize=14, fontweight='bold')
        
        self.ax2.set_ylabel('MV', fontsize=12, color='orange')
        self.ax2.tick_params(axis='y', labelcolor='orange')
        
        # 添加图例
        lines1, labels1 = self.ax1.get_legend_handles_labels()
        lines2, labels2 = self.ax2.get_legend_handles_labels()
        self.ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
        
        # 刷新画布
        self.canvas.draw()
    
    def start_server(self):
        """启动OPCUA Server"""
        if not self.data_records:
            QMessageBox.warning(self, "警告", "请先运行模拟！")
            return
        
        try:
            port = int(self.port_input.text() or "18951")
        except ValueError:
            QMessageBox.warning(self, "警告", "端口号必须是数字！")
            return
        
        # 获取实例名
        instance_name = self.instance_name_input.text().strip()
        if not instance_name:
            QMessageBox.warning(self, "警告", "请输入实例名！")
            return
        
        # 禁用开始按钮，启用停止按钮
        self.start_server_button.setEnabled(False)
        self.stop_server_button.setEnabled(True)
        
        # 重置进度
        self.server_progress_bar.setValue(0)
        self.progress_label.setText("正在启动服务器...")
        
        # 创建并启动服务器线程
        self.server_thread = OPCUAServerThread(
            data_records=self.data_records,
            port=port,
            instance_name=instance_name
        )
        self.server_thread.progress_updated.connect(self._on_server_progress_updated)
        self.server_thread.status_updated.connect(self._on_status_updated)
        self.server_thread.finished.connect(self._on_server_finished)
        self.server_thread.error_occurred.connect(self._on_error_occurred)
        self.server_thread.start()
    
    def stop_server(self):
        """停止OPCUA Server"""
        if self.server_thread:
            self.server_thread.stop()
            self.progress_label.setText("正在停止服务器...")
    
    def _on_server_progress_updated(self, progress: float, current_index: int, sim_time: str):
        """服务器进度更新回调"""
        self.server_progress_bar.setValue(int(progress))
        self.progress_label.setText(f"进度: {current_index}/{len(self.data_records)} ({progress:.1f}%) - {sim_time}")
    
    def _on_status_updated(self, message: str):
        """状态更新回调"""
        self.progress_label.setText(message)
    
    def _on_server_finished(self):
        """服务器完成回调"""
        self.start_server_button.setEnabled(True)
        self.stop_server_button.setEnabled(False)
        self.progress_label.setText("服务器已停止")
    
    def _on_error_occurred(self, error_message: str):
        """错误回调"""
        QMessageBox.critical(self, "错误", error_message)
        self._on_server_finished()


def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    window = UnifiedToolWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

