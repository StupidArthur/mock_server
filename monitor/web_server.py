"""
PLC监控模块
Web界面展示实时和历史数据
"""
import json
import time
import threading
import uuid
import redis
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
from plc.plc_configuration import Configuration
from plc.data_storage import DataStorage
from plc.clock import Clock
from module.cylindrical_tank import CylindricalTank
from module.valve import Valve
from algorithm.pid import PID
from utils.logger import get_logger

logger = get_logger()

# 模拟任务存储（内存中，实际应该使用Redis或数据库）
_simulation_tasks: Dict[str, Dict[str, Any]] = {}


class Monitor:
    """
    PLC监控模块
    
    界面化、图表化展示历史数据查询、历史数据统计接口
    支持实时数据推送和历史数据展示
    """
    
    def __init__(self, configuration: Configuration, redis_config: dict,
                 data_storage: DataStorage, runner=None, host: str = '0.0.0.0', port: int = 5000):
        """
        初始化监控模块
        
        Args:
            configuration: 组态模板实例
            redis_config: Redis配置字典
            data_storage: 数据存储模块实例
            host: Web服务器主机地址，默认0.0.0.0
            port: Web服务器端口，默认5000
        """
        self.config = configuration
        self.redis_config = redis_config
        self.data_storage = data_storage
        self.runner = runner  # Runner实例，用于管理时间加速
        self.host = host
        self.port = port
        
        # 运行控制
        self._running = False
        self._broadcast_thread: Optional[threading.Thread] = None
        
        # 初始化Redis连接（用于实时数据）
        try:
            self.redis_client = redis.Redis(
                host=redis_config.get('host', 'localhost'),
                port=redis_config.get('port', 6379),
                password=redis_config.get('password'),
                db=redis_config.get('db', 0),
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # 测试Redis连接
            self.redis_client.ping()
            logger.info("Redis connection established in Monitor module")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
        
        # 创建Flask应用
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        # 注意：生产环境应该使用环境变量或配置文件中的SECRET_KEY
        self.app.config['SECRET_KEY'] = redis_config.get('secret_key', 'plc_mock_server_secret_key')
        # 注意：生产环境应该限制CORS来源
        cors_origins = redis_config.get('cors_origins', '*')
        self.socketio = SocketIO(self.app, cors_allowed_origins=cors_origins)
        
        # 注册路由
        self._register_routes()
        
        logger.info(f"Monitor initialized with host={host}, port={port}")
    
    def _register_routes(self):
        """注册Web路由"""
        
        @self.app.route('/')
        def index():
            """首页"""
            return render_template('index.html')
        
        @self.app.route('/realtime-data')
        def realtime_data():
            """实时数据页面"""
            return render_template('index.html')
        
        @self.app.route('/simulation')
        def simulation():
            """数据调试页面"""
            return render_template('index.html')
        
        @self.app.route('/config_display')
        def config_display():
            """组态页面"""
            return render_template('index.html')
        
        @self.app.route('/api/configuration')
        def get_configuration():
            """获取组态配置API（包含回路分析）"""
            try:
                # 获取回路分析结果
                circuits = self.config.analyze_circuits()
                
                # 获取所有模型和算法配置
                models = self.config.get_models()
                algorithms = self.config.get_algorithms()
                connections = self.config.get_connections()
                
                # 获取参数默认值定义
                from config.param_definitions import (
                    MODEL_PARAMS, ALGORITHM_PARAMS,
                    get_model_param_def, get_algorithm_param_def
                )
                
                # 构建回路数据
                circuits_data = {}
                for circuit_name, instance_list in circuits.items():
                    circuit_instances = []
                    
                    for instance_name in instance_list:
                        # 判断是模型还是算法
                        instance_type = None
                        instance_config = None
                        if instance_name in models:
                            instance_type = 'model'
                            instance_config = models[instance_name]
                        elif instance_name in algorithms:
                            instance_type = 'algorithm'
                            instance_config = algorithms[instance_name]
                        
                        if not instance_config:
                            continue
                        
                        # 获取实例类型（如'cylindrical_tank', 'PID'）
                        type_name = instance_config.get('type', 'unknown')
                        params = instance_config.get('params', {})
                        
                        # 构建参数列表（参数名、参数值、参数默认值）
                        param_list = []
                        if instance_type == 'model':
                            param_defs = MODEL_PARAMS.get(type_name, {})
                        else:
                            param_defs = ALGORITHM_PARAMS.get(type_name, {})
                        
                        # 添加所有定义的参数
                        for param_name, param_def in param_defs.items():
                            param_value = params.get(param_name, param_def.get('default'))
                            param_default = param_def.get('default')
                            param_list.append({
                                'name': param_name,
                                'value': param_value,
                                'default': param_default,
                                'unit': param_def.get('unit', ''),
                                'desc': param_def.get('desc', '')
                            })
                        
                        # 添加配置中存在的但不在定义中的参数（兼容性）
                        for param_name, param_value in params.items():
                            if not any(p['name'] == param_name for p in param_list):
                                param_list.append({
                                    'name': param_name,
                                    'value': param_value,
                                    'default': None,
                                    'unit': '',
                                    'desc': ''
                                })
                        
                        # 获取该实例的连接关系
                        instance_connections = []
                        for conn in connections:
                            from_str = conn.get('from', '')
                            to_str = conn.get('to', '')
                            
                            # 兼容旧格式
                            if 'from_param' in conn:
                                from_obj = conn['from']
                                to_obj = conn['to']
                                from_param = conn.get('from_param', '')
                                to_param = conn.get('to_param', '')
                            else:
                                # 新格式
                                from_parts = from_str.split('.', 1)
                                to_parts = to_str.split('.', 1)
                                if len(from_parts) == 2 and len(to_parts) == 2:
                                    from_obj, from_param = from_parts
                                    to_obj, to_param = to_parts
                                else:
                                    continue
                            
                            # 如果连接涉及当前实例
                            if from_obj == instance_name or to_obj == instance_name:
                                instance_connections.append({
                                    'from': from_str,
                                    'to': to_str,
                                    'from_instance': from_obj,
                                    'from_param': from_param,
                                    'to_instance': to_obj,
                                    'to_param': to_param
                                })
                        
                        circuit_instances.append({
                            'name': instance_name,
                            'type': instance_type,
                            'type_name': type_name,
                            'params': param_list,
                            'connections': instance_connections
                        })
                    
                    circuits_data[circuit_name] = {
                        'name': circuit_name,
                        'instances': circuit_instances
                    }
                
                return jsonify({
                    'success': True,
                    'data': {
                        'circuits': circuits_data,
                        'cycle_time': self.config.get_cycle_time()
                    }
                })
            except Exception as e:
                logger.error(f"Failed to get configuration: {e}", exc_info=True)
                return jsonify({
                    'success': False,
                    'message': str(e)
                }), 500
        
        @self.app.route('/api/realtime')
        def get_realtime_data():
            """获取实时数据API"""
            try:
                redis_key = f"plc:data:current"
                json_data = self.redis_client.get(redis_key)
                
                if json_data:
                    data = json.loads(json_data)
                    return jsonify({
                        'success': True,
                        'data': data
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': 'No data available'
                    })
            except Exception as e:
                logger.error(f"Failed to get realtime data: {e}")
                return jsonify({
                    'success': False,
                    'message': str(e)
                }), 500
        
        @self.app.route('/api/history')
        def get_history_data():
            """获取历史数据API"""
            try:
                param_name = request.args.get('param_name')
                instance_name = request.args.get('instance_name')
                start_time_str = request.args.get('start_time')
                end_time_str = request.args.get('end_time')
                limit = int(request.args.get('limit', 1000))
                sample_interval = request.args.get('sample_interval')
                
                # 解析时间（处理时区问题）
                start_time = None
                end_time = None
                if start_time_str:
                    try:
                        # 处理ISO格式时间字符串（可能带时区Z）
                        start_time_str_clean = start_time_str.replace('Z', '+00:00')
                        start_time = datetime.fromisoformat(start_time_str_clean)
                        # 如果有时区信息，转换为本地时间（数据库存储的是本地时间）
                        if start_time.tzinfo is not None:
                            start_time = start_time.astimezone().replace(tzinfo=None)
                    except ValueError as e:
                        logger.warning(f"Failed to parse start_time '{start_time_str}': {e}")
                if end_time_str:
                    try:
                        # 处理ISO格式时间字符串（可能带时区Z）
                        end_time_str_clean = end_time_str.replace('Z', '+00:00')
                        end_time = datetime.fromisoformat(end_time_str_clean)
                        # 如果有时区信息，转换为本地时间（数据库存储的是本地时间）
                        if end_time.tzinfo is not None:
                            end_time = end_time.astimezone().replace(tzinfo=None)
                    except ValueError as e:
                        logger.warning(f"Failed to parse end_time '{end_time_str}': {e}")
                
                logger.debug(f"History query: param_name={param_name}, start_time={start_time}, end_time={end_time}, sample_interval={sample_interval}")
                
                # 解析采样间隔
                sample_interval_float = None
                if sample_interval:
                    try:
                        sample_interval_float = float(sample_interval)
                    except ValueError:
                        pass
                
                # 如果没有指定采样间隔，但查询范围较大，自动启用采样
                if sample_interval_float is None and start_time and end_time:
                    time_range = (end_time - start_time).total_seconds()
                    # 如果时间范围超过1小时，自动使用60秒采样间隔
                    if time_range > 3600:
                        sample_interval_float = 60.0
                        logger.info(f"Auto-enabling sampling with interval {sample_interval_float}s for large time range")
                
                # 查询历史数据
                records = self.data_storage.query_history(
                    param_name=param_name,
                    instance_name=instance_name,
                    start_time=start_time,
                    end_time=end_time,
                    limit=limit,
                    sample_interval=sample_interval_float
                )
                
                return jsonify({
                    'success': True,
                    'data': records,
                    'count': len(records),
                    'sampled': sample_interval_float is not None
                })
            except Exception as e:
                logger.error(f"Failed to get history data: {e}")
                return jsonify({
                    'success': False,
                    'message': str(e)
                }), 500
        
        @self.app.route('/api/statistics')
        def get_statistics():
            """获取统计信息API"""
            try:
                param_name = request.args.get('param_name')
                start_time_str = request.args.get('start_time')
                end_time_str = request.args.get('end_time')
                
                if not param_name:
                    return jsonify({
                        'success': False,
                        'message': 'param_name is required'
                    }), 400
                
                # 解析时间
                start_time = None
                end_time = None
                if start_time_str:
                    start_time = datetime.fromisoformat(start_time_str)
                if end_time_str:
                    end_time = datetime.fromisoformat(end_time_str)
                
                # 获取统计信息
                stats = self.data_storage.get_statistics(
                    param_name=param_name,
                    start_time=start_time,
                    end_time=end_time
                )
                
                return jsonify({
                    'success': True,
                    'data': stats
                })
            except Exception as e:
                logger.error(f"Failed to get statistics: {e}")
                return jsonify({
                    'success': False,
                    'message': str(e)
                }), 500
        
        @self.app.route('/api/simulation/start', methods=['POST'])
        def start_simulation():
            """启动PID模拟API"""
            try:
                data = request.get_json()
                
                # 获取参数
                tank_params = data.get('tank', {})
                valve_params = data.get('valve', {})
                pid_params = data.get('pid', {})
                duration = float(data.get('duration', 900.0))
                sv_values = pid_params.get('sv_values', [1.5, 0.5, 0])
                
                # 生成任务ID
                task_id = str(uuid.uuid4())
                
                # 创建模拟任务
                task = {
                    'task_id': task_id,
                    'status': 'running',
                    'progress': 0.0,
                    'data': [],
                    'tank_params': tank_params,
                    'valve_params': valve_params,
                    'pid_params': pid_params,
                    'duration': duration,
                    'sv_values': sv_values,
                    'error': None
                }
                
                _simulation_tasks[task_id] = task
                
                # 在后台线程中运行模拟
                thread = threading.Thread(
                    target=self._run_simulation,
                    args=(task_id, tank_params, valve_params, pid_params, duration, sv_values),
                    daemon=True
                )
                thread.start()
                
                return jsonify({
                    'success': True,
                    'task_id': task_id,
                    'message': 'Simulation started'
                })
            except Exception as e:
                logger.error(f"Failed to start simulation: {e}")
                return jsonify({
                    'success': False,
                    'message': str(e)
                }), 500
        
        @self.app.route('/api/simulation/status/<task_id>')
        def get_simulation_status(task_id):
            """获取模拟状态API"""
            try:
                if task_id not in _simulation_tasks:
                    return jsonify({
                        'success': False,
                        'message': 'Task not found'
                    }), 404
                
                task = _simulation_tasks[task_id]
                return jsonify({
                    'success': True,
                    'status': {
                        'status': task['status'],
                        'progress': task['progress'],
                        'data': task['data'][-100:] if len(task['data']) > 100 else task['data'],  # 只返回最后100条
                        'error': task.get('error')
                    }
                })
            except Exception as e:
                logger.error(f"Failed to get simulation status: {e}")
                return jsonify({
                    'success': False,
                    'message': str(e)
                }), 500
        
        @self.app.route('/api/simulation/result/<task_id>')
        def get_simulation_result(task_id):
            """获取模拟结果API"""
            try:
                if task_id not in _simulation_tasks:
                    return jsonify({
                        'success': False,
                        'message': 'Task not found'
                    }), 404
                
                task = _simulation_tasks[task_id]
                
                if task['status'] != 'completed':
                    return jsonify({
                        'success': False,
                        'message': 'Simulation not completed'
                    }), 400
                
                return jsonify({
                    'success': True,
                    'data': task['data']
                })
            except Exception as e:
                logger.error(f"Failed to get simulation result: {e}")
                return jsonify({
                    'success': False,
                    'message': str(e)
                }), 500
        
        @self.app.route('/api/write_parameter', methods=['POST'])
        def write_parameter():
            """写入参数值API"""
            try:
                data = request.get_json()
                param_name = data.get('param_name')
                value = data.get('value')
                
                if not param_name or value is None:
                    return jsonify({
                        'success': False,
                        'message': 'param_name and value are required'
                    }), 400
                
                # 转换value类型（尝试转换为数字）
                try:
                    if isinstance(value, str):
                        # 尝试转换为float或int
                        if '.' in value or 'e' in value.lower():
                            value = float(value)
                        else:
                            value = int(value)
                except ValueError:
                    pass  # 保持原值
                
                # 如果Runner可用，直接调用
                if self.runner:
                    success = self.runner.set_parameter(param_name, value)
                    if success:
                        return jsonify({
                            'success': True,
                            'message': f'Parameter {param_name} set to {value}'
                        })
                    else:
                        return jsonify({
                            'success': False,
                            'message': f'Failed to set parameter {param_name}'
                        }), 400
                else:
                    # Runner不可用，通过Redis发布消息（独立运行模式）
                    try:
                        # 发布参数写入消息到Redis
                        write_message = {
                            'action': 'write_parameter',
                            'param_name': param_name,
                            'value': value,
                            'timestamp': datetime.now().isoformat()
                        }
                        redis_key = "plc:command:write_parameter"
                        self.redis_client.publish(redis_key, json.dumps(write_message, ensure_ascii=False))
                        logger.info(f"Published parameter write command to Redis: {param_name} = {value}")
                        
                        return jsonify({
                            'success': True,
                            'message': f'Parameter write command sent to Redis: {param_name} = {value}'
                        })
                    except Exception as e:
                        logger.error(f"Failed to publish parameter write command to Redis: {e}")
                        return jsonify({
                            'success': False,
                            'message': f'Failed to send parameter write command: {str(e)}'
                        }), 500
            except Exception as e:
                logger.error(f"Failed to write parameter: {e}")
                return jsonify({
                    'success': False,
                    'message': str(e)
                }), 500
        
        
        @self.socketio.on('connect')
        def handle_connect():
            """WebSocket连接处理"""
            logger.info('Client connected')
            emit('connected', {'message': 'Connected to PLC Mock Server'})
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            """WebSocket断开处理"""
            logger.info('Client disconnected')
        
        @self.socketio.on('request_realtime')
        def handle_realtime_request():
            """处理实时数据请求"""
            try:
                redis_key = f"plc:data:current"
                json_data = self.redis_client.get(redis_key)
                
                if json_data:
                    data = json.loads(json_data)
                    emit('realtime_data', data)
            except Exception as e:
                logger.error(f"Failed to handle realtime request: {e}")
                emit('error', {'message': str(e)})
    
    def _realtime_broadcast_loop(self):
        """
        实时数据广播循环
        
        注意：此方法运行在独立线程中，定期从Redis读取数据并广播给所有连接的客户端
        """
        redis_key = "plc:data:current"
        broadcast_interval = 0.5  # 500ms周期
        
        while self._running:
            try:
                # 从Redis读取当前数据
                json_data = self.redis_client.get(redis_key)
                
                if json_data:
                    try:
                        data = json.loads(json_data)
                        # 广播给所有连接的客户端
                        self.socketio.emit('realtime_data', data)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse JSON data from Redis: {e}")
                    except Exception as e:
                        logger.error(f"Failed to emit realtime data: {e}")
                else:
                    # 如果没有数据，记录调试信息（但不频繁记录）
                    logger.debug("No data available in Redis")
                
                # 等待下一个周期
                time.sleep(broadcast_interval)
                
            except redis.RedisError as e:
                logger.error(f"Redis error in broadcast loop: {e}")
                # Redis错误时等待更长时间再重试
                time.sleep(1.0)
            except Exception as e:
                logger.error(f"Unexpected error in realtime broadcast loop: {e}", exc_info=True)
                time.sleep(broadcast_interval)
        
        logger.info("Realtime broadcast loop stopped")
    
    def start(self):
        """
        启动监控模块
        
        注意：此方法会阻塞，直到服务器停止
        """
        if self._running:
            logger.warning("Monitor is already running")
            return
        
        self._running = True
        
        # 启动实时数据广播线程
        self._broadcast_thread = threading.Thread(
            target=self._realtime_broadcast_loop,
            daemon=True,
            name="MonitorBroadcastThread"
        )
        self._broadcast_thread.start()
        logger.info("Realtime broadcast thread started")
        
        # 启动Flask应用（阻塞运行）
        logger.info(f"Starting Monitor web server on {self.host}:{self.port}")
        try:
            self.socketio.run(self.app, host=self.host, port=self.port, allow_unsafe_werkzeug=True)
        except Exception as e:
            logger.error(f"Error starting web server: {e}", exc_info=True)
            self._running = False
            raise
    
    def stop(self):
        """
        停止监控模块
        
        注意：会停止广播线程，但Flask服务器需要外部信号（如SIGINT）才能停止
        """
        if not self._running:
            logger.warning("Monitor is not running")
            return
        
        logger.info("Stopping Monitor module...")
        self._running = False
        
        # 等待广播线程结束
        if self._broadcast_thread and self._broadcast_thread.is_alive():
            self._broadcast_thread.join(timeout=2.0)
            if self._broadcast_thread.is_alive():
                logger.warning("Broadcast thread did not stop within timeout")
        
        logger.info("Monitor stopped")
    
    def _run_simulation(self, task_id: str, tank_params: Dict[str, Any], 
                       valve_params: Dict[str, Any], pid_params: Dict[str, Any],
                       duration: float, sv_values: List[float]):
        """运行模拟（在后台线程中）"""
        try:
            task = _simulation_tasks[task_id]
            
            # 初始化模型和算法
            tank = CylindricalTank(**tank_params)
            valve = Valve(**valve_params)
            
            # PID参数处理
            pid_init_params = {
                'kp': pid_params.get('kp', 12.0),
                'ti': pid_params.get('ti', 30.0),
                'td': pid_params.get('td', 0.15),
                'sv': sv_values[0] if sv_values else 0.0,
                'pv': 0.0,
                'mv': 0.0,
                'h': pid_params.get('h', 100.0),
                'l': pid_params.get('l', 0.0)
            }
            pid = PID(**pid_init_params)
            
            # 初始化时钟
            cycle_time = 0.5
            clock = Clock(cycle_time=cycle_time)
            clock.start()
            
            # 数据记录
            data_records = []
            
            # 计算SV切换时间点
            if len(sv_values) > 1:
                segment_duration = duration / len(sv_values)
                sv_switch_times = [i * segment_duration for i in range(len(sv_values))]
            else:
                sv_switch_times = [0.0]
                sv_values = [sv_values[0] if sv_values else 0.0]
            
            # 初始化参数值
            tank_level = tank.level
            valve_opening = valve.current_opening
            
            # 设置初始SV值
            current_sv_index = 0
            pid.input['sv'] = sv_values[current_sv_index]
            
            # 运行循环
            target_sim_time = duration
            last_update_time = time.time()
            update_interval = 0.5  # 每0.5秒更新一次进度
            
            while clock.current_time < target_sim_time:
                # 检查是否需要切换SV值
                if current_sv_index < len(sv_values) - 1:
                    next_switch_time = sv_switch_times[current_sv_index + 1]
                    if clock.current_time >= next_switch_time:
                        current_sv_index += 1
                        pid.input['sv'] = sv_values[current_sv_index]
                
                # 更新PID的PV（从水箱获取）
                pid.input['pv'] = tank_level
                
                # 执行PID算法
                pid.execute(input_params={'pv': tank_level, 'sv': pid.input['sv']})
                pid_mv = pid.output['mv']
                
                # PID输出 -> 阀门目标开度（通过属性设置）
                valve.target_opening = pid_mv
                valve_opening = valve.execute(step=cycle_time)
                
                # 阀门开度 -> 水箱输入（通过属性设置）
                tank.valve_opening = valve_opening
                tank_level = tank.execute(step=cycle_time)
                
                # 步进时钟
                clock.step()
                
                # 记录数据
                record = {
                    'sim_time': clock.current_time,
                    'pid.sv': pid.input['sv'],
                    'pid.pv': pid.input['pv'],
                    'pid.mv': pid.output['mv'],
                    'tank.level': tank_level,
                    'valve.current_opening': valve_opening
                }
                data_records.append(record)
                
                # 定期更新任务状态（每0.5秒）
                current_time = time.time()
                if current_time - last_update_time >= update_interval:
                    progress = (clock.current_time / target_sim_time) * 100
                    task['progress'] = progress
                    task['data'] = data_records.copy()  # 复制数据，避免线程安全问题
                    last_update_time = current_time
            
            clock.stop()
            
            # 完成
            task['status'] = 'completed'
            task['progress'] = 100.0
            task['data'] = data_records
            
            logger.info(f"Simulation task {task_id} completed with {len(data_records)} records")
            
        except Exception as e:
            logger.error(f"Simulation task {task_id} failed: {e}", exc_info=True)
            if task_id in _simulation_tasks:
                _simulation_tasks[task_id]['status'] = 'error'
                _simulation_tasks[task_id]['error'] = str(e)

