# config/configuration 与 PLC组态交互说明

## 交互架构

```
┌─────────────────────────────────┐
│  config/configuration.py         │
│  ConfigurationManager            │
│                                  │
│  - 管理配置文件（config目录）    │
│  - 提供组态管理功能              │
└──────────────┬──────────────────┘
               │
               │ get_plc_running_config()
               │ update_config_to_plc()
               │
               ▼
┌─────────────────────────────────┐
│  plc/plc_configuration.py      │
│  Configuration                   │
│                                  │
│  - 管理PLC运行时配置             │
│  - 从plc/local目录加载           │
│  - 提供在线配置API               │
└─────────────────────────────────┘
```

---

## 交互方式

### 1. 获取PLC运行配置

`get_plc_running_config()` 方法通过调用 `plc_configuration` 的API获取当前PLC运行的组态内容：

```python
def get_plc_running_config(self, plc_configuration) -> Dict[str, Any]:
    """
    内部调用流程：
    
    1. plc_configuration.get_cycle_time()
       ↓ 返回运行周期（float）
    
    2. plc_configuration.get_models()
       ↓ 返回模型配置字典（Dict[str, Dict]）
    
    3. plc_configuration.get_algorithms()
       ↓ 返回算法配置字典（Dict[str, Dict]）
    
    4. plc_configuration.get_connections()
       ↓ 返回连接关系列表（List[Dict]）
    
    5. plc_configuration.get_execution_order()（可选）
       ↓ 返回执行顺序列表（List[str]）
    
    6. 组装成统一的配置字典格式
       ↓
    返回配置字典
    """
```

---

## 使用示例

### 示例1: 基本交互

```python
from config.configuration import ConfigurationManager
from plc.plc_configuration import Configuration

# 步骤1: 创建两个模块实例
config_manager = ConfigurationManager()  # config目录下的模块
plc_config = Configuration(local_dir="plc/local")  # plc目录下的模块

# 步骤2: 通过config_manager获取PLC运行配置
# config_manager内部会调用plc_config的方法
plc_running_config = config_manager.get_plc_running_config(plc_config)

# 现在plc_running_config包含了PLC当前运行的完整配置
print(f"运行周期: {plc_running_config['cycle_time']}")
print(f"模型数量: {len(plc_running_config['models'])}")
print(f"算法数量: {len(plc_running_config['algorithms'])}")
```

---

### 示例2: 直接调用PLC组态API（对比）

```python
from plc.plc_configuration import Configuration

# 直接使用PLC组态模块
plc_config = Configuration(local_dir="plc/local")

# 直接调用API获取配置
cycle_time = plc_config.get_cycle_time()
models = plc_config.get_models()
algorithms = plc_config.get_algorithms()
connections = plc_config.get_connections()

# 手动组装配置字典
plc_running_config = {
    'cycle_time': cycle_time,
    'models': models,
    'algorithms': algorithms,
    'connections': connections
}
```

**对比**：
- **直接调用**: 需要手动调用多个API并组装
- **使用config_manager**: 一键获取，自动组装，格式统一

---

### 示例3: 完整交互流程

```python
from config.configuration import ConfigurationManager
from plc.plc_configuration import Configuration

# 1. 初始化
manager = ConfigurationManager()
plc_config = Configuration(local_dir="plc/local")

# 2. 获取PLC运行配置（config_manager调用plc_config的API）
plc_running_config = manager.get_plc_running_config(plc_config)

# 3. 加载配置文件
file_config = manager.load_config_file("config/example_config.yaml")

# 4. 分析差异（比较文件配置和PLC运行配置）
diff = manager.analyze_config_diff(file_config, plc_running_config)

# 5. 更新到PLC（config_manager调用plc_config的在线配置API）
if diff['added_models'] or diff['modified_models']:
    # manager内部会调用：
    # - plc_config.online_add_model()
    # - plc_config.online_update_model()
    # - plc_config.online_remove_model()
    # 等等
    success = manager.update_config_to_plc(plc_config)
```

---

## 内部调用关系

### get_plc_running_config() 内部调用

```python
# config/configuration.py
def get_plc_running_config(self, plc_configuration):
    # 调用1: 获取运行周期
    cycle_time = plc_configuration.get_cycle_time()
    # ↓ 内部调用: plc_configuration.config.get('cycle_time', 0.5)
    
    # 调用2: 获取模型配置
    models = plc_configuration.get_models()
    # ↓ 内部调用: plc_configuration.config.get('models', {}).copy()
    
    # 调用3: 获取算法配置
    algorithms = plc_configuration.get_algorithms()
    # ↓ 内部调用: plc_configuration.config.get('algorithms', {}).copy()
    
    # 调用4: 获取连接关系
    connections = plc_configuration.get_connections()
    # ↓ 内部调用: plc_configuration.config.get('connections', []).copy()
    
    # 调用5: 获取执行顺序（可选）
    execution_order = plc_configuration.get_execution_order()
    # ↓ 内部调用: calculate_execution_order() 或 config.get('execution_order')
    
    # 组装并返回
    return {
        'cycle_time': cycle_time,
        'models': models,
        'algorithms': algorithms,
        'connections': connections,
        'execution_order': execution_order  # 如果存在
    }
```

---

### update_config_to_plc() 内部调用

```python
# config/configuration.py
def update_config_to_plc(self, plc_configuration, config):
    # 分析差异后，根据差异调用不同的API
    
    # 删除模型
    for name in diff['removed_models']:
        plc_configuration.online_remove_model(name)
        # ↓ 内部: 删除config['models'][name]，删除相关连接
    
    # 添加模型
    for name, model_config in diff['added_models'].items():
        plc_configuration.online_add_model(name, model_type, params)
        # ↓ 内部: config['models'][name] = {...}
    
    # 更新模型
    for name, change in diff['modified_models'].items():
        plc_configuration.online_update_model(name, params)
        # ↓ 内部: config['models'][name]['params'].update(params)
    
    # 类似地处理算法和连接...
```

---

## 数据流向

### 读取配置（从PLC获取）

```
plc/local/config.yaml
        ↓
plc_configuration.Configuration (加载)
        ↓
plc_configuration.get_models() 等方法
        ↓
config_manager.get_plc_running_config()
        ↓
返回配置字典
```

### 更新配置（向PLC写入）

```
配置文件 (config/example_config.yaml)
        ↓
config_manager.load_config_file()
        ↓
config_manager.analyze_config_diff()
        ↓
config_manager.update_config_to_plc()
        ↓
plc_configuration.online_add_model() 等方法
        ↓
plc_configuration.config (更新)
        ↓
plc/local/config.yaml (可选保存)
```

---

## 关键点

### 1. 模块职责分离

- **config/configuration.py**: 
  - 管理配置文件（config目录）
  - 提供组态管理功能
  - 不直接访问plc/local目录

- **plc/plc_configuration.py**:
  - 管理PLC运行时配置（plc/local目录）
  - 提供在线配置API
  - 线程安全的配置操作

### 2. 交互方式

- **config_manager** 通过 **plc_configuration实例** 与PLC组态交互
- 不直接访问文件系统，而是通过API调用
- 保证线程安全和数据一致性

### 3. 配置格式统一

- 两个模块返回的配置格式一致
- 便于比较和更新
- 使用相同的字典结构

---

## 实际应用场景

### 场景1: Web界面组态管理

```python
# 在Web服务器中
from config.configuration import ConfigurationManager
from plc.plc_configuration import Configuration

# 获取当前PLC运行配置并展示
plc_config = Configuration(local_dir="plc/local")
manager = ConfigurationManager()
plc_running_config = manager.get_plc_running_config(plc_config)

# 返回给前端
return jsonify({
    'success': True,
    'config': plc_running_config
})
```

### 场景2: 配置同步工具

```python
# 命令行工具
manager = ConfigurationManager()
plc_config = Configuration(local_dir="plc/local")

# 一键同步
success, diff = manager.sync_config_to_plc(
    config_file="config/new_config.yaml",
    plc_configuration=plc_config,
    save_to_local=True
)
```

### 场景3: 配置验证

```python
# 验证配置是否一致
manager = ConfigurationManager()
plc_config = Configuration(local_dir="plc/local")

file_config = manager.load_config_file("config/example_config.yaml")
plc_running_config = manager.get_plc_running_config(plc_config)
diff = manager.analyze_config_diff(file_config, plc_running_config)

if not any(diff.values()):
    print("配置一致")
else:
    print("配置不一致，需要同步")
```

---

## 总结

`get_plc_running_config()` 方法通过以下方式与PLC组态交互：

1. **接收PLC组态实例**：作为参数传入 `plc.plc_configuration.Configuration` 实例
2. **调用PLC组态API**：调用 `get_cycle_time()`, `get_models()`, `get_algorithms()`, `get_connections()` 等方法
3. **组装配置字典**：将获取的信息组装成统一的配置字典格式
4. **返回配置**：返回与文件配置格式一致的字典，便于后续比较和更新

这种设计的优势：
- ✅ **解耦**：config模块不直接访问plc/local目录
- ✅ **统一接口**：返回统一的配置字典格式
- ✅ **便于比较**：文件配置和PLC运行配置使用相同格式
- ✅ **便于更新**：可以直接使用配置字典更新PLC
- ✅ **线程安全**：通过plc_configuration的线程安全API访问

