"""
PLC运行模块
每个运行周期执行已组态的控制算法和物理模型的时序计算，并将数据推送到Redis
"""
import threading
import time
import json
import redis
from datetime import datetime
from typing import Dict, Any, Optional
from plc.plc_configuration import Configuration
from plc.clock import Clock
from plc.snapshot_manager import SnapshotManager
from module.cylindrical_tank import CylindricalTank
from module.valve import Valve
from algorithm.pid import PID
from utils.logger import get_logger

logger = get_logger()


class Runner:
    """
    PLC运行模块
    
    根据组态模板实例化模型和算法，按照连接关系执行运行
    每个周期将数据推送到Redis
    """
    
    # Redis键前缀
    REDIS_KEY_PREFIX = "plc:data:"
    
    # 默认本地目录
    DEFAULT_LOCAL_DIR = "plc/local"
    
    # 快照保存周期（每N个周期保存一次）
    SNAPSHOT_SAVE_INTERVAL = 10
    
    def __init__(self, configuration: Configuration = None, redis_config: dict = None,
                 data_storage=None, local_dir: str = None):
        """
        初始化运行模块
        
        Args:
            configuration: 组态模板实例（可选，如果提供则直接使用）
            redis_config: Redis配置字典，包含host, port, password, db等
            data_storage: 数据存储模块实例（可选），如果提供，每个周期会直接存储数据
            local_dir: 本地配置目录（如果提供，从本地目录加载配置和快照）
        """
        self.local_dir = local_dir or self.DEFAULT_LOCAL_DIR
        self.redis_config = redis_config or {}
        self.data_storage = data_storage  # 数据存储模块实例
        
        # 初始化快照管理器
        snapshot_file = f"{self.local_dir}/snapshot.yaml"
        self.snapshot_manager = SnapshotManager(snapshot_file=snapshot_file)
        
        # 加载配置和快照的优先级：
        # 1. 优先使用快照（如果存在）
        # 2. 如果没有快照，使用本地目录的config.yaml
        # 3. 如果提供了configuration参数，直接使用（用于测试等场景）
        
        snapshot = self.snapshot_manager.load_snapshot()
        if snapshot:
            # 优先使用快照：先加载config.yaml作为基础配置，然后应用快照
            logger.info(f"Snapshot found, loading base config and applying snapshot ({len(snapshot)} parameters)")
            # 先加载基础配置（从本地目录）
            if configuration:
                self.config = configuration
            else:
                self.config = Configuration(local_dir=self.local_dir)
            # 应用快照到配置
            self._apply_snapshot_to_config(snapshot)
            logger.info("Configuration initialized from snapshot")
        else:
            # 没有快照，使用本地目录的config.yaml
            if configuration:
                # 如果提供了配置，直接使用
                self.config = configuration
                logger.info("Using provided configuration")
            else:
                # 从本地目录加载配置
                self.config = Configuration(local_dir=self.local_dir)
                logger.info(f"Configuration loaded from local directory: {self.local_dir}")
            logger.info("No snapshot found, using configuration file values")
        
        # 初始化Redis连接（如果提供了redis_config）
        if self.redis_config:
            self.redis_client = redis.Redis(
                host=self.redis_config.get('host', 'localhost'),
                port=self.redis_config.get('port', 6379),
                password=self.redis_config.get('password'),
                db=self.redis_config.get('db', 0),
                decode_responses=True
            )
        else:
            # 如果没有提供redis_config，创建一个默认连接（用于测试）
            self.redis_client = redis.Redis(
                host='localhost',
                port=6379,
                decode_responses=True
            )
        
        # 测试Redis连接
        try:
            self.redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
        
        # 初始化时钟
        self.clock = Clock(cycle_time=self.config.get_cycle_time())
        
        # 存储模型和算法实例
        self.models: Dict[str, Any] = {}
        self.algorithms: Dict[str, Any] = {}
        
        # 存储参数值（用于连接）
        self.params: Dict[str, Any] = {}
        
        # 运行控制
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._command_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        
        # 配置更新标志（用于在周期间隙执行更新）
        self._config_update_pending = False
        self._pending_config_update = None  # 存储待应用的配置更新消息
        
        # 初始化模型和算法
        self._initialize_models()
        self._initialize_algorithms()
        
        # 获取执行顺序（由组态模块计算）
        try:
            self.execution_order = self.config.get_execution_order()
            logger.info(f"Execution order: {self.execution_order}")
        except ValueError as e:
            logger.error(f"Failed to get execution order: {e}")
            raise
        
        # 标记是否是第一个周期（用于初始化参数字典）
        self._first_cycle = True
        
        # 快照保存计数器
        self._snapshot_counter = 0
        
        logger.info("Runner initialized")
    
    def _apply_snapshot_to_config(self, snapshot: Dict[str, Any]):
        """
        将快照应用到配置（更新初始参数值）
        
        Args:
            snapshot: 快照参数字典，格式为 {instance_name.param_name: value}
        """
        try:
            models_config = self.config.get_models()
            algorithms_config = self.config.get_algorithms()
            
            # 更新模型参数
            for model_name in models_config:
                model_params = models_config[model_name].get('params', {})
                for param_name, value in snapshot.items():
                    if param_name.startswith(f"{model_name}."):
                        # 提取参数名（去掉实例名前缀和点）
                        param_key = param_name[len(model_name) + 1:]
                        # 直接匹配参数名（使用小写格式）
                        if param_key in model_params:
                            model_params[param_key] = value
                            logger.debug(f"Updated {model_name}.{param_key} = {value} from snapshot")
            
            # 更新算法参数
            for algo_name in algorithms_config:
                algo_params = algorithms_config[algo_name].get('params', {})
                for param_name, value in snapshot.items():
                    if param_name.startswith(f"{algo_name}."):
                        # 提取参数名
                        param_key = param_name[len(algo_name) + 1:]
                        # 算法参数可能是嵌套的（如 config.kp, input.pv）
                        if '.' in param_key:
                            parts = param_key.split('.', 1)
                            if len(parts) == 2:
                                section, key = parts
                                if section in ['config', 'input', 'output']:
                                    if section not in algo_params:
                                        algo_params[section] = {}
                                    algo_params[section][key] = value
                                    logger.debug(f"Updated {algo_name}.{section}.{key} = {value} from snapshot")
                        else:
                            # 简单参数
                            algo_params[param_key] = value
                            logger.debug(f"Updated {algo_name}.{param_key} = {value} from snapshot")
            
            logger.info(f"Snapshot applied to configuration")
            
        except Exception as e:
            logger.error(f"Failed to apply snapshot to config: {e}", exc_info=True)
    
    def _initialize_models(self):
        """初始化所有模型实例"""
        models_config = self.config.get_models()
        
        with self._lock:
            self.models.clear()
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
        cycle_time = self.config.get_cycle_time()
        
        with self._lock:
            self.algorithms.clear()
            for name, algo_config in algorithms_config.items():
                algo_type = algo_config['type']
                params = algo_config.get('params', {}).copy()
                
                if algo_type == 'PID':
                    # 如果配置中没有指定sample_time，自动使用cycle_time
                    if 'sample_time' not in params:
                        params['sample_time'] = cycle_time
                        logger.debug(f"PID '{name}' sample_time not specified, using cycle_time={cycle_time}s")
                    algorithm = PID(**params)
                else:
                    logger.warning(f"Unknown algorithm type: {algo_type}")
                    continue
                
                self.algorithms[name] = algorithm
                logger.info(f"Algorithm '{name}' ({algo_type}) initialized")
    
    def _update_params_from_models(self):
        """从模型更新参数值（通用方法，适用于所有模型类型）"""
        for name, model in self.models.items():
            # 使用基类的get_params方法获取所有参数（用于实时数据展示和OPCUA通信）
            model_params = model.get_params()
            for param_name, param_value in model_params.items():
                self.params[f"{name}.{param_name}"] = param_value
    
    def _update_all_params(self):
        """
        更新所有参数值到参数字典
        
        从所有模型实例和算法实例中读取当前参数值，
        更新到 self.params 字典中，格式为 "实例名.参数名"。
        
        这个参数字典用于：
        1. 连接关系的数据传递（将输出参数值传递到输入参数）
        2. 推送到Redis供其他模块使用（通信模块、监控模块）
        3. 返回给调用者作为周期执行结果
        
        注意：此方法会读取模型和算法的当前状态，建立参数快照。
        """
        self._update_params_from_models()
        self._update_params_from_algorithms()
    
    def _get_storable_params_from_models(self):
        """从模型获取需要存储的参数（只包含运行时变化的参数）"""
        storable_params = {}
        for name, model in self.models.items():
            # 使用get_storable_params方法获取需要存储的参数
            if hasattr(model, 'get_storable_params'):
                model_storable_params = model.get_storable_params()
                for param_name, param_value in model_storable_params.items():
                    storable_params[f"{name}.{param_name}"] = param_value
        return storable_params
    
    def _update_params_from_algorithms(self):
        """从算法更新参数值"""
        for name, algorithm in self.algorithms.items():
            all_params = algorithm.get_all_params()
            # 更新配置参数（如kp, ti, td）
            for param_name, param_value in all_params['config'].items():
                self.params[f"{name}.{param_name}"] = param_value
            # 更新输入参数（如pv, sv）
            for param_name, param_value in all_params['input'].items():
                self.params[f"{name}.{param_name}"] = param_value
            # 更新输出参数（如mv, MODE）
            for param_name, param_value in all_params['output'].items():
                self.params[f"{name}.{param_name}"] = param_value
    
    def _get_storable_params_from_algorithms(self):
        """从算法获取需要存储的参数（使用算法的get_storable_params方法）"""
        storable_params = {}
        for name, algorithm in self.algorithms.items():
            # 使用算法的get_storable_params方法获取需要存储的参数
            if hasattr(algorithm, 'get_storable_params'):
                algo_storable_params = algorithm.get_storable_params()
                for param_name, param_value in algo_storable_params.items():
                    storable_params[f"{name}.{param_name}"] = param_value
        return storable_params
    
    def _apply_connections(self):
        """应用连接关系，将输出参数映射到输入参数"""
        connections = self.config.get_connections()
        
        for conn in connections:
            # 解析连接关系：from和to格式为 "instance.param"
            from_str = conn.get('from', '')
            to_str = conn.get('to', '')
            
            # 兼容旧格式（from/from_param和to/to_param）
            if 'from_param' in conn:
                from_obj = conn['from']
                from_param = conn['from_param']
                to_obj = conn['to']
                to_param = conn['to_param']
            else:
                # 新格式：从 "instance.param" 解析
                from_parts = from_str.split('.', 1)
                to_parts = to_str.split('.', 1)
                if len(from_parts) != 2 or len(to_parts) != 2:
                    logger.warning(f"Invalid connection format: {from_str} -> {to_str}")
                    continue
                from_obj, from_param = from_parts
                to_obj, to_param = to_parts
            
            # 获取源参数值
            source_key = f"{from_obj}.{from_param}"
            if source_key not in self.params:
                logger.warning(f"Source parameter not found: {source_key}")
                continue
            
            value = self.params[source_key]
            
            # 应用到目标（通用方法，适用于所有模型和算法类型）
            if to_obj in self.models:
                # 模型参数：直接使用setattr设置，模型内部会处理
                model = self.models[to_obj]
                setattr(model, f'_input_{to_param.lower()}', value)
            elif to_obj in self.algorithms:
                # 算法参数：根据参数是否存在于input或config字典中自动判断
                algorithm = self.algorithms[to_obj]
                if to_param in algorithm.input:
                    algorithm.input[to_param] = value
                elif to_param in algorithm.config:
                    algorithm.config[to_param] = value
                else:
                    # 如果都不存在，默认设置到input（通常连接关系是输入）
                    algorithm.input[to_param] = value
                    logger.debug(f"Parameter {to_param} not found in input/config, setting to input")
            
            logger.debug(f"Connection: {source_key} -> {to_obj}.{to_param} = {value}")
    
    def _set_instance_input(self, instance_name: str, param_name: str, value: Any):
        """
        设置实例的输入参数
        
        统一接口，不区分模型和算法。根据连接关系，将上游实例的输出值
        设置到当前实例的参数中。
        
        设置逻辑：
        - 模型实例：直接设置到属性（如 model.valve_opening = value）
        - 算法实例：设置到 input 或 config 字典
        
        Args:
            instance_name: 实例名称
            param_name: 参数名称（从连接关系中的 to_param 获取）
            value: 参数值（从上游实例的参数字典中读取）
        """
        instance = self._get_instance(instance_name)
        if instance is None:
            logger.warning(f"Instance {instance_name} not found when setting input")
            return
        
        if instance_name in self.models:
            # 模型参数：直接设置到属性
            # 参数名保持原样（如 valve_opening），不添加 _input_ 前缀
            setattr(instance, param_name, value)
            logger.debug(f"Set model {instance_name}.{param_name} = {value}")
        elif instance_name in self.algorithms:
            # 算法参数：设置到 input 或 config 字典
            algorithm = instance
            if param_name in algorithm.input:
                algorithm.input[param_name] = value
                logger.debug(f"Set algorithm {instance_name}.input[{param_name}] = {value}")
            elif param_name in algorithm.config:
                algorithm.config[param_name] = value
                logger.debug(f"Set algorithm {instance_name}.config[{param_name}] = {value}")
            else:
                # 如果都不存在，默认设置到input（通常连接关系是输入）
                algorithm.input[param_name] = value
                logger.debug(f"Parameter {param_name} not found in input/config, set to input[{param_name}] = {value}")
    
    def _apply_connections_for_instance(self, instance_name: str):
        """
        只应用与指定实例相关的连接关系（输入连接）
        
        从参数字典读取上游实例的输出值，设置到当前实例的输入参数中。
        连接关系是固定的，不需要每个周期都全局应用，只需要在实例执行前
        应用该实例的输入连接即可。
        
        Args:
            instance_name: 实例名称
        """
        connections = self.config.get_connections()
        
        for conn in connections:
            # 解析连接关系：from和to格式为 "instance.param"
            from_str = conn.get('from', '')
            to_str = conn.get('to', '')
            
            # 兼容旧格式（from/from_param和to/to_param）
            if 'from_param' in conn:
                from_obj = conn['from']
                from_param = conn['from_param']
                to_obj = conn['to']
                to_param = conn['to_param']
            else:
                # 新格式：从 "instance.param" 解析
                from_parts = from_str.split('.', 1)
                to_parts = to_str.split('.', 1)
                if len(from_parts) != 2 or len(to_parts) != 2:
                    continue
                from_obj, from_param = from_parts
                to_obj, to_param = to_parts
            
            # 只处理目标为当前实例的连接
            if to_obj != instance_name:
                continue
            
            # 从参数字典读取源参数值
            source_key = f"{from_obj}.{from_param}"
            if source_key not in self.params:
                # 如果参数字典中没有值，可能是第一个周期或上游实例还未执行
                # 跳过，等待上游实例执行后更新参数字典
                logger.debug(f"Source parameter not found in params dict: {source_key}, skipping")
                continue
            
            value = self.params[source_key]
            
            # 设置到当前实例的输入
            self._set_instance_input(instance_name, to_param, value)
            logger.debug(f"Connection: {source_key} -> {instance_name}.{to_param} = {value}")
    
    def _get_instance(self, instance_name: str):
        """
        获取实例（模型或算法）
        
        Args:
            instance_name: 实例名称
            
        Returns:
            模型或算法实例，如果不存在返回None
        """
        if instance_name in self.models:
            return self.models[instance_name]
        elif instance_name in self.algorithms:
            return self.algorithms[instance_name]
        else:
            return None
    
    def _execute_single_instance(self, instance_name: str):
        """
        执行单个实例（模型或算法）
        
        统一接口，不区分模型和算法。实例执行时会使用已经设置好的输入参数
        （通过 _apply_connections_for_instance() 设置）。
        
        执行逻辑：
        - 模型实例：直接调用 execute(step=step_size)
          - 模型的 execute() 方法应该自己从属性中读取输入参数
          - 例如：model.execute(step=step_size) 内部读取 model.valve_opening
        - 算法实例：直接调用 execute()
          - 算法的 execute() 方法从 input/config 字典读取参数
        
        注意：
        - 输入参数已经通过连接关系设置到实例的属性或字典中
        - 此方法只负责执行计算，不负责参数更新
        - 参数更新由 _update_params_from_single_instance() 负责
        
        Args:
            instance_name: 实例名称
        """
        instance = self._get_instance(instance_name)
        if instance is None:
            logger.warning(f"Instance {instance_name} not found")
            return
        
        if instance_name in self.models:
            # 模型执行：传递 step 参数，模型自己从属性读取输入
            step_size = self.clock.cycle_time
            try:
                instance.execute(step=step_size)
            except TypeError:
                # 如果execute不接受step参数，尝试无参数调用
                try:
                    instance.execute()
                except Exception as e:
                    logger.warning(
                        f"Model {instance_name} execute() failed: {e}. "
                        f"Model should read input parameters from its attributes."
                    )
        else:
            # 算法执行：算法从 input/config 字典读取参数，直接调用 execute()
            instance.execute()
    
    def _update_params_from_single_instance(self, instance_name: str):
        """
        更新单个实例的参数值
        
        Args:
            instance_name: 实例名称
        """
        if instance_name in self.models:
            model = self.models[instance_name]
            model_params = model.get_params()
            for param_name, param_value in model_params.items():
                self.params[f"{instance_name}.{param_name}"] = param_value
        elif instance_name in self.algorithms:
            algorithm = self.algorithms[instance_name]
            all_params = algorithm.get_all_params()
            for param_name, param_value in all_params['config'].items():
                self.params[f"{instance_name}.{param_name}"] = param_value
            for param_name, param_value in all_params['input'].items():
                self.params[f"{instance_name}.{param_name}"] = param_value
            for param_name, param_value in all_params['output'].items():
                self.params[f"{instance_name}.{param_name}"] = param_value
    
    def execute_one_cycle(self):
        """
        执行一个运行周期的计算逻辑
        
        注意：此方法只负责计算逻辑，不包含时间控制。
        时间控制（步进时钟和阻塞等待）由 _run_loop() 负责。
        
        执行流程：
        1. 第一个周期：初始化参数字典（建立初始快照）
        2. 按组态提供的顺序执行所有实例（模型+算法）：
           - 每个实例执行前：应用该实例的输入连接关系（从参数字典读取上游输出）
           - 执行实例
           - 每个实例执行后：立即更新参数到参数字典，供后续实例使用
        3. 存储和推送数据
        
        优化说明：
        - 连接关系是固定的，不需要每个周期都全局应用
        - 每个实例执行前只应用该实例的输入连接，从参数字典拉取上游输出
        - 参数字典在实例执行后立即更新，供后续实例使用
        
        Returns:
            当前周期的所有参数值字典
        """
        with self._lock:
            # 步骤1: 第一个周期初始化参数字典（建立初始快照）
            if self._first_cycle:
                self._update_all_params()
                self._first_cycle = False
                logger.debug("First cycle: initialized params dictionary")
            
            # 步骤2: 按组态提供的顺序执行所有实例
            for instance_name in self.execution_order:
                # 2.1: 应用该实例的输入连接关系（从参数字典读取上游输出）
                self._apply_connections_for_instance(instance_name)
                
                # 2.2: 执行实例
                self._execute_single_instance(instance_name)
                
                # 2.3: 立即更新参数到参数字典，供后续实例使用
                self._update_params_from_single_instance(instance_name)
            
            # 步骤3: 存储和推送数据（所有实例执行完成后）
            self._store_and_push_data()
            
            # 步骤4: 定期保存快照
            self._snapshot_counter += 1
            if self._snapshot_counter >= self.SNAPSHOT_SAVE_INTERVAL:
                self._save_snapshot()
                self._snapshot_counter = 0
            
            # 返回当前周期的所有参数
            return self.params.copy()
    
    def _store_and_push_data(self):
        """
        存储和推送周期数据
        
        1. 推送到Redis：
           - 更新 plc:data:current 键（最新数据）
           - 追加到 plc:data:history 列表（历史数据，保留最近1000条）
           - 供通信模块（OPCUA）和监控模块（Web）读取
        
        2. 存储到数据库（如果提供了数据存储模块）：
           - 只存储需要存储的参数（使用 get_storable_params()）
           - 同步存储，避免数据丢失
           - 供历史数据查询使用
        """
        # 推送到Redis（用于实时数据展示和OPCUA通信）
        self._push_to_redis()
        
        # 如果提供了数据存储模块，直接存储数据（避免Redis历史列表溢出）
        if self.data_storage:
            try:
                # 使用系统时间戳
                timestamp = datetime.now()
                sim_time = self.clock.current_time
                
                # 只存储需要存储的参数（运行时变化的参数）
                storable_params = {}
                storable_params.update(self._get_storable_params_from_models())
                storable_params.update(self._get_storable_params_from_algorithms())
                
                # 直接存储数据（同步调用）
                self.data_storage.store_data_sync(
                    params=storable_params,
                    timestamp=timestamp,
                    sim_time=sim_time
                )
            except Exception as e:
                logger.error(f"Failed to store data directly: {e}", exc_info=True)
    
    def _push_to_redis(self):
        """将当前参数推送到Redis"""
        try:
            # 使用系统时间戳
            timestamp = time.time()
            datetime_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
            
            data = {
                'timestamp': timestamp,
                'datetime': datetime_str,
                'params': self.params.copy()
            }
            
            # 序列化为JSON
            json_data = json.dumps(data, ensure_ascii=False)
            
            # 推送到Redis（使用当前时间戳作为键的一部分）
            redis_key = f"{self.REDIS_KEY_PREFIX}current"
            self.redis_client.set(redis_key, json_data)
            
            # 同时推送到历史数据列表（保留最近1000条）
            history_key = f"{self.REDIS_KEY_PREFIX}history"
            self.redis_client.lpush(history_key, json_data)
            self.redis_client.ltrim(history_key, 0, 999)  # 只保留最近1000条
            
            logger.debug(f"Data pushed to Redis: {len(self.params)} parameters")
        except Exception as e:
            logger.error(f"Failed to push data to Redis: {e}")
    
    def _update_instance_params(self):
        """
        更新已有实例的参数值（不重新创建实例，保留状态）
        
        只更新配置参数，不重新创建实例，这样可以保留算法的内部状态
        （如PID的积分项、历史值等）。
        
        注意：如果配置中新增或删除了实例，需要使用 rebuild_instances=True。
        """
        # 检测新增或删除的实例
        algorithms_config = self.config.get_algorithms()
        models_config = self.config.get_models()
        
        config_algorithm_names = set(algorithms_config.keys())
        config_model_names = set(models_config.keys())
        current_algorithm_names = set(self.algorithms.keys())
        current_model_names = set(self.models.keys())
        
        new_algorithms = config_algorithm_names - current_algorithm_names
        removed_algorithms = current_algorithm_names - config_algorithm_names
        new_models = config_model_names - current_model_names
        removed_models = current_model_names - config_model_names
        
        if new_algorithms or removed_algorithms or new_models or removed_models:
            logger.warning(
                f"Configuration has instance changes: "
                f"new algorithms={new_algorithms}, removed algorithms={removed_algorithms}, "
                f"new models={new_models}, removed models={removed_models}. "
                f"Use rebuild_instances=True to apply these changes."
            )
        
        # 更新算法实例参数
        for name, algo_config in algorithms_config.items():
            if name in self.algorithms:
                algorithm = self.algorithms[name]
                params = algo_config.get('params', {})
                
                # 更新配置参数（如kp, ti, td等）
                for param_name, param_value in params.items():
                    if param_name in algorithm.config:
                        algorithm.config[param_name] = param_value
                        logger.debug(f"Updated algorithm {name} config param {param_name} = {param_value}")
                    elif param_name in algorithm.input:
                        algorithm.input[param_name] = param_value
                        logger.debug(f"Updated algorithm {name} input param {param_name} = {param_value}")
                    # 注意：不更新output参数，因为output是算法计算的结果
        
        # 更新模型实例参数
        for name, model_config in models_config.items():
            if name in self.models:
                model = self.models[name]
                params = model_config.get('params', {})
                
                # 更新模型参数（通过setattr设置）
                for param_name, param_value in params.items():
                    if hasattr(model, param_name):
                        setattr(model, param_name, param_value)
                        logger.debug(f"Updated model {name} param {param_name} = {param_value}")
        
        # 更新参数字典
        self._update_params_from_models()
        self._update_params_from_algorithms()
    
    def update_configuration(self, rebuild_instances: bool = False):
        """
        更新配置（在线配置时调用）
        
        Args:
            rebuild_instances: 是否重新创建实例
                - True: 重新创建所有实例（会丢失算法状态，如PID的积分项）
                - False: 只更新参数值（保留算法状态，推荐用于参数调优）
        
        注意：参数更新在调用时立即生效到实例和参数字典，
        但实际使用是在下一个周期执行时。
        """
        with self._lock:
            if rebuild_instances:
                # 重新创建实例（会丢失状态）
                logger.info("Rebuilding all instances (state will be lost)")
                self._initialize_models()
                self._initialize_algorithms()
            else:
                # 只更新参数（保留状态）
                logger.info("Updating instance parameters (state will be preserved)")
                self._update_instance_params()
            
            # 重新获取执行顺序（如果连接关系变化了）
            try:
                new_execution_order = self.config.get_execution_order()
                if new_execution_order != self.execution_order:
                    self.execution_order = new_execution_order
                    logger.info(f"Execution order updated: {self.execution_order}")
            except ValueError as e:
                logger.error(f"Failed to get execution order: {e}")
                # 如果获取失败，使用当前顺序（不更新）
            
            # 更新时钟周期
            self.clock.cycle_time = self.config.get_cycle_time()
            
            # 如果重新创建了实例，需要重新初始化参数值
            if rebuild_instances:
                self.params.clear()
                self._update_params_from_models()
                self._update_params_from_algorithms()
                # 重置第一个周期标志，下次执行时会重新初始化
                self._first_cycle = True
            
            logger.info("Configuration updated")
    
    def _save_snapshot(self):
        """
        保存运行时快照
        
        将当前所有实例的参数值保存到快照文件。
        """
        try:
            snapshot_params = self.params.copy()
            success = self.snapshot_manager.save_snapshot(snapshot_params)
            if success:
                logger.debug(f"Snapshot saved ({len(snapshot_params)} parameters)")
            else:
                logger.warning("Failed to save snapshot")
        except Exception as e:
            logger.error(f"Error saving snapshot: {e}", exc_info=True)
    
    def _command_subscriber_loop(self):
        """
        命令订阅循环（监听Redis中的参数写入命令和配置更新）
        
        订阅两个频道：
        1. plc:command:write_parameter - 参数写入命令
        2. plc:config:update - 配置更新
        """
        import redis
        
        # 创建Redis订阅连接（需要单独的连接）
        pubsub = self.redis_client.pubsub()
        pubsub.subscribe(
            "plc:command:write_parameter",
            "plc:config:update"
        )
        
        logger.info("Command subscriber started, listening for parameter write commands and config updates")
        
        try:
            while self._running:
                try:
                    # 非阻塞接收消息
                    message = pubsub.get_message(timeout=0.1)
                    if message and message['type'] == 'message':
                        channel = message['channel']
                        try:
                            if channel == "plc:command:write_parameter":
                                # 参数写入命令
                                command_data = json.loads(message['data'])
                                if command_data.get('action') == 'write_parameter':
                                    param_name = command_data.get('param_name')
                                    value = command_data.get('value')
                                    if param_name and value is not None:
                                        logger.info(f"Received parameter write command from Redis: {param_name} = {value}")
                                        success = self.set_parameter(param_name, value)
                                        if success:
                                            logger.info(f"Parameter {param_name} set to {value} successfully")
                                        else:
                                            logger.warning(f"Failed to set parameter {param_name} to {value}")
                            
                            elif channel == "plc:config:update":
                                # 配置更新
                                config_data = json.loads(message['data'])
                                config_type = config_data.get('type', 'config_update')
                                
                                if config_type == 'config_update_diff':
                                    # 差异化的配置更新（新方式）
                                    logger.info("Received configuration update diff from Redis")
                                    # 设置更新标志，在周期间隙执行
                                    self._config_update_pending = True
                                    self._pending_config_update = config_data
                                    logger.info("Configuration update pending, will be applied at next cycle gap")
                                
                                elif config_type == 'config_update':
                                    # 完整配置更新（兼容旧方式）
                                    new_config = config_data.get('config', {})
                                    logger.info("Received full configuration update from Redis")
                                    # 设置更新标志，在周期间隙执行
                                    self._config_update_pending = True
                                    self._pending_config_update = {
                                        'type': 'config_update',
                                        'config': new_config
                                    }
                                    logger.info("Configuration update pending, will be applied at next cycle gap")
                                
                                elif config_type == 'config_reset':
                                    # 配置重置
                                    new_config = config_data.get('config', {})
                                    logger.info("Received configuration reset from Redis")
                                    # 设置更新标志，在周期间隙执行
                                    self._config_update_pending = True
                                    self._pending_config_update = {
                                        'type': 'config_reset',
                                        'config': new_config
                                    }
                                    logger.info("Configuration reset pending, will be applied at next cycle gap")
                                
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse message: {e}")
                        except Exception as e:
                            logger.error(f"Error processing message: {e}", exc_info=True)
                except Exception as e:
                    logger.error(f"Error in command subscriber loop: {e}")
                    time.sleep(0.1)
        finally:
            pubsub.close()
            logger.info("Command subscriber stopped")
    
    def _apply_pending_config_update(self):
        """
        应用待处理的配置更新（在周期间隙执行）
        
        此方法在_run_loop()的周期间隙调用，确保线程安全
        """
        if not self._pending_config_update:
            return
        
        update_data = self._pending_config_update
        config_type = update_data.get('type', 'config_update')
        
        if config_type == 'config_update_diff':
            # 差异化的配置更新
            self._apply_config_update_diff(update_data)
        elif config_type == 'config_update':
            # 完整配置更新（兼容旧方式）
            config_dict = update_data.get('config', {})
            self._apply_full_config_update(config_dict)
        elif config_type == 'config_reset':
            # 配置重置
            config_dict = update_data.get('config', {})
            self._apply_config_reset(config_dict)
    
    def _apply_config_update_diff(self, update_data: dict):
        """
        应用差异化的配置更新
        
        Args:
            update_data: 包含diff和full_config的更新数据
        """
        diff = update_data.get('diff', {})
        full_config = update_data.get('full_config', {})
        rebuild_instances = update_data.get('rebuild_instances', False)
        cycle_time_changed = update_data.get('cycle_time_changed', False)
        new_cycle_time = update_data.get('cycle_time')
        
        with self._lock:
            # 1. 应用差异到plc_configuration（使用在线配置API）
            # 删除已移除的模型
            for name in diff.get('removed_models', []):
                self.config.online_remove_model(name)
                logger.info(f"Removed model: {name}")
            
            # 删除已移除的算法
            for name in diff.get('removed_algorithms', []):
                self.config.online_remove_algorithm(name)
                logger.info(f"Removed algorithm: {name}")
            
            # 添加新模型
            for name, model_config in diff.get('added_models', {}).items():
                model_type = model_config.get('type', 'unknown')
                params = model_config.get('params', {})
                self.config.online_add_model(name, model_type, params)
                logger.info(f"Added model: {name} ({model_type})")
            
            # 添加新算法
            for name, algo_config in diff.get('added_algorithms', {}).items():
                algo_type = algo_config.get('type', 'unknown')
                params = algo_config.get('params', {})
                self.config.online_add_algorithm(name, algo_type, params)
                logger.info(f"Added algorithm: {name} ({algo_type})")
            
            # 更新修改的模型
            for name, change in diff.get('modified_models', {}).items():
                new_config = change.get('to', {})
                params = new_config.get('params', {})
                self.config.online_update_model(name, params)
                logger.info(f"Updated model: {name}")
            
            # 更新修改的算法
            for name, change in diff.get('modified_algorithms', {}).items():
                new_config = change.get('to', {})
                params = new_config.get('params', {})
                self.config.online_update_algorithm(name, params)
                logger.info(f"Updated algorithm: {name}")
            
            # 删除已移除的连接
            for conn in diff.get('removed_connections', []):
                from_str = conn.get('from', '')
                to_str = conn.get('to', '')
                if from_str and to_str:
                    self.config.online_remove_connection(from_str=from_str, to_str=to_str)
                    logger.info(f"Removed connection: {from_str} -> {to_str}")
            
            # 添加新连接
            for conn in diff.get('added_connections', []):
                from_str = conn.get('from', '')
                to_str = conn.get('to', '')
                if from_str and to_str:
                    self.config.online_add_connection(from_str=from_str, to_str=to_str)
                    logger.info(f"Added connection: {from_str} -> {to_str}")
            
            # 2. 保存到本地config.yaml
            self.config.save_to_local(self.local_dir)
            
            # 3. 更新Runner实例（重建或更新参数）
            self.update_configuration(rebuild_instances=rebuild_instances)
            
            # 4. 更新执行顺序
            try:
                self.execution_order = self.config.get_execution_order()
                logger.info(f"Execution order updated: {self.execution_order}")
            except ValueError as e:
                logger.error(f"Failed to get execution order: {e}")
                raise
            
            # 5. 更新cycle_time（如果变化）
            if cycle_time_changed and new_cycle_time is not None:
                self.clock.cycle_time = new_cycle_time
                logger.info(f"Cycle time updated to {new_cycle_time}s")
            
            logger.info("Configuration update diff applied successfully")
    
    def _apply_full_config_update(self, config_dict: dict):
        """
        应用完整配置更新（兼容旧方式）
        
        Args:
            config_dict: 新的完整配置字典
        """
        with self._lock:
            # 1. 更新Configuration
            success = self.config.update_from_dict(config_dict)
            if not success:
                logger.error("Failed to update configuration from dictionary")
                raise ValueError("Failed to update configuration from dictionary")
            
            # 2. 保存到本地config.yaml
            self.config.save_to_local(self.local_dir)
            
            # 3. 重建实例（保留内部状态）
            self.update_configuration(rebuild_instances=True)
            
            # 4. 重新计算执行顺序
            try:
                self.execution_order = self.config.get_execution_order()
                logger.info(f"Execution order updated: {self.execution_order}")
            except ValueError as e:
                logger.error(f"Failed to get execution order: {e}")
                raise
            
            logger.info("Full configuration update applied successfully")
    
    def apply_config_update(self, config_dict: dict) -> bool:
        """
        应用配置更新（从Redis接收，兼容旧接口）
        
        Args:
            config_dict: 新的配置字典
        
        Returns:
            bool: 更新是否成功
        """
        try:
            self._apply_full_config_update(config_dict)
            return True
        except Exception as e:
            logger.error(f"Failed to apply config update: {e}", exc_info=True)
            return False
    
    def _apply_config_reset(self, config_dict: dict):
        """
        应用配置重置（清空快照，使用新配置）
        
        Args:
            config_dict: 新的配置字典
        """
        with self._lock:
            # 1. 清除快照
            self.snapshot_manager.clear_snapshot()
            
            # 2. 应用配置更新
            self._apply_full_config_update(config_dict)
    
    def apply_config_reset(self, config_dict: dict) -> bool:
        """
        应用配置重置（兼容旧接口）
        
        Args:
            config_dict: 新的配置字典
        
        Returns:
            bool: 重置是否成功
        """
        try:
            self._apply_config_reset(config_dict)
            return True
        except Exception as e:
            logger.error(f"Failed to apply config reset: {e}", exc_info=True)
            return False
    
    def _run_loop(self):
        """
        运行循环（在独立线程中执行）
        
        负责周期调度和时间控制：
        1. 步进模拟时钟（更新模拟时间标签）
        2. 执行周期计算逻辑
        3. 检查并应用配置更新（在周期间隙）
        4. 等待到下一个周期（控制真实时间）
        """
        self.clock.start()
        
        while self._running:
            try:
                # 1. 步进模拟时钟（更新模拟时间标签）
                self.clock.step()
                
                # 2. 执行周期计算逻辑
                self.execute_one_cycle()
                
                # 3. 在周期间隙检查并应用配置更新
                if self._config_update_pending and self._pending_config_update:
                    try:
                        logger.info("Applying pending configuration update at cycle gap")
                        self._apply_pending_config_update()
                        self._config_update_pending = False
                        self._pending_config_update = None
                        logger.info("Configuration update applied successfully")
                    except Exception as e:
                        logger.error(f"Failed to apply configuration update: {e}", exc_info=True)
                        # 清除标志，避免重复尝试
                        self._config_update_pending = False
                        self._pending_config_update = None
                
                # 4. 等待到下一个周期（控制真实时间）
                self.clock.sleep_to_next_cycle()
                
            except Exception as e:
                logger.error(f"Error in run loop: {e}", exc_info=True)
                # 即使出错也要等待，避免CPU占用过高
                time.sleep(self.clock.cycle_time)
        
        self.clock.stop()
        logger.info("Run loop stopped")
    
    def start(self):
        """启动运行模块"""
        if self._running:
            logger.warning("Runner is already running")
            return
        
        self._running = True
        
        # 启动运行循环线程
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        
        # 启动命令订阅线程（监听Redis中的参数写入命令）
        self._command_thread = threading.Thread(target=self._command_subscriber_loop, daemon=True)
        self._command_thread.start()
        
        logger.info("Runner started")
    
    def stop(self):
        """停止运行模块"""
        if not self._running:
            logger.warning("Runner is not running")
            return
        
        self._running = False
        
        # 保存最后一次快照
        try:
            self._save_snapshot()
            logger.info("Final snapshot saved before stop")
        except Exception as e:
            logger.error(f"Failed to save final snapshot: {e}")
        
        # 等待运行循环线程结束
        if self._thread:
            self._thread.join(timeout=5.0)
        
        # 等待命令订阅线程结束
        if self._command_thread:
            self._command_thread.join(timeout=2.0)
        
        logger.info("Runner stopped")
    
    def get_all_params(self) -> Dict[str, Any]:
        """
        获取所有参数值
        
        Returns:
            所有参数值字典
        """
        with self._lock:
            return self.params.copy()
    
    def get_model(self, name: str):
        """
        获取模型实例
        
        Args:
            name: 模型名称
        
        Returns:
            模型实例
        """
        with self._lock:
            return self.models.get(name)
    
    def get_algorithm(self, name: str):
        """
        获取算法实例
        
        Args:
            name: 算法名称
        
        Returns:
            算法实例
        """
        with self._lock:
            return self.algorithms.get(name)
    
    def set_parameter(self, param_name: str, value: Any) -> bool:
        """
        设置参数值（用于位号写入）
        
        Args:
            param_name: 参数名，格式为 "{instance_name}.{param_name}"，如 "pid1.sv", "tank1.level"
            value: 参数值
        
        Returns:
            是否设置成功
        """
        with self._lock:
            try:
                # 解析参数名
                if '.' not in param_name:
                    logger.warning(f"Invalid parameter name format: {param_name}")
                    return False
                
                instance_name, param = param_name.split('.', 1)
                
                # 查找对应的模型或算法实例
                if instance_name in self.models:
                    # 模型参数
                    model = self.models[instance_name]
                    # 模型参数通过 _input_xxx 属性设置
                    # 参数名需要转换为小写并添加 _input_ 前缀
                    attr_name = f'_input_{param.lower()}'
                    setattr(model, attr_name, value)
                    logger.info(f"Set model parameter {param_name} = {value}")
                    
                elif instance_name in self.algorithms:
                    # 算法参数
                    algorithm = self.algorithms[instance_name]
                    # 根据参数是否存在于input或config字典中自动判断
                    if param in algorithm.input:
                        algorithm.input[param] = value
                    elif param in algorithm.config:
                        algorithm.config[param] = value
                    else:
                        # 如果都不存在，默认设置到input（通常连接关系是输入）
                        algorithm.input[param] = value
                        logger.debug(f"Parameter {param} not found in input/config, setting to input")
                    logger.info(f"Set algorithm parameter {param_name} = {value}")
                else:
                    logger.warning(f"Instance {instance_name} not found")
                    return False
                
                # 更新params字典（立即生效，下个周期会使用新值）
                self.params[param_name] = value
                
                return True
            except Exception as e:
                logger.error(f"Failed to set parameter {param_name}: {e}", exc_info=True)
                return False
    

