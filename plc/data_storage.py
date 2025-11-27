"""
PLC数据模块
从Redis读取数据，存储到SQLite数据库，提供历史数据查询和统计接口
"""
import threading
import time
import json
import sqlite3
import redis
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy import create_engine, Column, Float, String, DateTime, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from plc.plc_configuration import Configuration
from utils.logger import get_logger

logger = get_logger()

Base = declarative_base()


class DataRecord(Base):
    """数据记录表"""
    __tablename__ = 'data_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    param_name = Column(String(255), nullable=False, index=True)
    param_value = Column(Float, nullable=False)
    instance_name = Column(String(255), nullable=False, index=True)
    param_type = Column(String(50), nullable=False)  # 'model' or 'algorithm'


class DataStorage:
    """
    PLC数据模块
    
    根据组态信息，每个存储周期从运行模块的Redis获取当前周期数据，
    更新到本地SQLite数据库，同时对外实现历史数据查询接口，历史数据统计接口
    """
    
    # 默认存储周期（秒），1秒（降低磁盘I/O频率）
    # 注意：可以根据实际需求调整，更长的周期可以减少磁盘I/O，但会降低数据精度
    DEFAULT_STORAGE_CYCLE = 1.0
    
    # Redis键前缀
    REDIS_KEY_PREFIX = "plc:data:"
    
    def __init__(self, configuration: Configuration, redis_config: dict,
                 db_path: str = "plc_data.db", enable_storage_loop: bool = False):
        """
        初始化数据存储模块
        
        Args:
            configuration: 组态模板实例
            redis_config: Redis配置字典
            db_path: SQLite数据库路径，默认"plc_data.db"
            enable_storage_loop: 是否启用异步存储循环（从Redis读取数据），默认False
                                注意：如果Runner直接调用store_data_sync，则不需要启用此选项
        """
        self.config = configuration
        self.redis_config = redis_config
        self.db_path = db_path
        self.enable_storage_loop = enable_storage_loop
        
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
            logger.info("Redis connection established in DataStorage module")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
        
        # 初始化SQLite数据库
        # 使用WAL模式提高写入性能，减少磁盘I/O
        self.engine = create_engine(
            f'sqlite:///{db_path}',
            echo=False,
            connect_args={
                'check_same_thread': False,
                'timeout': 20.0
            }
        )
        Base.metadata.create_all(self.engine)
        
        # 启用WAL模式和优化SQLite设置（减少磁盘I/O）
        # 直接使用SQLite连接设置PRAGMA
        sqlite_conn = sqlite3.connect(db_path, check_same_thread=False)
        sqlite_conn.execute("PRAGMA journal_mode=WAL")
        sqlite_conn.execute("PRAGMA synchronous=NORMAL")
        sqlite_conn.execute("PRAGMA cache_size=-64000")
        sqlite_conn.execute("PRAGMA temp_store=MEMORY")
        sqlite_conn.close()
        
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        
        # 创建复合索引以提高查询性能（在表创建后）
        self._create_indexes()
        
        # 运行控制
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        
        # 存储周期（真实时间，秒）
        self.storage_cycle = self.DEFAULT_STORAGE_CYCLE
        
        # 记录上次存储的真实时间戳（用于确保按真实时间间隔存储）
        self._last_stored_real_time: Optional[datetime] = None
        
        # 记录上次存储的模拟时间（用于确保按模拟时间间隔存储）
        self._last_stored_sim_time: Optional[float] = None
        
        # 记录已处理的Redis历史数据索引（用于避免重复处理）
        self._processed_history_count = 0
        
        # 批量提交计数器（用于减少磁盘I/O）
        self._flush_count = 0
        
        logger.info(f"DataStorage initialized with db_path={db_path}")
    
    def _create_indexes(self):
        """创建数据库索引以提高查询性能"""
        try:
            from sqlalchemy import Index, text
            # 创建复合索引：timestamp + param_name（最常用的查询组合）
            # 注意：SQLAlchemy的Index需要在表创建后单独创建
            with self.engine.connect() as conn:
                # 检查索引是否已存在
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_timestamp_param 
                    ON data_records(timestamp, param_name)
                """))
                # 创建时间戳索引（如果不存在）
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_timestamp 
                    ON data_records(timestamp)
                """))
                # 创建参数名索引（如果不存在）
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_param_name 
                    ON data_records(param_name)
                """))
                conn.commit()
            logger.info("Database indexes created successfully")
        except Exception as e:
            logger.warning(f"Failed to create indexes: {e}")
    
    def store_data_sync(self, params: Dict[str, Any], timestamp: datetime, 
                        sim_time: Optional[float] = None):
        """
        同步存储数据到SQLite（供Runner模块直接调用）
        
        Args:
            params: 参数字典
            timestamp: 时间戳（datetime对象）
            sim_time: 模拟时间（秒），用于判断是否达到存储周期（已废弃，改为基于真实时间）
        """
        # 检查是否应该存储（基于真实时间间隔，而不是模拟时间）
        # 这样可以确保在真实时间内按固定间隔存储，不受模拟时间影响
        if self._last_stored_real_time is None:
            # 第一次存储
            self._last_stored_real_time = timestamp
        else:
            # 检查真实时间间隔是否达到存储周期
            time_diff = (timestamp - self._last_stored_real_time).total_seconds()
            if time_diff < self.storage_cycle:
                # 未达到存储周期，不存储
                return
        
        # 调用内部存储方法
        self._store_data(params, timestamp)
        
        # 更新上次存储的真实时间
        self._last_stored_real_time = timestamp
    
    def _store_data(self, params: Dict[str, Any], timestamp: datetime):
        """
        存储数据到SQLite（内部方法）
        
        注意：此方法使用锁保护，确保线程安全
        
        Args:
            params: 参数字典
            timestamp: 时间戳
        """
        with self._lock:
            try:
                records = []
                
                for param_name, param_value in params.items():
                    # 解析参数名：instance_name.param_name
                    parts = param_name.split('.', 1)
                    if len(parts) != 2:
                        continue
                    
                    instance_name = parts[0]
                    param = parts[1]
                    
                    # 判断是模型还是算法
                    models_config = self.config.get_models()
                    algorithms_config = self.config.get_algorithms()
                    
                    if instance_name in models_config:
                        param_type = 'model'
                    elif instance_name in algorithms_config:
                        param_type = 'algorithm'
                    else:
                        param_type = 'unknown'
                    
                    # 只存储数值类型
                    if isinstance(param_value, (int, float)):
                        record = DataRecord(
                            timestamp=timestamp,
                            param_name=param_name,
                            param_value=float(param_value),
                            instance_name=instance_name,
                            param_type=param_type
                        )
                        records.append(record)
                
                # 批量插入（优化：减少commit频率以降低磁盘I/O）
                if records:
                    self.session.bulk_save_objects(records)
                    # 使用flush而不是立即commit，减少磁盘同步频率
                    # flush会将数据写入数据库但不立即同步到磁盘
                    self.session.flush()
                    # 每10次flush才commit一次，进一步减少磁盘I/O
                    # 注意：这可能会在系统崩溃时丢失少量数据，但大幅提高性能
                    self._flush_count += 1
                    if self._flush_count >= 10:
                        self.session.commit()
                        self._flush_count = 0
                    logger.debug(f"Stored {len(records)} records to database (flush count: {self._flush_count})")
            except Exception as e:
                logger.error(f"Failed to store data: {e}", exc_info=True)
                self.session.rollback()
                self._flush_count = 0
    
    def _storage_loop(self):
        """
        存储循环（从Redis读取数据并存储到SQLite）
        
        在时间加速模式下，从Redis历史列表批量读取数据，
        按照模拟时间间隔决定是否存储，确保每个存储周期（模拟时间）的数据都被记录
        """
        while self._running:
            try:
                cycle_start_time = time.time()
                
                # 从Redis历史列表读取未处理的数据
                history_key = f"{self.REDIS_KEY_PREFIX}history"
                history_length = self.redis_client.llen(history_key)
                
                if history_length > self._processed_history_count:
                    # 有新的历史数据，批量读取
                    new_data_count = history_length - self._processed_history_count
                    # 读取所有未处理的数据（从新到旧）
                    new_data_list = self.redis_client.lrange(
                        history_key, 
                        self._processed_history_count, 
                        history_length - 1
                    )
                    
                    # 按时间顺序处理（从旧到新）
                    for json_data in reversed(new_data_list):
                        try:
                            data = json.loads(json_data)
                            params = data.get('params', {})
                            timestamp_str = data.get('timestamp')
                            
                            # 转换时间戳
                            if timestamp_str:
                                timestamp = datetime.fromtimestamp(timestamp_str)
                                sim_time = timestamp_str  # 使用时间戳作为模拟时间
                            else:
                                timestamp = datetime.now()
                                sim_time = timestamp.timestamp()
                            
                            # 检查是否应该存储（基于模拟时间间隔）
                            should_store = False
                            if self._last_stored_sim_time is None:
                                # 第一次存储
                                should_store = True
                            else:
                                # 检查模拟时间间隔是否达到存储周期
                                time_diff = abs(sim_time - self._last_stored_sim_time)
                                if time_diff >= self.storage_cycle:
                                    should_store = True
                            
                            if should_store:
                                # 存储数据
                                self._store_data(params, timestamp)
                                self._last_stored_sim_time = sim_time
                                logger.debug(f"Stored data at simulation time {sim_time:.2f}s")
                        
                        except Exception as e:
                            logger.error(f"Failed to process history data: {e}", exc_info=True)
                    
                    # 更新已处理的数据计数
                    self._processed_history_count = history_length
                
                else:
                    # 没有新的history数据，尝试从current键读取（用于正常速度模式或history列表为空的情况）
                    # 注意：在正常速度模式下，history列表也会被更新，但可能更新较慢
                    # 这里作为备用方案，确保数据能够被存储
                    redis_key = f"{self.REDIS_KEY_PREFIX}current"
                    json_data = self.redis_client.get(redis_key)
                    
                    if json_data:
                        try:
                            data = json.loads(json_data)
                            params = data.get('params', {})
                            timestamp_str = data.get('timestamp')
                            
                            # 转换时间戳
                            if timestamp_str:
                                timestamp = datetime.fromtimestamp(timestamp_str)
                                sim_time = timestamp_str
                            else:
                                timestamp = datetime.now()
                                sim_time = timestamp.timestamp()
                            
                            # 检查是否应该存储（基于模拟时间间隔）
                            should_store = False
                            if self._last_stored_sim_time is None:
                                should_store = True
                            else:
                                time_diff = abs(sim_time - self._last_stored_sim_time)
                                if time_diff >= self.storage_cycle:
                                    should_store = True
                            
                            if should_store:
                                self._store_data(params, timestamp)
                                self._last_stored_sim_time = sim_time
                        except Exception as e:
                            logger.error(f"Failed to process current data: {e}", exc_info=True)
                
                # 计算执行时间
                cycle_time = time.time() - cycle_start_time
                
                # 睡眠到下一个周期（真实时间，用于定期检查）
                # 在加速模式下，这个周期应该较短，以便及时处理历史数据
                sleep_time = min(self.storage_cycle, 0.1) - cycle_time  # 最多等待0.1秒或存储周期
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    # 如果执行时间超过等待时间，记录警告但不等待
                    if cycle_time > 0.1:
                        logger.warning(f"Storage cycle time ({cycle_time:.4f}s) exceeds check interval (0.1s)")
                        
            except Exception as e:
                logger.error(f"Error in storage loop: {e}", exc_info=True)
                time.sleep(0.1)  # 出错时等待0.1秒再重试
    
    def query_history(self, param_name: str = None, instance_name: str = None,
                     start_time: datetime = None, end_time: datetime = None,
                     limit: int = 1000, sample_interval: float = None) -> List[Dict[str, Any]]:
        """
        查询历史数据（优化版本）
        
        Args:
            param_name: 参数名称（可选），如"tank1.level"
            instance_name: 实例名称（可选），如"tank1"
            start_time: 开始时间（可选）
            end_time: 结束时间（可选）
            limit: 返回记录数限制，默认1000
            sample_interval: 采样间隔（秒），如果提供，会按时间间隔采样，减少返回数据量
        
        Returns:
            历史数据记录列表
        """
        try:
            import time as time_module
            query_start_time = time_module.time()
            
            query = self.session.query(DataRecord)
            
            # 应用过滤条件
            if param_name:
                query = query.filter(DataRecord.param_name == param_name)
            if instance_name:
                query = query.filter(DataRecord.instance_name == instance_name)
            if start_time:
                query = query.filter(DataRecord.timestamp >= start_time)
            if end_time:
                query = query.filter(DataRecord.timestamp <= end_time)
            
            # 如果指定了采样间隔，先获取所有记录的时间戳，然后采样
            if sample_interval and sample_interval > 0:
                # 先获取所有符合条件的时间戳（去重）
                time_query = self.session.query(DataRecord.timestamp).distinct()
                if param_name:
                    time_query = time_query.filter(DataRecord.param_name == param_name)
                if instance_name:
                    time_query = time_query.filter(DataRecord.instance_name == instance_name)
                if start_time:
                    time_query = time_query.filter(DataRecord.timestamp >= start_time)
                if end_time:
                    time_query = time_query.filter(DataRecord.timestamp <= end_time)
                time_query = time_query.order_by(DataRecord.timestamp)
                
                all_timestamps = [row[0] for row in time_query.all()]
                
                # 采样时间戳
                sampled_timestamps = []
                last_sampled_time = None
                for ts in all_timestamps:
                    if last_sampled_time is None:
                        sampled_timestamps.append(ts)
                        last_sampled_time = ts
                    else:
                        time_diff = (ts - last_sampled_time).total_seconds()
                        if time_diff >= sample_interval:
                            sampled_timestamps.append(ts)
                            last_sampled_time = ts
                
                # 只查询采样后的时间戳
                if sampled_timestamps:
                    query = query.filter(DataRecord.timestamp.in_(sampled_timestamps))
                else:
                    return []
            
            # 按时间倒序排列
            query = query.order_by(DataRecord.timestamp.desc())
            
            # 限制返回数量
            records = query.limit(limit).all()
            
            # 转换为字典列表（优化：使用列表推导式）
            result = [
                {
                    'id': record.id,
                    'timestamp': record.timestamp.isoformat(),
                    'param_name': record.param_name,
                    'param_value': record.param_value,
                    'instance_name': record.instance_name,
                    'param_type': record.param_type
                }
                for record in records
            ]
            
            query_time = time_module.time() - query_start_time
            logger.debug(f"Query history completed in {query_time:.3f}s, returned {len(result)} records")
            
            return result
        except Exception as e:
            logger.error(f"Failed to query history: {e}", exc_info=True)
            return []
    
    def get_statistics(self, param_name: str, start_time: datetime = None,
                      end_time: datetime = None) -> Dict[str, Any]:
        """
        获取历史数据统计信息（优化版本：使用SQL聚合函数）
        
        Args:
            param_name: 参数名称，如"tank1.level"
            start_time: 开始时间（可选）
            end_time: 结束时间（可选）
        
        Returns:
            统计信息字典，包含count, min, max, avg, sum等
        """
        try:
            from sqlalchemy import func
            
            query = self.session.query(
                func.count(DataRecord.param_value).label('count'),
                func.min(DataRecord.param_value).label('min'),
                func.max(DataRecord.param_value).label('max'),
                func.avg(DataRecord.param_value).label('avg'),
                func.sum(DataRecord.param_value).label('sum')
            ).filter(
                DataRecord.param_name == param_name
            )
            
            # 应用时间过滤
            if start_time:
                query = query.filter(DataRecord.timestamp >= start_time)
            if end_time:
                query = query.filter(DataRecord.timestamp <= end_time)
            
            # 执行查询（返回单行结果）
            result = query.first()
            
            if not result or result.count == 0:
                return {
                    'param_name': param_name,
                    'count': 0,
                    'min': None,
                    'max': None,
                    'avg': None,
                    'sum': None
                }
            
            return {
                'param_name': param_name,
                'count': result.count,
                'min': float(result.min) if result.min is not None else None,
                'max': float(result.max) if result.max is not None else None,
                'avg': float(result.avg) if result.avg is not None else None,
                'sum': float(result.sum) if result.sum is not None else None
            }
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}", exc_info=True)
            return {}
    
    def get_latest_values(self, instance_name: str = None) -> Dict[str, Any]:
        """
        获取最新参数值
        
        Args:
            instance_name: 实例名称（可选），如果提供则只返回该实例的参数
        
        Returns:
            参数字典，key为参数名，value为最新值
        """
        try:
            query = self.session.query(DataRecord)
            
            if instance_name:
                query = query.filter(DataRecord.instance_name == instance_name)
            
            # 获取每个参数的最新值
            # 使用子查询获取每个参数的最大时间戳
            from sqlalchemy import func
            subquery = query.group_by(DataRecord.param_name).with_entities(
                DataRecord.param_name,
                func.max(DataRecord.timestamp).label('max_timestamp')
            ).subquery()
            
            # 连接查询获取最新记录
            latest_records = self.session.query(DataRecord).join(
                subquery,
                (DataRecord.param_name == subquery.c.param_name) &
                (DataRecord.timestamp == subquery.c.max_timestamp)
            ).all()
            
            result = {}
            for record in latest_records:
                result[record.param_name] = record.param_value
            
            return result
        except Exception as e:
            logger.error(f"Failed to get latest values: {e}", exc_info=True)
            return {}
    
    def update_configuration(self):
        """更新配置（在线配置时调用）"""
        logger.info("Configuration updated in DataStorage")
    
    def start(self):
        """
        启动数据存储模块
        
        注意：如果enable_storage_loop=False，则不会启动异步存储循环
        此时数据存储完全依赖Runner直接调用store_data_sync方法
        """
        if self._running:
            logger.warning("DataStorage is already running")
            return
        
        self._running = True
        
        # 只有在启用异步存储循环时才启动线程
        if self.enable_storage_loop:
            self._thread = threading.Thread(target=self._storage_loop, daemon=True)
            self._thread.start()
            logger.info("DataStorage started (with async storage loop)")
        else:
            logger.info("DataStorage started (sync mode only, no async loop)")
    
    def stop(self):
        """
        停止数据存储模块
        
        注意：会确保所有未提交的数据被提交，避免数据丢失
        """
        if not self._running:
            logger.warning("DataStorage is not running")
            return
        
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        
        # 确保所有未提交的数据被提交
        with self._lock:
            try:
                if self._flush_count > 0:
                    self.session.commit()
                    self._flush_count = 0
                    logger.info("Committed pending data before stopping")
            except Exception as e:
                logger.error(f"Failed to commit pending data: {e}", exc_info=True)
        
        logger.info("DataStorage stopped")
    
    def close(self):
        """
        关闭数据库连接
        
        注意：会确保所有未提交的数据被提交，然后关闭session和engine
        """
        # 确保所有未提交的数据被提交
        with self._lock:
            try:
                if self._flush_count > 0:
                    self.session.commit()
                    self._flush_count = 0
                    logger.info("Committed pending data before closing")
            except Exception as e:
                logger.error(f"Failed to commit pending data: {e}", exc_info=True)
        
        # 关闭session和engine
        try:
            self.session.close()
            self.engine.dispose()
            logger.info("DataStorage closed")
        except Exception as e:
            logger.error(f"Failed to close DataStorage: {e}", exc_info=True)

