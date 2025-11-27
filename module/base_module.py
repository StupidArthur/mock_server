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
    
    def __init__(self, step: float = 0.5):
        """
        初始化基类模型
        
        Args:
            step: 步进时间（秒），默认0.5秒（500ms）
        """
        self.step = step
        logger.debug(f"BaseModule initialized with step={step}")
    
    @abstractmethod
    def execute(self, step: float = None):
        """
        执行模型计算
        
        输入参数从实例属性中读取（通过连接关系设置）。
        模型应该从自己的属性中读取输入参数，而不是通过方法参数传递。
        
        Args:
            step: 步进时间，如果为None则使用实例化时的step值
        
        Returns:
            模型输出参数
        """
        pass
    
    def get_params(self):
        """
        获取模型的所有参数
        
        Returns:
            参数字典
        """
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
    
    def get_storable_params(self):
        """
        获取需要存储到历史数据库的参数（运行时变化的参数）
        
        默认实现返回空字典，子类应重写此方法，只返回需要存储的参数
        例如：状态参数、输入参数等运行时变化的参数
        
        Returns:
            需要存储的参数字典
        """
        return {}

