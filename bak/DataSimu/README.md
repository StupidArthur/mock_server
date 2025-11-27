# 数据模拟平台

工业数据模拟系统，用于模拟物理模型和控制算法的运行。

## 技术栈

- Python 3.13
- simple_pid
- control
- scipy
- pandas
- numpy
- matplotlib

## 项目结构

```
DataSimu/
├── module/                    # 物理模型模块
│   ├── base_module.py         # BaseModule 基类
│   ├── cylindrical_tank.py    # 圆柱体水箱模型
│   └── valve.py               # 阀门模型
├── algorithm/                 # 控制算法模块
│   ├── base_algorithm.py      # BaseAlgorithm 基类
│   └── pid.py                 # PID算法
├── plc/                       # PLC层
│   ├── configuration.py       # 组态模板设计
│   ├── clock.py               # 时钟模块
│   ├── runner.py              # 组态模板运行模块
│   ├── data_exporter.py       # 运行数据导出模板
│   ├── data_simulator.py      # 数据模拟模块
│   └── simulation_runner.py  # 仿真运行模块
├── utils/                     # 工具模块
│   └── logger.py              # 日志模块
└── doc/                       # 文档目录
```

## 安装

```bash
pip install -r requirements.txt
```

## 快速开始

### 1. 创建组态配置文件

创建YAML配置文件（例如 `config.yaml`）：

```yaml
cycle_time: 0.1
models:
  tank1:
    type: cylindrical_tank
    params:
      height: 10.0
      radius: 2.0
      initial_level: 5.0
  valve1:
    type: valve
    params:
      full_travel_time: 20.0
algorithms:
  pid1:
    type: PID
    params:
      kp: 1.0
      Ti: 10.0
      Td: 0.1
      sv: 5.0
connections:
  - from: pid1
    from_param: mv
    to: valve1
    to_param: target_opening
  - from: valve1
    from_param: current_opening
    to: tank1
    to_param: valve_opening
  - from: tank1
    from_param: level
    to: pid1
    to_param: pv
```

### 2. 运行数据模拟

```python
from plc.configuration import Configuration
from plc.data_simulator import DataSimulator

# 加载配置
config = Configuration(config_file='config.yaml')

# 创建模拟器
simulator = DataSimulator(config)

# 运行模拟（持续10秒）
simulator.run(duration=10.0, output_file='output.xlsx')
```

### 3. 运行仿真（带通信）

```python
from plc.configuration import Configuration
from plc.simulation_runner import SimulationRunner, CommunicationInterface

# 自定义通信接口
class MyCommunication(CommunicationInterface):
    def send_data(self, data):
        # 实现数据发送逻辑
        print(f"Sending: {data}")

# 加载配置
config = Configuration(config_file='config.yaml')

# 创建仿真运行器
runner = SimulationRunner(config, MyCommunication())

# 运行仿真
runner.run(cycles=1000)
```

## 日志

日志文件按等级输出到 `D:\arthur_log` 目录：
- `datasimu_debug.log` - DEBUG级别日志
- `datasimu_info.log` - INFO级别日志
- `datasimu_warning.log` - WARNING级别日志
- `datasimu_error.log` - ERROR级别日志

## 文档

详细文档请参考 `doc/` 目录：
- `architecture.md` - 程序架构图
- `user_guide.md` - 使用说明文档
- `design_doc.md` - 设计文档

