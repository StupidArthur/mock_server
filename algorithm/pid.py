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
    
    # 数值精度阈值
    EPSILON = 1e-9
    
    def __init__(
        self,
        name: str = "PID",
        kp: float = 12.0,
        ti: float = 30.0,
        td: float = 0.15,
        pv: float = 0.0,
        sv: float = 0.0,
        mv: float = 0.0,
        h: float = 100.0,
        l: float = 0.0,
        sample_time: float = 0.5,
        mode: int = 1
    ):
        """
        初始化PID算法
        
        Args:
            name: 算法名称，默认"PID"
            kp: 比例系数，默认12.0（优化后，加快响应）
            ti: 积分时间（秒），默认30.0秒（优化后，加快积分作用）
            td: 微分时间（秒），默认0.15秒（优化后，抑制超调）
            pv: 过程变量（Process Value），默认0.0
            sv: 设定值（Set Value），默认0.0
            mv: 输出值（Manipulated Value），默认0.0
            h: 输出上限，默认100.0
            l: 输出下限，默认0.0
            sample_time: 采样周期（秒），默认0.5秒（500ms）
            mode: 运行模式，默认1（自动模式），0=手动模式
        
        Raises:
            ValueError: 如果参数无效
        """
        # 参数验证
        if sample_time <= 0:
            raise ValueError(f"sample_time must be positive, got {sample_time}")
        if h <= l:
            raise ValueError(f"Output upper limit h ({h}) must be greater than lower limit l ({l})")
        if ti < 0:
            raise ValueError(f"Integral time ti cannot be negative, got {ti}")
        if td < 0:
            raise ValueError(f"Derivative time td cannot be negative, got {td}")
        if mode not in [0, 1]:
            raise ValueError(f"Mode must be 0 (manual) or 1 (auto), got {mode}")
        
        initial_config = {
            'kp': kp,
            'ti': ti,
            'td': td,
            'h': h,
            'l': l,
            'sample_time': sample_time
        }
        initial_input = {
            'pv': pv,
            'sv': sv
        }
        initial_output = {
            'mv': mv,
            'mode': mode
        }
        
        super().__init__(name, initial_config, initial_input, initial_output)
        
        # PID内部状态
        self.last_error = 0.0
        self.integral = 0.0
        self._first_run = True  # 标记是否为首次执行
        
        # 计算积分项的最大值限制（防止积分饱和）
        # 积分项最大值 = (输出上限 - 输出下限) * ti / kp
        # 但考虑到比例项和微分项，实际限制应该更宽松
        if ti > self.EPSILON and kp > self.EPSILON:
            max_integral_term = (h - l) * ti / kp
            self.max_integral = max_integral_term * ti / sample_time if sample_time > self.EPSILON else float('inf')
        else:
            self.max_integral = float('inf')
        
        logger.info(
            f"PID '{name}' initialized: kp={kp}, ti={ti}s, td={td}s, "
            f"output_range=[{l}, {h}], sample_time={sample_time}s"
        )
    
    def execute(self, input_params: dict = None, config_params: dict = None):
        """
        执行PID算法运算
        
        Args:
            input_params: 输入参数字典，包含PV和SV
            config_params: 配置参数字典，包含kp, ti, td
        
        Returns:
            全量参数字典（kp, ti, td, PV, SV, MV）
        """
        # 更新配置参数
        if config_params is not None:
            if 'kp' in config_params:
                self.config['kp'] = config_params['kp']
            if 'ti' in config_params:
                self.config['ti'] = config_params['ti']
            if 'td' in config_params:
                self.config['td'] = config_params['td']
        
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
        ti = self.config['ti']
        td = self.config['td']
        sample_time = self.config['sample_time']
        h = self.config['h']
        l = self.config['l']
        
        # 参数验证（防止运行时修改导致无效参数）
        if sample_time <= 0:
            logger.error(f"Invalid sample_time={sample_time}, using previous value")
            sample_time = self.EPSILON  # 使用最小值避免除零
        
        # 计算误差
        error = sv - pv
        
        # 比例项
        p_term = kp * error
        
        # 积分项（使用矩形积分）
        if ti > self.EPSILON:
            # 计算积分增量
            integral_increment = error * sample_time
            
            # 更新积分值
            self.integral += integral_increment
            
            # 限制积分项的最大值（防止积分饱和）
            if self.max_integral != float('inf'):
                max_integral_value = self.max_integral
                self.integral = max(-max_integral_value, min(max_integral_value, self.integral))
            
            # 计算积分项
            i_term = (kp / ti) * self.integral
        else:
            i_term = 0.0
            integral_increment = 0.0
        
        # 微分项
        if self._first_run:
            # 首次执行时，last_error=0，避免微分项突变
            d_term = 0.0
            self._first_run = False
        else:
            # 计算误差变化率
            error_diff = error - self.last_error
            if sample_time > self.EPSILON:
                d_term = (kp * td) * error_diff / sample_time
            else:
                d_term = 0.0
        
        # 计算未限幅的输出
        mv_unlimited = p_term + i_term + d_term
        
        # 限制输出范围
        mv = max(l, min(h, mv_unlimited))
        
        # 积分抗饱和（Anti-Windup）：如果输出达到限幅，且误差与输出方向一致，则停止积分累积
        if ti > self.EPSILON:
            if mv >= h and error > 0:
                # 输出达到上限，且误差为正（需要增大输出），停止积分累积
                self.integral -= integral_increment
                i_term = (kp / ti) * self.integral
                # 重新计算输出（考虑修正后的积分项）
                mv = max(l, min(h, p_term + i_term + d_term))
            elif mv <= l and error < 0:
                # 输出达到下限，且误差为负（需要减小输出），停止积分累积
                self.integral -= integral_increment
                i_term = (kp / ti) * self.integral
                # 重新计算输出（考虑修正后的积分项）
                mv = max(l, min(h, p_term + i_term + d_term))
        
        # 更新输出
        self.output['mv'] = mv
        # mode参数始终为1
        self.output['mode'] = 1
        
        # 保存当前误差用于下次计算
        self.last_error = error
        
        logger.debug(
            f"PID '{self.name}' execute: pv={pv:.4f}, sv={sv:.4f}, "
            f"error={error:.4f}, mv={mv:.4f}"
        )
        
        return self.get_all_params()
    
    def get_storable_params(self) -> dict:
        """
        获取需要存储到历史数据库的参数
        
        只返回运行时变化的参数：
        - kp: 比例系数（配置参数，但可能在运行时调整）
        - ti: 积分时间（配置参数，但可能在运行时调整）
        - td: 微分时间（配置参数，但可能在运行时调整）
        - pv: 过程变量（输入参数）
        - sv: 设定值（输入参数）
        - mv: 输出值（输出参数）
        
        Returns:
            需要存储的参数字典
        """
        return {
            'kp': self.config.get('kp', 0.0),
            'ti': self.config.get('ti', 0.0),
            'td': self.config.get('td', 0.0),
            'pv': self.input.get('pv', 0.0),
            'sv': self.input.get('sv', 0.0),
            'mv': self.output.get('mv', 0.0)
        }

