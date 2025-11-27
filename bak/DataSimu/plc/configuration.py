"""
组态模板设计
使用YAML格式定义模型、算法实例及其连接关系
"""
import yaml
from typing import Dict, List, Any
from utils.logger import get_logger

logger = get_logger()


class Configuration:
    """
    组态模板类
    
    用于表示当前需要运行的每个模型、算法实例及其参数，
    以及模型和算法之间的连接和映射关系
    """
    
    def __init__(self, config_file: str = None, config_dict: dict = None):
        """
        初始化组态模板
        
        Args:
            config_file: YAML配置文件路径
            config_dict: 配置字典（如果提供config_file则忽略此参数）
        """
        if config_file:
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
        elif config_dict:
            self.config = config_dict
        else:
            self.config = {
                'cycle_time': 0.1,
                'models': {},
                'algorithms': {},
                'connections': [],
                'start_datetime': None,
                'end_datetime': None,
                'sample_interval': None
            }
        
        logger.info("Configuration initialized")
    
    def get_cycle_time(self) -> float:
        """
        获取系统运行周期
        
        Returns:
            运行周期（秒）
        """
        return self.config.get('cycle_time', 0.1)
    
    def get_start_datetime(self) -> str:
        """
        获取起始时间（用于数据生成模式）
        
        Returns:
            起始时间字符串（格式：YYYY-MM-DD HH:MM:SS），如果未配置则返回None
        """
        return self.config.get('start_datetime')
    
    def get_end_datetime(self) -> str:
        """
        获取结束时间（用于数据生成模式）
        
        Returns:
            结束时间字符串（格式：YYYY-MM-DD HH:MM:SS），如果未配置则返回None
        """
        return self.config.get('end_datetime')
    
    def get_sample_interval(self) -> float:
        """
        获取数据采样时间间隔（用于数据生成模式）
        
        Returns:
            采样时间间隔（秒），如果未配置则返回cycle_time
        """
        return self.config.get('sample_interval', self.get_cycle_time())
    
    def get_export_config(self) -> Dict[str, Any]:
        """
        获取数据导出配置
        
        支持两种格式：
        1. 新格式：tags（键值对，key是位号名，value是描述）
        2. 旧格式：tag_names和tag_descriptions（向后兼容）
        
        Returns:
            导出配置字典，包含output_file, tag_names, tag_descriptions
        """
        export_config = self.config.get('export', {})
        
        # 检查是否使用新格式（tags键值对）
        if 'tags' in export_config:
            tags = export_config.get('tags', {})
            # 从tags字典中提取tag_names和tag_descriptions
            tag_names = list(tags.keys())
            tag_descriptions = tags.copy()
            return {
                'output_file': export_config.get('output_file', 'simulation_data.xlsx'),
                'tag_names': tag_names,
                'tag_descriptions': tag_descriptions
            }
        else:
            # 使用旧格式（向后兼容）
            return {
                'output_file': export_config.get('output_file', 'simulation_data.xlsx'),
                'tag_names': export_config.get('tag_names'),
                'tag_descriptions': export_config.get('tag_descriptions')
            }
    
    def get_models(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有模型实例配置
        
        Returns:
            模型配置字典，key为模型名称，value为模型配置
        """
        return self.config.get('models', {})
    
    def get_algorithms(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有算法实例配置
        
        Returns:
            算法配置字典，key为算法名称，value为算法配置
        """
        return self.config.get('algorithms', {})
    
    def get_connections(self) -> List[Dict[str, str]]:
        """
        获取所有连接关系
        
        Returns:
            连接关系列表，每个连接包含from、to、from_param、to_param
        """
        return self.config.get('connections', [])
    
    def save_to_file(self, file_path: str):
        """
        保存配置到YAML文件
        
        Args:
            file_path: 保存路径
        """
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
        logger.info(f"Configuration saved to {file_path}")
    
    @staticmethod
    def create_example_config() -> dict:
        """
        创建示例配置
        
        Returns:
            示例配置字典
        """
        return {
            'cycle_time': 0.1,
            'models': {
                'tank1': {
                    'type': 'cylindrical_tank',
                    'params': {
                        'height': 10.0,
                        'radius': 2.0,
                        'inlet_area': 0.01,
                        'inlet_velocity': 5.0,
                        'outlet_area': 0.005,
                        'initial_level': 5.0,
                        'step': 0.1
                    }
                },
                'valve1': {
                    'type': 'valve',
                    'params': {
                        'min_opening': 0.0,
                        'max_opening': 100.0,
                        'step': 0.1,
                        'full_travel_time': 20.0
                    }
                }
            },
            'algorithms': {
                'pid1': {
                    'type': 'PID',
                    'params': {
                        'name': 'PID1',
                        'kp': 1.0,
                        'Ti': 10.0,
                        'Td': 0.1,
                        'pv': 0.0,
                        'sv': 5.0,
                        'mv': 0.0,
                        'h': 100.0,
                        'l': 0.0,
                        'T': 0.1
                    }
                }
            },
            'connections': [
                {
                    'from': 'pid1',
                    'from_param': 'mv',
                    'to': 'valve1',
                    'to_param': 'target_opening'
                },
                {
                    'from': 'valve1',
                    'from_param': 'current_opening',
                    'to': 'tank1',
                    'to_param': 'valve_opening'
                },
                {
                    'from': 'tank1',
                    'from_param': 'level',
                    'to': 'pid1',
                    'to_param': 'pv'
                }
            ]
        }

