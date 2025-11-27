"""
PLC Mock Server - 监控模块独立启动脚本
启动监控Web服务器，通过Redis和数据库与运行模块通信
"""
import yaml
import signal
import sys
from plc.plc_configuration import Configuration
from plc.data_storage import DataStorage
from monitor.web_server import Monitor
from utils.logger import get_logger

logger = get_logger()


class MonitorRunner:
    """
    PLC监控模块管理器
    
    独立启动监控Web服务器，通过Redis和数据库与运行模块通信
    """
    
    def __init__(self, config_file: str = "config/config.yaml",
                 group_config_file: str = "config/example_config.yaml"):
        """
        初始化监控模块管理器
        
        Args:
            config_file: 系统配置文件路径
            group_config_file: 组态配置文件路径
        """
        # 加载系统配置
        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        # 加载组态配置
        self.group_config = Configuration(config_file=group_config_file)
        
        # 初始化各个模块
        redis_config = self.config.get('redis', {})
        
        # 数据存储模块（用于历史数据查询）
        storage_config = self.config.get('storage', {})
        db_path = storage_config.get('db_path', 'plc_data.db')
        self.data_storage = DataStorage(self.group_config, redis_config, db_path)
        
        # 监控模块（不传入Runner实例，独立运行）
        monitor_config = self.config.get('monitor', {})
        monitor_host = monitor_config.get('host', '0.0.0.0')
        monitor_port = monitor_config.get('port', 5000)
        self.monitor = Monitor(self.group_config, redis_config, self.data_storage,
                              runner=None, host=monitor_host, port=monitor_port)
        
        logger.info("MonitorRunner initialized")
    
    def start(self):
        """启动监控模块"""
        try:
            # 启动监控模块（阻塞运行）
            logger.info("Starting Monitor module...")
            logger.info("Monitor web server will start on http://{}:{}".format(
                self.monitor.host, self.monitor.port))
            self.monitor.start()
            
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
            self.stop()
        except Exception as e:
            logger.error(f"Error starting monitor: {e}", exc_info=True)
            self.stop()
            raise
    
    def stop(self):
        """停止监控模块"""
        logger.info("Stopping monitor module...")
        
        try:
            self.monitor.stop()
        except Exception as e:
            logger.error(f"Error stopping Monitor: {e}")
        
        try:
            self.data_storage.close()
        except Exception as e:
            logger.error(f"Error closing DataStorage: {e}")
        
        logger.info("Monitor module stopped")
    
    def update_configuration(self, new_group_config: Configuration):
        """
        更新组态配置（在线配置）
        
        Args:
            new_group_config: 新的组态配置实例
        """
        self.group_config = new_group_config
        
        # 更新各个模块的配置
        self.monitor.config = new_group_config
        self.data_storage.config = new_group_config
        self.data_storage.update_configuration()
        
        logger.info("Configuration updated")


def main(config_file: str = "config/config.yaml",
         group_config_file: str = "config/example_config.yaml"):
    """
    主函数 - 启动监控模块
    
    Args:
        config_file: 系统配置文件路径，默认"config/config.yaml"
        group_config_file: 组态配置文件路径，默认"config/example_config.yaml"
    """
    # 创建监控实例
    monitor = MonitorRunner(config_file, group_config_file)
    
    # 注册信号处理
    def signal_handler(sig, frame):
        logger.info("Received signal, shutting down...")
        monitor.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 启动监控
    try:
        monitor.start()
    except Exception as e:
        logger.error(f"Monitor error: {e}", exc_info=True)
        monitor.stop()
        sys.exit(1)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='PLC Mock Server - 监控模块')
    parser.add_argument('--config', type=str, default='config/config.yaml',
                       help='系统配置文件路径')
    parser.add_argument('--group-config', type=str, default='config/example_config.yaml',
                       help='组态配置文件路径')
    
    args = parser.parse_args()
    main(args.config, args.group_config)

