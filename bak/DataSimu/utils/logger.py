"""
日志模块
提供按等级输出日志到指定目录的功能
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime


class Logger:
    """日志管理器"""
    
    def __init__(self, log_dir: str = r"D:\arthur_log", name: str = "datasimu"):
        """
        初始化日志管理器
        
        Args:
            log_dir: 日志输出目录
            name: 日志名称
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
        debug_handler = RotatingFileHandler(
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
        info_handler = RotatingFileHandler(
            os.path.join(self.log_dir, f"{self.name}_info.log"),
            maxBytes=10*1024*1024,
            backupCount=5,
            encoding='utf-8'
        )
        info_handler.setLevel(logging.INFO)
        info_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        info_handler.setFormatter(info_formatter)
        
        # WARNING级别日志
        warning_handler = RotatingFileHandler(
            os.path.join(self.log_dir, f"{self.name}_warning.log"),
            maxBytes=10*1024*1024,
            backupCount=5,
            encoding='utf-8'
        )
        warning_handler.setLevel(logging.WARNING)
        warning_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        warning_handler.setFormatter(warning_formatter)
        
        # ERROR级别日志
        error_handler = RotatingFileHandler(
            os.path.join(self.log_dir, f"{self.name}_error.log"),
            maxBytes=10*1024*1024,
            backupCount=5,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
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


# 全局日志实例
_logger_instance = None


def get_logger(log_dir: str = r"D:\arthur_log", name: str = "datasimu"):
    """
    获取全局日志实例
    
    Args:
        log_dir: 日志输出目录
        name: 日志名称
    
    Returns:
        logger实例
    """
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = Logger(log_dir, name)
    return _logger_instance.get_logger()

