"""
控制算法基类
"""
from abc import ABC, abstractmethod
from utils.logger import get_logger

logger = get_logger()


class BaseAlgorithm(ABC):
    """
    控制算法基类
    
    所有控制算法都继承自此类，实现execute方法进行算法运算
    """
    
    def __init__(
        self,
        name: str = "algorithm",
        initial_config: dict = None,
        initial_input: dict = None,
        initial_output: dict = None
    ):
        """
        初始化基础算法
        
        Args:
            name: 算法名称，默认"algorithm"
            initial_config: 初始配置参数，默认空字典
            initial_input: 初始输入参数，默认空字典
            initial_output: 初始输出参数，默认空字典
        """
        self.name = name
        self.config = initial_config if initial_config is not None else {}
        self.input = initial_input if initial_input is not None else {}
        self.output = initial_output if initial_output is not None else {}
        
        logger.debug(f"BaseAlgorithm '{name}' initialized")
    
    @abstractmethod
    def execute(self, input_params: dict = None, config_params: dict = None):
        """
        执行算法运算
        
        Args:
            input_params: 输入参数字典
            config_params: 配置参数字典
        
        Returns:
            全量参数字典（包含配置参数、输入参数、输出参数）
        """
        pass
    
    def get_all_params(self):
        """
        获取全量参数
        
        Returns:
            包含config、input、output的字典
        """
        return {
            'config': self.config.copy(),
            'input': self.input.copy(),
            'output': self.output.copy()
        }
    
    def get_storable_params(self) -> dict:
        """
        获取需要存储到历史数据库的参数（运行时变化的参数）
        
        默认实现返回空字典，子类应重写此方法，只返回需要存储的参数
        例如：对于PID算法，应返回kp, ti, td, pv, sv, mv等运行时可能变化的参数
        
        Returns:
            需要存储的参数字典
        """
        return {}

