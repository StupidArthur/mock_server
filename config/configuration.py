"""
组态管理模块
提供组态文件的加载、管理、差异分析和更新功能
"""
import os
import yaml
import json
import redis
from typing import Dict, List, Any, Optional, Tuple
from utils.logger import get_logger

logger = get_logger()


class ConfigurationManager:
    """
    组态管理器
    
    功能：
    1. 加载组态文件
    2. 管理组态内容
    3. 向plc_configuration获取当前PLC运行的组态内容
    4. 分析两边组态信息的差异
    5. 更新组态到PLC
    """
    
    def __init__(self, config_dir: str = "config", local_dir: str = "plc/local", 
                 redis_config: dict = None):
        """
        初始化组态管理器
        
        Args:
            config_dir: 配置文件目录，默认"config"
            local_dir: PLC本地配置目录，默认"plc/local"
            redis_config: Redis配置字典，包含host, port, password, db等，用于发送配置更新消息
        """
        self.config_dir = config_dir
        self.local_dir = local_dir
        self.local_config_file = os.path.join(local_dir, "config.yaml")
        
        # 当前加载的组态配置
        self._current_config: Optional[Dict[str, Any]] = None
        self._current_config_file: Optional[str] = None
        
        # Redis配置（用于发送配置更新消息）
        self.redis_config = redis_config or {}
        self._redis_client = None
        
        logger.info(f"ConfigurationManager initialized: config_dir={config_dir}, local_dir={local_dir}")
    
    def load_config_file(self, config_file: str) -> Dict[str, Any]:
        """
        加载组态文件
        
        Args:
            config_file: 配置文件路径（可以是绝对路径或相对于config_dir的路径）
        
        Returns:
            组态配置字典
        
        Raises:
            FileNotFoundError: 文件不存在
            yaml.YAMLError: YAML解析错误
        """
        # 如果是相对路径，尝试相对于config_dir解析
        if not os.path.isabs(config_file):
            # 先尝试直接路径
            if not os.path.exists(config_file):
                # 再尝试相对于config_dir
                config_file = os.path.join(self.config_dir, config_file)
        
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if config is None:
                config = {}
            
            # 验证配置格式
            self._validate_config_format(config)
            
            self._current_config = config
            self._current_config_file = config_file
            
            logger.info(f"Config file loaded: {config_file}")
            return config
            
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML file {config_file}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load config file {config_file}: {e}")
            raise
    
    def _validate_config_format(self, config: Dict[str, Any]):
        """
        验证配置格式
        
        Args:
            config: 配置字典
        
        Raises:
            ValueError: 配置格式错误
        """
        # 检查必需字段
        if not isinstance(config, dict):
            raise ValueError("Config must be a dictionary")
        
        # 检查是否有models或algorithms字段
        if 'models' not in config and 'algorithms' not in config:
            logger.warning("Config file has no 'models' or 'algorithms' fields")
        
        # 验证models格式
        if 'models' in config:
            if not isinstance(config['models'], dict):
                raise ValueError("'models' must be a dictionary")
        
        # 验证algorithms格式
        if 'algorithms' in config:
            if not isinstance(config['algorithms'], dict):
                raise ValueError("'algorithms' must be a dictionary")
        
        # 验证connections格式
        if 'connections' in config:
            if not isinstance(config['connections'], list):
                raise ValueError("'connections' must be a list")
    
    def get_current_config(self) -> Optional[Dict[str, Any]]:
        """
        获取当前加载的组态配置
        
        Returns:
            当前组态配置字典，如果未加载则返回None
        """
        return self._current_config.copy() if self._current_config else None
    
    def get_plc_running_config(self, plc_configuration) -> Dict[str, Any]:
        """
        从plc_configuration获取当前PLC运行的组态内容
        
        Args:
            plc_configuration: PLC组态模块实例（plc.plc_configuration.Configuration）
        
        Returns:
            PLC当前运行的组态配置字典
        """
        try:
            config = {
                'cycle_time': plc_configuration.get_cycle_time(),
                'models': plc_configuration.get_models(),
                'algorithms': plc_configuration.get_algorithms(),
                'connections': plc_configuration.get_connections()
            }
            
            # 如果有execution_order，也获取
            try:
                execution_order = plc_configuration.get_execution_order()
                if execution_order:
                    config['execution_order'] = execution_order
            except Exception:
                pass
            
            logger.info("PLC running config retrieved")
            return config
            
        except Exception as e:
            logger.error(f"Failed to get PLC running config: {e}")
            raise
    
    def analyze_config_diff(self, config1: Dict[str, Any], config2: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析两个组态配置的差异
        
        Args:
            config1: 第一个配置（通常是文件配置）
            config2: 第二个配置（通常是PLC运行配置）
        
        Returns:
            差异分析结果字典，包含：
            - added_models: 新增的模型实例
            - removed_models: 删除的模型实例
            - modified_models: 修改的模型实例
            - added_algorithms: 新增的算法实例
            - removed_algorithms: 删除的算法实例
            - modified_algorithms: 修改的算法实例
            - added_connections: 新增的连接关系
            - removed_connections: 删除的连接关系
            - cycle_time_changed: cycle_time是否改变
        """
        diff = {
            'added_models': {},
            'removed_models': {},
            'modified_models': {},
            'added_algorithms': {},
            'removed_algorithms': {},
            'modified_algorithms': {},
            'added_connections': [],
            'removed_connections': [],
            'cycle_time_changed': False
        }
        
        # 比较cycle_time
        cycle_time1 = config1.get('cycle_time', 0.5)
        cycle_time2 = config2.get('cycle_time', 0.5)
        if cycle_time1 != cycle_time2:
            diff['cycle_time_changed'] = True
            diff['cycle_time'] = {'from': cycle_time2, 'to': cycle_time1}
        
        # 比较models
        models1 = config1.get('models', {})
        models2 = config2.get('models', {})
        
        # 新增的模型
        for name in models1:
            if name not in models2:
                diff['added_models'][name] = models1[name]
        
        # 删除的模型
        for name in models2:
            if name not in models1:
                diff['removed_models'][name] = models2[name]
        
        # 修改的模型
        for name in models1:
            if name in models2:
                if models1[name] != models2[name]:
                    diff['modified_models'][name] = {
                        'from': models2[name],
                        'to': models1[name]
                    }
        
        # 比较algorithms
        algorithms1 = config1.get('algorithms', {})
        algorithms2 = config2.get('algorithms', {})
        
        # 新增的算法
        for name in algorithms1:
            if name not in algorithms2:
                diff['added_algorithms'][name] = algorithms1[name]
        
        # 删除的算法
        for name in algorithms2:
            if name not in algorithms1:
                diff['removed_algorithms'][name] = algorithms2[name]
        
        # 修改的算法
        for name in algorithms1:
            if name in algorithms2:
                if algorithms1[name] != algorithms2[name]:
                    diff['modified_algorithms'][name] = {
                        'from': algorithms2[name],
                        'to': algorithms1[name]
                    }
        
        # 比较connections
        connections1 = self._normalize_connections(config1.get('connections', []))
        connections2 = self._normalize_connections(config2.get('connections', []))
        
        # 新增的连接
        for conn in connections1:
            if conn not in connections2:
                diff['added_connections'].append(conn)
        
        # 删除的连接
        for conn in connections2:
            if conn not in connections1:
                diff['removed_connections'].append(conn)
        
        logger.info("Config diff analyzed")
        return diff
    
    def _normalize_connections(self, connections: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        标准化连接关系格式，便于比较
        
        Args:
            connections: 连接关系列表
        
        Returns:
            标准化后的连接关系列表
        """
        normalized = []
        for conn in connections:
            # 统一格式为 {'from': 'instance.param', 'to': 'instance.param'}
            if 'from' in conn and 'to' in conn:
                normalized.append({
                    'from': str(conn['from']),
                    'to': str(conn['to'])
                })
            elif 'from_param' in conn:
                # 旧格式转换
                from_str = f"{conn.get('from', '')}.{conn.get('from_param', '')}"
                to_str = f"{conn.get('to', '')}.{conn.get('to_param', '')}"
                normalized.append({
                    'from': from_str,
                    'to': to_str
                })
        return normalized
    
    def _get_redis_client(self):
        """获取Redis客户端（懒加载）"""
        if self._redis_client is None and self.redis_config:
            try:
                self._redis_client = redis.Redis(
                    host=self.redis_config.get('host', 'localhost'),
                    port=self.redis_config.get('port', 6379),
                    password=self.redis_config.get('password'),
                    db=self.redis_config.get('db', 0),
                    decode_responses=False  # 保持二进制模式，用于json序列化
                )
                # 测试连接
                self._redis_client.ping()
                logger.info("Redis client connected for configuration updates")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self._redis_client = None
        return self._redis_client
    
    def update_config_to_plc(self, plc_configuration=None, config: Dict[str, Any] = None, 
                            rebuild_instances: bool = False, use_redis: bool = True) -> bool:
        """
        更新组态到PLC（通过Redis消息通知，PLC在运行过程中自动更新）
        
        Args:
            plc_configuration: PLC组态模块实例（可选，如果use_redis=True则不需要）
            config: 要更新的配置字典，如果为None则使用当前加载的配置
            rebuild_instances: 是否重建实例（当有新增或删除时，会自动判断）
            use_redis: 是否通过Redis发送消息（默认True），如果False则直接调用API（兼容旧方式）
        
        Returns:
            是否更新成功
        """
        if config is None:
            config = self._current_config
            if config is None:
                logger.error("No config loaded, cannot update")
                return False
        
        try:
            # 如果使用Redis方式，需要分析差异并发送消息
            if use_redis:
                # 获取当前PLC运行的配置（从plc_configuration或从文件读取）
                if plc_configuration:
                    plc_config = self.get_plc_running_config(plc_configuration)
                else:
                    # 如果没有提供plc_configuration，尝试从文件读取
                    try:
                        with open(self.local_config_file, 'r', encoding='utf-8') as f:
                            plc_config = yaml.safe_load(f) or {}
                    except Exception as e:
                        logger.warning(f"Failed to read PLC config from file: {e}, using empty config")
                        plc_config = {}
                
                # 分析差异
                diff = self.analyze_config_diff(config, plc_config)
                
                # 检查是否有变更
                has_changes = (
                    diff['added_models'] or diff['removed_models'] or diff['modified_models'] or
                    diff['added_algorithms'] or diff['removed_algorithms'] or diff['modified_algorithms'] or
                    diff['added_connections'] or diff['removed_connections'] or diff['cycle_time_changed']
                )
                
                if not has_changes:
                    logger.info("No changes detected, config is already up to date")
                    return True
                
                # 如果有新增或删除，需要重建实例
                if (diff['added_models'] or diff['removed_models'] or 
                    diff['added_algorithms'] or diff['removed_algorithms']):
                    rebuild_instances = True
                
                # 通过Redis发送配置更新消息
                redis_client = self._get_redis_client()
                if redis_client is None:
                    logger.error("Redis client not available, cannot send configuration update")
                    return False
                
                # 构造更新消息（包含差异信息和完整配置）
                update_message = {
                    'type': 'config_update_diff',  # 使用差异更新类型
                    'diff': diff,  # 差异信息
                    'full_config': config,  # 完整配置（用于重建实例时使用）
                    'rebuild_instances': rebuild_instances,
                    'cycle_time_changed': diff['cycle_time_changed'],
                    'cycle_time': config.get('cycle_time') if diff['cycle_time_changed'] else None
                }
                
                # 发送到Redis频道
                channel = "plc:config:update"
                message_json = json.dumps(update_message, ensure_ascii=False)
                redis_client.publish(channel, message_json.encode('utf-8'))
                
                logger.info(f"Configuration update message sent to Redis channel '{channel}'")
                logger.info(f"Changes: added_models={len(diff['added_models'])}, "
                          f"removed_models={len(diff['removed_models'])}, "
                          f"added_algorithms={len(diff['added_algorithms'])}, "
                          f"removed_algorithms={len(diff['removed_algorithms'])}, "
                          f"rebuild_instances={rebuild_instances}")
                
                return True
            
            else:
                # 兼容旧方式：直接调用API（不推荐，但保留兼容性）
                if plc_configuration is None:
                    logger.error("plc_configuration is required when use_redis=False")
                    return False
                
                # 获取当前PLC运行的配置
                plc_config = self.get_plc_running_config(plc_configuration)
                
                # 分析差异
                diff = self.analyze_config_diff(config, plc_config)
                
                # 检查是否有变更
                has_changes = (
                    diff['added_models'] or diff['removed_models'] or diff['modified_models'] or
                    diff['added_algorithms'] or diff['removed_algorithms'] or diff['modified_algorithms'] or
                    diff['added_connections'] or diff['removed_connections'] or diff['cycle_time_changed']
                )
                
                if not has_changes:
                    logger.info("No changes detected, config is already up to date")
                    return True
                
                # 如果有新增或删除，需要重建实例
                if (diff['added_models'] or diff['removed_models'] or 
                    diff['added_algorithms'] or diff['removed_algorithms']):
                    rebuild_instances = True
                
                # 直接调用API（旧方式）
                # ... (保留原有逻辑)
                logger.warning("Direct API update is deprecated, use Redis message instead")
                return False
            
        except Exception as e:
            logger.error(f"Failed to update config to PLC: {e}", exc_info=True)
            return False
    
    def save_config_to_local(self, config: Dict[str, Any] = None) -> bool:
        """
        保存组态配置到PLC本地目录
        
        Args:
            config: 要保存的配置字典，如果为None则使用当前加载的配置
        
        Returns:
            是否保存成功
        """
        if config is None:
            config = self._current_config
            if config is None:
                logger.error("No config loaded, cannot save")
                return False
        
        try:
            # 确保目录存在
            os.makedirs(self.local_dir, exist_ok=True)
            
            # 保存到本地配置文件
            with open(self.local_config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
            
            logger.info(f"Config saved to local file: {self.local_config_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save config to local: {e}", exc_info=True)
            return False
    
    def sync_config_to_plc(self, config_file: str, plc_configuration, 
                          save_to_local: bool = True) -> Tuple[bool, Dict[str, Any]]:
        """
        同步组态文件到PLC（加载、分析差异、更新）
        
        Args:
            config_file: 组态文件路径
            plc_configuration: PLC组态模块实例
            save_to_local: 是否同时保存到PLC本地目录
        
        Returns:
            (是否成功, 差异分析结果)
        """
        try:
            # 1. 加载配置文件
            config = self.load_config_file(config_file)
            
            # 2. 获取PLC当前运行的配置
            plc_config = self.get_plc_running_config(plc_configuration)
            
            # 3. 分析差异
            diff = self.analyze_config_diff(config, plc_config)
            
            # 4. 更新到PLC
            success = self.update_config_to_plc(plc_configuration, config)
            
            # 5. 保存到本地（如果需要）
            if save_to_local and success:
                self.save_config_to_local(config)
            
            return success, diff
            
        except Exception as e:
            logger.error(f"Failed to sync config to PLC: {e}", exc_info=True)
            return False, {}

