"""
运行数据导出模板
将每个实例化的模型和算法的参数导出为Excel或CSV
"""
import pandas as pd
import csv
from typing import Dict, List, Any, Optional
from plc.runner import Runner
from utils.logger import get_logger

logger = get_logger()


class DataExporter:
    """
    运行数据导出模板
    
    每个实例化的模型和算法都有一个名字object，也有自己的参数args，
    object.args作为模板中的名字
    """
    
    def __init__(self, runner: Runner):
        """
        初始化数据导出器
        
        Args:
            runner: 运行模块实例
        """
        self.runner = runner
        self.data_history: List[Dict[str, Any]] = []
        
        logger.info("DataExporter initialized")
    
    def record(self, cycle_data: Dict[str, Any] = None):
        """
        记录一个周期的数据
        
        Args:
            cycle_data: 周期数据字典，如果为None则从runner获取
        """
        if cycle_data is None:
            cycle_data = self.runner.get_all_params()
        
        # 添加时间戳
        # 优先使用真实时间戳（数据生成模式），否则使用相对时间
        datetime_str = self.runner.clock.get_current_datetime_string()
        if datetime_str:
            record = {
                'datetime': datetime_str,
                'time': self.runner.clock.get_current_time(),
                **cycle_data
            }
            logger.debug(f"Data recorded at datetime={datetime_str}")
        else:
            record = {
                'time': self.runner.clock.get_current_time(),
                **cycle_data
            }
            logger.debug(f"Data recorded at time={record['time']:.2f}s")
        
        self.data_history.append(record)
    
    def export_to_excel(self, file_path: str):
        """
        导出数据到Excel文件
        
        Args:
            file_path: Excel文件路径
        """
        if not self.data_history:
            logger.warning("No data to export")
            return
        
        # 转换为DataFrame
        df = pd.DataFrame(self.data_history)
        
        # 导出到Excel
        df.to_excel(file_path, index=False, engine='openpyxl')
        logger.info(f"Data exported to {file_path}, total records: {len(self.data_history)}")
    
    def export_to_csv(
        self,
        file_path: str,
        tag_names: Optional[List[str]] = None,
        tag_descriptions: Optional[Dict[str, str]] = None
    ):
        """
        导出数据到CSV文件
        
        格式：
        - 第一行：Timestamp 和一系列需要输出的位号名
        - 第二行：时间戳 对应位号名的位号描述
        - 从第三行开始：数据行
        
        Args:
            file_path: CSV文件路径
            tag_names: 要导出的位号名列表（格式：设备名.后缀名），如果为None则导出所有参数
            tag_descriptions: 位号名的中文解释字典，key为位号名，value为描述
        """
        if not self.data_history:
            logger.warning("No data to export")
            return
        
        # 确定要导出的列
        if tag_names is None:
            # 导出所有列
            all_keys = set()
            for record in self.data_history:
                all_keys.update(record.keys())
            # 确保datetime或time在第一列
            if 'datetime' in all_keys:
                columns = ['datetime'] + sorted([k for k in all_keys if k != 'datetime'])
            elif 'time' in all_keys:
                columns = ['time'] + sorted([k for k in all_keys if k != 'time'])
            else:
                columns = sorted(all_keys)
        else:
            # 只导出指定的列
            # 确保时间戳在第一列
            if 'datetime' in tag_names:
                columns = ['datetime'] + [k for k in tag_names if k != 'datetime']
            elif 'time' in tag_names:
                columns = ['time'] + [k for k in tag_names if k != 'time']
            else:
                columns = tag_names
        
        # 准备描述行
        description_row = []
        if tag_descriptions:
            for col in columns:
                description_row.append(tag_descriptions.get(col, ''))
        else:
            # 如果没有提供描述，使用默认描述或空字符串
            for col in columns:
                description_row.append('')
        
        # 准备数据
        data_rows = []
        for record in self.data_history:
            row = []
            for col in columns:
                if col in record:
                    row.append(record[col])
                else:
                    row.append('')
            data_rows.append(row)
        
        # 写入CSV文件
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            # 第一行：标题行（Timestamp、位号名）
            # 将第一列改为Timestamp（如果是datetime或time）
            header_columns = columns.copy()
            if header_columns[0] == 'datetime' or header_columns[0] == 'time':
                header_columns[0] = 'Timestamp'
            writer.writerow(header_columns)
            # 第二行：描述行（时间戳、位号描述）
            writer.writerow(description_row)
            # 从第三行开始：数据行
            writer.writerows(data_rows)
        
        logger.info(f"Data exported to {file_path}, total records: {len(self.data_history)}")
    
    def clear_history(self):
        """清空历史数据"""
        self.data_history.clear()
        logger.info("Data history cleared")
    
    def get_history(self) -> List[Dict[str, Any]]:
        """
        获取历史数据
        
        Returns:
            历史数据列表
        """
        return self.data_history.copy()

