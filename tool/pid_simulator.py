"""
PID回路模拟工具
使用PyQt6实现的图形化工具，用于模拟PID控制回路（水箱+阀门+PID算法）
"""
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import csv
import time
import threading

# 添加项目根目录到Python路径
SCRIPT_DIR = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(SCRIPT_DIR))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QGroupBox, QGridLayout,
    QFileDialog, QMessageBox, QProgressBar
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
                 pid_params: Dict[str, Any], duration: float, cycle_time: float = 0.5):
        """
        初始化模拟线程
        
        Args:
            tank_params: 水箱参数
            valve_params: 阀门参数
            pid_params: PID参数
            duration: 模拟时长（秒）
            cycle_time: 运行周期（秒）
        """
        super().__init__()
        self.tank_params = tank_params
        self.valve_params = valve_params
        self.pid_params = pid_params
        self.duration = duration
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
            
            # 初始化参数值
            tank_level = tank.level
            valve_opening = valve.current_opening
            pid_pv = tank_level
            pid_sv = pid.input['sv']
            pid_mv = pid.output['mv']
            
            # 运行循环
            start_time = time.time()
            target_sim_time = self.duration
            
            while clock.current_time < target_sim_time and self._running:
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


class PIDSimulatorWindow(QMainWindow):
    """PID模拟器主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PID回路模拟工具")
        self.setGeometry(100, 100, 1400, 800)
        
        # 数据存储
        self.data_records: List[Dict[str, Any]] = []
        self.simulation_thread: Optional[SimulationThread] = None
        
        # 创建主界面
        self._create_ui()
        
        # 设置默认值
        self._set_default_values()
    
    def _create_ui(self):
        """创建用户界面"""
        # 主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # 主布局（水平布局：左侧配置 + 右侧图表）
        main_layout = QHBoxLayout()
        main_widget.setLayout(main_layout)
        
        # 左侧：参数配置区域
        left_panel = self._create_left_panel()
        main_layout.addWidget(left_panel, stretch=1)
        
        # 右侧：图表区域
        right_panel = self._create_right_panel()
        main_layout.addWidget(right_panel, stretch=2)
    
    def _create_left_panel(self) -> QWidget:
        """创建左侧参数配置面板"""
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
        self.pid_sv = QLineEdit()
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
        pid_layout.addWidget(QLabel("设定值 (SV):"), 3, 0)
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
        self.start_button = QPushButton("开始模拟")
        self.start_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
        self.start_button.clicked.connect(self.start_simulation)
        layout.addWidget(self.start_button)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 添加弹性空间
        layout.addStretch()
        
        return panel
    
    def _create_right_panel(self) -> QWidget:
        """创建右侧图表面板"""
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
        
        # 导出按钮（右下角）
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.export_button = QPushButton("生成数据文件")
        self.export_button.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 8px;")
        self.export_button.clicked.connect(self.export_data)
        self.export_button.setEnabled(False)
        button_layout.addWidget(self.export_button)
        layout.addLayout(button_layout)
        
        # 初始化图表
        self._init_chart()
        
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
        self.pid_sv.setText("1.0")
        self.pid_pv.setText("0.0")
        self.pid_mv.setText("0.0")
        self.pid_h.setText("100.0")
        self.pid_l.setText("0.0")
        
        # 模拟时长默认值
        self.duration_input.setText("900.0")
    
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
            'sv': float(self.pid_sv.text() or "1.0"),
            'pv': float(self.pid_pv.text() or "0.0"),
            'mv': float(self.pid_mv.text() or "0.0"),
            'h': float(self.pid_h.text() or "100.0"),
            'l': float(self.pid_l.text() or "0.0")
        }
    
    def start_simulation(self):
        """开始模拟"""
        try:
            # 获取参数
            tank_params = self._get_tank_params()
            valve_params = self._get_valve_params()
            pid_params = self._get_pid_params()
            duration = float(self.duration_input.text() or "900.0")
            
            # 清空之前的数据
            self.data_records = []
            
            # 重置图表
            self._init_chart()
            
            # 禁用开始按钮
            self.start_button.setEnabled(False)
            self.start_button.setText("模拟中...")
            
            # 显示进度条
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            
            # 创建并启动模拟线程
            self.simulation_thread = SimulationThread(
                tank_params=tank_params,
                valve_params=valve_params,
                pid_params=pid_params,
                duration=duration
            )
            self.simulation_thread.progress_updated.connect(self._on_progress_updated)
            self.simulation_thread.data_updated.connect(self._on_data_updated)
            self.simulation_thread.finished.connect(self._on_simulation_finished)
            self.simulation_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动模拟失败: {str(e)}")
            self.start_button.setEnabled(True)
            self.start_button.setText("开始模拟")
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
        self.start_button.setEnabled(True)
        self.start_button.setText("开始模拟")
        self.progress_bar.setVisible(False)
        
        # 启用导出按钮
        self.export_button.setEnabled(True)
        
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
    
    def export_data(self):
        """导出数据到CSV文件"""
        if not self.data_records:
            QMessageBox.warning(self, "警告", "没有数据可导出！")
            return
        
        # 选择保存文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"pid_simulation_{timestamp}.csv"
        
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "保存数据文件",
            default_filename,
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if not filename:
            return
        
        try:
            # 获取所有参数名（除了sim_time）
            param_names = set()
            for record in self.data_records:
                param_names.update(record.keys())
            param_names.discard('sim_time')
            param_names = sorted(param_names)
            
            # 写入CSV文件
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['sim_time'] + param_names)
                writer.writeheader()
                writer.writerows(self.data_records)
            
            QMessageBox.information(self, "成功", f"数据已导出到：\n{filename}")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出数据失败：{str(e)}")


def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    window = PIDSimulatorWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

