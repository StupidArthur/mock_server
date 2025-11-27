"""
绘图工具
读取调试运行模块生成的数据文件，进行绘图展示
"""
import csv
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False


def load_data(file_path: str) -> List[Dict[str, Any]]:
    """
    加载CSV数据文件
    
    Args:
        file_path: CSV文件路径
    
    Returns:
        数据记录列表
    """
    records = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 转换数值类型
            record = {}
            for key, value in row.items():
                if key == 'sim_time':
                    record[key] = float(value)
                else:
                    try:
                        record[key] = float(value)
                    except ValueError:
                        record[key] = value
            records.append(record)
    return records


def plot_parameter(data: List[Dict[str, Any]], param_name: str, 
                   ax=None, label=None):
    """
    绘制单个参数
    
    Args:
        data: 数据记录列表
        param_name: 参数名称
        ax: matplotlib axes对象，如果为None则创建新的
        label: 图例标签，如果为None则使用参数名
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 6))
    
    sim_times = [r['sim_time'] for r in data]
    values = [r.get(param_name, 0) for r in data]
    
    ax.plot(sim_times, values, label=label or param_name, linewidth=1.5)
    ax.set_xlabel('模拟时间 (秒)', fontsize=12)
    ax.set_ylabel('参数值', fontsize=12)
    ax.set_title(f'{param_name} 随时间变化', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend()
    
    return ax


def plot_multiple_parameters(data: List[Dict[str, Any]], param_names: List[str],
                             figsize=(12, 8)):
    """
    绘制多个参数（子图）
    
    Args:
        data: 数据记录列表
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
        plot_parameter(data, param_name, ax=ax)
    
    # 隐藏多余的子图
    for i in range(n_params, len(axes)):
        axes[i].set_visible(False)
    
    plt.tight_layout()
    return fig


def plot_all_parameters(data: List[Dict[str, Any]], param_names: Optional[List[str]] = None,
                        output_file: str = None):
    """
    绘制参数（单图，多条曲线）
    
    Args:
        data: 数据记录列表
        param_names: 要绘制的参数名称列表，如果为None则绘制所有参数
        output_file: 输出文件路径，如果为None则显示图形
    """
    if not data:
        print("No data to plot")
        return
    
    # 获取参数名（除了sim_time）
    if param_names is None:
        param_names = [k for k in data[0].keys() if k != 'sim_time']
    else:
        # 过滤出数据中存在的参数
        available_params = [k for k in data[0].keys() if k != 'sim_time']
        param_names = [p for p in param_names if p in available_params]
    
    if not param_names:
        print("No parameters to plot")
        return
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    sim_times = [r['sim_time'] for r in data]
    
    for param_name in param_names:
        values = [r.get(param_name, 0) for r in data]
        ax.plot(sim_times, values, label=param_name, linewidth=1.5, alpha=0.7)
    
    ax.set_xlabel('模拟时间 (秒)', fontsize=12)
    ax.set_ylabel('参数值', fontsize=12)
    if len(param_names) == len([k for k in data[0].keys() if k != 'sim_time']):
        ax.set_title('所有参数随时间变化', fontsize=14, fontweight='bold')
    else:
        ax.set_title(f'参数随时间变化 ({len(param_names)}个参数)', fontsize=14, fontweight='bold')
    ax.grid(True, alpha=0.3)
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    
    plt.tight_layout()
    
    if output_file:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Plot saved to {output_file}")
    else:
        plt.show()


def main(data_file: str, params: Optional[List[str]] = None,
         output: Optional[str] = None, subplot: bool = False):
    """
    主函数：加载数据并绘制图形
    
    Args:
        data_file: 数据文件路径（CSV格式）
        params: 要绘制的参数名称列表，如果为None则绘制所有参数
        output: 输出图片文件路径，如果为None则显示图形
        subplot: 是否使用子图模式（每个参数一个子图）
    """
    # 加载数据
    print(f"Loading data from {data_file}...")
    data = load_data(data_file)
    print(f"Loaded {len(data)} records")
    
    if not data:
        print("No data to plot")
        return
    
    # 获取参数名
    param_names = [k for k in data[0].keys() if k != 'sim_time']
    print(f"Available parameters: {', '.join(param_names)}")
    
    # 确定要绘制的参数
    if params:
        plot_params = [p for p in params if p in param_names]
        if not plot_params:
            print(f"Warning: None of the specified parameters found. Using all parameters.")
            plot_params = param_names
    else:
        plot_params = param_names
    
    print(f"Plotting parameters: {', '.join(plot_params)}")
    
    # 绘制图形
    if subplot and len(plot_params) > 1:
        # 子图模式
        fig = plot_multiple_parameters(data, plot_params)
        if output:
            plt.savefig(output, dpi=300, bbox_inches='tight')
            print(f"Plot saved to {output}")
        else:
            plt.show()
    else:
        # 单图模式
        if len(plot_params) == 1:
            # 单个参数
            fig, ax = plt.subplots(figsize=(10, 6))
            plot_parameter(data, plot_params[0], ax=ax)
            if output:
                plt.savefig(output, dpi=300, bbox_inches='tight')
                print(f"Plot saved to {output}")
            else:
                plt.show()
        else:
            # 多个参数
            plot_all_parameters(data, param_names=plot_params, output_file=output)


if __name__ == '__main__':
    # import argparse
    # parser = argparse.ArgumentParser(description='绘图工具 - 展示调试运行数据')
    # parser.add_argument('data_file', type=str,
    #                    help='数据文件路径（CSV格式）')
    # parser.add_argument('--params', type=str, nargs='+', default=None,
    #                    help='要绘制的参数名称列表，如果未指定则绘制所有参数')
    # parser.add_argument('--output', type=str, default=None,
    #                    help='输出图片文件路径，如果未指定则显示图形')
    # parser.add_argument('--subplot', action='store_true',
    #                    help='使用子图模式（每个参数一个子图）')
    #
    # args = parser.parse_args()
    # main(
    #     data_file=args.data_file,
    #     params=args.params,
    #     output=args.output,
    #     subplot=args.subplot
    # )
    main(
        data_file="./../debug_data.csv",
        params=["pid1.pv", "pid1.sv", "pid1.mv"],
    )

