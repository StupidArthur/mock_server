"""
PLC组态模块
支持在线和离线配置，管理物理模型实例、算法实例及其关联关系
"""
import os
import yaml
import threading
from typing import Dict, List, Any, Optional, Tuple
from utils.logger import get_logger

logger = get_logger()


class Configuration:
    """
    PLC组态类
    
    用于表示当前需要运行的每个模型、算法实例及其参数，
    以及模型和算法之间的连接和映射关系
    支持在线配置和离线配置
    """
    
    # 默认运行周期（秒），500ms
    DEFAULT_CYCLE_TIME = 0.5
    
    # 默认本地配置目录
    DEFAULT_LOCAL_DIR = "plc/local"
    
    # 默认本地配置文件
    DEFAULT_LOCAL_CONFIG_FILE = "plc/local/config.yaml"
    
    def __init__(self, config_file: str = None, config_dict: dict = None, local_dir: str = None):
        """
        初始化组态模板
        
        Args:
            config_file: YAML配置文件路径（如果提供，优先使用）
            config_dict: 配置字典（如果提供config_file则忽略此参数）
            local_dir: 本地配置目录（如果提供，从本地目录加载config.yaml）
        """
        self._lock = threading.RLock()  # 用于在线配置的线程安全
        self.local_dir = local_dir or self.DEFAULT_LOCAL_DIR
        self.local_config_file = os.path.join(self.local_dir, "config.yaml")
        
        # 加载配置的优先级：
        # 1. config_file（显式指定）
        # 2. config_dict（从字典创建）
        # 3. local_dir（从本地目录加载config.yaml）
        # 4. 默认空配置
        
        if config_file:
            # 显式指定配置文件，直接加载
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from file: {config_file}")
        elif config_dict:
            # 从字典创建
            self.config = config_dict
            logger.info("Configuration created from dictionary")
        elif local_dir and os.path.exists(self.local_config_file):
            # 从本地目录加载
            with open(self.local_config_file, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from local directory: {self.local_config_file}")
        else:
            # 默认空配置
            self.config = {
                'cycle_time': self.DEFAULT_CYCLE_TIME,
                'models': {},
                'algorithms': {},
                'connections': []
            }
            logger.info("Configuration initialized with default empty config")
        
        logger.info("Configuration initialized")
    
    def get_cycle_time(self) -> float:
        """
        获取系统运行周期
        
        Returns:
            运行周期（秒）
        """
        with self._lock:
            return self.config.get('cycle_time', self.DEFAULT_CYCLE_TIME)
    
    def get_models(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有模型实例配置
        
        Returns:
            模型配置字典，key为模型名称，value为模型配置
        """
        with self._lock:
            return self.config.get('models', {}).copy()
    
    def get_algorithms(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有算法实例配置
        
        Returns:
            算法配置字典，key为算法名称，value为算法配置
        """
        with self._lock:
            return self.config.get('algorithms', {}).copy()
    
    def get_connections(self) -> List[Dict[str, str]]:
        """
        获取所有连接关系
        
        Returns:
            连接关系列表，每个连接包含from、to、from_param、to_param
        """
        with self._lock:
            return self.config.get('connections', []).copy()
    
    def get_all_config(self) -> dict:
        """
        获取完整配置
        
        Returns:
            完整配置字典
        """
        with self._lock:
            return self.config.copy()
    
    def get_all_instances(self) -> List[str]:
        """
        获取所有实例名称（模型+算法）
        
        Returns:
            所有实例名称列表
        """
        with self._lock:
            instances = []
            instances.extend(self.config.get('models', {}).keys())
            instances.extend(self.config.get('algorithms', {}).keys())
            return instances
    
    def _build_dependency_graph(self) -> Dict[str, List[str]]:
        """
        构建依赖图
        
        根据连接关系构建依赖图，A -> B 表示 A的输出连接到B的输入，所以B依赖于A。
        
        Returns:
            Dict[str, List[str]]: 依赖图，key为实例名，value为依赖的实例列表
            例如：{"pid2": ["pid1"]} 表示 pid2 依赖于 pid1
        """
        connections = self.get_connections()
        all_instances = set(self.get_all_instances())
        
        # 构建依赖图：graph[to_instance] = [from_instance1, from_instance2, ...]
        graph = {instance: [] for instance in all_instances}
        
        for conn in connections:
            # 解析连接关系
            from_str = conn.get('from', '')
            to_str = conn.get('to', '')
            
            # 兼容旧格式
            if 'from_param' in conn:
                from_obj = conn['from']
                to_obj = conn['to']
            else:
                # 新格式：从 "instance.param" 解析
                from_parts = from_str.split('.', 1)
                to_parts = to_str.split('.', 1)
                if len(from_parts) != 2 or len(to_parts) != 2:
                    continue
                from_obj, from_param = from_parts
                to_obj, to_param = to_parts
            
            # 只处理实例之间的连接（忽略参数名）
            if from_obj in all_instances and to_obj in all_instances:
                # to_obj 依赖于 from_obj（from_obj的输出连接到to_obj的输入）
                if from_obj not in graph[to_obj]:
                    graph[to_obj].append(from_obj)
        
        return graph
    
    def _build_connection_graph(self) -> Dict[str, List[str]]:
        """
        构建连接图（无向图，用于回路分析）
        
        根据连接关系构建无向图，用于找到所有连通的实例组（回路）。
        
        Returns:
            Dict[str, List[str]]: 连接图，key为实例名，value为连接的实例列表（双向）
        """
        connections = self.get_connections()
        all_instances = set(self.get_all_instances())
        
        # 构建无向图：graph[instance] = [connected_instance1, connected_instance2, ...]
        graph = {instance: [] for instance in all_instances}
        
        for conn in connections:
            # 解析连接关系
            from_str = conn.get('from', '')
            to_str = conn.get('to', '')
            
            # 兼容旧格式
            if 'from_param' in conn:
                from_obj = conn['from']
                to_obj = conn['to']
            else:
                # 新格式：从 "instance.param" 解析
                from_parts = from_str.split('.', 1)
                to_parts = to_str.split('.', 1)
                if len(from_parts) != 2 or len(to_parts) != 2:
                    continue
                from_obj, from_param = from_parts
                to_obj, to_param = to_parts
            
            # 只处理实例之间的连接（忽略参数名）
            if from_obj in all_instances and to_obj in all_instances:
                # 无向图：双向连接
                if to_obj not in graph[from_obj]:
                    graph[from_obj].append(to_obj)
                if from_obj not in graph[to_obj]:
                    graph[to_obj].append(from_obj)
        
        return graph
    
    def analyze_circuits(self) -> Dict[str, List[str]]:
        """
        分析回路（使用图论算法找到所有连通分量）
        
        所有相连的实例归结为一个回路，回路的名字使用回路中序号最靠前的实例名。
        
        Returns:
            Dict[str, List[str]]: 回路字典，key为回路名（序号最靠前的实例名），value为回路中的实例列表
            例如：{"pid1": ["pid1", "valve1", "tank1"], "pid2": ["pid2", "valve2", "tank2"]}
        """
        all_instances = self.get_all_instances()
        if not all_instances:
            return {}
        
        # 构建连接图（无向图）
        graph = self._build_connection_graph()
        
        # 使用DFS找到所有连通分量
        visited = set()
        circuits = {}
        
        def dfs(node, circuit_nodes):
            """深度优先搜索，找到所有连通的节点"""
            visited.add(node)
            circuit_nodes.append(node)
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, circuit_nodes)
        
        # 对每个未访问的节点进行DFS
        for instance in all_instances:
            if instance not in visited:
                circuit_nodes = []
                dfs(instance, circuit_nodes)
                
                # 回路名使用回路中序号最靠前的实例名
                # 按照实例在all_instances中的顺序排序，取第一个
                circuit_nodes_sorted = sorted(circuit_nodes, key=lambda x: all_instances.index(x))
                circuit_name = circuit_nodes_sorted[0]
                
                circuits[circuit_name] = circuit_nodes_sorted
        
        return circuits
    
    def _topological_sort(self, graph: Dict[str, List[str]]) -> Tuple[List[str], List[str]]:
        """
        拓扑排序算法（Kahn算法）
        
        依赖图结构：graph[B] = [A] 表示 B 依赖于 A（A的输出连接到B的输入）
        拓扑排序中，入度表示有多少个节点指向当前节点。
        如果 graph[B] = [A]，那么 B 的入度应该是1（A指向B）。
        
        Args:
            graph: 依赖图，key为实例名，value为依赖的实例列表
            
        Returns:
            Tuple[List[str], List[str]]: (排序后的实例列表, 环中的实例列表)
            如果无环，环列表为空；如果有环，返回环中的实例
        """
        # 计算入度：graph[B] = [A] 表示 B 依赖于 A，所以 B 的入度+1
        in_degree = {node: 0 for node in graph}
        for node in graph:
            # node 依赖于 graph[node] 中的每个 dep
            # 所以 node 的入度应该增加（有多少个节点指向 node）
            for dep in graph[node]:
                in_degree[node] = in_degree.get(node, 0) + 1
        
        # 找到所有入度为0的节点（没有依赖的节点）
        queue = [node for node in graph if in_degree[node] == 0]
        result = []
        
        while queue:
            node = queue.pop(0)
            result.append(node)
            
            # 减少依赖此节点的其他节点的入度
            # 优化：直接遍历所有节点，找到依赖 node 的节点
            for other_node in graph:
                if node in graph[other_node]:
                    in_degree[other_node] -= 1
                    if in_degree[other_node] == 0:
                        queue.append(other_node)
        
        # 如果结果数量小于总节点数，说明存在环
        if len(result) < len(graph):
            # 找出环中的节点（未在结果中的节点）
            cycle_nodes = [node for node in graph if node not in result]
            return result, cycle_nodes
        else:
            return result, []
    
    def _detect_cycles(self, graph: Dict[str, List[str]]) -> List[List[str]]:
        """
        检测所有环
        
        Args:
            graph: 依赖图
            
        Returns:
            List[List[str]]: 环列表，每个环是一个节点列表
        """
        cycles = []
        visited = set()
        rec_stack = set()
        path = []
        
        def dfs(node):
            if node in rec_stack:
                # 找到环
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
                return
            
            if node in visited:
                return
            
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in graph.get(node, []):
                dfs(neighbor)
            
            rec_stack.remove(node)
            path.pop()
        
        for node in graph:
            if node not in visited:
                dfs(node)
        
        return cycles
    
    def calculate_execution_order(self) -> List[str]:
        """
        计算所有实例（模型+算法）的执行顺序
        
        根据连接关系构建依赖图，进行拓扑排序。
        如果存在环，抛出异常，要求用户手动指定 execution_order。
        
        Returns:
            List[str]: 实例执行顺序列表，包含所有模型和算法实例名
            
        Raises:
            ValueError: 如果存在环但配置中没有 execution_order
        """
        with self._lock:
            # 如果配置中已有 execution_order，直接返回
            if 'execution_order' in self.config:
                order = self.config['execution_order']
                all_instances = set(self.get_all_instances())
                # 验证执行顺序是否包含所有实例
                if set(order) != all_instances:
                    missing = all_instances - set(order)
                    extra = set(order) - all_instances
                    if missing:
                        logger.warning(f"Execution order missing instances: {missing}")
                    if extra:
                        logger.warning(f"Execution order has extra instances: {extra}")
                return order
            
            # 构建依赖图
            graph = self._build_dependency_graph()
            
            # 拓扑排序
            sorted_order, cycle_nodes = self._topological_sort(graph)
            
            # 如果存在环，抛出异常
            if cycle_nodes:
                cycles = self._detect_cycles(graph)
                cycle_info = "; ".join([" -> ".join(cycle) + " -> " + cycle[0] for cycle in cycles])
                raise ValueError(
                    f"检测到循环依赖，存在环: {cycle_info}。"
                    f"请在配置文件中添加 execution_order 字段，手动指定执行顺序。"
                    f"环中的实例: {cycle_nodes}"
                )
            
            # 如果没有环，但拓扑排序后的顺序不包含所有实例，补充缺失的实例
            all_instances = set(self.get_all_instances())
            sorted_set = set(sorted_order)
            missing = all_instances - sorted_set
            
            if missing:
                # 将缺失的实例追加到末尾（按名称排序）
                sorted_order.extend(sorted(missing))
                logger.debug(f"Added instances without dependencies to execution order: {missing}")
            
            return sorted_order
    
    def get_execution_order(self) -> List[str]:
        """
        获取执行顺序
        
        如果配置中已有 execution_order，直接返回。
        否则计算执行顺序。
        
        Returns:
            List[str]: 实例执行顺序列表
        """
        with self._lock:
            return self.calculate_execution_order()
    
    def offline_config(self, new_config: dict):
        """
        离线配置：清空当前配置，设置全新配置
        
        Args:
            new_config: 新的配置字典
        """
        with self._lock:
            self.config = new_config.copy()
            logger.info("Offline configuration applied")
    
    def online_add_model(self, name: str, model_type: str, params: dict):
        """
        在线配置：添加模型实例
        
        Args:
            name: 模型实例名称
            model_type: 模型类型（如'cylindrical_tank', 'valve'）
            params: 模型参数
        """
        with self._lock:
            if 'models' not in self.config:
                self.config['models'] = {}
            self.config['models'][name] = {
                'type': model_type,
                'params': params.copy()
            }
            logger.info(f"Online add model: {name} ({model_type})")
    
    def online_update_model(self, name: str, params: dict):
        """
        在线配置：更新模型实例参数
        
        Args:
            name: 模型实例名称
            params: 更新的参数（只更新提供的参数）
        """
        with self._lock:
            if 'models' not in self.config:
                self.config['models'] = {}
            if name not in self.config['models']:
                logger.warning(f"Model {name} not found, creating new one")
                self.config['models'][name] = {'type': 'unknown', 'params': {}}
            
            if 'params' not in self.config['models'][name]:
                self.config['models'][name]['params'] = {}
            
            self.config['models'][name]['params'].update(params)
            logger.info(f"Online update model: {name}")
    
    def online_remove_model(self, name: str):
        """
        在线配置：删除模型实例
        
        Args:
            name: 模型实例名称
        """
        with self._lock:
            if 'models' in self.config and name in self.config['models']:
                del self.config['models'][name]
                # 删除相关的连接
                if 'connections' in self.config:
                    self.config['connections'] = [
                        conn for conn in self.config['connections']
                        if conn.get('from') != name and conn.get('to') != name
                    ]
                logger.info(f"Online remove model: {name}")
    
    def online_add_algorithm(self, name: str, algo_type: str, params: dict):
        """
        在线配置：添加算法实例
        
        Args:
            name: 算法实例名称
            algo_type: 算法类型（如'PID'）
            params: 算法参数
        """
        with self._lock:
            if 'algorithms' not in self.config:
                self.config['algorithms'] = {}
            self.config['algorithms'][name] = {
                'type': algo_type,
                'params': params.copy()
            }
            logger.info(f"Online add algorithm: {name} ({algo_type})")
    
    def online_update_algorithm(self, name: str, params: dict):
        """
        在线配置：更新算法实例参数
        
        Args:
            name: 算法实例名称
            params: 更新的参数（只更新提供的参数）
        """
        with self._lock:
            if 'algorithms' not in self.config:
                self.config['algorithms'] = {}
            if name not in self.config['algorithms']:
                logger.warning(f"Algorithm {name} not found, creating new one")
                self.config['algorithms'][name] = {'type': 'unknown', 'params': {}}
            
            if 'params' not in self.config['algorithms'][name]:
                self.config['algorithms'][name]['params'] = {}
            
            self.config['algorithms'][name]['params'].update(params)
            logger.info(f"Online update algorithm: {name}")
    
    def online_remove_algorithm(self, name: str):
        """
        在线配置：删除算法实例
        
        Args:
            name: 算法实例名称
        """
        with self._lock:
            if 'algorithms' in self.config and name in self.config['algorithms']:
                del self.config['algorithms'][name]
                # 删除相关的连接
                if 'connections' in self.config:
                    self.config['connections'] = [
                        conn for conn in self.config['connections']
                        if conn.get('from') != name and conn.get('to') != name
                    ]
                logger.info(f"Online remove algorithm: {name}")
    
    def online_add_connection(self, from_obj: str = None, from_param: str = None,
                             to_obj: str = None, to_param: str = None,
                             from_str: str = None, to_str: str = None):
        """
        在线配置：添加连接关系
        
        Args:
            from_obj: 源对象名称（模型或算法实例名），旧格式兼容
            from_param: 源参数名称，旧格式兼容
            to_obj: 目标对象名称（模型或算法实例名），旧格式兼容
            to_param: 目标参数名称，旧格式兼容
            from_str: 源连接字符串，格式为 "instance.param"，新格式
            to_str: 目标连接字符串，格式为 "instance.param"，新格式
        """
        with self._lock:
            if 'connections' not in self.config:
                self.config['connections'] = []
            
            # 支持新格式和旧格式
            if from_str and to_str:
                connection = {
                    'from': from_str,
                    'to': to_str
                }
                connection_str = f"{from_str} -> {to_str}"
            elif from_obj and from_param and to_obj and to_param:
                # 旧格式兼容
                connection = {
                    'from': from_obj,
                    'from_param': from_param,
                    'to': to_obj,
                    'to_param': to_param
                }
                connection_str = f"{from_obj}.{from_param} -> {to_obj}.{to_param}"
            else:
                raise ValueError("Must provide either (from_str, to_str) or (from_obj, from_param, to_obj, to_param)")
            
            # 检查是否已存在
            if connection not in self.config['connections']:
                self.config['connections'].append(connection)
                logger.info(f"Online add connection: {connection_str}")
    
    def online_remove_connection(self, from_obj: str = None, from_param: str = None,
                                to_obj: str = None, to_param: str = None,
                                from_str: str = None, to_str: str = None):
        """
        在线配置：删除连接关系
        
        Args:
            from_obj: 源对象名称，旧格式兼容
            from_param: 源参数名称，旧格式兼容
            to_obj: 目标对象名称，旧格式兼容
            to_param: 目标参数名称，旧格式兼容
            from_str: 源连接字符串，格式为 "instance.param"，新格式
            to_str: 目标连接字符串，格式为 "instance.param"，新格式
        """
        with self._lock:
            if 'connections' in self.config:
                if from_str and to_str:
                    # 新格式
                    self.config['connections'] = [
                        conn for conn in self.config['connections']
                        if not (conn.get('from') == from_str and conn.get('to') == to_str)
                    ]
                    connection_str = f"{from_str} -> {to_str}"
                elif from_obj and from_param and to_obj and to_param:
                    # 旧格式兼容
                    self.config['connections'] = [
                        conn for conn in self.config['connections']
                        if not (conn.get('from') == from_obj and 
                               conn.get('from_param') == from_param and
                               conn.get('to') == to_obj and
                               conn.get('to_param') == to_param)
                    ]
                    connection_str = f"{from_obj}.{from_param} -> {to_obj}.{to_param}"
                else:
                    raise ValueError("Must provide either (from_str, to_str) or (from_obj, from_param, to_obj, to_param)")
                logger.info(f"Online remove connection: {connection_str}")
    
    def save_to_file(self, file_path: str):
        """
        保存配置到YAML文件
        
        Args:
            file_path: 保存路径
        """
        with self._lock:
            # 确保目录存在
            file_dir = os.path.dirname(file_path)
            if file_dir and not os.path.exists(file_dir):
                os.makedirs(file_dir, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
            logger.info(f"Configuration saved to {file_path}")
    
    def load_from_local(self, local_dir: str = None) -> bool:
        """
        从本地目录加载组态文件
        
        Args:
            local_dir: 本地目录路径，如果为None则使用self.local_dir
        
        Returns:
            bool: 加载是否成功
        """
        try:
            with self._lock:
                target_dir = local_dir or self.local_dir
                config_file = os.path.join(target_dir, "config.yaml")
                
                if not os.path.exists(config_file):
                    logger.warning(f"Local config file not found: {config_file}")
                    return False
                
                with open(config_file, 'r', encoding='utf-8') as f:
                    self.config = yaml.safe_load(f)
                
                self.local_dir = target_dir
                self.local_config_file = config_file
                
                logger.info(f"Configuration loaded from local directory: {config_file}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to load from local directory: {e}", exc_info=True)
            return False
    
    def save_to_local(self, local_dir: str = None) -> bool:
        """
        保存组态文件到本地目录
        
        Args:
            local_dir: 本地目录路径，如果为None则使用self.local_dir
        
        Returns:
            bool: 保存是否成功
        """
        try:
            with self._lock:
                target_dir = local_dir or self.local_dir
                config_file = os.path.join(target_dir, "config.yaml")
                
                # 确保目录存在
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir, exist_ok=True)
                    logger.info(f"Created local directory: {target_dir}")
                
                with open(config_file, 'w', encoding='utf-8') as f:
                    yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
                
                self.local_dir = target_dir
                self.local_config_file = config_file
                
                logger.info(f"Configuration saved to local directory: {config_file}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save to local directory: {e}", exc_info=True)
            return False
    
    def update_from_dict(self, config_dict: dict) -> bool:
        """
        从字典更新配置（用于接收配置更新）
        
        Args:
            config_dict: 新的配置字典
        
        Returns:
            bool: 更新是否成功
        """
        try:
            with self._lock:
                # 验证配置格式
                if not isinstance(config_dict, dict):
                    logger.error("Invalid config_dict: must be a dictionary")
                    return False
                
                # 更新配置
                self.config.update(config_dict)
                
                # 确保必需字段存在
                if 'models' not in self.config:
                    self.config['models'] = {}
                if 'algorithms' not in self.config:
                    self.config['algorithms'] = {}
                if 'connections' not in self.config:
                    self.config['connections'] = []
                
                logger.info("Configuration updated from dictionary")
                return True
                
        except Exception as e:
            logger.error(f"Failed to update from dictionary: {e}", exc_info=True)
            return False
    
    def get_snapshot_data(self) -> Dict[str, Any]:
        """
        获取当前配置的快照数据（用于保存）
        
        返回所有实例的初始参数值，格式为 {instance_name.param_name: value}
        
        Returns:
            Dict[str, Any]: 快照参数字典
        """
        snapshot = {}
        
        with self._lock:
            # 获取模型参数
            models_config = self.get_models()
            for model_name, model_config in models_config.items():
                params = model_config.get('params', {})
                for param_name, value in params.items():
                    # 模型参数使用大写格式
                    snapshot_key = f"{model_name}.{param_name.upper()}"
                    snapshot[snapshot_key] = value
            
            # 获取算法参数
            algorithms_config = self.get_algorithms()
            for algo_name, algo_config in algorithms_config.items():
                params = algo_config.get('params', {})
                for param_name, value in params.items():
                    # 算法参数保持小写
                    snapshot_key = f"{algo_name}.{param_name}"
                    snapshot[snapshot_key] = value
        
        return snapshot
    
    @staticmethod
    def create_example_config() -> dict:
        """
        创建示例配置
        
        Returns:
            示例配置字典
        """
        return {
            'cycle_time': 0.5,
            'models': {
                'tank1': {
                    'type': 'cylindrical_tank',
                    'params': {
                        'height': 10.0,
                        'radius': 2.0,
                        'inlet_area': 0.01,
                        'inlet_velocity': 2.0,
                        'outlet_area': 0.005,
                        'initial_level': 5.0,
                        'step': 0.5
                    }
                },
                'valve1': {
                    'type': 'valve',
                    'params': {
                        'min_opening': 0.0,
                        'max_opening': 100.0,
                        'step': 0.5,
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
                        'ti': 10.0,
                        'td': 0.1,
                        'pv': 0.0,
                        'sv': 5.0,
                        'mv': 0.0,
                        'h': 100.0,
                        'l': 0.0,
                        'sample_time': 0.5
                    }
                }
            },
            'connections': [
                {
                    'from': 'pid1.mv',
                    'to': 'valve1.target_opening'
                },
                {
                    'from': 'valve1.current_opening',
                    'to': 'tank1.valve_opening'
                },
                {
                    'from': 'tank1.level',
                    'to': 'pid1.pv'
                }
            ]
        }

