# config/configuration模块使用说明

## 模块概述

`config/configuration.py` 是组态管理模块，提供组态文件的加载、管理、差异分析和更新功能。

## 主要功能

1. **加载组态文件**：从YAML文件加载组态配置
2. **管理组态内容**：管理当前加载的组态配置
3. **获取PLC运行配置**：从`plc.plc_configuration`获取当前PLC运行的组态内容
4. **分析配置差异**：分析文件配置与PLC运行配置的差异
5. **更新组态到PLC**：将配置更新到PLC运行环境

---

## 基本使用

### 1. 初始化组态管理器

```python
from config.configuration import ConfigurationManager

# 创建组态管理器实例
manager = ConfigurationManager(
    config_dir="config",      # 配置文件目录
    local_dir="plc/local"      # PLC本地配置目录
)
```

### 2. 加载组态文件

```python
# 加载组态文件（可以是绝对路径或相对于config_dir的路径）
config = manager.load_config_file("example_config.yaml")

# 或者使用绝对路径
config = manager.load_config_file("/path/to/config.yaml")
```

### 3. 获取当前加载的配置

```python
# 获取当前加载的组态配置
current_config = manager.get_current_config()
```

### 4. 获取PLC运行配置

```python
from plc.plc_configuration import Configuration

# 假设已经有一个PLC配置实例
plc_config = Configuration(local_dir="plc/local")

# 获取PLC当前运行的组态配置
plc_running_config = manager.get_plc_running_config(plc_config)
```

### 5. 分析配置差异

```python
# 加载文件配置
file_config = manager.load_config_file("example_config.yaml")

# 获取PLC运行配置
plc_config = Configuration(local_dir="plc/local")
plc_running_config = manager.get_plc_running_config(plc_config)

# 分析差异
diff = manager.analyze_config_diff(file_config, plc_running_config)

# diff包含以下字段：
# - added_models: 新增的模型实例
# - removed_models: 删除的模型实例
# - modified_models: 修改的模型实例
# - added_algorithms: 新增的算法实例
# - removed_algorithms: 删除的算法实例
# - modified_algorithms: 修改的算法实例
# - added_connections: 新增的连接关系
# - removed_connections: 删除的连接关系
# - cycle_time_changed: cycle_time是否改变
```

### 6. 更新组态到PLC

```python
from plc.plc_configuration import Configuration

# 创建PLC配置实例
plc_config = Configuration(local_dir="plc/local")

# 加载配置文件
manager.load_config_file("example_config.yaml")

# 更新到PLC
success = manager.update_config_to_plc(plc_config, rebuild_instances=False)

if success:
    print("配置更新成功")
else:
    print("配置更新失败")
```

### 7. 同步组态到PLC（一键操作）

```python
from plc.plc_configuration import Configuration

# 创建PLC配置实例
plc_config = Configuration(local_dir="plc/local")

# 同步组态文件到PLC（加载、分析差异、更新、保存到本地）
success, diff = manager.sync_config_to_plc(
    config_file="example_config.yaml",
    plc_configuration=plc_config,
    save_to_local=True
)

if success:
    print("同步成功")
    print(f"差异分析结果: {diff}")
else:
    print("同步失败")
```

### 8. 保存配置到本地

```python
# 保存当前加载的配置到PLC本地目录
success = manager.save_config_to_local()

# 或者保存指定的配置
config = manager.load_config_file("example_config.yaml")
success = manager.save_config_to_local(config)
```

---

## 完整示例

```python
from config.configuration import ConfigurationManager
from plc.plc_configuration import Configuration

# 1. 初始化组态管理器
manager = ConfigurationManager()

# 2. 加载组态文件
try:
    config = manager.load_config_file("config/example_config.yaml")
    print("组态文件加载成功")
except FileNotFoundError as e:
    print(f"文件不存在: {e}")
except Exception as e:
    print(f"加载失败: {e}")

# 3. 获取PLC运行配置
plc_config = Configuration(local_dir="plc/local")
plc_running_config = manager.get_plc_running_config(plc_config)

# 4. 分析差异
diff = manager.analyze_config_diff(config, plc_running_config)

# 5. 打印差异信息
print("\n=== 配置差异分析 ===")
if diff['added_models']:
    print(f"新增模型: {list(diff['added_models'].keys())}")
if diff['removed_models']:
    print(f"删除模型: {list(diff['removed_models'].keys())}")
if diff['modified_models']:
    print(f"修改模型: {list(diff['modified_models'].keys())}")
if diff['added_algorithms']:
    print(f"新增算法: {list(diff['added_algorithms'].keys())}")
if diff['removed_algorithms']:
    print(f"删除算法: {list(diff['removed_algorithms'].keys())}")
if diff['modified_algorithms']:
    print(f"修改算法: {list(diff['modified_algorithms'].keys())}")
if diff['added_connections']:
    print(f"新增连接: {len(diff['added_connections'])}个")
if diff['removed_connections']:
    print(f"删除连接: {len(diff['removed_connections'])}个")
if diff['cycle_time_changed']:
    print(f"cycle_time变更: {diff['cycle_time']}")

# 6. 更新到PLC
if any([diff['added_models'], diff['removed_models'], diff['modified_models'],
        diff['added_algorithms'], diff['removed_algorithms'], diff['modified_algorithms'],
        diff['added_connections'], diff['removed_connections']]):
    print("\n开始更新配置到PLC...")
    success = manager.update_config_to_plc(plc_config, rebuild_instances=True)
    if success:
        print("配置更新成功")
        # 保存到本地
        manager.save_config_to_local()
    else:
        print("配置更新失败")
else:
    print("\n配置无变更，无需更新")
```

---

## API参考

### ConfigurationManager类

#### `__init__(config_dir: str = "config", local_dir: str = "plc/local")`
初始化组态管理器

#### `load_config_file(config_file: str) -> Dict[str, Any]`
加载组态文件

**参数**：
- `config_file`: 配置文件路径（可以是绝对路径或相对于config_dir的路径）

**返回**：组态配置字典

**异常**：
- `FileNotFoundError`: 文件不存在
- `yaml.YAMLError`: YAML解析错误

#### `get_current_config() -> Optional[Dict[str, Any]]`
获取当前加载的组态配置

**返回**：当前组态配置字典，如果未加载则返回None

#### `get_plc_running_config(plc_configuration) -> Dict[str, Any]`
从plc_configuration获取当前PLC运行的组态内容

**参数**：
- `plc_configuration`: PLC组态模块实例（plc.plc_configuration.Configuration）

**返回**：PLC当前运行的组态配置字典

#### `analyze_config_diff(config1: Dict[str, Any], config2: Dict[str, Any]) -> Dict[str, Any]`
分析两个组态配置的差异

**参数**：
- `config1`: 第一个配置（通常是文件配置）
- `config2`: 第二个配置（通常是PLC运行配置）

**返回**：差异分析结果字典

#### `update_config_to_plc(plc_configuration, config: Dict[str, Any] = None, rebuild_instances: bool = False) -> bool`
更新组态到PLC

**参数**：
- `plc_configuration`: PLC组态模块实例
- `config`: 要更新的配置字典，如果为None则使用当前加载的配置
- `rebuild_instances`: 是否重建实例（当有新增或删除时）

**返回**：是否更新成功

#### `save_config_to_local(config: Dict[str, Any] = None) -> bool`
保存组态配置到PLC本地目录

**参数**：
- `config`: 要保存的配置字典，如果为None则使用当前加载的配置

**返回**：是否保存成功

#### `sync_config_to_plc(config_file: str, plc_configuration, save_to_local: bool = True) -> Tuple[bool, Dict[str, Any]]`
同步组态文件到PLC（加载、分析差异、更新）

**参数**：
- `config_file`: 组态文件路径
- `plc_configuration`: PLC组态模块实例
- `save_to_local`: 是否同时保存到PLC本地目录

**返回**：`(是否成功, 差异分析结果)`

---

## 注意事项

1. **配置格式验证**：加载配置文件时会自动验证配置格式
2. **差异分析**：差异分析会标准化连接关系格式，便于比较
3. **更新顺序**：更新配置时，会先删除已移除的实例和连接，再添加新的实例和连接
4. **实例重建**：如果有新增或删除实例，需要调用`Runner.update_configuration(rebuild_instances=True)`重建实例
5. **cycle_time变更**：cycle_time变更无法直接更新，需要重启PLC Runner

---

## 与plc/plc_configuration的关系

- `plc/plc_configuration.py`：PLC组态模块，管理PLC运行时的组态配置
- `config/configuration.py`：组态管理模块，提供组态文件的加载、管理和更新功能

两个模块的关系：
- `config/configuration.py` 通过 `plc/plc_configuration.py` 的API获取和更新PLC运行配置
- `config/configuration.py` 负责组态文件的加载和管理
- `plc/plc_configuration.py` 负责PLC运行时的组态管理

