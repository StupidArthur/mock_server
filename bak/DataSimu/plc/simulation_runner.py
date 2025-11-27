"""
仿真运行模块
基于组态模板运行模块，按运行周期模拟运行，每个周期输出结果，
通过外挂的通信模块将数据传送到外部（如OPCUA，http，websocket等）
"""
from typing import Callable, Optional
from plc.runner import Runner
from plc.configuration import Configuration
from utils.logger import get_logger

logger = get_logger()


class CommunicationInterface:
    """
    通信接口抽象类
    
    外部通信模块需要实现此接口
    """
    
    def send_data(self, data: dict):
        """
        发送数据到外部
        
        Args:
            data: 要发送的数据字典
        """
        raise NotImplementedError("Subclass must implement send_data method")
    
    def close(self):
        """关闭连接"""
        pass


class SimulationRunner:
    """
    仿真运行模块
    
    基于组态模板运行模块，按运行周期模拟运行，每个周期输出结果，
    通过外挂的通信模块将数据传送到外部
    """
    
    def __init__(
        self,
        configuration: Configuration,
        communication: Optional[CommunicationInterface] = None
    ):
        """
        初始化仿真运行器
        
        Args:
            configuration: 组态模板实例
            communication: 通信接口实例，如果为None则不发送数据
        """
        self.config = configuration
        self.runner = Runner(configuration)
        self.communication = communication
        self.is_running = False
        
        logger.info("SimulationRunner initialized")
    
    def set_communication(self, communication: CommunicationInterface):
        """
        设置通信接口
        
        Args:
            communication: 通信接口实例
        """
        self.communication = communication
        logger.info("Communication interface set")
    
    def run_one_cycle(self):
        """
        运行一个周期并发送数据
        
        Returns:
            当前周期的数据字典
        """
        # 执行一个周期
        cycle_data = self.runner.execute_one_cycle()
        
        # 添加时间戳
        output_data = {
            'time': self.runner.clock.get_current_time(),
            **cycle_data
        }
        
        # 通过通信接口发送数据
        if self.communication:
            try:
                self.communication.send_data(output_data)
            except Exception as e:
                logger.error(f"Failed to send data via communication interface: {e}")
        
        return output_data
    
    def run(self, duration: float = None, cycles: int = None):
        """
        运行仿真
        
        Args:
            duration: 模拟持续时间（秒），如果提供则忽略cycles
            cycles: 运行周期数，如果duration为None则使用cycles
        """
        self.is_running = True
        self.runner.clock.start()
        
        if duration:
            cycles = int(duration / self.config.get_cycle_time())
        
        logger.info(f"SimulationRunner started, cycles={cycles}")
        
        for i in range(cycles):
            if not self.is_running:
                break
            
            # 运行一个周期
            self.run_one_cycle()
            
            # 同步到下一个周期（用于实时运行）
            self.runner.clock.sleep_to_next_cycle()
            
            if (i + 1) % 100 == 0:
                logger.info(f"Simulation progress: {i+1}/{cycles} cycles")
        
        self.is_running = False
        self.runner.clock.stop()
        
        logger.info("SimulationRunner completed")
    
    def stop(self):
        """停止仿真"""
        self.is_running = False
        if self.communication:
            self.communication.close()
        logger.info("SimulationRunner stopped")
    
    def get_runner(self) -> Runner:
        """
        获取运行模块实例
        
        Returns:
            Runner实例
        """
        return self.runner

