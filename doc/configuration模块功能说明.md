# Configuration模块功能说明

## 模块概述

`Configuration` 模块是PLC Mock Server的核心组态管理模块，负责管理物理模型实例、算法实例及其连接关系。支持在线配置和离线配置两种模式。

---

## 核心功能

### 1. 配置加载和初始化

#### 1.1 从文件加载配置
```python
from plc.configuration import Configuration

# 从YAML文件加载配置
config = Configuration(config_file="config/example_config.yaml")
```

#### 1.2 从字典创建配置
```python
# 从字典创建配置
config_dict = {
    'cycle_time': 0.5,
    'models': {...},
    'algorithms': {...},
    'connections': [...]
}
config = Configuration(config_dict=config_dict)
```

#### 1.3 创建空配置
```python
# 创建空配置（使用默认值）
config = Configuration()
```

---

### 2. 配置读取

#### 2.1 获取运行周期
```python
cycle_time = config.get_cycle_time()  # 返回: 0.5
```

#### 2.2 获取模型配置
```python
models = config.get_models()
# 返回: {
#     'tank1': {
#         'type': 'cylindrical_tank',
#         'params': {...}
#     },
#     'valve1': {
#         'type': 'valve',
#         'params': {...}
#     }
# }
```

#### 2.3 获取算法配置
```python
algorithms = config.get_algorithms()
# 返回: {
#     'pid1': {
#         'type': 'PID',
#         'params': {...}
#     }
# }
```

#### 2.4 获取连接关系
```python
connections = config.get_connections()
# 返回: [
#     {'from': 'pid1.mv', 'to': 'valve1.TARGET_OPENING'},
#     {'from': 'valve1.CURRENT_OPENING', 'to': 'tank1.VALVE_OPENING'},
#     {'from': 'tank1.LEVEL', 'to': 'pid1.pv'}
# ]
```

#### 2.5 获取所有实例名称
```python
instances = config.get_all_instances()
# 返回: ['tank1', 'valve1', 'pid1']
```

#### 2.6 获取完整配置
```python
all_config = config.get_all_config()
# 返回完整的配置字典
```

---

### 3. 执行顺序计算

#### 3.1 自动计算执行顺序
```python
execution_order = config.calculate_execution_order()
# 根据依赖关系自动计算执行顺序
# 返回: ['pid1', 'valve1', 'tank1']
```

**工作原理**：
1. 根据连接关系构建依赖图
2. 使用拓扑排序算法计算执行顺序
3. 如果存在环，抛出异常要求手动指定执行顺序

#### 3.2 获取执行顺序（带缓存）
```python
execution_order = config.get_execution_order()
# 如果配置中有 execution_order，直接返回
# 否则调用 calculate_execution_order()
```

#### 3.3 手动指定执行顺序
```yaml
# config.yaml
execution_order:
  - pid1
  - valve1
  - tank1
```

---

### 4. 配置验证

#### 4.1 验证配置有效性
```python
errors = config.validate_config()
if errors:
    for error in errors:
        print(f"配置错误: {error}")
else:
    print("配置有效")
```

**验证内容**：
- ✅ 必需字段检查（models、algorithms）
- ✅ 实例名称唯一性检查
- ✅ 连接关系有效性检查（实例是否存在）
- ✅ execution_order完整性检查

---

### 5. 离线配置

#### 5.1 清空并设置新配置
```python
new_config = {
    'cycle_time': 0.5,
    'models': {...},
    'algorithms': {...},
    'connections': [...]
}
config.offline_config(new_config)
```

**用途**：停止运行模块，清空组态信息，配置全新组态

---

### 6. 在线配置 - 模型管理

#### 6.1 添加模型实例
```python
config.online_add_model(
    name='tank2',
    model_type='cylindrical_tank',
    params={
        'height': 2.0,
        'radius': 0.5,
        'initial_level': 0.0
    }
)
```

#### 6.2 更新模型参数
```python
config.online_update_model(
    name='tank1',
    params={
        'initial_level': 1.0  # 只更新这个参数
    }
)
```

#### 6.3 删除模型实例
```python
config.online_remove_model('tank2')
# 同时删除相关的连接关系
```

---

### 7. 在线配置 - 算法管理

#### 7.1 添加算法实例
```python
config.online_add_algorithm(
    name='pid2',
    algo_type='PID',
    params={
        'kp': 10.0,
        'ti': 30.0,
        'td': 0.15,
        'sv': 5.0
    }
)
```

#### 7.2 更新算法参数
```python
config.online_update_algorithm(
    name='pid1',
    params={
        'kp': 12.0  # 只更新这个参数
    }
)
```

#### 7.3 删除算法实例
```python
config.online_remove_algorithm('pid2')
# 同时删除相关的连接关系
```

---

### 8. 在线配置 - 连接管理

#### 8.1 添加连接关系（新格式）
```python
config.online_add_connection(
    from_str='pid1.mv',
    to_str='valve1.TARGET_OPENING'
)
```

#### 8.2 添加连接关系（旧格式兼容）
```python
config.online_add_connection(
    from_obj='pid1',
    from_param='mv',
    to_obj='valve1',
    to_param='TARGET_OPENING'
)
```

#### 8.3 删除连接关系
```python
config.online_remove_connection(
    from_str='pid1.mv',
    to_str='valve1.TARGET_OPENING'
)
```

---

### 9. 配置保存

#### 9.1 保存配置到文件
```python
config.save_to_file('config/new_config.yaml')
```

---

### 10. 示例配置生成

#### 10.1 创建示例配置
```python
example_config = Configuration.create_example_config()
# 返回一个示例配置字典
```

---

## 依赖图构建和拓扑排序

### 依赖图结构

依赖图表示实例之间的依赖关系：
- `graph[B] = [A]` 表示 B 依赖于 A（A的输出连接到B的输入）
- 拓扑排序确保：如果 B 依赖于 A，则 A 在 B 之前执行

### 示例

```yaml
connections:
  - from: pid1.mv
    to: valve1.TARGET_OPENING
  - from: valve1.CURRENT_OPENING
    to: tank1.VALVE_OPENING
  - from: tank1.LEVEL
    to: pid1.pv
```

**依赖关系**：
- `valve1` 依赖于 `pid1`
- `tank1` 依赖于 `valve1`
- `pid1` 依赖于 `tank1`（形成环！）

**执行顺序**：
1. 如果无环：`['pid1', 'valve1', 'tank1']`
2. 如果有环：抛出异常，要求手动指定 `execution_order`

---

## 线程安全

所有配置操作都使用 `RLock` 保护，支持多线程环境下的安全访问：

```python
with config._lock:
    # 线程安全的配置操作
    models = config.get_models()
```

---

## 使用示例

### 完整示例

```python
from plc.configuration import Configuration

# 1. 加载配置
config = Configuration(config_file="config/example_config.yaml")

# 2. 验证配置
errors = config.validate_config()
if errors:
    print("配置错误:", errors)
    exit(1)

# 3. 获取执行顺序
execution_order = config.get_execution_order()
print("执行顺序:", execution_order)

# 4. 在线更新参数
config.online_update_model('tank1', {'initial_level': 1.0})
config.online_update_algorithm('pid1', {'sv': 6.0})

# 5. 添加新连接
config.online_add_connection(
    from_str='tank1.LEVEL',
    to_str='pid2.pv'
)

# 6. 保存配置
config.save_to_file('config/updated_config.yaml')
```

---

## 配置格式

### YAML配置文件格式

```yaml
cycle_time: 0.5  # 运行周期（秒）

models:
  tank1:
    type: cylindrical_tank
    params:
      height: 2.0
      radius: 0.5
      initial_level: 0.0

algorithms:
  pid1:
    type: PID
    params:
      kp: 12.0
      ti: 30.0
      td: 0.15
      sv: 5.0

connections:
  - from: pid1.mv
    to: valve1.TARGET_OPENING
  - from: tank1.LEVEL
    to: pid1.pv

# 可选：手动指定执行顺序（如果存在环）
execution_order:
  - pid1
  - valve1
  - tank1
```

---

## 注意事项

1. **线程安全**：所有配置操作都是线程安全的，可以在多线程环境下使用
2. **配置验证**：建议在修改配置后调用 `validate_config()` 验证配置有效性
3. **执行顺序**：如果存在循环依赖，必须手动指定 `execution_order`
4. **参数命名**：模型参数使用大写（如 `LEVEL`），算法参数使用小写（如 `pv`、`sv`、`mv`）
5. **连接格式**：推荐使用新格式（`"instance.param"`），旧格式已兼容但可能在未来版本中移除

---

## API参考

### 主要方法

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `get_cycle_time()` | 获取运行周期 | `float` |
| `get_models()` | 获取模型配置 | `Dict[str, Dict]` |
| `get_algorithms()` | 获取算法配置 | `Dict[str, Dict]` |
| `get_connections()` | 获取连接关系 | `List[Dict]` |
| `get_all_instances()` | 获取所有实例名称 | `List[str]` |
| `get_execution_order()` | 获取执行顺序 | `List[str]` |
| `calculate_execution_order()` | 计算执行顺序 | `List[str]` |
| `validate_config()` | 验证配置 | `List[str]` |
| `offline_config(new_config)` | 离线配置 | `None` |
| `online_add_model(...)` | 添加模型 | `None` |
| `online_update_model(...)` | 更新模型 | `None` |
| `online_remove_model(...)` | 删除模型 | `None` |
| `online_add_algorithm(...)` | 添加算法 | `None` |
| `online_update_algorithm(...)` | 更新算法 | `None` |
| `online_remove_algorithm(...)` | 删除算法 | `None` |
| `online_add_connection(...)` | 添加连接 | `None` |
| `online_remove_connection(...)` | 删除连接 | `None` |
| `save_to_file(file_path)` | 保存配置 | `None` |
| `create_example_config()` | 创建示例配置 | `dict` |

