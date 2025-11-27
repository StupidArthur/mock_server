"""
时钟模块
管理系统的运行周期
"""
import time
from utils.logger import get_logger

logger = get_logger()


class Clock:
    """
    时钟模块
    
    管理系统的运行周期，提供时间步进和同步功能
    """
    
    # PLC运行周期（秒），默认500ms
    DEFAULT_CYCLE_TIME = 0.5
    
    def __init__(self, cycle_time: float = DEFAULT_CYCLE_TIME):
        """
        初始化时钟模块
        
        Args:
            cycle_time: 运行周期（秒），默认0.5秒（500ms）
        """
        self.cycle_time = cycle_time
        self.current_time = 0.0
        self.start_time = None
        self.is_running = False
        
        logger.info(f"Clock initialized with cycle_time={cycle_time}s")
    
    def start(self):
        """启动时钟"""
        if not self.is_running:
            self.start_time = time.time()
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
        
        return self.current_time
    
    def get_current_time(self):
        """
        获取当前时间（秒）
        
        Returns:
            当前时间（秒）
        """
        return self.current_time
    
    def sleep_to_next_cycle(self):
        """
        睡眠到下一个周期（用于实时运行）
        """
        # 正常模式：等待一个周期时间
        if self.cycle_time > 0:
            time.sleep(self.cycle_time)
