"""
阀门模型
实现阀门开度的线性行程过程
"""
from module.base_module import BaseModule
from utils.logger import get_logger

logger = get_logger()


class Valve(BaseModule):
    """
    阀门模型
    
    物理模型：当阀门给予一个控制目标值的时候，并不是瞬间就能达成的，
    而是根据当前开度和目标开度有一个线性的行程过程
    """
    
    def __init__(
        self,
        min_opening: float = 0.0,
        max_opening: float = 100.0,
        step: float = 0.1,
        full_travel_time: float = 20.0
    ):
        """
        初始化阀门模型
        
        Args:
            min_opening: 控制下限（%），默认0.0%
            max_opening: 控制上限（%），默认100.0%
            step: 步进时间（秒），默认0.1秒
            full_travel_time: 满行程达成时间（秒），默认20.0秒
        """
        super().__init__(step)
        self.min_opening = min_opening
        self.max_opening = max_opening
        self.full_travel_time = full_travel_time
        self.current_opening = min_opening
        self.target_opening = min_opening
        
        # 阀门开度精度（%）
        self.precision = 0.01
        
        logger.info(
            f"Valve initialized: range=[{min_opening}, {max_opening}], "
            f"full_travel_time={full_travel_time}s"
        )
    
    def execute(self, target_opening: float, step: float = None):
        """
        执行阀门模型计算
        
        Args:
            target_opening: 控制目标值（开度，%），范围0~100
            step: 步进时间，如果为None则使用实例化时的step值
        
        Returns:
            当前阀门开度（%）
        """
        if step is None:
            step = self.step
        
        # 限制目标开度范围
        target_opening = max(self.min_opening, min(self.max_opening, target_opening))
        self.target_opening = target_opening
        
        # 计算开度差
        opening_diff = target_opening - self.current_opening
        
        # 如果开度差小于精度，直接返回当前开度
        if abs(opening_diff) < self.precision:
            self.current_opening = target_opening
            return self.current_opening
        
        # 计算行程速度（开度/秒）
        # 满行程时间对应从min到max的开度变化
        travel_range = self.max_opening - self.min_opening
        travel_speed = travel_range / self.full_travel_time
        
        # 计算本次步进的开度变化
        max_change = travel_speed * step
        
        # 根据目标开度方向决定变化量
        if opening_diff > 0:
            change = min(max_change, opening_diff)
        else:
            change = max(-max_change, opening_diff)
        
        # 更新当前开度
        self.current_opening += change
        
        # 限制开度范围
        self.current_opening = max(self.min_opening, min(self.max_opening, self.current_opening))
        
        logger.debug(
            f"Valve execute: target={target_opening:.4f}, "
            f"current={self.current_opening:.4f}, change={change:.6f}"
        )
        
        return self.current_opening

