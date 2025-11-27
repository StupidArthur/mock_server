"""
PLC Mock Server - PLC运行模块独立启动脚本
启动PLC运行模块（Runner、DataStorage、Communication），不启动监控Web服务器

PLC模块从本地目录（plc/local/）加载组态配置和运行时快照，完全独立于组态模块。
支持通过Redis接收配置更新，支持异常恢复。
"""
import yaml
import signal
import sys
import os
from plc.runner import Runner
from plc.communication import Communication
from plc.data_storage import DataStorage
from utils.logger import get_logger

logger = get_logger()


class PLCRunner:
    """
    PLC运行模块管理器
    
    管理PLC运行模块的启动、停止和协调，包括：
    - Runner：运行模块（执行模型和算法计算）
    - DataStorage：数据存储模块（历史数据存储）
    - Communication：通信模块（OPCUA Server）
    
    不包含监控Web服务器（由run_monitor.py独立启动）
    """
    
    # 默认系统配置文件
    DEFAULT_CONFIG_FILE = "config/config.yaml"
    
    # 默认本地配置目录
    DEFAULT_LOCAL_DIR = "plc/local"
    
    def __init__(self, config_file: str = None, local_dir: str = None):
        """
        初始化PLC运行模块管理器
        
        Args:
            config_file: 系统配置文件路径，默认"config/config.yaml"
            local_dir: 本地配置目录路径，默认"plc/local"
                      PLC模块从该目录加载组态配置和快照
        """
        # 加载系统配置
        self.config_file = config_file or self.DEFAULT_CONFIG_FILE
        if not os.path.exists(self.config_file):
            logger.error(f"System config file not found: {self.config_file}")
            raise FileNotFoundError(f"System config file not found: {self.config_file}")
        
        with open(self.config_file, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        # 本地配置目录
        self.local_dir = local_dir or self.DEFAULT_LOCAL_DIR
        
        # 检查本地配置目录是否存在
        local_config_file = os.path.join(self.local_dir, "config.yaml")
        if not os.path.exists(local_config_file):
            logger.warning(f"Local config file not found: {local_config_file}")
            logger.warning("PLC module will use default empty configuration")
            logger.info("You can copy a config file to plc/local/config.yaml")
        
        # 初始化各个模块
        redis_config = self.config.get('redis', {})
        
        # 1. 运行模块（从本地目录加载配置和快照）
        # 注意：不再从config目录加载组态文件，而是从plc/local目录加载
        logger.info(f"Initializing Runner module (loading from {self.local_dir})...")
        self.runner = Runner(
            configuration=None,  # 不传入配置，让Runner从本地目录加载
            redis_config=redis_config,
            data_storage=None,  # 先不传入，等Runner初始化后再设置
            local_dir=self.local_dir
        )
        
        # 2. 数据存储模块（需要Runner的配置，所以后初始化）
        logger.info("Initializing DataStorage module...")
        storage_config = self.config.get('storage', {})
        db_path = storage_config.get('db_path', 'plc_data.db')
        self.data_storage = DataStorage(self.runner.config, redis_config, db_path)
        
        # 设置Runner的数据存储模块
        self.runner.data_storage = self.data_storage
        
        # 3. 通信模块（使用Runner的配置）
        logger.info("Initializing Communication module...")
        opcua_config = self.config.get('opcua', {})
        server_url = opcua_config.get('server_url', Communication.DEFAULT_SERVER_URL)
        self.communication = Communication(
            self.runner.config, 
            redis_config, 
            server_url, 
            opcua_config
        )
        
        logger.info("PLCRunner initialized successfully")
        logger.info(f"  - Local config directory: {self.local_dir}")
        logger.info(f"  - System config file: {self.config_file}")
        logger.info(f"  - Redis: {redis_config.get('host', 'localhost')}:{redis_config.get('port', 6379)}")
        logger.info(f"  - OPCUA Server: {server_url}")
        logger.info(f"  - Database: {db_path}")
    
    def start(self):
        """
        启动所有PLC运行模块
        
        启动顺序：
        1. Runner模块（运行循环和配置更新订阅）
        2. DataStorage模块（历史数据存储）
        3. Communication模块（OPCUA Server）
        """
        try:
            # 启动运行模块
            logger.info("=" * 60)
            logger.info("Starting PLC Runner module...")
            logger.info("=" * 60)
            self.runner.start()
            logger.info("✓ Runner module started")
            
            # 启动数据存储模块
            logger.info("=" * 60)
            logger.info("Starting DataStorage module...")
            logger.info("=" * 60)
            self.data_storage.start()
            logger.info("✓ DataStorage module started")
            
            # 启动通信模块
            logger.info("=" * 60)
            logger.info("Starting Communication module (OPCUA Server)...")
            logger.info("=" * 60)
            self.communication.start()
            logger.info("✓ Communication module started")
            
            # 显示运行状态
            logger.info("=" * 60)
            logger.info("All PLC modules started successfully!")
            logger.info("=" * 60)
            logger.info("PLC Mock Server is running...")
            logger.info("  - Press Ctrl+C to stop")
            logger.info("  - Configuration updates: Subscribe to Redis channel 'plc:config:update'")
            logger.info("  - Runtime snapshot: Saved to plc/local/snapshot.yaml (every 10 cycles)")
            logger.info("=" * 60)
            
            # 保持运行（等待信号）
            try:
                import time
                while True:
                    time.sleep(1)  # 等待信号（Windows兼容）
            except KeyboardInterrupt:
                logger.info("Received interrupt signal (Ctrl+C)")
                self.stop()
            
        except KeyboardInterrupt:
            logger.info("Received interrupt signal (Ctrl+C)")
            self.stop()
        except Exception as e:
            logger.error(f"Error starting PLC modules: {e}", exc_info=True)
            self.stop()
            raise
    
    def stop(self):
        """
        停止所有PLC运行模块
        
        停止顺序（与启动顺序相反）：
        1. Communication模块
        2. DataStorage模块
        3. Runner模块（会保存最后一次快照）
        """
        logger.info("=" * 60)
        logger.info("Stopping all PLC modules...")
        logger.info("=" * 60)
        
        # 停止通信模块
        try:
            logger.info("Stopping Communication module...")
            self.communication.stop()
            logger.info("✓ Communication module stopped")
        except Exception as e:
            logger.error(f"Error stopping Communication: {e}")
        
        # 停止数据存储模块
        try:
            logger.info("Stopping DataStorage module...")
            self.data_storage.stop()
            self.data_storage.close()
            logger.info("✓ DataStorage module stopped")
        except Exception as e:
            logger.error(f"Error stopping DataStorage: {e}")
        
        # 停止运行模块（会保存最后一次快照）
        try:
            logger.info("Stopping Runner module (saving final snapshot)...")
            self.runner.stop()
            logger.info("✓ Runner module stopped")
        except Exception as e:
            logger.error(f"Error stopping Runner: {e}")
        
        # 先刷新所有日志，确保所有日志都被写入
        try:
            for handler in logger.handlers[:]:
                handler.flush()
        except Exception:
            pass
        
        # 关闭日志处理器，确保日志文件被正确关闭（避免Windows上的文件占用问题）
        # 注意：关闭日志处理器后，不能再使用logger记录日志
        try:
            from utils.logger import close_logger
            close_logger()
        except Exception:
            pass  # 忽略关闭日志时的错误
        
        # 使用print输出最后的状态信息（因为日志处理器已关闭）
        print("=" * 60)
        print("All PLC modules stopped")
        print("=" * 60)
    
    def get_status(self) -> dict:
        """
        获取PLC模块运行状态
        
        Returns:
            dict: 状态信息字典
        """
        return {
            'runner_running': self.runner._running if hasattr(self.runner, '_running') else False,
            'data_storage_running': self.data_storage._running if hasattr(self.data_storage, '_running') else False,
            'communication_running': self.communication._running if hasattr(self.communication, '_running') else False,
            'local_dir': self.local_dir,
            'config_file': self.config_file,
            'snapshot_exists': self.runner.snapshot_manager.snapshot_exists() if hasattr(self.runner, 'snapshot_manager') else False
        }


def main(config_file: str = None, local_dir: str = None):
    """
    主函数 - 启动PLC运行模块
    
    Args:
        config_file: 系统配置文件路径，默认"config/config.yaml"
        local_dir: 本地配置目录路径，默认"plc/local"
    """
    # 创建PLC运行模块实例
    try:
        server = PLCRunner(config_file=config_file, local_dir=local_dir)
    except Exception as e:
        logger.error(f"Failed to initialize PLC Runner: {e}", exc_info=True)
        sys.exit(1)
    
    # 注册信号处理
    def signal_handler(sig, frame):
        try:
            logger.info("Received signal, shutting down...")
            # 刷新所有日志，确保日志被写入
            try:
                for handler in logger.handlers[:]:
                    handler.flush()
            except Exception:
                pass
        except Exception:
            pass
        
        try:
            server.stop()
        finally:
            # 确保日志被关闭（stop()中已经关闭，这里再次确保）
            try:
                from utils.logger import close_logger
                close_logger()
            except Exception:
                pass
            sys.exit(0)
    
    # Windows下SIGTERM可能不可用，只注册SIGINT
    signal.signal(signal.SIGINT, signal_handler)
    try:
        signal.signal(signal.SIGTERM, signal_handler)
    except (AttributeError, OSError):
        # Windows可能不支持SIGTERM
        pass
    
    # 启动服务器
    try:
        server.start()
    except Exception as e:
        logger.error(f"PLC Server error: {e}", exc_info=True)
        server.stop()
        sys.exit(1)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='PLC Mock Server - PLC运行模块独立启动脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认配置
  python run_plc.py
  
  # 指定系统配置文件
  python run_plc.py --config config/my_config.yaml
  
  # 指定本地配置目录
  python run_plc.py --local-dir plc/custom_local
  
  # 同时指定系统配置和本地目录
  python run_plc.py --config config/my_config.yaml --local-dir plc/custom_local

说明:
  - PLC模块从本地目录（plc/local/）加载组态配置和运行时快照
  - 组态配置：plc/local/config.yaml
  - 运行时快照：plc/local/snapshot.yaml（自动生成）
  - 支持通过Redis接收配置更新（频道：plc:config:update）
  - 支持异常恢复（重启后自动加载快照）
        """
    )
    parser.add_argument(
        '--config', 
        type=str, 
        default=None,
        help='系统配置文件路径（默认：config/config.yaml）'
    )
    parser.add_argument(
        '--local-dir', 
        type=str, 
        default=None,
        help='本地配置目录路径（默认：plc/local）'
    )
    
    args = parser.parse_args()
    main(config_file=args.config, local_dir=args.local_dir)
