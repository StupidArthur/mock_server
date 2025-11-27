"""
模型测试显示模块
用于对模型进行阶跃测试并绘制输出结果
"""
import matplotlib.pyplot as plt
import numpy as np
from typing import List, Union
from module.base_module import BaseModule
from module.valve import Valve
from module.cylindrical_tank import CylindricalTank
from utils.logger import get_logger

logger = get_logger()


class ModuleDisplayer:
    """
    模型测试显示类
    
    用于对模型进行多组阶跃测试，并绘制输出结果
    """
    
    def __init__(self, model: BaseModule, step: float = 0.1):
        """
        初始化模型测试显示器
        
        Args:
            model: 要测试的模型实例
            step: 步进时间（秒），默认0.1秒
        """
        self.model = model
        self.step = step
        logger.info(f"ModuleDisplayer initialized for {type(model).__name__}")
    
    def step_test(
        self,
        time_points: List[float],
        target_values: List[float],
        duration: float = None,
        output_file: str = None
    ):
        """
        进行阶跃测试并绘制结果
        
        Args:
            time_points: 时间节点列表（秒），表示在哪些时间点改变目标值
            target_values: 目标值列表，与time_points对应，表示在该时间点的目标值
            duration: 总运行时间（秒），如果为None则使用最后一个时间节点+10秒
            output_file: 输出图片文件路径，如果为None则显示图形
        """
        # 验证输入
        if len(time_points) != len(target_values):
            raise ValueError("时间节点列表和目标值列表长度必须相同")
        
        if len(time_points) == 0:
            raise ValueError("时间节点列表不能为空")
        
        # 确定总运行时间
        if duration is None:
            duration = max(time_points) + 10.0
        
        # 生成时间序列
        time_array = np.arange(0, duration, self.step)
        
        # 生成阶跃输入序列
        input_array = self._generate_step_input(time_array, time_points, target_values)
        
        # 运行模型并记录输出
        output_array = []
        current_time = 0.0
        
        # 重置模型状态（如果可能）
        self._reset_model()
        
        for i, t in enumerate(time_array):
            # 获取当前输入值
            current_input = input_array[i]
            
            # 执行模型
            if isinstance(self.model, Valve):
                output = self.model.execute(current_input, step=self.step)
            elif isinstance(self.model, CylindricalTank):
                output = self.model.execute(current_input, step=self.step)
            else:
                # 通用模型，尝试单参数调用
                output = self.model.execute(current_input, step=self.step)
            
            output_array.append(output)
            current_time = t
        
        # 绘制结果
        self._plot_results(time_array, input_array, output_array, time_points, target_values, output_file)
        
        logger.info(f"Step test completed, duration={duration:.2f}s")
    
    def _generate_step_input(
        self,
        time_array: np.ndarray,
        time_points: List[float],
        target_values: List[float]
    ) -> np.ndarray:
        """
        生成阶跃输入序列
        
        Args:
            time_array: 时间数组
            time_points: 时间节点列表
            target_values: 目标值列表
        
        Returns:
            输入值数组
        """
        input_array = np.zeros_like(time_array)
        
        # 初始值
        if len(target_values) > 0:
            initial_value = target_values[0]
        else:
            initial_value = 0.0
        
        # 填充初始值
        if len(time_points) > 0 and time_points[0] > 0:
            mask = time_array < time_points[0]
            input_array[mask] = initial_value
        
        # 填充阶跃值
        for i in range(len(time_points)):
            if i < len(time_points) - 1:
                mask = (time_array >= time_points[i]) & (time_array < time_points[i + 1])
            else:
                mask = time_array >= time_points[i]
            input_array[mask] = target_values[i]
        
        return input_array
    
    def _reset_model(self):
        """重置模型状态"""
        if isinstance(self.model, CylindricalTank):
            # 重置水位到初始值（如果需要，可以通过重新实例化或添加reset方法）
            pass
        elif isinstance(self.model, Valve):
            # 重置阀门开度
            self.model.current_opening = self.model.min_opening
            self.model.target_opening = self.model.min_opening
    
    def _plot_results(
        self,
        time_array: np.ndarray,
        input_array: np.ndarray,
        output_array: np.ndarray,
        time_points: List[float],
        target_values: List[float],
        output_file: str = None
    ):
        """
        绘制测试结果
        
        Args:
            time_array: 时间数组
            input_array: 输入值数组
            output_array: 输出值数组
            time_points: 时间节点列表
            target_values: 目标值列表
            output_file: 输出文件路径
        """
        # 确定输入和输出的标签
        if isinstance(self.model, Valve):
            input_label = "目标开度 (%)"
            output_label = "当前开度 (%)"
            title = "阀门模型阶跃测试"
        elif isinstance(self.model, CylindricalTank):
            input_label = "阀门开度 (%)"
            output_label = "液位高度 (m)"
            title = "水箱模型阶跃测试"
        else:
            input_label = "输入值"
            output_label = "输出值"
            title = f"{type(self.model).__name__}模型阶跃测试"
        
        # 创建图形
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
        fig.suptitle(title, fontsize=14, fontweight='bold')
        
        # 绘制输入
        ax1.plot(time_array, input_array, 'b-', linewidth=2, label='输入')
        ax1.set_xlabel('时间 (秒)', fontsize=10)
        ax1.set_ylabel(input_label, fontsize=10)
        ax1.set_title('输入信号', fontsize=12)
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        
        # 标记阶跃点
        for i, (t, v) in enumerate(zip(time_points, target_values)):
            ax1.axvline(x=t, color='r', linestyle='--', alpha=0.5)
            ax1.text(t, v, f'  {v:.2f}', verticalalignment='bottom', fontsize=8)
        
        # 绘制输出
        ax2.plot(time_array, output_array, 'g-', linewidth=2, label='输出')
        ax2.set_xlabel('时间 (秒)', fontsize=10)
        ax2.set_ylabel(output_label, fontsize=10)
        ax2.set_title('输出响应', fontsize=12)
        ax2.grid(True, alpha=0.3)
        ax2.legend()
        
        # 标记阶跃点
        for i, t in enumerate(time_points):
            ax2.axvline(x=t, color='r', linestyle='--', alpha=0.5)
        
        plt.tight_layout()
        
        # 保存或显示
        if output_file:
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            logger.info(f"Plot saved to {output_file}")
        else:
            plt.show()
        
        plt.close()

