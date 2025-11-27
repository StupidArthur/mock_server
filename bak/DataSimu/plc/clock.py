"""
时钟模块
管理系统的运行周期
"""
import time
from datetime import datetime, timedelta
from typing import Optional
from utils.logger import get_logger

logger = get_logger()


class Clock:
    """
    时钟模块
    
    管理系统的运行周期，提供时间步进和同步功能
    支持真实时间戳生成（用于数据生成模式）
    """
    
    def __init__(
        self,
        cycle_time: float = 0.1,
        start_datetime: Optional[str] = None,
        sample_interval: Optional[float] = None
    ):
        """
        初始化时钟模块
        
        Args:
            cycle_time: 运行周期（秒），默认0.1秒
            start_datetime: 起始时间（格式：YYYY-MM-DD HH:MM:SS），用于数据生成模式
            sample_interval: 数据采样时间间隔（秒），用于数据生成模式
        """
        self.cycle_time = cycle_time
        self.current_time = 0.0
        self.start_time = None
        self.is_running = False
        
        # 数据生成模式的时间配置
        self.start_datetime = None
        self.sample_interval = sample_interval if sample_interval else cycle_time
        self.current_datetime = None
        
        if start_datetime:
            try:
                self.start_datetime = datetime.strptime(start_datetime, "%Y-%m-%d %H:%M:%S")
                self.current_datetime = self.start_datetime
                logger.info(f"Clock initialized with start_datetime={start_datetime}, sample_interval={self.sample_interval}s")
            except ValueError:
                logger.warning(f"Invalid start_datetime format: {start_datetime}, expected: YYYY-MM-DD HH:MM:SS")
        else:
            logger.info(f"Clock initialized with cycle_time={cycle_time}s")
    
    def start(self):
        """启动时钟"""
        self.start_time = time.time()
        self.current_time = 0.0
        self.is_running = True
        logger.info("Clock started")
    
    def stop(self):
        """停止时钟"""
        self.is_running = False
        logger.info(f"Clock stopped at time={self.current_time:.2f}s")
    
    def step(self):
        """
        步进一个周期
        
        Returns:
            当前时间（秒）
        """
        if not self.is_running:
            self.start()
        
        self.current_time += self.cycle_time
        
        # 如果启用了数据生成模式，更新真实时间戳
        if self.start_datetime and self.current_datetime:
            self.current_datetime += timedelta(seconds=self.cycle_time)
        
        return self.current_time
    
    def get_current_time(self):
        """
        获取当前时间（秒）
        
        Returns:
            当前时间（秒）
        """
        return self.current_time
    
    def get_current_datetime_string(self) -> Optional[str]:
        """
        获取当前真实时间戳字符串（用于数据生成模式）
        
        Returns:
            时间戳字符串（格式：YYYY-MM-DD HH:MM:SS），如果未启用数据生成模式则返回None
        """
        if self.current_datetime:
            return self.current_datetime.strftime("%Y/%m/%d %H:%M:%S")
        return None
    
    def step_sample(self):
        """
        步进一个采样周期（用于数据生成模式）
        
        Returns:
            当前时间（秒）
        """
        if not self.is_running:
            self.start()
        
        self.current_time += self.sample_interval
        
        # 更新真实时间戳
        if self.start_datetime and self.current_datetime:
            self.current_datetime += timedelta(seconds=self.sample_interval)
        
        return self.current_time
    
    def sleep_to_next_cycle(self):
        """睡眠到下一个周期（用于实时运行）"""
        if self.start_time is not None:
            elapsed = time.time() - self.start_time
            expected_time = self.current_time
            sleep_time = expected_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

