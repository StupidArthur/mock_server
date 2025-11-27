"""
PLC通信模块
从Redis读取数据，更新到OPCUA Server，支持动态节点创建
"""
import threading
import time
import json
import asyncio
import redis
from typing import Dict, Any, Optional
from asyncua import Server, ua
from asyncua.common.methods import uamethod
from plc.plc_configuration import Configuration
from utils.logger import get_logger

logger = get_logger()


class Communication:
    """
    PLC通信模块
    
    根据组态信息，每个通信周期从运行模块的Redis获取当前周期数据，
    更新到OPCUA Server，支持动态节点创建
    """
    
    # 默认通信周期（秒），500ms
    DEFAULT_COMMUNICATION_CYCLE = 0.5
    
    # OPCUA Server地址
    DEFAULT_SERVER_URL = "opc.tcp://0.0.0.0:18951"
    
    # Redis键前缀
    REDIS_KEY_PREFIX = "plc:data:"
    
    def __init__(self, configuration: Configuration, redis_config: dict, 
                 server_url: str = DEFAULT_SERVER_URL, opcua_config: dict = None):
        """
        初始化通信模块
        
        Args:
            configuration: 组态模板实例
            redis_config: Redis配置字典
            server_url: OPCUA Server地址，默认opc.tcp://0.0.0.0:18951
            opcua_config: OPCUA配置字典（可选），包含security_policy等配置
        """
        self.config = configuration
        self.redis_config = redis_config
        self.server_url = server_url
        self.opcua_config = opcua_config or {}
        
        # 初始化Redis连接
        self.redis_client = redis.Redis(
            host=redis_config.get('host', 'localhost'),
            port=redis_config.get('port', 6379),
            password=redis_config.get('password'),
            db=redis_config.get('db', 0),
            decode_responses=True
        )
        
        # 测试Redis连接
        try:
            self.redis_client.ping()
            logger.info("Redis connection established in Communication module")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
        
        # OPCUA Server
        self.server: Optional[Server] = None
        self.namespace_idx: Optional[int] = None
        
        # 存储节点映射：参数名 -> 节点对象
        self.node_map: Dict[str, Any] = {}
        
        # 存储节点类型映射：参数名 -> VariantType（用于写入时类型转换）
        self.node_type_map: Dict[str, ua.VariantType] = {}
        
        # 存储实例文件夹映射：实例名 -> 文件夹对象（用于节点删除）
        self.instance_folders: Dict[str, Any] = {}
        
        # 运行控制
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        
        # 通信周期
        self.communication_cycle = self.DEFAULT_COMMUNICATION_CYCLE
        
        logger.info(f"Communication initialized with server_url={server_url}")
    
    def _get_security_policy(self):
        """
        获取安全策略配置
        
        从配置中读取安全策略，如果没有配置则使用默认的NoSecurity策略。
        
        Returns:
            List[ua.SecurityPolicyType]: 安全策略列表
        """
        security_policy_str = self.opcua_config.get('security_policy', 'NoSecurity')
        
        policy_map = {
            'NoSecurity': ua.SecurityPolicyType.NoSecurity,
            'Basic256Sha256': ua.SecurityPolicyType.Basic256Sha256,
            'Basic128Rsa15': ua.SecurityPolicyType.Basic128Rsa15,
            'Basic256': ua.SecurityPolicyType.Basic256,
        }
        
        policy = policy_map.get(security_policy_str, ua.SecurityPolicyType.NoSecurity)
        if security_policy_str not in policy_map:
            logger.warning(f"Unknown security policy '{security_policy_str}', using NoSecurity")
        
        return [policy]
    
    async def _create_server(self):
        """创建和初始化Server实例"""
        self.server = Server()
        if self.server is None:
            raise RuntimeError("Failed to create Server instance")
        
        # 初始化服务器
        await self.server.init()
        logger.debug("OPCUA Server instance created and initialized")
    
    async def _setup_security(self):
        """设置安全策略和端点"""
        # 解析URL获取host和port
        from urllib.parse import urlparse
        parsed = urlparse(self.server_url)
        host = parsed.hostname or "0.0.0.0"
        port = parsed.port or 4840
        
        # 设置安全策略（必须在set_endpoint之前设置）
        try:
            security_policy = self._get_security_policy()
            self.server.set_security_policy(security_policy)
            logger.debug(f"Security policy set: {security_policy}")
        except Exception as e:
            logger.warning(f"Failed to set security policy: {e}, continuing anyway")
        
        # 设置端点
        endpoint = f"opc.tcp://{host}:{port}"
        self.server.set_endpoint(endpoint)
        logger.debug(f"Server endpoint set: {endpoint}")
        
        # 设置服务器名称
        self.server.set_server_name("PLC Mock Server")
        
        # 设置命名空间为1（固定）
        self.namespace_idx = 1
    
    async def _create_folder_structure(self):
        """创建OPCUA文件夹结构"""
        # 创建根节点下的对象
        objects = self.server.get_objects_node()
        
        # 创建PLC对象
        plc_obj = await objects.add_object(
            self.namespace_idx,
            "PLC",
            ua.ObjectIds.BaseObjectType
        )
        
        # 创建模型和算法文件夹
        models_folder = await plc_obj.add_folder(
            self.namespace_idx,
            "Models"
        )
        algorithms_folder = await plc_obj.add_folder(
            self.namespace_idx,
            "Algorithms"
        )
        
        # 存储文件夹引用
        self.node_map['_models_folder'] = models_folder
        self.node_map['_algorithms_folder'] = algorithms_folder
        
        logger.debug("OPCUA folder structure created")
    
    async def _create_variable_node(self, parent_folder, tag_name: str, initial_value: Any, 
                                    variant_type: ua.VariantType = None):
        """
        创建变量节点的通用方法
        
        Args:
            parent_folder: 父文件夹对象
            tag_name: 位号名（用作nodeid）
            initial_value: 初始值
            variant_type: Variant类型，如果为None则自动推断
        
        Returns:
            创建的节点对象
        """
        # 自动推断Variant类型
        if variant_type is None:
            if isinstance(initial_value, bool):
                variant_type = ua.VariantType.Boolean
            elif isinstance(initial_value, int):
                variant_type = ua.VariantType.Int32
            elif isinstance(initial_value, float):
                variant_type = ua.VariantType.Double
            elif isinstance(initial_value, str):
                variant_type = ua.VariantType.String
            else:
                variant_type = ua.VariantType.String
        
        # 创建节点
        node = await parent_folder.add_variable(
            ua.NodeId(tag_name, self.namespace_idx),
            tag_name,
            ua.Variant(initial_value, variant_type)
        )
        
        # 设置为可写
        await node.set_writable()
        
        # 存储到节点映射
        self.node_map[tag_name] = node
        
        # 存储节点类型
        self.node_type_map[tag_name] = variant_type
        
        return node
    
    async def _create_model_nodes(self, model_name: str, model_config: dict, model_folder):
        """
        创建模型节点的通用方法
        
        Args:
            model_name: 模型实例名称
            model_config: 模型配置
            model_folder: 模型文件夹对象
        """
        model_type = model_config.get('type')
        
        if model_type == 'cylindrical_tank':
            # 水箱模型参数：level
            tag_name = f"{model_name}.level"
            await self._create_variable_node(model_folder, tag_name, 0.0, ua.VariantType.Double)
            
        elif model_type == 'valve':
            # 阀门模型参数：current_opening, target_opening
            tag_name_current = f"{model_name}.current_opening"
            await self._create_variable_node(model_folder, tag_name_current, 0.0, ua.VariantType.Double)
            
            tag_name_target = f"{model_name}.target_opening"
            await self._create_variable_node(model_folder, tag_name_target, 0.0, ua.VariantType.Double)
        
        else:
            logger.warning(f"Unknown model type: {model_type}, skipping node creation")
    
    async def _create_algorithm_nodes(self, algo_name: str, algo_config: dict, algo_folder):
        """
        创建算法节点的通用方法
        
        Args:
            algo_name: 算法实例名称
            algo_config: 算法配置
            algo_folder: 算法文件夹对象
        """
        algo_type = algo_config.get('type')
        
        if algo_type == 'PID':
            # PID算法参数
            # 配置参数
            await self._create_variable_node(algo_folder, f"{algo_name}.kp", 0.0, ua.VariantType.Double)
            await self._create_variable_node(algo_folder, f"{algo_name}.ti", 0.0, ua.VariantType.Double)
            await self._create_variable_node(algo_folder, f"{algo_name}.td", 0.0, ua.VariantType.Double)
            
            # 输入参数
            await self._create_variable_node(algo_folder, f"{algo_name}.pv", 0.0, ua.VariantType.Double)
            await self._create_variable_node(algo_folder, f"{algo_name}.sv", 0.0, ua.VariantType.Double)
            
            # 输出参数
            await self._create_variable_node(algo_folder, f"{algo_name}.mv", 0.0, ua.VariantType.Double)
            await self._create_variable_node(algo_folder, f"{algo_name}.mode", 1, ua.VariantType.Int32)
        
        else:
            logger.warning(f"Unknown algorithm type: {algo_type}, skipping node creation")
    
    async def _init_server(self):
        """
        初始化OPCUA Server
        
        按步骤初始化：
        1. 创建Server实例
        2. 设置安全策略和端点
        3. 创建文件夹结构
        4. 创建节点
        5. 启动服务器
        """
        try:
            # 步骤1: 创建Server实例
            await self._create_server()
            
            # 步骤2: 设置安全策略和端点
            await self._setup_security()
            
            # 步骤3: 创建文件夹结构
            await self._create_folder_structure()
            
            # 步骤4: 创建节点
            await self._create_nodes()
            
            # 步骤5: 启动服务器并运行更新循环
            await self._start_server()
            
        except KeyboardInterrupt:
            logger.info("OPCUA Server interrupted by user")
            raise
        except Exception as e:
            logger.error(f"Error in OPCUA Server: {e}", exc_info=True)
            # 不重新抛出异常，让服务器继续运行其他模块
            # 如果OPCUA Server启动失败，不影响其他模块
            logger.warning("OPCUA Server failed to start, but other modules will continue")
    
    async def _start_server(self):
        """启动OPCUA Server并运行更新循环"""
        logger.info(f"OPCUA Server starting at {self.server_url}")
        # 注意：NoSecurity策略会产生警告信息，这是正常的，不影响服务器运行
        async with self.server:
            logger.info(f"OPCUA Server started at {self.server_url}")
            
            # 运行更新循环
            await self._update_loop()
    
    async def _create_nodes(self):
        """根据组态信息创建OPCUA节点"""
        with self._lock:
            # 获取组态信息
            models_config = self.config.get_models()
            algorithms_config = self.config.get_algorithms()
            
            models_folder = self.node_map.get('_models_folder')
            algorithms_folder = self.node_map.get('_algorithms_folder')
            
            if not models_folder or not algorithms_folder:
                logger.error("Folders not initialized")
                return
            
            # 创建模型节点
            for model_name, model_config in models_config.items():
                try:
                    # 为每个模型创建文件夹
                    model_folder = await models_folder.add_folder(
                        self.namespace_idx,
                        model_name
                    )
                    self.instance_folders[f"model:{model_name}"] = model_folder
                    
                    # 创建模型节点
                    await self._create_model_nodes(model_name, model_config, model_folder)
                    
                    logger.info(f"Created OPCUA nodes for model: {model_name}")
                except Exception as e:
                    logger.error(f"Failed to create nodes for model {model_name}: {e}")
            
            # 创建算法节点
            for algo_name, algo_config in algorithms_config.items():
                try:
                    # 为每个算法创建文件夹
                    algo_folder = await algorithms_folder.add_folder(
                        self.namespace_idx,
                        algo_name
                    )
                    self.instance_folders[f"algorithm:{algo_name}"] = algo_folder
                    
                    # 创建算法节点
                    await self._create_algorithm_nodes(algo_name, algo_config, algo_folder)
                    
                    logger.info(f"Created OPCUA nodes for algorithm: {algo_name}")
                except Exception as e:
                    logger.error(f"Failed to create nodes for algorithm {algo_name}: {e}")
    
    async def _delete_instance_nodes(self, instance_name: str, instance_type: str):
        """
        删除实例的所有节点
        
        Args:
            instance_name: 实例名称
            instance_type: 实例类型（'model' 或 'algorithm'）
        """
        with self._lock:
            try:
                # 获取实例文件夹
                folder_key = f"{instance_type}:{instance_name}"
                instance_folder = self.instance_folders.get(folder_key)
                
                if not instance_folder:
                    logger.warning(f"Instance folder not found: {instance_name} ({instance_type})")
                    return
                
                # 删除该实例的所有节点（从node_map中移除）
                nodes_to_delete = []
                for tag_name, node in list(self.node_map.items()):
                    if tag_name.startswith(f"{instance_name}."):
                        nodes_to_delete.append(tag_name)
                
                # 删除节点（OPCUA Server会自动处理子节点的删除）
                # 注意：asyncua可能不支持直接删除节点，这里只从node_map中移除
                for tag_name in nodes_to_delete:
                    if tag_name in self.node_map:
                        del self.node_map[tag_name]
                    if tag_name in self.node_type_map:
                        del self.node_type_map[tag_name]
                
                # 删除实例文件夹
                await instance_folder.delete()
                del self.instance_folders[folder_key]
                
                logger.info(f"Deleted OPCUA nodes for {instance_type}: {instance_name}")
            except Exception as e:
                logger.error(f"Failed to delete nodes for {instance_type} {instance_name}: {e}")
    
    async def _update_nodes(self, params: Dict[str, Any]):
        """更新OPCUA节点值"""
        for param_name, param_value in params.items():
            if param_name in self.node_map:
                try:
                    node = self.node_map[param_name]
                    
                    # 从存储的类型映射中获取节点类型
                    variant_type = self.node_type_map.get(param_name)
                    
                    # 如果类型映射中没有，尝试读取节点类型
                    if variant_type is None:
                        try:
                            node_data_type = await node.read_data_type()
                            variant_type = node_data_type.to_variant_type()
                            # 存储类型以便下次使用
                            self.node_type_map[param_name] = variant_type
                        except Exception:
                            # 如果无法读取数据类型，根据参数名称和值类型推断
                            if param_name.endswith('.mode'):
                                variant_type = ua.VariantType.Int32
                            elif isinstance(param_value, bool):
                                variant_type = ua.VariantType.Boolean
                            elif isinstance(param_value, int):
                                variant_type = ua.VariantType.Int32
                            elif isinstance(param_value, float):
                                variant_type = ua.VariantType.Double
                            elif isinstance(param_value, str):
                                variant_type = ua.VariantType.String
                            else:
                                variant_type = ua.VariantType.String
                            # 存储推断的类型
                            self.node_type_map[param_name] = variant_type
                    
                    # 根据节点的数据类型转换值
                    if variant_type == ua.VariantType.Boolean:
                        variant_value = ua.Variant(bool(param_value), variant_type)
                    elif variant_type == ua.VariantType.Int32:
                        variant_value = ua.Variant(int(param_value), variant_type)
                    elif variant_type == ua.VariantType.Double:
                        variant_value = ua.Variant(float(param_value), variant_type)
                    elif variant_type == ua.VariantType.String:
                        variant_value = ua.Variant(str(param_value), variant_type)
                    else:
                        # 其他类型，尝试转换为字符串
                        variant_value = ua.Variant(str(param_value), ua.VariantType.String)
                    
                    await node.write_value(variant_value)
                except Exception as e:
                    logger.debug(f"Failed to update node {param_name}: {e}")
    
    async def _update_loop(self):
        """更新循环（从Redis读取数据并更新OPCUA节点）"""
        while self._running:
            try:
                cycle_start_time = time.time()
                
                # 从Redis读取当前数据
                redis_key = f"{self.REDIS_KEY_PREFIX}current"
                json_data = self.redis_client.get(redis_key)
                
                if json_data:
                    data = json.loads(json_data)
                    params = data.get('params', {})
                    
                    # 更新OPCUA节点
                    await self._update_nodes(params)
                
                # 计算执行时间
                cycle_time = time.time() - cycle_start_time
                
                # 睡眠到下一个周期
                sleep_time = self.communication_cycle - cycle_time
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                else:
                    logger.warning(f"Communication cycle time ({cycle_time:.4f}s) exceeds cycle time ({self.communication_cycle}s)")
            except Exception as e:
                logger.error(f"Error in update loop: {e}", exc_info=True)
                await asyncio.sleep(self.communication_cycle)
    
    def update_configuration(self, rebuild_instances: bool = False):
        """
        更新配置（在线配置时调用）
        
        Args:
            rebuild_instances: 是否重新创建实例节点
                - True: 重新创建所有节点（会删除现有节点）
                - False: 只更新节点值，不重新创建节点结构
        """
        if rebuild_instances:
            # 重新创建所有节点（需要停止服务器）
            logger.warning("Node recreation requires server restart, please restart the communication module")
        else:
            # 只更新节点值，节点结构不变
            logger.info("Configuration updated, node values will be updated in next cycle")
    
    def start(self):
        """启动通信模块"""
        if self._running:
            logger.warning("Communication is already running")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()
        logger.info("Communication started")
    
    def _run_server(self):
        """运行OPCUA Server（在独立线程中执行）"""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._init_server())
        except KeyboardInterrupt:
            logger.info("OPCUA Server interrupted")
        except Exception as e:
            logger.error(f"Error running OPCUA Server: {e}", exc_info=True)
            # 不重新抛出异常，让服务器继续运行其他模块
        finally:
            try:
                loop.close()
            except:
                pass
    
    def stop(self):
        """停止通信模块"""
        if not self._running:
            logger.warning("Communication is not running")
            return
        
        self._running = False
        
        # Server会在async with退出时自动停止，这里只需要等待线程结束
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("Communication stopped")

