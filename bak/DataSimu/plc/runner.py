"""
组态模板运行模块
根据组态模板执行模型和算法的运行
"""
from typing import Dict, Any
from plc.configuration import Configuration
from plc.clock import Clock
from module.cylindrical_tank import CylindricalTank
from module.valve import Valve
from algorithm.pid import PID
from algorithm.pidex import PIDEX
from utils.logger import get_logger

logger = get_logger()


class Runner:
    """
    组态模板运行模块
    
    根据组态模板实例化模型和算法，按照连接关系执行运行
    """
    
    def __init__(self, configuration: Configuration):
        """
        初始化运行模块
        
        Args:
            configuration: 组态模板实例
        """
        self.config = configuration
        self.clock = Clock(
            cycle_time=configuration.get_cycle_time(),
            start_datetime=configuration.get_start_datetime(),
            sample_interval=configuration.get_sample_interval()
        )
        
        # 存储模型和算法实例
        self.models: Dict[str, Any] = {}
        self.algorithms: Dict[str, Any] = {}
        
        # 存储参数值（用于连接）
        self.params: Dict[str, Any] = {}
        
        # 初始化模型和算法
        self._initialize_models()
        self._initialize_algorithms()
        
        # 初始化参数值
        self._update_params_from_models()
        self._update_params_from_algorithms()
        
        logger.info("Runner initialized")
    
    def _initialize_models(self):
        """初始化所有模型实例"""
        models_config = self.config.get_models()
        
        for name, model_config in models_config.items():
            model_type = model_config['type']
            params = model_config.get('params', {})
            
            if model_type == 'cylindrical_tank':
                model = CylindricalTank(**params)
            elif model_type == 'valve':
                model = Valve(**params)
            else:
                logger.warning(f"Unknown model type: {model_type}")
                continue
            
            self.models[name] = model
            logger.info(f"Model '{name}' ({model_type}) initialized")
    
    def _initialize_algorithms(self):
        """初始化所有算法实例"""
        algorithms_config = self.config.get_algorithms()
        
        for name, algo_config in algorithms_config.items():
            algo_type = algo_config['type']
            params = algo_config.get('params', {})
            
            if algo_type == 'PID':
                algorithm = PID(**params)
            elif algo_type == 'PIDEX':
                algorithm = PIDEX(**params)
            else:
                logger.warning(f"Unknown algorithm type: {algo_type}")
                continue
            
            self.algorithms[name] = algorithm
            logger.info(f"Algorithm '{name}' ({algo_type}) initialized")
    
    def _update_params_from_models(self):
        """从模型更新参数值"""
        for name, model in self.models.items():
            if isinstance(model, CylindricalTank):
                self.params[f"{name}.level"] = model.level
            elif isinstance(model, Valve):
                self.params[f"{name}.current_opening"] = model.current_opening
                self.params[f"{name}.target_opening"] = model.target_opening
    
    def _update_params_from_algorithms(self):
        """从算法更新参数值"""
        for name, algorithm in self.algorithms.items():
            all_params = algorithm.get_all_params()
            # 更新配置参数（如kp, Ti, Td）
            for param_name, param_value in all_params['config'].items():
                self.params[f"{name}.{param_name}"] = param_value
            # 更新输入参数（如pv, sv）
            for param_name, param_value in all_params['input'].items():
                self.params[f"{name}.{param_name}"] = param_value
            # 更新输出参数（如mv, MODE）
            for param_name, param_value in all_params['output'].items():
                self.params[f"{name}.{param_name}"] = param_value
    
    def _apply_connections(self):
        """应用连接关系，将输出参数映射到输入参数"""
        connections = self.config.get_connections()
        
        for conn in connections:
            from_obj = conn['from']
            from_param = conn['from_param']
            to_obj = conn['to']
            to_param = conn['to_param']
            
            # 获取源参数值
            source_key = f"{from_obj}.{from_param}"
            if source_key not in self.params:
                logger.warning(f"Source parameter not found: {source_key}")
                continue
            
            value = self.params[source_key]
            
            # 应用到目标
            if to_obj in self.models:
                # 模型输入参数
                model = self.models[to_obj]
                if isinstance(model, CylindricalTank) and to_param == 'valve_opening':
                    # 这个参数会在execute时传入
                    setattr(model, '_input_valve_opening', value)
                elif isinstance(model, Valve) and to_param == 'target_opening':
                    # 这个参数会在execute时传入
                    setattr(model, '_input_target_opening', value)
            elif to_obj in self.algorithms:
                # 算法输入参数
                algorithm = self.algorithms[to_obj]
                if to_param in ['pv', 'sv']:
                    algorithm.input[to_param] = value
                elif to_param in ['kp', 'Ti', 'Td']:
                    algorithm.config[to_param] = value
            
            logger.debug(f"Connection: {source_key} -> {to_obj}.{to_param} = {value}")
    
    def execute_one_cycle(self, step_clock: bool = True):
        """
        执行一个运行周期
        
        Args:
            step_clock: 是否步进时钟，默认为True。在数据生成模式下应设置为False，
                       因为时间已经在外部通过step_sample()步进了
        
        Returns:
            当前周期的所有参数值字典
        """
        # 步进时钟（如果需要在内部步进）
        if step_clock:
            self.clock.step()
        
        # 更新参数值
        self._update_params_from_models()
        self._update_params_from_algorithms()
        
        # 应用连接关系
        self._apply_connections()
        
        # 执行算法
        for name, algorithm in self.algorithms.items():
            algorithm.execute()
        
        # 更新算法输出参数
        self._update_params_from_algorithms()
        
        # 再次应用连接（算法输出可能影响模型输入）
        self._apply_connections()
        
        # 执行模型
        # 在数据生成模式下（step_clock=False），使用sample_interval作为步长；否则使用cycle_time
        if not step_clock and self.clock.start_datetime:
            # 数据生成模式：时间已在外部通过step_sample()步进，使用sample_interval作为模型执行步长
            step_size = self.clock.sample_interval
        else:
            # 正常模式：使用cycle_time作为模型执行步长
            step_size = self.clock.cycle_time
        for name, model in self.models.items():
            if isinstance(model, CylindricalTank):
                valve_opening = getattr(model, '_input_valve_opening', 0.0)
                model.execute(valve_opening, step=step_size)
            elif isinstance(model, Valve):
                target_opening = getattr(model, '_input_target_opening', 0.0)
                model.execute(target_opening, step=step_size)
        
        # 最终更新参数值
        self._update_params_from_models()
        self._update_params_from_algorithms()
        
        # 返回当前周期的所有参数
        return self.params.copy()
    
    def get_all_params(self) -> Dict[str, Any]:
        """
        获取所有参数值
        
        Returns:
            所有参数值字典
        """
        return self.params.copy()
    
    def get_model(self, name: str):
        """
        获取模型实例
        
        Args:
            name: 模型名称
        
        Returns:
            模型实例
        """
        return self.models.get(name)
    
    def get_algorithm(self, name: str):
        """
        获取算法实例
        
        Args:
            name: 算法名称
        
        Returns:
            算法实例
        """
        return self.algorithms.get(name)

