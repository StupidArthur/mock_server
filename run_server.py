"""
PLC Mock Server - 运行模块独立启动脚本
启动运行模块（Runner、DataStorage、Communication），不启动监控Web服务器
"""
import yaml
import signal
import sys
from plc.plc_configuration import Configuration
from plc.runner import Runner
from plc.communication import Communication
from plc.data_storage import DataStorage
from utils.logger import get_logger

logger = get_logger()


class ServerRunner:
    """
    PLC运行模块管理器
    
    管理运行模块的启动、停止和协调
    不包含监控Web服务器
    """
    
    def __init__(self, config_file: str = "config/config.yaml",
                 group_config_file: str = "config/example_config.yaml"):
        """
        初始化运行模块管理器
        
        Args:
            config_file: 系统配置文件路径
            group_config_file: 组态配置文件路径
        """
        # 加载系统配置
        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        # 初始化各个模块
        redis_config = self.config.get('redis', {})
        
        # 运行模块（从本地目录加载配置和快照，传入数据存储模块）
        # 注意：不再从config目录加载组态文件，而是从plc/local目录加载
        self.runner = Runner(
            configuration=None,  # 不传入配置，让Runner从本地目录加载
            redis_config=redis_config,
            data_storage=None,  # 先不传入，等Runner初始化后再设置
            local_dir="plc/local"
        )
        
        # 数据存储模块（需要Runner的配置，所以后初始化）
        storage_config = self.config.get('storage', {})
        db_path = storage_config.get('db_path', 'plc_data.db')
        self.data_storage = DataStorage(self.runner.config, redis_config, db_path)
        
        # 设置Runner的数据存储模块
        self.runner.data_storage = self.data_storage
        
        # 组态配置（用于其他模块，如Communication）
        self.group_config = self.runner.config
        
        # 通信模块（使用Runner的配置）
        opcua_config = self.config.get('opcua', {})
        server_url = opcua_config.get('server_url', Communication.DEFAULT_SERVER_URL)
        self.communication = Communication(self.group_config, redis_config, server_url, opcua_config)
        
        logger.info("ServerRunner initialized")
    
    def start(self):
        """启动所有运行模块"""
        try:
            # 启动运行模块
            logger.info("Starting Runner module...")
            self.runner.start()
            
            # 启动数据存储模块
            logger.info("Starting DataStorage module...")
            self.data_storage.start()
            
            # 启动通信模块
            logger.info("Starting Communication module...")
            self.communication.start()
            
            # 保持运行（等待信号）
            logger.info("All running modules started. Press Ctrl+C to stop.")
            try:
                import time
                while True:
                    time.sleep(1)  # 等待信号（Windows兼容）
            except KeyboardInterrupt:
                logger.info("Received interrupt signal")
                self.stop()
            
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
            self.stop()
        except Exception as e:
            logger.error(f"Error starting server: {e}", exc_info=True)
            self.stop()
            raise
    
    def stop(self):
        """停止所有运行模块"""
        logger.info("Stopping all running modules...")
        
        try:
            self.runner.stop()
        except Exception as e:
            logger.error(f"Error stopping Runner: {e}")
        
        try:
            self.data_storage.stop()
            self.data_storage.close()
        except Exception as e:
            logger.error(f"Error stopping DataStorage: {e}")
        
        try:
            self.communication.stop()
        except Exception as e:
            logger.error(f"Error stopping Communication: {e}")
        
        logger.info("All running modules stopped")
    
    def update_configuration(self, new_group_config: Configuration):
        """
        更新组态配置（在线配置）
        
        Args:
            new_group_config: 新的组态配置实例
        """
        self.group_config = new_group_config
        
        # 更新各个模块的配置
        self.runner.config = new_group_config
        self.runner.update_configuration()
        
        self.communication.config = new_group_config
        self.communication.update_configuration()
        
        self.data_storage.config = new_group_config
        self.data_storage.update_configuration()
        
        logger.info("Configuration updated")


def main(config_file: str = "config/config.yaml",
         group_config_file: str = "config/example_config.yaml"):
    """
    主函数 - 启动运行模块
    
    Args:
        config_file: 系统配置文件路径，默认"config/config.yaml"
        group_config_file: 组态配置文件路径，默认"config/example_config.yaml"
    """
    # 创建服务器实例
    server = ServerRunner(config_file, group_config_file)
    
    # 注册信号处理
    def signal_handler(sig, frame):
        logger.info("Received signal, shutting down...")
        server.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 启动服务器
    try:
        server.start()
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        server.stop()
        sys.exit(1)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='PLC Mock Server - 运行模块')
    parser.add_argument('--config', type=str, default='config/config.yaml',
                       help='系统配置文件路径')
    parser.add_argument('--group-config', type=str, default='config/example_config.yaml',
                       help='组态配置文件路径')
    
    args = parser.parse_args()
    main(args.config, args.group_config)

