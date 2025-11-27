"""
日志模块
提供按等级输出日志到指定目录的功能
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime


class SafeRotatingFileHandler(RotatingFileHandler):
    """
    安全的日志轮转处理器
    
    在Windows上，如果日志文件被其他进程占用，轮转可能会失败。
    这个类会捕获轮转异常，避免程序崩溃。
    """
    
    def doRollover(self):
        """
        执行日志轮转
        
        如果轮转失败（例如文件被占用），会捕获异常并继续使用当前日志文件
        """
        try:
            super().doRollover()
        except (PermissionError, OSError) as e:
            # 在Windows上，如果文件被其他进程占用，轮转会失败
            # 这种情况下，我们忽略错误，继续使用当前日志文件
            # 这样可以避免程序崩溃，但日志文件可能会继续增长
            pass
        except Exception as e:
            # 其他异常也忽略，避免影响程序运行
            pass


class Logger:
    """日志管理器"""
    
    def __init__(self, log_dir: str = "logs", name: str = "mock_server"):
        """
        初始化日志管理器
        
        Args:
            log_dir: 日志输出目录，默认"logs"
            name: 日志名称，默认"mock_server"
        """
        self.log_dir = log_dir
        self.name = name
        
        # 确保日志目录存在
        os.makedirs(log_dir, exist_ok=True)
        
        # 创建logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # 避免重复添加handler
        if not self.logger.handlers:
            # 创建不同级别的文件handler
            self._setup_handlers()
    
    def _setup_handlers(self):
        """设置不同级别的日志处理器"""
        # DEBUG级别日志
        debug_handler = SafeRotatingFileHandler(
            os.path.join(self.log_dir, f"{self.name}_debug.log"),
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        debug_handler.setLevel(logging.DEBUG)
        debug_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
        )
        debug_handler.setFormatter(debug_formatter)
        
        # INFO级别日志
        info_handler = SafeRotatingFileHandler(
            os.path.join(self.log_dir, f"{self.name}_info.log"),
            maxBytes=10*1024*1024,
            backupCount=5,
            encoding='utf-8'
        )
        info_handler.setLevel(logging.INFO)
        info_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        info_handler.setFormatter(info_formatter)
        
        # WARNING级别日志
        warning_handler = SafeRotatingFileHandler(
            os.path.join(self.log_dir, f"{self.name}_warning.log"),
            maxBytes=10*1024*1024,
            backupCount=5,
            encoding='utf-8'
        )
        warning_handler.setLevel(logging.WARNING)
        warning_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        warning_handler.setFormatter(warning_formatter)
        
        # ERROR级别日志
        error_handler = SafeRotatingFileHandler(
            os.path.join(self.log_dir, f"{self.name}_error.log"),
            maxBytes=10*1024*1024,
            backupCount=5,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
        )
        error_handler.setFormatter(error_formatter)
        
        # 添加所有handler
        self.logger.addHandler(debug_handler)
        self.logger.addHandler(info_handler)
        self.logger.addHandler(warning_handler)
        self.logger.addHandler(error_handler)
    
    def get_logger(self):
        """获取logger实例"""
        return self.logger
    
    def close(self):
        """
        关闭所有日志处理器
        
        在程序退出前调用，确保日志文件被正确关闭，避免Windows上的文件占用问题
        """
        # 先刷新所有日志，确保所有日志都被写入
        for handler in self.logger.handlers[:]:
            try:
                handler.flush()
            except Exception:
                pass
        
        # 然后关闭所有处理器
        # 注意：关闭处理器时，如果文件正在被其他进程占用，可能会失败
        # 但这是正常的，我们忽略这些错误，确保程序能正常退出
        handlers_to_close = list(self.logger.handlers)  # 创建副本，避免迭代时修改列表
        for handler in handlers_to_close:
            try:
                # 先尝试关闭流（这会释放文件句柄）
                if hasattr(handler, 'stream') and handler.stream:
                    try:
                        handler.stream.close()
                    except Exception:
                        pass
                # 然后关闭处理器
                handler.close()
                self.logger.removeHandler(handler)
            except Exception:
                # 忽略关闭时的错误，避免影响程序退出
                # 在Windows上，如果文件被其他进程占用，关闭可能会失败
                pass


# 全局日志实例
_logger_instance = None


def get_logger(log_dir: str = "logs", name: str = "mock_server"):
    """
    获取全局日志实例
    
    Args:
        log_dir: 日志输出目录，默认"logs"
        name: 日志名称，默认"mock_server"
    
    Returns:
        logger实例
    """
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = Logger(log_dir, name)
    return _logger_instance.get_logger()


def close_logger():
    """
    关闭全局日志实例
    
    在程序退出前调用，确保日志文件被正确关闭
    """
    global _logger_instance
    if _logger_instance is not None:
        _logger_instance.close()
        _logger_instance = None

