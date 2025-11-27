# config/configuration 与 PLC组态数据流向说明

## 数据流向图

```
plc/local/config.yaml (文件)
        ↓
    [初始化时加载]
        ↓
plc_configuration.Configuration.__init__()
        ↓
    self.config = yaml.safe_load(f)  # 加载到内存
        ↓
    [运行时可能通过在线配置修改]
        ↓
    self.config (内存中的配置字典)
        ↓
    [通过API读取]
        ↓
plc_configuration.get_models()
plc_configuration.get_algorithms()
plc_configuration.get_connections()
        ↓
config_manager.get_plc_running_config(plc_config)
        ↓
返回配置字典（来自内存中的self.config）
```

---

## 关键点说明

### 1. 初始化时加载文件

```python
# plc/plc_configuration.py
def __init__(self, local_dir: str = None):
    self.local_config_file = os.path.join(local_dir, "config.yaml")
    
    if local_dir and os.path.exists(self.local_config_file):
        # 从plc/local/config.yaml加载配置
        with open(self.local_config_file, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)  # ← 文件内容加载到内存
```

### 2. get_plc_running_config() 读取内存中的配置

```python
# config/configuration.py
def get_plc_running_config(self, plc_configuration):
    # 调用plc_configuration的API
    models = plc_configuration.get_models()
    # ↓ 内部实现
    # return self.config.get('models', {}).copy()  # ← 从内存读取
    
    # 所以获取的是内存中的配置，不是直接读文件
    return {
        'models': models,  # 来自内存中的self.config
        ...
    }
```

---

## 重要区别

### 情况1: 直接读取文件

```python
# 直接读取plc/local/config.yaml文件
import yaml
with open('plc/local/config.yaml', 'r') as f:
    file_config = yaml.safe_load(f)
# 获取的是文件中的配置（可能不是最新的）
```

### 情况2: 通过API获取（当前实现）

```python
# 通过plc_configuration API获取
plc_config = Configuration(local_dir="plc/local")
plc_running_config = config_manager.get_plc_running_config(plc_config)
# 获取的是内存中的配置（可能是运行时修改后的最新配置）
```

---

## 配置可能不一致的情况

### 场景：运行时在线配置修改

```python
# 1. PLC运行时，通过在线配置修改了参数
plc_config.online_update_algorithm('pid1', {'kp': 15.0})
# ↓ self.config 更新了，但文件还没保存

# 2. 此时获取配置
plc_running_config = config_manager.get_plc_running_config(plc_config)
# ↓ 获取的是内存中的配置（kp=15.0），不是文件中的配置

# 3. 如果直接读取文件
with open('plc/local/config.yaml', 'r') as f:
    file_config = yaml.safe_load(f)
# ↓ 文件中的配置可能还是旧的（kp=12.0）
```

---

## 当前实现的特点

### ✅ 优点

1. **获取最新配置**：获取的是内存中的配置，包括运行时修改的内容
2. **线程安全**：通过 `plc_configuration` 的线程安全API访问
3. **解耦**：`config_manager` 不直接访问文件系统
4. **统一接口**：通过API获取，格式统一

### ⚠️ 注意事项

1. **内存 vs 文件**：
   - `get_plc_running_config()` 获取的是**内存中的配置**
   - 如果运行时修改了配置但没保存，内存和文件可能不一致

2. **文件同步**：
   - 如果需要获取文件中的配置，需要重新加载：
   ```python
   plc_config.load_from_local()  # 重新从文件加载
   plc_running_config = config_manager.get_plc_running_config(plc_config)
   ```

3. **配置持久化**：
   - 在线配置修改后，需要调用 `save_to_local()` 保存到文件：
   ```python
   plc_config.online_update_algorithm('pid1', {'kp': 15.0})
   plc_config.save_to_local()  # 保存到plc/local/config.yaml
   ```

---

## 总结

**是的，`get_plc_running_config()` 获取的是从 `plc/local/config.yaml` 加载的配置内容**，但是：

1. **不是直接读文件**：通过 `plc_configuration` 的API间接获取
2. **获取的是内存中的配置**：可能包含运行时修改的内容
3. **如果文件被修改**：需要重新加载才能获取最新内容

**数据流向**：
```
plc/local/config.yaml 
    → [初始化时] → plc_configuration.config (内存)
    → [运行时可能修改] → plc_configuration.config (更新后的内存)
    → [通过API] → get_plc_running_config() → 返回配置字典
```

**如果需要获取文件中的配置**（而不是内存中的）：
```python
# 方法1: 重新加载文件
plc_config.load_from_local()
plc_running_config = config_manager.get_plc_running_config(plc_config)

# 方法2: 直接读取文件
import yaml
with open('plc/local/config.yaml', 'r') as f:
    file_config = yaml.safe_load(f)
```

