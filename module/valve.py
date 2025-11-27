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
    
    # 阀门开度精度（%）
    PRECISION = 0.01
    
    def __init__(
        self,
        min_opening: float = 0.0,
        max_opening: float = 100.0,
        step: float = 0.5,
        full_travel_time: float = 5.0
    ):
        """
        初始化阀门模型
        
        Args:
            min_opening: 控制下限（%），默认0.0%
            max_opening: 控制上限（%），默认100.0%
            step: 步进时间（秒），默认0.5秒（500ms）
            full_travel_time: 满行程达成时间（秒），默认5.0秒
        
        Raises:
            ValueError: 如果参数不合法
        """
        # 参数验证
        if min_opening >= max_opening:
            raise ValueError(
                f"min_opening ({min_opening}) must be less than max_opening ({max_opening})"
            )
        if full_travel_time <= 0:
            raise ValueError(
                f"full_travel_time must be positive, got {full_travel_time}"
            )
        if step <= 0:
            raise ValueError(f"step must be positive, got {step}")
        
        super().__init__(step)
        self.min_opening = min_opening
        self.max_opening = max_opening
        self.full_travel_time = full_travel_time
        self.current_opening = min_opening
        self.target_opening = min_opening
        
        logger.info(
            f"Valve initialized: range=[{min_opening}, {max_opening}], "
            f"full_travel_time={full_travel_time}s"
        )
    
    def execute(self, step: float = None) -> float:
        """
        执行阀门模型计算
        
        输入参数从实例属性中读取：
        - target_opening: 控制目标值（开度，%），范围由min_opening和max_opening决定
          通过连接关系设置到 self.target_opening 属性
        
        Args:
            step: 步进时间，如果为None则使用实例化时的step值
        
        Returns:
            当前阀门开度（%）
        """
        if step is None:
            step = self.step
        
        # 验证step参数
        if step <= 0:
            raise ValueError(f"step must be positive, got {step}")
        
        # 从属性读取输入参数（通过连接关系设置）
        # target_opening 属性已经通过连接关系设置，直接使用
        target_opening = self.target_opening
        
        # 限制目标开度范围
        target_opening = max(self.min_opening, min(self.max_opening, target_opening))
        self.target_opening = target_opening
        
        # 计算开度差
        opening_diff = target_opening - self.current_opening
        
        # 如果开度差小于精度阈值，直接设置为目标值，避免无限接近但无法达到
        if abs(opening_diff) < self.PRECISION:
            self.current_opening = target_opening
            return self.current_opening
        
        # 计算行程速度（开度/秒）
        # 满行程时间对应从min到max的开度变化
        travel_range = self.max_opening - self.min_opening
        # full_travel_time已在初始化时验证，这里不会除零
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
            f"current_opening={self.current_opening:.4f}, change={change:.6f}"
        )
        
        return self.current_opening
    
    def get_storable_params(self) -> dict:
        """
        获取需要存储到历史数据库的参数
        
        只返回运行时变化的参数：
        - current_opening: 当前开度（状态参数）
        - target_opening: 目标开度（输入参数）
        
        Returns:
            需要存储的参数字典
        """
        return {
            'current_opening': self.current_opening,
            'target_opening': self.target_opening
        }

