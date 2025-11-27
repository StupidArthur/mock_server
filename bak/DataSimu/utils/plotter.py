"""
绘图模块
使用matplotlib绘制数据曲线图
"""
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import warnings
from typing import List, Optional, Dict
from utils.logger import get_logger

# 设置matplotlib支持中文显示
# Windows系统常用字体：SimHei（黑体）、Microsoft YaHei（微软雅黑）
# 尝试设置中文字体，如果失败则使用默认字体
try:
    # 设置matplotlib的字体
    plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
except Exception:
    pass

# 禁用matplotlib的字体警告
# 过滤所有UserWarning（包括字体警告）
warnings.filterwarnings('ignore', category=UserWarning)
# 特别针对matplotlib的字体管理器警告
import logging
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)
# 禁用matplotlib的字体警告消息
matplotlib.font_manager._log.setLevel(logging.ERROR)

logger = get_logger()


class DataPlotter:
    """
    数据绘图类
    
    用于读取CSV数据并绘制曲线图
    """
    
    def __init__(self, csv_file: str):
        """
        初始化绘图器
        
        Args:
            csv_file: CSV文件路径
        """
        self.csv_file = csv_file
        self.df = None
        logger.info(f"DataPlotter initialized for {csv_file}")
    
    def load_data(self):
        """加载CSV数据"""
        try:
            # 读取CSV文件
            # 第一行是标题行（Timestamp、位号名），第二行是描述行，从第三行开始是数据
            self.df = pd.read_csv(self.csv_file, skiprows=[1], encoding='utf-8-sig')
            # 如果第一列是Timestamp，将其改回datetime或time以便后续处理
            if len(self.df.columns) > 0 and self.df.columns[0] == 'Timestamp':
                # 检查第一行数据，判断是datetime格式还是time格式
                if len(self.df) > 0:
                    first_value = self.df.iloc[0, 0]
                    if isinstance(first_value, str) and len(str(first_value)) > 10:
                        # 看起来是datetime格式
                        self.df.rename(columns={'Timestamp': 'datetime'}, inplace=True)
                    else:
                        # 看起来是time格式
                        self.df.rename(columns={'Timestamp': 'time'}, inplace=True)
                else:
                    # 如果没有数据，默认使用datetime
                    self.df.rename(columns={'Timestamp': 'datetime'}, inplace=True)
            logger.info(f"Data loaded: {len(self.df)} rows, {len(self.df.columns)} columns")
            return True
        except Exception as e:
            logger.error(f"Failed to load CSV file: {e}")
            return False
    
    def plot(
        self,
        output_file: Optional[str] = None,
        tag_names: Optional[List[str]] = None,
        title: str = "数据曲线图",
        figsize: tuple = (14, 8)
    ):
        """
        绘制数据曲线图
        
        Args:
            output_file: 输出图片文件路径，如果为None则显示图形
            tag_names: 要绘制的位号名列表，如果为None则绘制所有列（除时间戳外）
            title: 图表标题
            figsize: 图表大小（宽，高）
        """
        if self.df is None:
            if not self.load_data():
                return
        
        # 确定时间列
        if 'datetime' in self.df.columns:
            time_col = 'datetime'
            # 将datetime字符串转换为datetime对象
            self.df[time_col] = pd.to_datetime(self.df[time_col])
        elif 'time' in self.df.columns:
            time_col = 'time'
        else:
            logger.error("No time column found (datetime or time)")
            return
        
        # 确定要绘制的列
        if tag_names is None:
            # 绘制所有列（除时间列外）
            plot_columns = [col for col in self.df.columns if col != time_col]
        else:
            # 只绘制指定的列
            plot_columns = [col for col in tag_names if col in self.df.columns and col != time_col]
        
        if not plot_columns:
            logger.warning("No columns to plot")
            return
        
        # 创建图形
        fig, axes = plt.subplots(len(plot_columns), 1, figsize=figsize, sharex=True)
        
        # 如果只有一个子图，axes不是数组
        if len(plot_columns) == 1:
            axes = [axes]
        
        fig.suptitle(title, fontsize=16, fontweight='bold')
        
        # 绘制每个位号
        for idx, col in enumerate(plot_columns):
            ax = axes[idx]
            
            # 绘制曲线
            ax.plot(self.df[time_col], self.df[col], linewidth=1.5, label=col)
            
            # 设置标签和标题
            ax.set_ylabel(col, fontsize=11)
            ax.grid(True, alpha=0.3)
            ax.legend(loc='upper right')
            
            # 格式化x轴（如果是datetime）
            if time_col == 'datetime':
                ax.tick_params(axis='x', rotation=45)
                fig.autofmt_xdate()
        
        # 设置x轴标签（只在最后一个子图）
        axes[-1].set_xlabel(time_col, fontsize=11)
        
        plt.tight_layout()
        
        # 保存或显示
        if output_file:
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            logger.info(f"Plot saved to {output_file}")
            # 保存后也显示图形
            plt.show()
        else:
            plt.show()
        
        plt.close()
    
    def plot_multiple_in_one(
        self,
        output_file: Optional[str] = None,
        tag_names: Optional[List[str]] = None,
        title: str = "数据曲线图",
        figsize: tuple = (14, 8),
        ylabel: Optional[str] = None
    ):
        """
        在同一张图中绘制多条曲线
        
        Args:
            output_file: 输出图片文件路径，如果为None则显示图形
            tag_names: 要绘制的位号名列表，如果为None则绘制所有列（除时间戳外）
            title: 图表标题
            figsize: 图表大小（宽，高）
            ylabel: Y轴标签，如果为None则不设置
        """
        if self.df is None:
            if not self.load_data():
                return
        
        # 确定时间列
        if 'datetime' in self.df.columns:
            time_col = 'datetime'
            # 将datetime字符串转换为datetime对象
            self.df[time_col] = pd.to_datetime(self.df[time_col])
        elif 'time' in self.df.columns:
            time_col = 'time'
        else:
            logger.error("No time column found (datetime or time)")
            return
        
        # 确定要绘制的列
        if tag_names is None:
            # 绘制所有列（除时间列外）
            plot_columns = [col for col in self.df.columns if col != time_col]
        else:
            # 只绘制指定的列
            plot_columns = [col for col in tag_names if col in self.df.columns and col != time_col]
        
        if not plot_columns:
            logger.warning("No columns to plot")
            return
        
        # 创建图形
        fig, ax = plt.subplots(figsize=figsize)
        fig.suptitle(title, fontsize=16, fontweight='bold')
        
        # 绘制所有曲线
        for col in plot_columns:
            ax.plot(self.df[time_col], self.df[col], linewidth=1.5, label=col)
        
        # 设置标签
        ax.set_xlabel(time_col, fontsize=11)
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=11)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='best')
        
        # 格式化x轴（如果是datetime）
        if time_col == 'datetime':
            ax.tick_params(axis='x', rotation=45)
            fig.autofmt_xdate()
        
        plt.tight_layout()
        
        # 保存或显示
        if output_file:
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            logger.info(f"Plot saved to {output_file}")
            # 保存后也显示图形
            plt.show()
        else:
            plt.show()
        
        plt.close()

