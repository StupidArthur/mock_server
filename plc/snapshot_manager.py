"""
PLC运行时快照管理模块
负责保存和加载运行时数据快照，支持异常恢复
"""
import os
import yaml
import threading
from datetime import datetime
from typing import Dict, Any, Optional
from utils.logger import get_logger

logger = get_logger()


class SnapshotManager:
    """
    运行时快照管理器
    
    负责保存和加载运行时数据快照，支持异常恢复。
    快照包含所有实例的当前参数值，用于重启后恢复运行状态。
    """
    
    # 默认快照文件名
    DEFAULT_SNAPSHOT_FILE = "plc/local/snapshot.yaml"
    
    def __init__(self, snapshot_file: str = DEFAULT_SNAPSHOT_FILE):
        """
        初始化快照管理器
        
        Args:
            snapshot_file: 快照文件路径，默认 "plc/local/snapshot.yaml"
        """
        self.snapshot_file = snapshot_file
        self._lock = threading.RLock()
        
        # 确保目录存在
        snapshot_dir = os.path.dirname(self.snapshot_file)
        if snapshot_dir and not os.path.exists(snapshot_dir):
            os.makedirs(snapshot_dir, exist_ok=True)
            logger.info(f"Created snapshot directory: {snapshot_dir}")
        
        logger.info(f"SnapshotManager initialized with file: {snapshot_file}")
    
    def save_snapshot(self, params: Dict[str, Any]) -> bool:
        """
        保存运行时快照
        
        将当前所有实例的参数值保存到快照文件。
        
        Args:
            params: 参数字典，格式为 {instance_name.param_name: value}
                    例如：{"tank1.level": 1.5, "pid1.pv": 1.5}
        
        Returns:
            bool: 保存是否成功
        """
        try:
            with self._lock:
                # 组织快照数据结构
                snapshot = {
                    'timestamp': datetime.now().isoformat(),
                    'params': params.copy()
                }
                
                # 保存到文件
                with open(self.snapshot_file, 'w', encoding='utf-8') as f:
                    yaml.dump(snapshot, f, allow_unicode=True, default_flow_style=False)
                
                logger.debug(f"Snapshot saved to {self.snapshot_file}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save snapshot: {e}", exc_info=True)
            return False
    
    def load_snapshot(self) -> Optional[Dict[str, Any]]:
        """
        加载运行时快照
        
        从快照文件加载运行时参数值。
        
        Returns:
            Optional[Dict[str, Any]]: 参数字典，如果文件不存在或加载失败则返回None
                                     格式为 {instance_name.param_name: value}
        """
        try:
            with self._lock:
                if not os.path.exists(self.snapshot_file):
                    logger.debug(f"Snapshot file not found: {self.snapshot_file}")
                    return None
                
                with open(self.snapshot_file, 'r', encoding='utf-8') as f:
                    snapshot = yaml.safe_load(f)
                
                if not snapshot or 'params' not in snapshot:
                    logger.warning(f"Invalid snapshot file format: {self.snapshot_file}")
                    return None
                
                params = snapshot.get('params', {})
                timestamp = snapshot.get('timestamp', 'unknown')
                
                logger.info(f"Snapshot loaded from {self.snapshot_file} (timestamp: {timestamp})")
                logger.debug(f"Loaded {len(params)} parameters from snapshot")
                
                return params
                
        except Exception as e:
            logger.error(f"Failed to load snapshot: {e}", exc_info=True)
            return None
    
    def apply_snapshot_to_config(self, config: 'Configuration', snapshot: Dict[str, Any]) -> bool:
        """
        将快照应用到配置
        
        将快照中的参数值更新到配置中，用于重启后恢复运行状态。
        快照参数格式：{instance_name.param_name: value}
        
        Args:
            config: Configuration实例
            snapshot: 快照参数字典
        
        Returns:
            bool: 应用是否成功
        """
        try:
            with self._lock:
                models_config = config.get_models()
                algorithms_config = config.get_algorithms()
                
                # 更新模型参数
                for model_name in models_config:
                    model_params = models_config[model_name].get('params', {})
                    for param_name, value in snapshot.items():
                        if param_name.startswith(f"{model_name}."):
                            # 提取参数名（去掉实例名前缀）
                            param_key = param_name[len(model_name) + 1:]
                            model_params[param_key] = value
                            logger.debug(f"Updated {model_name}.{param_key} = {value} from snapshot")
                
                # 更新算法参数
                for algo_name in algorithms_config:
                    algo_params = algorithms_config[algo_name].get('params', {})
                    for param_name, value in snapshot.items():
                        if param_name.startswith(f"{algo_name}."):
                            # 算法参数可能是 config.input.output 格式
                            param_key = param_name[len(algo_name) + 1:]
                            # 检查是否是嵌套参数（如 pid1.config.kp）
                            if '.' in param_key:
                                # 嵌套参数，需要特殊处理
                                parts = param_key.split('.')
                                if len(parts) == 2:
                                    # 例如：pid1.config.kp -> config['kp'] = value
                                    section, key = parts
                                    if section not in algo_params:
                                        algo_params[section] = {}
                                    algo_params[section][key] = value
                                    logger.debug(f"Updated {algo_name}.{param_key} = {value} from snapshot")
                            else:
                                # 简单参数
                                algo_params[param_key] = value
                                logger.debug(f"Updated {algo_name}.{param_key} = {value} from snapshot")
                
                logger.info(f"Applied snapshot to configuration ({len(snapshot)} parameters)")
                return True
                
        except Exception as e:
            logger.error(f"Failed to apply snapshot to config: {e}", exc_info=True)
            return False
    
    def clear_snapshot(self) -> bool:
        """
        清除快照文件
        
        用于重置运行时状态。
        
        Returns:
            bool: 清除是否成功
        """
        try:
            with self._lock:
                if os.path.exists(self.snapshot_file):
                    os.remove(self.snapshot_file)
                    logger.info(f"Snapshot file cleared: {self.snapshot_file}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to clear snapshot: {e}", exc_info=True)
            return False
    
    def snapshot_exists(self) -> bool:
        """
        检查快照文件是否存在
        
        Returns:
            bool: 快照文件是否存在
        """
        return os.path.exists(self.snapshot_file)

