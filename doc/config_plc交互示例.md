# config/configuration 与 PLC组态交互示例

## 概述

`config/configuration.py` 模块中的 `ConfigurationManager` 类提供了与 `plc/plc_configuration.py` 模块交互的功能，可以获取当前PLC运行的组态内容，分析差异，并更新组态。

---

## 交互流程

```
config/configuration.py (ConfigurationManager)
         ↓
    get_plc_running_config()
         ↓
plc/plc_configuration.py (Configuration)
         ↓
    get_models(), get_algorithms(), get_connections()
         ↓
    返回当前PLC运行的组态配置
```

---

## 基本交互示例

### 1. 初始化两个模块

```python
from config.configuration import ConfigurationManager
from plc.plc_configuration import Configuration

# 初始化组态管理器（config目录下的模块）
config_manager = ConfigurationManager(
    config_dir="config",
    local_dir="plc/local"
)

# 初始化PLC组态模块（plc目录下的模块）
# 注意：PLC组态模块会从plc/local目录加载配置
plc_config = Configuration(local_dir="plc/local")
```

---

### 2. 获取PLC运行配置

```python
# 从PLC组态模块获取当前运行的配置
plc_running_config = config_manager.get_plc_running_config(plc_config)

# 返回的配置字典包含：
# {
#     'cycle_time': 0.5,
#     'models': {
#         'tank1': {
#             'type': 'cylindrical_tank',
#             'params': {...}
#         },
#         ...
#     },
#     'algorithms': {
#         'pid1': {
#             'type': 'PID',
#             'params': {...}
#         },
#         ...
#     },
#     'connections': [
#         {'from': 'pid1.mv', 'to': 'valve1.target_opening'},
#         ...
#     ],
#     'execution_order': ['pid1', 'valve1', 'tank1', ...]  # 如果存在
# }
```

---

### 3. 完整交互流程示例

```python
from config.configuration import ConfigurationManager
from plc.plc_configuration import Configuration

# 步骤1: 初始化模块
config_manager = ConfigurationManager()
plc_config = Configuration(local_dir="plc/local")

# 步骤2: 加载配置文件（从config目录）
file_config = config_manager.load_config_file("config/example_config.yaml")

# 步骤3: 获取PLC当前运行的配置（从plc/local目录）
plc_running_config = config_manager.get_plc_running_config(plc_config)

# 步骤4: 分析差异
diff = config_manager.analyze_config_diff(file_config, plc_running_config)

# 步骤5: 打印差异信息
print("=== 配置差异 ===")
print(f"新增模型: {list(diff['added_models'].keys())}")
print(f"删除模型: {list(diff['removed_models'].keys())}")
print(f"修改模型: {list(diff['modified_models'].keys())}")
print(f"新增算法: {list(diff['added_algorithms'].keys())}")
print(f"删除算法: {list(diff['removed_algorithms'].keys())}")
print(f"修改算法: {list(diff['modified_algorithms'].keys())}")

# 步骤6: 更新到PLC（如果需要）
if any([diff['added_models'], diff['removed_models'], diff['modified_models'],
        diff['added_algorithms'], diff['removed_algorithms'], diff['modified_algorithms'],
        diff['added_connections'], diff['removed_connections']]):
    success = config_manager.update_config_to_plc(plc_config)
    if success:
        print("✓ 配置已更新到PLC")
        # 保存到本地
        config_manager.save_config_to_local()
```

---

## 交互方法详解

### get_plc_running_config() 内部实现

```python
def get_plc_running_config(self, plc_configuration) -> Dict[str, Any]:
    """
    从plc_configuration获取当前PLC运行的组态内容
    
    内部调用：
    1. plc_configuration.get_cycle_time() - 获取运行周期
    2. plc_configuration.get_models() - 获取所有模型配置
    3. plc_configuration.get_algorithms() - 获取所有算法配置
    4. plc_configuration.get_connections() - 获取所有连接关系
    5. plc_configuration.get_execution_order() - 获取执行顺序（如果存在）
    """
    config = {
        'cycle_time': plc_configuration.get_cycle_time(),
        'models': plc_configuration.get_models(),
        'algorithms': plc_configuration.get_algorithms(),
        'connections': plc_configuration.get_connections()
    }
    
    # 如果有execution_order，也获取
    try:
        execution_order = plc_configuration.get_execution_order()
        if execution_order:
            config['execution_order'] = execution_order
    except Exception:
        pass
    
    return config
```

---

## PLC组态模块的API

`plc/plc_configuration.py` 提供的API：

### 读取配置

```python
# 获取运行周期
cycle_time = plc_config.get_cycle_time()  # float

# 获取所有模型配置
models = plc_config.get_models()  # Dict[str, Dict[str, Any]]

# 获取所有算法配置
algorithms = plc_config.get_algorithms()  # Dict[str, Dict[str, Any]]

# 获取所有连接关系
connections = plc_config.get_connections()  # List[Dict[str, str]]

# 获取执行顺序
execution_order = plc_config.get_execution_order()  # List[str]

# 获取所有实例名称
instances = plc_config.get_all_instances()  # List[str]

# 获取完整配置
all_config = plc_config.get_all_config()  # Dict[str, Any]
```

### 在线配置（更新）

```python
# 添加模型
plc_config.online_add_model(name, model_type, params)

# 更新模型参数
plc_config.online_update_model(name, params)

# 删除模型
plc_config.online_remove_model(name)

# 添加算法
plc_config.online_add_algorithm(name, algo_type, params)

# 更新算法参数
plc_config.online_update_algorithm(name, params)

# 删除算法
plc_config.online_remove_algorithm(name)

# 添加连接
plc_config.online_add_connection(from_str="pid1.mv", to_str="valve1.target_opening")

# 删除连接
plc_config.online_remove_connection(from_str="pid1.mv", to_str="valve1.target_opening")
```

---

## 实际使用场景

### 场景1: 从配置文件同步到PLC

```python
from config.configuration import ConfigurationManager
from plc.plc_configuration import Configuration

# 初始化
manager = ConfigurationManager()
plc_config = Configuration(local_dir="plc/local")

# 一键同步：加载配置 -> 分析差异 -> 更新到PLC -> 保存到本地
success, diff = manager.sync_config_to_plc(
    config_file="config/example_config.yaml",
    plc_configuration=plc_config,
    save_to_local=True
)

if success:
    print("同步成功！")
    print(f"差异: {diff}")
else:
    print("同步失败！")
```

### 场景2: 检查配置是否一致

```python
from config.configuration import ConfigurationManager
from plc.plc_configuration import Configuration

manager = ConfigurationManager()
plc_config = Configuration(local_dir="plc/local")

# 加载配置文件
file_config = manager.load_config_file("config/example_config.yaml")

# 获取PLC运行配置
plc_running_config = manager.get_plc_running_config(plc_config)

# 分析差异
diff = manager.analyze_config_diff(file_config, plc_running_config)

# 检查是否一致
is_consistent = (
    not diff['added_models'] and
    not diff['removed_models'] and
    not diff['modified_models'] and
    not diff['added_algorithms'] and
    not diff['removed_algorithms'] and
    not diff['modified_algorithms'] and
    not diff['added_connections'] and
    not diff['removed_connections'] and
    not diff['cycle_time_changed']
)

if is_consistent:
    print("✓ 配置一致")
else:
    print("✗ 配置不一致，存在差异")
    print(f"差异详情: {diff}")
```

### 场景3: 只更新特定参数

```python
from config.configuration import ConfigurationManager
from plc.plc_configuration import Configuration

manager = ConfigurationManager()
plc_config = Configuration(local_dir="plc/local")

# 获取当前PLC运行配置
plc_running_config = manager.get_plc_running_config(plc_config)

# 修改特定参数
plc_running_config['algorithms']['pid1']['params']['kp'] = 15.0

# 直接通过plc_configuration更新
plc_config.online_update_algorithm('pid1', {'kp': 15.0})

# 或者通过ConfigurationManager更新
manager.update_config_to_plc(plc_config, config=plc_running_config)
```

---

## 注意事项

### 1. 配置来源

- **config目录**: 存放配置文件模板（`example_config.yaml`, `debug_config.yaml`）
- **plc/local目录**: PLC实际运行的配置（`plc/local/config.yaml`）

### 2. 配置同步

- `config/configuration.py` 负责管理配置文件
- `plc/plc_configuration.py` 负责管理PLC运行时配置
- 通过 `sync_config_to_plc()` 可以将配置文件同步到PLC

### 3. 线程安全

- `plc_configuration` 使用 `RLock` 保证线程安全
- 多个线程可以安全地读取配置
- 更新配置时需要注意线程安全

### 4. 实例重建

- 如果有新增或删除实例，需要调用 `Runner.update_configuration(rebuild_instances=True)` 重建实例
- `update_config_to_plc()` 会检测是否需要重建，并给出警告

---

## 完整示例脚本

创建一个测试脚本 `test_config_interaction.py`:

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试config/configuration与plc/plc_configuration的交互
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.configuration import ConfigurationManager
from plc.plc_configuration import Configuration

def main():
    print("=" * 60)
    print("config/configuration 与 PLC组态交互测试")
    print("=" * 60)
    
    # 1. 初始化模块
    print("\n1. 初始化模块...")
    config_manager = ConfigurationManager(
        config_dir="config",
        local_dir="plc/local"
    )
    plc_config = Configuration(local_dir="plc/local")
    print("✓ 模块初始化完成")
    
    # 2. 获取PLC运行配置
    print("\n2. 获取PLC当前运行的配置...")
    try:
        plc_running_config = config_manager.get_plc_running_config(plc_config)
        print(f"✓ 获取成功")
        print(f"  - 运行周期: {plc_running_config.get('cycle_time', 'N/A')}")
        print(f"  - 模型数量: {len(plc_running_config.get('models', {}))}")
        print(f"  - 算法数量: {len(plc_running_config.get('algorithms', {}))}")
        print(f"  - 连接数量: {len(plc_running_config.get('connections', []))}")
    except Exception as e:
        print(f"✗ 获取失败: {e}")
        return
    
    # 3. 加载配置文件
    print("\n3. 加载配置文件...")
    try:
        file_config = config_manager.load_config_file("config/example_config.yaml")
        print(f"✓ 加载成功: example_config.yaml")
        print(f"  - 模型数量: {len(file_config.get('models', {}))}")
        print(f"  - 算法数量: {len(file_config.get('algorithms', {}))}")
        print(f"  - 连接数量: {len(file_config.get('connections', []))}")
    except Exception as e:
        print(f"✗ 加载失败: {e}")
        return
    
    # 4. 分析差异
    print("\n4. 分析配置差异...")
    diff = config_manager.analyze_config_diff(file_config, plc_running_config)
    
    print("\n差异详情:")
    if diff['added_models']:
        print(f"  新增模型: {list(diff['added_models'].keys())}")
    if diff['removed_models']:
        print(f"  删除模型: {list(diff['removed_models'].keys())}")
    if diff['modified_models']:
        print(f"  修改模型: {list(diff['modified_models'].keys())}")
    if diff['added_algorithms']:
        print(f"  新增算法: {list(diff['added_algorithms'].keys())}")
    if diff['removed_algorithms']:
        print(f"  删除算法: {list(diff['removed_algorithms'].keys())}")
    if diff['modified_algorithms']:
        print(f"  修改算法: {list(diff['modified_algorithms'].keys())}")
    if diff['added_connections']:
        print(f"  新增连接: {len(diff['added_connections'])}个")
    if diff['removed_connections']:
        print(f"  删除连接: {len(diff['removed_connections'])}个")
    if diff['cycle_time_changed']:
        print(f"  cycle_time变更: {diff['cycle_time']}")
    
    # 检查是否有差异
    has_changes = (
        diff['added_models'] or diff['removed_models'] or diff['modified_models'] or
        diff['added_algorithms'] or diff['removed_algorithms'] or diff['modified_algorithms'] or
        diff['added_connections'] or diff['removed_connections'] or diff['cycle_time_changed']
    )
    
    if not has_changes:
        print("\n✓ 配置一致，无差异")
    else:
        print("\n⚠ 配置存在差异")
        
        # 5. 询问是否更新
        print("\n5. 是否更新配置到PLC？")
        print("   (注意：此操作会修改PLC运行配置)")
        response = input("   输入 'yes' 继续，其他任意键取消: ")
        
        if response.lower() == 'yes':
            print("\n开始更新配置...")
            success = config_manager.update_config_to_plc(plc_config, rebuild_instances=False)
            if success:
                print("✓ 配置更新成功")
                # 保存到本地
                save = input("是否保存到本地配置文件？(yes/no): ")
                if save.lower() == 'yes':
                    config_manager.save_config_to_local()
                    print("✓ 已保存到本地")
            else:
                print("✗ 配置更新失败")
        else:
            print("已取消更新")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == '__main__':
    main()
```

---

## 总结

`get_plc_running_config()` 方法通过以下方式与PLC组态交互：

1. **接收PLC组态实例**: 接收 `plc.plc_configuration.Configuration` 实例作为参数
2. **调用PLC组态API**: 调用 `get_cycle_time()`, `get_models()`, `get_algorithms()`, `get_connections()` 等方法
3. **组装配置字典**: 将获取的信息组装成统一的配置字典格式
4. **返回配置**: 返回与文件配置格式一致的字典，便于后续比较和更新

这样设计的好处：
- ✅ 解耦：config模块不直接访问plc/local目录
- ✅ 统一接口：返回统一的配置字典格式
- ✅ 便于比较：文件配置和PLC运行配置使用相同格式
- ✅ 便于更新：可以直接使用配置字典更新PLC

