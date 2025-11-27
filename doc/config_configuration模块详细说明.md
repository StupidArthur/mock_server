# config/configuration 模块详细说明

## 模块概述

`config/configuration.py` 是组态管理模块，提供组态文件的加载、管理、差异分析和更新功能。它是连接配置文件与PLC运行环境的桥梁。

---

## 类结构

### ConfigurationManager 类

**功能**：
1. 加载组态文件
2. 管理组态内容
3. 向plc_configuration获取当前PLC运行的组态内容
4. 分析两边组态信息的差异
5. 更新组态到PLC（通过Redis消息）

---

## 主要方法详解

### 1. `__init__(config_dir, local_dir, redis_config)`

**初始化组态管理器**

**参数**：
- `config_dir`: 配置文件目录，默认"config"
- `local_dir`: PLC本地配置目录，默认"plc/local"
- `redis_config`: Redis配置字典，用于发送配置更新消息

**功能**：
- 设置配置目录路径
- 初始化当前配置状态
- 配置Redis连接（懒加载）

---

### 2. `load_config_file(config_file) -> Dict[str, Any]`

**加载组态文件**

**参数**：
- `config_file`: 配置文件路径（绝对路径或相对于config_dir的路径）

**返回**：
- 组态配置字典

**功能**：
- 支持绝对路径和相对路径
- 自动解析相对于config_dir的路径
- YAML文件解析
- 配置格式验证
- 错误处理和日志记录

**示例**：
```python
manager = ConfigurationManager()
config = manager.load_config_file("example_config.yaml")
# 或使用绝对路径
config = manager.load_config_file("/path/to/config.yaml")
```

---

### 3. `get_current_config() -> Optional[Dict[str, Any]]`

**获取当前加载的组态配置**

**返回**：
- 当前组态配置字典的副本，如果未加载则返回None

**功能**：
- 返回当前加载的配置
- 返回副本，避免外部修改影响内部状态

---

### 4. `get_plc_running_config(plc_configuration) -> Dict[str, Any]`

**从plc_configuration获取当前PLC运行的组态内容**

**参数**：
- `plc_configuration`: PLC组态模块实例（`plc.plc_configuration.Configuration`）

**返回**：
- PLC当前运行的组态配置字典

**功能**：
- 从`plc.plc_configuration.Configuration`获取当前运行的配置
- 获取cycle_time、models、algorithms、connections
- 如果存在execution_order，也会获取

**返回的配置字典结构**：
```python
{
    'cycle_time': 0.5,
    'models': {
        'tank1': {
            'type': 'cylindrical_tank',
            'params': {...}
        },
        ...
    },
    'algorithms': {
        'pid1': {
            'type': 'PID',
            'params': {...}
        },
        ...
    },
    'connections': [
        {'from': 'pid1.mv', 'to': 'valve1.target_opening'},
        ...
    ],
    'execution_order': ['pid1', 'valve1', 'tank1', ...]  # 如果存在
}
```

---

### 5. `analyze_config_diff(config1, config2) -> Dict[str, Any]`

**分析两个组态配置的差异**

**参数**：
- `config1`: 第一个配置（通常是文件配置）
- `config2`: 第二个配置（通常是PLC运行配置）

**返回**：
- 差异分析结果字典

**差异字典结构**：
```python
{
    'added_models': {},           # 新增的模型实例
    'removed_models': {},        # 删除的模型实例
    'modified_models': {},       # 修改的模型实例（包含from/to）
    'added_algorithms': {},      # 新增的算法实例
    'removed_algorithms': {},    # 删除的算法实例
    'modified_algorithms': {},   # 修改的算法实例（包含from/to）
    'added_connections': [],     # 新增的连接关系
    'removed_connections': [],   # 删除的连接关系
    'cycle_time_changed': False, # cycle_time是否改变
    'cycle_time': {...}          # cycle_time变更详情（如果改变）
}
```

**功能**：
- 比较cycle_time
- 比较models（新增/删除/修改）
- 比较algorithms（新增/删除/修改）
- 比较connections（新增/删除）
- 标准化连接关系格式便于比较

---

### 6. `_normalize_connections(connections) -> List[Dict[str, str]]`

**标准化连接关系格式**

**参数**：
- `connections`: 连接关系列表

**返回**：
- 标准化后的连接关系列表

**功能**：
- 统一格式为 `{'from': 'instance.param', 'to': 'instance.param'}`
- 支持旧格式转换（from/from_param和to/to_param）

---

### 7. `update_config_to_plc(plc_configuration, config, rebuild_instances, use_redis) -> bool`

**更新组态到PLC（通过Redis消息通知，PLC在运行过程中自动更新）**

**参数**：
- `plc_configuration`: PLC组态模块实例（可选，如果use_redis=True则不需要）
- `config`: 要更新的配置字典，如果为None则使用当前加载的配置
- `rebuild_instances`: 是否重建实例（当有新增或删除时，会自动判断）
- `use_redis`: 是否通过Redis发送消息（默认True）

**返回**：
- 是否更新成功

**功能**：
- **Redis方式（推荐）**：
  1. 获取当前PLC运行的配置（从plc_configuration或从文件读取）
  2. 分析差异
  3. 构造更新消息（包含差异信息和完整配置）
  4. 通过Redis发送到频道 `plc:config:update`
  5. PLC在运行过程中自动接收并应用更新

- **直接API方式（已废弃）**：
  - 直接调用plc_configuration的在线配置API
  - 不推荐使用，保留仅为兼容性

**更新消息格式**：
```python
{
    'type': 'config_update_diff',
    'diff': {
        'added_models': {...},
        'removed_models': {...},
        'modified_models': {...},
        'added_algorithms': {...},
        'removed_algorithms': {...},
        'modified_algorithms': {...},
        'added_connections': [...],
        'removed_connections': [...],
        'cycle_time_changed': False
    },
    'full_config': {...},           # 完整配置（用于重建实例时使用）
    'rebuild_instances': True,      # 是否需要重建实例
    'cycle_time_changed': False,    # cycle_time是否改变
    'cycle_time': 0.5               # 新的cycle_time（如果改变）
}
```

---

### 8. `save_config_to_local(config) -> bool`

**保存组态配置到PLC本地目录**

**参数**：
- `config`: 要保存的配置字典，如果为None则使用当前加载的配置

**返回**：
- 是否保存成功

**功能**：
- 保存到 `plc/local/config.yaml`
- 确保目录存在
- YAML格式保存

---

### 9. `sync_config_to_plc(config_file, plc_configuration, save_to_local) -> Tuple[bool, Dict[str, Any]]`

**同步组态文件到PLC（加载、分析差异、更新）**

**参数**：
- `config_file`: 组态文件路径
- `plc_configuration`: PLC组态模块实例
- `save_to_local`: 是否同时保存到PLC本地目录

**返回**：
- `(是否成功, 差异分析结果)`

**功能**：
- 完整的同步流程：
  1. 加载配置文件
  2. 获取PLC当前运行的配置
  3. 分析差异
  4. 更新到PLC（通过Redis）
  5. 保存到本地（如果需要）

---

### 10. `_get_redis_client()`

**获取Redis客户端（懒加载）**

**功能**：
- 懒加载Redis连接
- 测试连接
- 错误处理

---

### 11. `_validate_config_format(config)`

**验证配置格式**

**参数**：
- `config`: 配置字典

**功能**：
- 检查必需字段
- 验证models格式
- 验证algorithms格式
- 验证connections格式

---

## 使用示例

### 基本使用

```python
from config.configuration import ConfigurationManager
from plc.plc_configuration import Configuration

# 1. 初始化
redis_config = {
    'host': 'localhost',
    'port': 6379,
    'db': 0
}
config_manager = ConfigurationManager(
    config_dir="config",
    local_dir="plc/local",
    redis_config=redis_config
)

# 2. 加载配置文件
file_config = config_manager.load_config_file("example_config.yaml")

# 3. 获取PLC运行配置
plc_config = Configuration(local_dir="plc/local")
plc_running_config = config_manager.get_plc_running_config(plc_config)

# 4. 分析差异
diff = config_manager.analyze_config_diff(file_config, plc_running_config)

# 5. 更新到PLC（通过Redis）
success = config_manager.update_config_to_plc(
    plc_configuration=plc_config,
    config=file_config,
    use_redis=True
)

# 6. 保存到本地
if success:
    config_manager.save_config_to_local(file_config)
```

### 完整同步流程

```python
# 使用sync_config_to_plc方法，一次性完成所有操作
success, diff = config_manager.sync_config_to_plc(
    config_file="example_config.yaml",
    plc_configuration=plc_config,
    save_to_local=True
)

if success:
    print("配置同步成功")
    print(f"差异: {diff}")
else:
    print("配置同步失败")
```

---

## 数据流向

### 更新配置到PLC的完整流程

```
配置文件 (config/example_config.yaml)
    ↓
config_manager.load_config_file()
    ↓
config_manager.update_config_to_plc(use_redis=True)
    ↓
分析差异 (analyze_config_diff)
    ↓
构造更新消息（包含diff和full_config）
    ↓
发送到Redis频道 "plc:config:update"
    ↓
Runner._command_subscriber_loop() 接收消息
    ↓
设置 _config_update_pending = True
    ↓
Runner._run_loop() 在周期间隙检测标志
    ↓
_apply_pending_config_update() 应用更新
    ↓
使用plc_configuration在线API更新配置
    ↓
Runner.update_configuration() 重建/更新实例
    ↓
更新执行顺序和cycle_time
```

---

## 关键特性

### 1. 自动化更新机制
- 通过Redis消息通知PLC
- PLC在运行过程中自动检测并应用更新
- 无需手动调用Runner的update_configuration方法

### 2. 差异化更新
- 只更新变化的部分，而不是替换整个配置
- 减少不必要的实例重建
- 提高更新效率

### 3. 线程安全
- 配置更新在PLC运行循环的周期间隙执行
- 使用锁机制确保更新过程不会被其他操作打断

### 4. 完整支持
- 支持实例增删改
- 支持连接关系更新
- 支持执行顺序更新
- 支持cycle_time更新

---

## 相关模块

### 1. `plc/plc_configuration.py`
- PLC组态模块
- 管理PLC运行的组态配置
- 提供在线配置API

### 2. `plc/runner.py`
- PLC运行模块
- 接收配置更新消息
- 在周期间隙应用更新

### 3. `config/param_definitions.py`
- 参数定义文件
- 定义所有模型和算法的参数元数据
- 用于UI界面自动生成参数编辑表格

---

## 注意事项

1. **Redis连接**：使用Redis方式更新时，需要配置Redis连接
2. **PLC运行状态**：PLC必须在运行状态才能接收并应用更新
3. **状态丢失**：重建实例会丢失算法状态（如PID的积分项）
4. **文件同步**：配置更新后会自动保存到 `plc/local/config.yaml`

---

## 错误处理

模块包含完善的错误处理：
- 文件不存在：`FileNotFoundError`
- YAML解析错误：`yaml.YAMLError`
- 配置格式错误：`ValueError`
- Redis连接失败：记录错误日志，返回False
- 所有异常都会记录详细日志

---

## 日志记录

模块使用 `utils.logger` 记录日志：
- INFO级别：正常操作信息
- WARNING级别：警告信息（如配置格式问题）
- ERROR级别：错误信息（包含异常堆栈）

