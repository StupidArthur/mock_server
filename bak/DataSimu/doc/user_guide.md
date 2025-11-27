# 使用说明文档

## 目录

1. [快速开始](#快速开始)
2. [组态配置](#组态配置)
3. [数据模拟](#数据模拟)
4. [仿真运行](#仿真运行)
5. [日志查看](#日志查看)

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 创建配置文件

创建 `config.yaml` 文件：

```yaml
cycle_time: 0.1
models:
  tank1:
    type: cylindrical_tank
    params:
      height: 10.0
      radius: 2.0
      inlet_area: 0.01
      inlet_velocity: 5.0
      outlet_area: 0.005
      initial_level: 5.0
      step: 0.1
  valve1:
    type: valve
    params:
      min_opening: 0.0
      max_opening: 100.0
      step: 0.1
      full_travel_time: 20.0
algorithms:
  pid1:
    type: PID
    params:
      name: PID1
      kp: 1.0
      Ti: 10.0
      Td: 0.1
      pv: 0.0
      sv: 5.0
      mv: 0.0
      h: 100.0
      l: 0.0
      T: 0.1
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

## 组态配置

### 配置文件结构

组态配置文件使用YAML格式，包含以下部分：

#### 1. cycle_time
系统运行周期（秒）

```yaml
cycle_time: 0.1
```

#### 2. models
模型实例配置

```yaml
models:
  模型名称:
    type: 模型类型  # cylindrical_tank 或 valve
    params:
      # 模型参数
```

**cylindrical_tank 参数：**
- `height`: 水箱高度（米），默认10.0
- `radius`: 水箱半径（米），默认2.0
- `inlet_area`: 入水管满开面积（平方米），默认0.01
- `inlet_velocity`: 入水口水流速（米/秒），默认5.0
- `outlet_area`: 出水口面积（平方米），默认0.005
- `initial_level`: 初始水位高度（米），默认5.0
- `step`: 步进时间（秒），默认0.1

**valve 参数：**
- `min_opening`: 控制下限（%），默认0.0%
- `max_opening`: 控制上限（%），默认100.0%
- `step`: 步进时间（秒），默认0.1
- `full_travel_time`: 满行程达成时间（秒），默认20.0

#### 3. algorithms
算法实例配置

```yaml
algorithms:
  算法名称:
    type: 算法类型  # PID
    params:
      # 算法参数
```

**PID 参数：**
- `name`: 算法名称，默认"PID"
- `kp`: 比例系数，默认1.0
- `Ti`: 积分时间（秒），默认10.0秒（值越小，积分作用越强）
- `Td`: 微分时间（秒），默认0.1秒（值越大，微分作用越强）
- `pv`: 过程变量初始值，默认0.0
- `sv`: 设定值，默认0.0
- `mv`: 输出值初始值，默认0.0
- `h`: 输出上限，默认100.0
- `l`: 输出下限，默认0.0
- `T`: 采样周期（秒），默认0.1

#### 4. connections
连接关系配置

```yaml
connections:
  - from: 源对象名称
    from_param: 源参数名
    to: 目标对象名称
    to_param: 目标参数名
```

**支持的连接：**
- 算法输出 → 模型输入
- 模型输出 → 算法输入
- 算法输出 → 算法输入

## 数据模拟

### 基本用法

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

### 参数说明

- `duration`: 模拟持续时间（秒）
- `output_file`: 输出Excel文件路径

### 输出数据格式

Excel文件包含以下列：
- `time`: 时间戳（秒）
- `模型名.参数名`: 模型参数值
- `算法名.参数名`: 算法参数值

例如：
- `tank1.level`: 水箱液位
- `valve1.current_opening`: 阀门开度（%）
- `pid1.mv`: PID输出值

## 仿真运行

### 基本用法

```python
from plc.configuration import Configuration
from plc.simulation_runner import SimulationRunner, CommunicationInterface

# 自定义通信接口
class MyCommunication(CommunicationInterface):
    def send_data(self, data):
        # 实现数据发送逻辑
        print(f"Sending: {data}")
    
    def close(self):
        # 关闭连接
        pass

# 加载配置
config = Configuration(config_file='config.yaml')

# 创建仿真运行器
runner = SimulationRunner(config, MyCommunication())

# 运行仿真（1000个周期）
runner.run(cycles=1000)

# 或按时间运行
runner.run(duration=100.0)
```

### 通信接口实现示例

#### HTTP通信

```python
import requests

class HTTPCommunication(CommunicationInterface):
    def __init__(self, url):
        self.url = url
    
    def send_data(self, data):
        requests.post(self.url, json=data)
```

#### WebSocket通信

```python
import websocket

class WebSocketCommunication(CommunicationInterface):
    def __init__(self, url):
        self.ws = websocket.create_connection(url)
    
    def send_data(self, data):
        self.ws.send(json.dumps(data))
    
    def close(self):
        self.ws.close()
```

#### OPC UA通信

```python
from opcua import Client

class OPCUACommunication(CommunicationInterface):
    def __init__(self, endpoint):
        self.client = Client(endpoint)
        self.client.connect()
    
    def send_data(self, data):
        # 实现OPC UA数据写入
        pass
    
    def close(self):
        self.client.disconnect()
```

## 日志查看

日志文件按等级输出到 `D:\arthur_log` 目录：

- `datasimu_debug.log`: DEBUG级别日志，包含详细的调试信息
- `datasimu_info.log`: INFO级别日志，包含一般信息
- `datasimu_warning.log`: WARNING级别日志，包含警告信息
- `datasimu_error.log`: ERROR级别日志，包含错误信息

### 日志格式

**DEBUG/ERROR日志：**
```
2024-01-01 12:00:00 - datasimu - DEBUG - file.py:123 - message
```

**INFO/WARNING日志：**
```
2024-01-01 12:00:00 - datasimu - INFO - message
```

## 示例代码

### 完整示例：PID控制水箱液位

```python
from plc.configuration import Configuration
from plc.data_simulator import DataSimulator

# 创建配置
config_dict = {
    'cycle_time': 0.1,
    'models': {
        'tank1': {
            'type': 'cylindrical_tank',
            'params': {
                'height': 10.0,
                'radius': 2.0,
                'initial_level': 3.0,
                'sv': 5.0  # 目标液位
            }
        },
        'valve1': {
            'type': 'valve',
            'params': {
                'full_travel_time': 20.0
            }
        }
    },
    'algorithms': {
        'pid1': {
            'type': 'PID',
            'params': {
                'kp': 2.0,
                'Ti': 4.0,
                'Td': 0.05,
                'sv': 5.0
            }
        }
    },
    'connections': [
        {'from': 'pid1', 'from_param': 'mv', 'to': 'valve1', 'to_param': 'target_opening'},
        {'from': 'valve1', 'from_param': 'current_opening', 'to': 'tank1', 'to_param': 'valve_opening'},
        {'from': 'tank1', 'from_param': 'level', 'to': 'pid1', 'to_param': 'pv'}
    ]
}

config = Configuration(config_dict=config_dict)
simulator = DataSimulator(config)
simulator.run(duration=60.0, output_file='tank_control.xlsx')
```

## 常见问题

### 1. 如何修改PID参数？

在配置文件中修改 `algorithms.pid1.params` 中的 `kp`、`Ti`、`Td` 参数。

### 2. 如何添加新的模型？

继承 `BaseModule` 类，实现 `execute` 方法，然后在 `Runner._initialize_models` 中添加模型类型判断。

### 3. 如何添加新的算法？

继承 `BaseAlgorithm` 类，实现 `execute` 方法，然后在 `Runner._initialize_algorithms` 中添加算法类型判断。

### 4. 数据导出失败？

检查是否安装了 `openpyxl`：
```bash
pip install openpyxl
```

### 5. 日志目录不存在？

程序会自动创建日志目录，如果失败请检查权限。

