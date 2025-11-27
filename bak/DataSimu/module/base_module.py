"""
物理模型基类
"""
from abc import ABC, abstractmethod
from utils.logger import get_logger

logger = get_logger()


class BaseModule(ABC):
    """
    物理模型基类
    
    所有物理模型都继承自此类，实现execute方法进行过程模拟
    """
    
    def __init__(self, step: float = 0.1):
        """
        初始化基类模型
        
        Args:
            step: 步进时间（秒），默认0.1秒
        """
        self.step = step
        logger.debug(f"BaseModule initialized with step={step}")
    
    @abstractmethod
    def execute(self, *args, step: float = None):
        """
        执行模型计算
        
        Args:
            *args: 运行输入参数
            step: 步进时间，如果为None则使用实例化时的step值
        
        Returns:
            模型输出参数
        """
        pass

