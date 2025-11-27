"""
数据模拟模块
基于组态模板运行模块，非阻塞地运行，输出Excel或CSV数据
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from plc.runner import Runner
from plc.data_exporter import DataExporter
from plc.configuration import Configuration
from utils.logger import get_logger

logger = get_logger()


class DataSimulator:
    """
    数据模拟模块
    
    基于组态模板运行模块，非阻塞地运行，输出Excel数据
    支持基于起始时间和结束时间的数据生成模式
    """
    
    def __init__(self, configuration: Configuration):
        """
        初始化数据模拟器
        
        Args:
            configuration: 组态模板实例
        """
        self.config = configuration
        self.runner = Runner(configuration)
        self.exporter = DataExporter(self.runner)
        self.is_running = False
        
        logger.info("DataSimulator initialized")
    
    def run(
        self,
        duration: float = None,
        output_file: str = "simulation_data.xlsx",
        tag_names: Optional[List[str]] = None,
        tag_descriptions: Optional[Dict[str, str]] = None
    ):
        """
        运行模拟
        
        Args:
            duration: 模拟持续时间（秒），如果配置了start_datetime和end_datetime则忽略此参数
            output_file: 输出Excel文件路径
        """
        self.is_running = True
        self.runner.clock.start()
        
        # 检查是否使用数据生成模式（基于起始时间和结束时间）
        start_datetime = self.config.get_start_datetime()
        end_datetime = self.config.get_end_datetime()
        sample_interval = self.config.get_sample_interval()
        
        if start_datetime and end_datetime:
            # 数据生成模式：基于真实时间戳
            try:
                start_dt = datetime.strptime(start_datetime, "%Y-%m-%d %H:%M:%S")
                end_dt = datetime.strptime(end_datetime, "%Y-%m-%d %H:%M:%S")
                total_duration = (end_dt - start_dt).total_seconds()
                samples = int(total_duration / sample_interval)
                
                logger.info(f"DataSimulator started in data generation mode")
                logger.info(f"Start datetime: {start_datetime}, End datetime: {end_datetime}")
                logger.info(f"Sample interval: {sample_interval}s, Total samples: {samples}")
                
                for i in range(samples):
                    if not self.is_running:
                        break
                    
                    # 执行一个周期（使用采样间隔）
                    self.runner.clock.step_sample()
                    # 在数据生成模式下，时间已经在step_sample()中步进，所以不需要在execute_one_cycle中再次步进
                    cycle_data = self.runner.execute_one_cycle(step_clock=False)
                    
                    # 记录数据（包含真实时间戳）
                    self.exporter.record(cycle_data)
                    
                    if (i + 1) % 100 == 0:
                        current_dt = self.runner.clock.get_current_datetime_string()
                        logger.info(f"Simulation progress: {i+1}/{samples} samples, current datetime: {current_dt}")
                
            except ValueError as e:
                logger.error(f"Invalid datetime format: {e}")
                return
        else:
            # 传统模式：基于持续时间
            if duration is None:
                duration = 60.0
            
            logger.info(f"DataSimulator started, duration={duration}s")
            
            cycles = int(duration / self.config.get_cycle_time())
            
            for i in range(cycles):
                if not self.is_running:
                    break
                
                # 执行一个周期
                cycle_data = self.runner.execute_one_cycle()
                
                # 记录数据
                self.exporter.record(cycle_data)
                
                if (i + 1) % 100 == 0:
                    logger.info(f"Simulation progress: {i+1}/{cycles} cycles")
        
        # 导出数据
        # 根据文件扩展名决定导出格式
        if output_file.endswith('.csv'):
            # CSV格式导出
            self.exporter.export_to_csv(output_file, tag_names, tag_descriptions)
        else:
            # Excel格式导出
            self.exporter.export_to_excel(output_file)
        
        self.is_running = False
        self.runner.clock.stop()
        
        logger.info(f"DataSimulator completed, data exported to {output_file}")
    
    def stop(self):
        """停止模拟"""
        self.is_running = False
        logger.info("DataSimulator stopped")

