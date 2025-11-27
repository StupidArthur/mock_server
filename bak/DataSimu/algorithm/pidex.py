"""
PID扩展控制算法
在PID基础上添加性能指标和扩展功能
"""
import random
import math
from algorithm.base_algorithm import BaseAlgorithm
from utils.logger import get_logger

logger = get_logger()


class PIDEX(BaseAlgorithm):
    """
    PID扩展控制算法
    
    在PID控制算法基础上，添加以下功能：
    - 设定值滤波（一阶低通滤波）
    - 测量噪声
    - 性能指标计算（稳态误差、超调量、调节时间）
    """
    
    def __init__(
        self,
        name: str = "PIDEX",
        kp: float = 1.0,
        Ti: float = 10.0,
        Td: float = 0.1,
        pv: float = 0.0,
        sv: float = 0.0,
        mv: float = 0.0,
        h: float = 100.0,
        l: float = 0.0,
        T: float = 0.1,
        Tf: float = 0.0,
        noise_level: float = 0.0,
        Ts: float = 5.0
    ):
        """
        初始化PIDEX算法
        
        Args:
            name: 算法名称，默认"PIDEX"
            kp: 比例系数，默认1.0
            Ti: 积分时间（秒），默认10.0秒
            Td: 微分时间（秒），默认0.1秒
            pv: 过程变量（Process Value），默认0.0
            sv: 设定值（Set Value），默认0.0
            mv: 输出值（Manipulated Value），默认0.0
            h: 输出上限，默认100.0
            l: 输出下限，默认0.0
            T: 采样周期（秒），默认0.1秒
            Tf: 设定值滤波时间常数（秒），默认0.0（无滤波）
            noise_level: 测量噪声水平（标准差），默认0.0（无噪声）
            Ts: 采样时间（秒），默认5.0秒
        """
        initial_config = {
            'kp': kp,
            'Ti': Ti,
            'Td': Td,
            'h': h,
            'l': l,
            'T': T,
            'Tf': Tf,
            'noise_level': noise_level,
            'Ts': Ts
        }
        initial_input = {
            'pv': pv,
            'sv': sv
        }
        initial_output = {
            'mv': mv,
            'MODE': 1,
            'Ess': 0.0,
            'OverShoot': 0.0,
            'SettlingTime': 0.0,
            'OutputRange': f"[{l}, {h}]",
            'NoiseLevel': noise_level,
            'Tf': Tf,
            'RampRate': 0.0,
            'Ts': Ts
        }
        
        super().__init__(name, initial_config, initial_input, initial_output)
        
        # PID内部状态
        self.last_error = 0.0
        self.integral = 0.0
        
        # 设定值滤波状态
        self.filtered_sv = sv
        
        # 设定值变化率计算相关状态
        self.last_sv = sv  # 上一次的设定值
        self.last_sv_time = 0.0  # 上一次设定值的时间
        
        # 性能指标计算相关状态
        self.pv_history = []  # 存储pv历史值
        self.error_history = []  # 存储误差历史值
        self.max_pv = pv  # 记录最大pv值
        self.settling_time = 0.0  # 调节时间
        self.settled = False  # 是否已进入稳态
        self.overshoot_calculated = False  # 超调量是否已计算
        self.initial_sv = sv  # 初始设定值，用于检测设定值变化
        
        # 稳态判断参数
        self.settling_threshold = 0.02  # 稳态阈值（2%）
        self.settling_window = 10  # 稳态判断窗口（连续10个采样点）
        
        logger.info(
            f"PIDEX '{name}' initialized: kp={kp}, Ti={Ti}s, Td={Td}s, "
            f"output_range=[{l}, {h}], Tf={Tf}s, noise_level={noise_level}"
        )
    
    def _apply_noise(self, value: float) -> float:
        """
        对测量值添加噪声
        
        Args:
            value: 原始值
            
        Returns:
            添加噪声后的值
        """
        noise_level = self.config['noise_level']
        if noise_level > 0:
            noise = random.gauss(0, noise_level)
            return value + noise
        return value
    
    def _filter_setpoint(self, sv: float) -> float:
        """
        对设定值进行一阶低通滤波
        
        Args:
            sv: 原始设定值
            
        Returns:
            滤波后的设定值
        """
        Tf = self.config['Tf']
        T = self.config['T']
        
        if Tf > 0:
            # 一阶低通滤波：y(k) = y(k-1) + (T/(T+Tf)) * (x(k) - y(k-1))
            alpha = T / (T + Tf)
            self.filtered_sv = self.filtered_sv + alpha * (sv - self.filtered_sv)
            return self.filtered_sv
        else:
            self.filtered_sv = sv
            return sv
    
    def _calculate_performance_metrics(self, pv: float, sv: float, error: float):
        """
        计算性能指标
        
        Args:
            pv: 当前过程变量
            sv: 当前设定值
            error: 当前误差
        """
        # 检测设定值变化
        if abs(sv - self.initial_sv) > 0.01:
            # 设定值发生变化，重置性能指标
            self.pv_history = []
            self.error_history = []
            self.max_pv = pv
            self.settling_time = 0.0
            self.settled = False
            self.overshoot_calculated = False
            self.initial_sv = sv
        
        # 记录历史值
        self.pv_history.append(pv)
        self.error_history.append(abs(error))
        
        # 限制历史记录长度（保留最近1000个点）
        if len(self.pv_history) > 1000:
            self.pv_history.pop(0)
            self.error_history.pop(0)
        
        # 更新最大pv值
        if pv > self.max_pv:
            self.max_pv = pv
        
        # 计算超调量（仅在设定值变化后第一次计算）
        if not self.overshoot_calculated and len(self.pv_history) > 1:
            if sv > 0:
                overshoot = ((self.max_pv - sv) / sv) * 100.0
                if overshoot > 0:
                    self.output['OverShoot'] = overshoot
                    self.overshoot_calculated = True
                else:
                    self.output['OverShoot'] = 0.0
            else:
                self.output['OverShoot'] = 0.0
        
        # 计算稳态误差（使用最近一段时间的平均误差）
        if len(self.error_history) >= 10:
            recent_errors = self.error_history[-10:]
            avg_error = sum(recent_errors) / len(recent_errors)
            self.output['Ess'] = avg_error
        
        # 计算调节时间（进入稳态的时间）
        if not self.settled and len(self.pv_history) >= self.settling_window:
            # 检查最近settling_window个点是否都在稳态范围内
            recent_pvs = self.pv_history[-self.settling_window:]
            if sv > 0:
                # 相对误差
                max_deviation = max([abs(pv_val - sv) / sv for pv_val in recent_pvs])
            else:
                # 绝对误差
                max_deviation = max([abs(pv_val - sv) for pv_val in recent_pvs])
            
            if max_deviation <= self.settling_threshold:
                # 进入稳态
                if self.settling_time == 0.0:
                    # 计算从设定值变化到进入稳态的时间
                    # 简化处理：使用历史记录长度估算
                    self.settling_time = len(self.pv_history) * self.config['T']
                self.output['SettlingTime'] = self.settling_time
                self.settled = True
            else:
                # 未进入稳态，更新调节时间
                if self.settling_time > 0:
                    self.settling_time = len(self.pv_history) * self.config['T']
                    self.output['SettlingTime'] = self.settling_time
    
    def execute(self, input_params: dict = None, config_params: dict = None):
        """
        执行PIDEX算法运算
        
        Args:
            input_params: 输入参数字典，包含pv和sv
            config_params: 配置参数字典，包含kp, Ti, Td, Tf, noise_level
        
        Returns:
            全量参数字典
        """
        # 更新配置参数
        if config_params is not None:
            if 'kp' in config_params:
                self.config['kp'] = config_params['kp']
            if 'Ti' in config_params:
                self.config['Ti'] = config_params['Ti']
            if 'Td' in config_params:
                self.config['Td'] = config_params['Td']
            if 'Tf' in config_params:
                self.config['Tf'] = config_params['Tf']
                self.output['Tf'] = config_params['Tf']
            if 'noise_level' in config_params:
                self.config['noise_level'] = config_params['noise_level']
                self.output['NoiseLevel'] = config_params['noise_level']
            if 'Ts' in config_params:
                self.config['Ts'] = config_params['Ts']
                self.output['Ts'] = config_params['Ts']
            if 'h' in config_params:
                self.config['h'] = config_params['h']
                self.output['OutputRange'] = f"[{self.config['l']}, {config_params['h']}]"
            if 'l' in config_params:
                self.config['l'] = config_params['l']
                self.output['OutputRange'] = f"[{config_params['l']}, {self.config['h']}]"
        
        # 更新输入参数
        if input_params is not None:
            if 'pv' in input_params:
                self.input['pv'] = input_params['pv']
            if 'sv' in input_params:
                self.input['sv'] = input_params['sv']
        
        # 获取当前值
        raw_pv = self.input['pv']
        raw_sv = self.input['sv']
        
        # 对pv添加噪声
        pv = self._apply_noise(raw_pv)
        
        # 对sv进行滤波
        sv = self._filter_setpoint(raw_sv)
        
        kp = self.config['kp']
        Ti = self.config['Ti']
        Td = self.config['Td']
        T = self.config['T']
        h = self.config['h']
        l = self.config['l']
        
        # 计算误差（使用滤波后的设定值）
        error = sv - pv
        
        # 比例项
        p_term = kp * error
        
        # 积分项
        self.integral += error * T
        if Ti > 0:
            i_term = (kp / Ti) * self.integral
        else:
            i_term = 0.0
        
        # 微分项
        d_term = (kp * Td) * (error - self.last_error) / T
        
        # 计算输出
        mv = p_term + i_term + d_term
        
        # 限制输出范围
        mv = max(l, min(h, mv))
        
        # 更新输出
        self.output['mv'] = mv
        self.output['MODE'] = 1
        
        # 更新输出范围字符串
        self.output['OutputRange'] = f"[{l}, {h}]"
        
        # 计算设定值变化率（RampRate）
        # 使用原始设定值计算变化率
        time_diff = T  # 使用采样周期作为时间差
        sv_diff = raw_sv - self.last_sv
        ramp_rate = sv_diff / time_diff if time_diff > 0 else 0.0
        self.output['RampRate'] = ramp_rate
        self.last_sv = raw_sv
        
        # 更新Ts输出
        self.output['Ts'] = self.config['Ts']
        
        # 计算性能指标
        # 注意：这里使用原始pv和原始sv来计算性能指标，而不是带噪声的pv
        self._calculate_performance_metrics(raw_pv, raw_sv, raw_sv - raw_pv)
        
        # 保存当前误差用于下次计算
        self.last_error = error
        
        logger.debug(
            f"PIDEX '{self.name}' execute: pv={pv:.4f}, sv={sv:.4f}, "
            f"error={error:.4f}, mv={mv:.4f}, Ess={self.output['Ess']:.4f}, "
            f"OverShoot={self.output['OverShoot']:.2f}%"
        )
        
        return self.get_all_params()

