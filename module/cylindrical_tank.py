"""
圆柱体水箱模型
基于托里拆利定律实现液位动态计算
"""
import math
from module.base_module import BaseModule
from utils.logger import get_logger

logger = get_logger()


class CylindricalTank(BaseModule):
    """
    圆柱体水箱模型
    
    物理模型：一个圆柱体的水箱，在水箱最高同高的地方有一个圆形的入水管口，
    由一个阀门（0~100%）控制，在水箱最低的地方有一个圆形的出水口，一直在出水，
    出水的流量与当前水位高度相关（根据托里拆利定律）
    """
    
    # 重力加速度（米/秒²）
    GRAVITY = 9.81
    
    def __init__(
        self,
        height: float = 2.0,
        radius: float = 0.5,
        inlet_area: float = 0.06,
        inlet_velocity: float = 3.0,
        outlet_area: float = 0.001,
        initial_level: float = 0.0,
        step: float = 0.5
    ):
        """
        初始化圆柱体水箱模型
        
        Args:
            height: 水箱高度（米），默认2.0米（优化后）
            radius: 水箱半径（米），默认0.5米（优化后，加快响应）
            inlet_area: 水箱入水管（圆形）满开面积（平方米），默认0.06平方米（优化后，增大入水流量）
            inlet_velocity: 入水口水流速（米/秒），默认3.0米/秒（优化后，加快入水）
            outlet_area: 水箱出水口面积（平方米），默认0.001平方米（优化后）
            initial_level: 初始水位高度（米），默认0.0米
            step: 步进时间（秒），默认0.5秒（500ms）
        """
        super().__init__(step)
        self.height = height
        self.radius = radius
        self.inlet_area = inlet_area
        self.inlet_velocity = inlet_velocity
        self.outlet_area = outlet_area
        self.level = initial_level
        
        # 记录最后一次的输入参数值（用于历史数据存储）
        self.valve_opening = 0.0
        
        # 水箱底面积
        self.base_area = math.pi * radius ** 2
        
        logger.info(
            f"CylindricalTank initialized: height={height}, radius={radius}, "
            f"initial_level={initial_level}"
        )
    
    def execute(self, step: float = None):
        """
        执行水箱模型计算
        
        输入参数从实例属性中读取：
        - valve_opening: 入水管阀门开度（%），范围0~100
          通过连接关系设置到 self.valve_opening 属性
        
        Args:
            step: 步进时间，如果为None则使用实例化时的step值
        
        Returns:
            水箱液位高度（米）
        """
        if step is None:
            step = self.step
        
        # 从属性读取输入参数（通过连接关系设置）
        valve_opening = getattr(self, 'valve_opening', 0.0)
        
        # 限制阀门开度范围（%）
        valve_opening = max(0.0, min(100.0, valve_opening))
        
        # 转换为0~1的比例用于计算
        valve_opening_ratio = valve_opening / 100.0
        
        # 计算入水流量（立方米/秒）
        # Q_in = A_inlet * v_inlet * valve_opening_ratio
        inlet_flow = self.inlet_area * self.inlet_velocity * valve_opening_ratio
        
        # 计算出水流量（立方米/秒）
        # 根据托里拆利定律：v = sqrt(2gh)
        # Q_out = A_outlet * v_outlet = A_outlet * sqrt(2gh)
        if self.level > 0:
            outlet_velocity = math.sqrt(2 * self.GRAVITY * self.level)
            outlet_flow = self.outlet_area * outlet_velocity
        else:
            outlet_flow = 0.0
        
        # 计算净流量
        net_flow = inlet_flow - outlet_flow
        
        # 计算水位变化
        volume_change = net_flow * step
        level_change = volume_change / self.base_area
        
        # 更新水位
        self.level += level_change
        
        # 限制水位范围
        self.level = max(0.0, min(self.height, self.level))
        
        logger.debug(
            f"CylindricalTank execute: valve_opening={valve_opening:.4f}, "
            f"level={self.level:.4f}, inlet_flow={inlet_flow:.6f}, "
            f"outlet_flow={outlet_flow:.6f}"
        )
        
        return self.level
    
    def get_storable_params(self):
        """
        获取需要存储到历史数据库的参数
        
        只返回运行时变化的参数：
        - level: 液位高度（状态参数）
        - valve_opening: 入水管阀门开度（输入参数）
        
        Returns:
            需要存储的参数字典
        """
        return {
            'level': self.level,
            'valve_opening': self.valve_opening
        }

