"""
调试运行模块
独立的调试模块，支持时间加速，生成数据文件用于快速调试模拟
支持数据绘图功能
"""
import json
import csv
import time
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

# 添加项目根目录到Python路径
SCRIPT_DIR = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(SCRIPT_DIR))

from plc.plc_configuration import Configuration
from plc.clock import Clock
from module.cylindrical_tank import CylindricalTank
from module.valve import Valve
from algorithm.pid import PID
from utils.logger import get_logger

logger = get_logger()

# 绘图相关导入
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import numpy as np
    # 设置中文字体
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
    plt.rcParams['axes.unicode_minus'] = False
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.warning("matplotlib not available, plotting functions will be disabled")


class DebugClock(Clock):
    """
    调试时钟模块
    支持时间加速功能
    """
    
    def __init__(self, cycle_time: float = 0.5, time_acceleration: float = 1.0):
        """
        初始化调试时钟
        
        Args:
            cycle_time: 运行周期（秒）
            time_acceleration: 时间加速倍数，1.0表示正常速度，>1.0表示加速
        """
        super().__init__(cycle_time)
        self.time_acceleration = time_acceleration
    
    def set_time_acceleration(self, acceleration: float):
        """设置时间加速倍数"""
        self.time_acceleration = max(0.0, acceleration)
        logger.info(f"Time acceleration set to {self.time_acceleration}x")
    
    def sleep_to_next_cycle(self):
        """睡眠到下一个周期（加速模式下不等待）"""
        if self.time_acceleration > 1.0:
            # 加速模式：不等待
            return
        # 正常模式：等待一个周期时间
        if self.cycle_time > 0:
            time.sleep(self.cycle_time)


class DebugRunner:
    """
    调试运行模块
    
    独立的调试模块，包含runner+模型+组态，支持时间加速
    生成数据文件用于后续绘图展示
    """
    
    def __init__(self, config_file: str, output_file: str = None, 
                 time_acceleration: float = 1000.0):
        """
        初始化调试运行模块
        
        Args:
            config_file: 组态配置文件路径（相对路径或绝对路径）
            output_file: 输出数据文件路径（CSV格式），如果为None则自动生成
            time_acceleration: 时间加速倍数，默认1000倍
        """
        # 解析配置文件路径（支持相对路径和绝对路径）
        config_path = Path(config_file)
        if not config_path.is_absolute():
            # 相对路径：相对于脚本所在目录的父目录（项目根目录）
            config_path = SCRIPT_DIR / config_file
        config_file_resolved = str(config_path.resolve())
        
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file_resolved}")
        
        self.config = Configuration(config_file=config_file_resolved)
        self.time_acceleration = time_acceleration
        
        # 初始化时钟（支持时间加速）
        self.clock = DebugClock(
            cycle_time=self.config.get_cycle_time(),
            time_acceleration=time_acceleration
        )
        
        # 存储模型和算法实例
        self.models: Dict[str, Any] = {}
        self.algorithms: Dict[str, Any] = {}
        self.params: Dict[str, Any] = {}
        
        # 初始化模型和算法
        self._initialize_models()
        self._initialize_algorithms()
        
        # 初始化参数值
        self._update_params_from_models()
        self._update_params_from_algorithms()
        
        # 数据记录
        self.data_records: List[Dict[str, Any]] = []
        
        # 输出文件
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"debug_data_{timestamp}.csv"
        
        # 解析输出文件路径（支持相对路径和绝对路径）
        output_path = Path(output_file)
        if not output_path.is_absolute():
            # 相对路径：相对于脚本所在目录的父目录（项目根目录）
            output_path = SCRIPT_DIR / output_file
        self.output_file = output_path.resolve()
        
        logger.info(f"DebugRunner initialized with output_file={self.output_file}, "
                   f"time_acceleration={time_acceleration}x")
    
    def _initialize_models(self):
        """初始化物理模型实例"""
        models_config = self.config.get_models()
        
        for name, model_config in models_config.items():
            model_type = model_config.get('type')
            params = model_config.get('params', {})
            
            if model_type == 'cylindrical_tank':
                model = CylindricalTank(**params)
            elif model_type == 'valve':
                model = Valve(**params)
            else:
                logger.warning(f"Unknown model type: {model_type}")
                continue
            
            self.models[name] = model
            logger.info(f"Model '{name}' ({model_type}) initialized")
    
    def _initialize_algorithms(self):
        """初始化控制算法实例"""
        algorithms_config = self.config.get_algorithms()
        
        for name, algo_config in algorithms_config.items():
            algo_type = algo_config.get('type')
            params = algo_config.get('params', {}).copy()  # 复制一份，避免修改原配置
            
            if algo_type == 'PID':
                # PID构造函数直接接受参数（kp, Ti, Td等）
                # 如果params中有name，使用params中的name，否则使用配置中的name
                if 'name' in params:
                    algorithm = PID(**params)
                else:
                    algorithm = PID(name=name, **params)
            else:
                logger.warning(f"Unknown algorithm type: {algo_type}")
                continue
            
            self.algorithms[name] = algorithm
            logger.info(f"Algorithm '{name}' ({algo_type}) initialized")
    
    def _update_params_from_models(self):
        """从模型更新参数值（通用方法，适用于所有模型类型）"""
        for name, model in self.models.items():
            # 使用基类的get_params方法获取所有参数
            model_params = model.get_params()
            for param_name, param_value in model_params.items():
                self.params[f"{name}.{param_name}"] = param_value
    
    def _update_params_from_algorithms(self):
        """从算法更新参数值"""
        for name, algorithm in self.algorithms.items():
            all_params = algorithm.get_all_params()
            # 更新配置参数（如kp, Ti, Td）
            for param_name, param_value in all_params['config'].items():
                self.params[f"{name}.{param_name}"] = param_value
            # 更新输入参数（如pv, sv）
            for param_name, param_value in all_params['input'].items():
                self.params[f"{name}.{param_name}"] = param_value
            # 更新输出参数（如mv, MODE）
            for param_name, param_value in all_params['output'].items():
                self.params[f"{name}.{param_name}"] = param_value
    
    def _apply_connections(self):
        """应用连接关系"""
        connections = self.config.get_connections()
        
        for conn in connections:
            # 解析连接关系：from和to格式为 "instance.param"
            from_str = conn.get('from', '')
            to_str = conn.get('to', '')
            
            # 兼容旧格式（from/from_param和to/to_param）
            if 'from_param' in conn:
                from_obj = conn.get('from')
                from_param = conn.get('from_param')
                to_obj = conn.get('to')
                to_param = conn.get('to_param')
            else:
                # 新格式：从 "instance.param" 解析
                from_parts = from_str.split('.', 1)
                to_parts = to_str.split('.', 1)
                if len(from_parts) != 2 or len(to_parts) != 2:
                    logger.warning(f"Invalid connection format: {from_str} -> {to_str}")
                    continue
                from_obj, from_param = from_parts
                to_obj, to_param = to_parts
            
            # 获取源参数值
            source_key = f"{from_obj}.{from_param}"
            if source_key not in self.params:
                continue
            
            source_value = self.params[source_key]
            
            # 设置目标参数（通用方法，适用于所有模型和算法类型）
            if to_obj in self.models:
                # 模型参数：直接使用setattr设置，模型内部会处理
                model = self.models[to_obj]
                setattr(model, f'_input_{to_param.lower()}', source_value)
            elif to_obj in self.algorithms:
                # 算法参数：根据参数是否存在于input或config字典中自动判断
                algorithm = self.algorithms[to_obj]
                if to_param in algorithm.input:
                    algorithm.input[to_param] = source_value
                elif to_param in algorithm.config:
                    algorithm.config[to_param] = source_value
                else:
                    # 如果都不存在，默认设置到input（通常连接关系是输入）
                    algorithm.input[to_param] = source_value
                    logger.debug(f"Parameter {to_param} not found in input/config, setting to input")
    
    def execute_one_cycle(self):
        """执行一个周期"""
        # 步进时钟
        self.clock.step()
        
        # 更新参数值
        self._update_params_from_models()
        self._update_params_from_algorithms()
        
        # 应用连接关系
        self._apply_connections()
        
        # 执行算法
        for name, algorithm in self.algorithms.items():
            algorithm.execute()
        
        # 更新算法输出参数
        self._update_params_from_algorithms()
        
        # 再次应用连接（算法输出可能影响模型输入）
        self._apply_connections()
        
        # 执行模型（通用方法，适用于所有模型类型）
        # 约定：模型的输入参数通过 _input_xxx 属性传递，execute方法从这些属性读取
        step_size = self.clock.cycle_time
        for name, model in self.models.items():
            # 获取所有可能的 _input_xxx 属性
            input_attrs = {k: v for k, v in model.__dict__.items() if k.startswith('_input_')}
            if input_attrs:
                # 如果有输入属性，提取参数名（去掉_input_前缀）并传递给execute
                # 约定：参数名格式为 _input_PARAM_NAME，execute方法接收对应的参数
                # 这里需要根据实际的实现约定来处理，暂时保持向后兼容
                if hasattr(model, '_input_valve_opening'):
                    valve_opening = getattr(model, '_input_valve_opening', 0.0)
                    model.execute(valve_opening, step=step_size)
                elif hasattr(model, '_input_target_opening'):
                    target_opening = getattr(model, '_input_target_opening', 0.0)
                    model.execute(target_opening, step=step_size)
                else:
                    # 通用情况：尝试使用第一个输入属性
                    first_input_key = list(input_attrs.keys())[0]
                    param_value = input_attrs[first_input_key]
                    # 尝试调用execute，传递参数值
                    try:
                        model.execute(param_value, step=step_size)
                    except Exception as e:
                        logger.warning(f"Failed to execute model {name} with generic method: {e}")
            else:
                # 如果没有输入属性，尝试无参数调用（某些模型可能不需要外部输入）
                try:
                    model.execute(step=step_size)
                except TypeError:
                    logger.warning(f"Model {name} requires input parameters but none provided")
        
        # 最终更新参数值
        self._update_params_from_models()
        self._update_params_from_algorithms()
        
        # 记录数据
        record = {
            'sim_time': self.clock.current_time,
            **self.params.copy()
        }
        self.data_records.append(record)
    
    def run(self, duration: float):
        """
        运行模拟
        
        Args:
            duration: 模拟持续时间（秒，模拟时间）
        """
        logger.info(f"Starting debug simulation for {duration}s (simulation time)")
        self.clock.start()
        
        start_real_time = time.time()
        target_sim_time = duration
        
        while self.clock.current_time < target_sim_time:
            self.execute_one_cycle()
            self.clock.sleep_to_next_cycle()
            
            # 每1000个周期记录一次进度
            if len(self.data_records) % 1000 == 0:
                progress = (self.clock.current_time / target_sim_time) * 100
                elapsed_real_time = time.time() - start_real_time
                logger.info(f"Progress: {progress:.1f}% ({self.clock.current_time:.1f}s / {target_sim_time:.1f}s), "
                          f"real time: {elapsed_real_time:.1f}s")
        
        self.clock.stop()
        elapsed_real_time = time.time() - start_real_time
        logger.info(f"Simulation completed: {len(self.data_records)} records, "
                   f"real time: {elapsed_real_time:.1f}s")
        
        # 保存数据
        self.save_data()
    
    def save_data(self):
        """保存数据到CSV文件"""
        if not self.data_records:
            logger.warning("No data to save")
            return
        
        logger.info(f"Saving {len(self.data_records)} records to {self.output_file}")
        
        # 获取所有参数名（除了sim_time）
        param_names = set()
        for record in self.data_records:
            param_names.update(record.keys())
        param_names.discard('sim_time')
        param_names = sorted(param_names)
        
        # 写入CSV文件
        with open(str(self.output_file), 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['sim_time'] + param_names)
            writer.writeheader()
            writer.writerows(self.data_records)
        
        logger.info(f"Data saved to {self.output_file}")
    
    def plot(self, params: Optional[List[List[str]]] = None, 
              output: Optional[str] = None):
        """
        绘制数据图形
        
        Args:
            params: 要绘制的参数名称列表（二维数组），每个子列表中的参数共享同一个纵坐标轴
                   所有组绘制在同一张图上，但使用不同的y轴
                   如果为None则绘制所有参数（每个参数一个子图）
                    例如：[["pid1.pv", "pid1.sv"], ["pid1.mv"], ["tank1.level"]]
                    表示：pv和sv共享左侧y轴，mv使用右侧y轴，level使用另一个右侧y轴
            output: 输出图片文件路径，如果为None则显示图形
        """
        if not MATPLOTLIB_AVAILABLE:
            logger.error("matplotlib not available, cannot plot")
            return
        
        if not self.data_records:
            logger.warning("No data to plot")
            return
        
        # 获取所有可用参数名（除了sim_time）
        available_params = set()
        for record in self.data_records:
            available_params.update(record.keys())
        available_params.discard('sim_time')
        
        # 处理参数列表
        if params is None:
            # 如果没有指定参数，每个参数一个子图
            param_groups = [[p] for p in sorted(available_params)]
            # 使用旧的子图模式
            self._plot_multiple_parameters([p for p in sorted(available_params)], output_file=output)
            return
        else:
            # 过滤出数据中存在的参数
            param_groups = []
            for group in params:
                filtered_group = [p for p in group if p in available_params]
                if filtered_group:
                    param_groups.append(filtered_group)
            
            if not param_groups:
                logger.warning(f"None of the specified parameters found. Available: {sorted(available_params)}")
                return
        
        logger.info(f"Plotting {len(param_groups)} parameter groups: {param_groups}")
        
        # 绘制图形：所有组在同一张图上，但使用不同的y轴
        self._plot_multi_axis_parameters(param_groups, output_file=output)
    
    def _plot_parameter(self, param_name: str, ax=None, label=None):
        """
        绘制单个参数
        
        Args:
            param_name: 参数名称
            ax: matplotlib axes对象，如果为None则创建新的
            label: 图例标签，如果为None则使用参数名
        """
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 6))
        
        sim_times = [r['sim_time'] for r in self.data_records]
        values = [r.get(param_name, 0) for r in self.data_records]
        
        ax.plot(sim_times, values, label=label or param_name, linewidth=1.5)
        ax.set_xlabel('模拟时间 (秒)', fontsize=12)
        ax.set_ylabel('参数值', fontsize=12)
        ax.set_title(f'{param_name} 随时间变化', fontsize=14, fontweight='bold')
        ax.grid(True, alpha=0.3)
        ax.legend()
        
        return ax
    
    def _plot_multiple_parameters(self, param_names: List[str], figsize=(12, 8)):
        """
        绘制多个参数（子图）
        
        Args:
            param_names: 参数名称列表
            figsize: 图形大小
        """
        n_params = len(param_names)
        n_cols = 2
        n_rows = (n_params + 1) // 2
        
        fig, axes = plt.subplots(n_rows, n_cols, figsize=figsize)
        if n_params == 1:
            axes = [axes]
        else:
            axes = axes.flatten()
        
        for i, param_name in enumerate(param_names):
            ax = axes[i]
            self._plot_parameter(param_name, ax=ax)
        
        # 隐藏多余的子图
        for i in range(n_params, len(axes)):
            axes[i].set_visible(False)
        
        plt.tight_layout()
        return fig
    
    def _plot_multi_axis_parameters(self, param_groups: List[List[str]], output_file: str = None):
        """
        绘制多y轴参数（所有组在同一张图上，但使用不同的y轴）
        
        Args:
            param_groups: 参数组列表，每个子列表中的参数共享同一个纵坐标轴
                         第一组使用左侧y轴，后续组使用右侧y轴
            output_file: 输出文件路径，如果为None则显示图形
        """
        fig, ax1 = plt.subplots(figsize=(14, 8))
        
        sim_times = [r['sim_time'] for r in self.data_records]
        
        # 第一组使用左侧y轴
        first_group = param_groups[0]
        colors = plt.cm.tab10(range(len(first_group)))
        
        for i, param_name in enumerate(first_group):
            values = [r.get(param_name, 0) for r in self.data_records]
            ax1.plot(sim_times, values, label=param_name, linewidth=1.5, 
                    alpha=0.7, color=colors[i % len(colors)])
        
        ax1.set_xlabel('模拟时间 (秒)', fontsize=12)
        ax1.set_ylabel(f'{" & ".join(first_group)}', fontsize=12, color=colors[0])
        ax1.tick_params(axis='y', labelcolor=colors[0])
        ax1.grid(True, alpha=0.3)
        
        # 后续组使用右侧y轴
        axes_list = [ax1]
        for group_idx, param_group in enumerate(param_groups[1:], start=1):
            # 创建新的y轴（共享x轴）
            ax = ax1.twinx()
            axes_list.append(ax)
            
            # 偏移y轴位置，避免重叠
            ax.spines['right'].set_position(('outward', 60 * group_idx))
            
            colors = plt.cm.tab10(range(len(param_group)))
            for i, param_name in enumerate(param_group):
                values = [r.get(param_name, 0) for r in self.data_records]
                ax.plot(sim_times, values, label=param_name, linewidth=1.5, 
                       alpha=0.7, color=colors[i % len(colors)], linestyle='--')
            
            ax.set_ylabel(f'{" & ".join(param_group)}', fontsize=12, color=colors[0])
            ax.tick_params(axis='y', labelcolor=colors[0])
        
        # 合并所有图例
        lines1, labels1 = ax1.get_legend_handles_labels()
        for ax in axes_list[1:]:
            lines2, labels2 = ax.get_legend_handles_labels()
            lines1.extend(lines2)
            labels1.extend(labels2)
        
        ax1.legend(lines1, labels1, loc='upper left', bbox_to_anchor=(1.15, 1))
        
        plt.title('参数随时间变化（多y轴）', fontsize=14, fontweight='bold')
        plt.tight_layout()
        
        if output_file:
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            logger.info(f"Plot saved to {output_file}")
        else:
            plt.show()


def main(config_file: str = 'config/debug_config.yaml', output_file: str = None, 
         duration: float = 3600.0, time_acceleration: float = 1000.0,
         plot_params: Optional[List[List[str]]] = None,
         plot_output: Optional[str] = None):
    """
    主函数
    
    Args:
        config_file: 组态配置文件路径，默认使用调试专用配置文件 config/debug_config.yaml
        output_file: 输出数据文件路径（CSV格式），默认自动生成
        duration: 模拟持续时间（秒，模拟时间），默认3600秒
        time_acceleration: 时间加速倍数，默认1000倍
        plot_params: 要绘制的参数名称列表（二维数组），每个子列表中的参数共享同一个纵坐标轴
                     如果为None则不绘图
                      例如：[["pid1.pv", "pid1.sv"], ["pid1.mv"], ["tank1.level"]]
        plot_output: 输出图片文件路径，如果为None则显示图形
    """
    runner = DebugRunner(
        config_file=config_file,
        output_file=output_file,
        time_acceleration=time_acceleration
    )
    
    # 运行模拟
    runner.run(duration=duration)
    
    # 如果指定了绘图参数，则绘图
    if plot_params is not None:
        runner.plot(params=plot_params, output=plot_output)


if __name__ == '__main__':
    # 示例调用
    # 注意：使用独立的调试配置文件 config/debug_config.yaml，避免影响主系统配置
    main(
        config_file='config/debug_config.yaml',  # 调试专用配置文件
        output_file="debug_data.csv",  # 自动生成文件名
        duration=900.0,  # 模拟x秒
        time_acceleration=1000.0,  # 1000倍加速
        # plot_params 是二维数组，同一子列表中的参数共享y轴
        plot_params=[
            ["pid1.pv", "pid1.sv"],
            ["pid1.mv"],
            ["tank1.level"]
        ],
        # plot_output="plot.png",  # 保存图片到文件，不指定则显示图形
    )

