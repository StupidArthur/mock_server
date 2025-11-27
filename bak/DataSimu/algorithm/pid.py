"""
PID控制算法
"""
from algorithm.base_algorithm import BaseAlgorithm
from utils.logger import get_logger

logger = get_logger()


class PID(BaseAlgorithm):
    """
    PID控制算法
    
    通用的PID（比例-积分-微分）控制算法
    """
    
    def __init__(
        self,
        name: str = "PID",
        kp: float = 1.0,
        Ti: float = 10.0,
        Td: float = 0.1,
        pv: float = 0.0,
        sv: float = 0.0,
        mv: float = 0.0,
        h: float = 100.0,
        l: float = 0.0,
        T: float = 0.1
    ):
        """
        初始化PID算法
        
        Args:
            name: 算法名称，默认"PID"
            kp: 比例系数，默认1.0
            Ti: 积分时间（秒），默认10.0秒（值越小，积分作用越强）
            Td: 微分时间（秒），默认0.1秒（值越大，微分作用越强）
            pv: 过程变量（Process Value），默认0.0
            sv: 设定值（Set Value），默认0.0
            mv: 输出值（Manipulated Value），默认0.0
            h: 输出上限，默认100.0
            l: 输出下限，默认0.0
            T: 采样周期（秒），默认0.1秒
        """
        initial_config = {
            'kp': kp,
            'Ti': Ti,
            'Td': Td,
            'h': h,
            'l': l,
            'T': T
        }
        initial_input = {
            'pv': pv,
            'sv': sv
        }
        initial_output = {
            'mv': mv,
            'MODE': 1  # MODE参数，默认值为1
        }
        
        super().__init__(name, initial_config, initial_input, initial_output)
        
        # PID内部状态
        self.last_error = 0.0
        self.integral = 0.0
        
        logger.info(
            f"PID '{name}' initialized: kp={kp}, Ti={Ti}s, Td={Td}s, "
            f"output_range=[{l}, {h}]"
        )
    
    def execute(self, input_params: dict = None, config_params: dict = None):
        """
        执行PID算法运算
        
        Args:
            input_params: 输入参数字典，包含pv和sv
            config_params: 配置参数字典，包含kp, Ti, Td
        
        Returns:
            全量参数字典（kp, Ti, Td, pv, sv, mv）
        """
        # 更新配置参数
        if config_params is not None:
            if 'kp' in config_params:
                self.config['kp'] = config_params['kp']
            if 'Ti' in config_params:
                self.config['Ti'] = config_params['Ti']
            if 'Td' in config_params:
                self.config['Td'] = config_params['Td']
        
        # 更新输入参数
        if input_params is not None:
            if 'pv' in input_params:
                self.input['pv'] = input_params['pv']
            if 'sv' in input_params:
                self.input['sv'] = input_params['sv']
        
        # 获取当前值
        pv = self.input['pv']
        sv = self.input['sv']
        kp = self.config['kp']
        Ti = self.config['Ti']
        Td = self.config['Td']
        T = self.config['T']
        h = self.config['h']
        l = self.config['l']
        
        # 计算误差
        error = sv - pv
        
        # 比例项
        p_term = kp * error
        
        # 积分项（使用梯形积分）
        # 时间形式：i_term = (kp / Ti) * integral
        # self.integral += (error + self.last_error) * T / 2.0
        self.integral += error * T
        if Ti > 0:
            i_term = (kp / Ti) * self.integral
        else:
            i_term = 0.0
        
        # 微分项
        # 时间形式：d_term = (kp * Td) * (error - last_error) / T
        d_term = (kp * Td) * (error - self.last_error) / T
        
        # 计算输出
        mv = p_term + i_term + d_term
        
        # 限制输出范围
        mv = max(l, min(h, mv))
        
        # 更新输出
        self.output['mv'] = mv
        # MODE参数始终为1
        self.output['MODE'] = 1
        
        # 保存当前误差用于下次计算
        self.last_error = error
        
        logger.debug(
            f"PID '{self.name}' execute: pv={pv:.4f}, sv={sv:.4f}, "
            f"error={error:.4f}, mv={mv:.4f}"
        )
        
        return self.get_all_params()

