# config/configuration模块功能总结

## 模块概述

`config/configuration.py` 是组态管理模块，提供组态文件的加载、管理、差异分析和更新功能。

---

## 已实现的功能

### 1. 组态文件加载 ✅

**方法**: `load_config_file(config_file: str) -> Dict[str, Any]`

**功能**:
- 支持绝对路径和相对路径
- 自动解析相对于config_dir的路径
- YAML文件解析和格式验证
- 错误处理和日志记录

**示例**:
```python
manager = ConfigurationManager()
config = manager.load_config_file("example_config.yaml")
```

---

### 2. 组态内容管理 ✅

**方法**: `get_current_config() -> Optional[Dict[str, Any]]`

**功能**:
- 获取当前加载的组态配置
- 返回配置字典的副本

**示例**:
```python
current_config = manager.get_current_config()
```

---

### 3. 获取PLC运行配置 ✅

**方法**: `get_plc_running_config(plc_configuration) -> Dict[str, Any]`

**功能**:
- 从`plc.plc_configuration.Configuration`获取当前PLC运行的组态内容
- 获取cycle_time、models、algorithms、connections
- 如果存在execution_order，也会获取

**示例**:
```python
from plc.plc_configuration import Configuration
plc_config = Configuration(local_dir="plc/local")
plc_running_config = manager.get_plc_running_config(plc_config)
```

---

### 4. 组态差异分析 ✅

**方法**: `analyze_config_diff(config1: Dict[str, Any], config2: Dict[str, Any]) -> Dict[str, Any]`

**功能**:
- 分析两个组态配置的差异
- 检测新增/删除/修改的模型实例
- 检测新增/删除/修改的算法实例
- 检测新增/删除的连接关系
- 检测cycle_time变更
- 标准化连接关系格式便于比较

**返回的差异字典包含**:
- `added_models`: 新增的模型实例
- `removed_models`: 删除的模型实例
- `modified_models`: 修改的模型实例（包含from/to）
- `added_algorithms`: 新增的算法实例
- `removed_algorithms`: 删除的算法实例
- `modified_algorithms`: 修改的算法实例（包含from/to）
- `added_connections`: 新增的连接关系
- `removed_connections`: 删除的连接关系
- `cycle_time_changed`: cycle_time是否改变
- `cycle_time`: cycle_time变更详情（如果改变）

**示例**:
```python
diff = manager.analyze_config_diff(file_config, plc_running_config)
if diff['added_models']:
    print(f"新增模型: {list(diff['added_models'].keys())}")
```

---

### 5. 更新组态到PLC ✅

**方法**: `update_config_to_plc(plc_configuration, config: Dict[str, Any] = None, rebuild_instances: bool = False) -> bool`

**功能**:
- 自动分析差异
- 删除已移除的模型和算法实例
- 添加新的模型和算法实例
- 更新修改的模型和算法参数
- 删除已移除的连接关系
- 添加新的连接关系
- 检测是否需要重建实例

**更新顺序**:
1. 先删除已移除的实例和连接
2. 再添加新的实例和连接
3. 最后更新修改的实例参数

**示例**:
```python
success = manager.update_config_to_plc(plc_config, rebuild_instances=True)
```

---

### 6. 保存配置到本地 ✅

**方法**: `save_config_to_local(config: Dict[str, Any] = None) -> bool`

**功能**:
- 保存组态配置到PLC本地目录（`plc/local/config.yaml`）
- 自动创建目录（如果不存在）
- 使用YAML格式保存

**示例**:
```python
success = manager.save_config_to_local()
```

---

### 7. 同步组态到PLC（一键操作）✅

**方法**: `sync_config_to_plc(config_file: str, plc_configuration, save_to_local: bool = True) -> Tuple[bool, Dict[str, Any]]`

**功能**:
- 加载配置文件
- 获取PLC运行配置
- 分析差异
- 更新到PLC
- 保存到本地（可选）

**返回**: `(是否成功, 差异分析结果)`

**示例**:
```python
success, diff = manager.sync_config_to_plc(
    config_file="example_config.yaml",
    plc_configuration=plc_config,
    save_to_local=True
)
```

---

### 8. 配置格式验证 ✅

**方法**: `_validate_config_format(config: Dict[str, Any])`

**功能**:
- 验证配置是否为字典类型
- 验证models格式（如果存在）
- 验证algorithms格式（如果存在）
- 验证connections格式（如果存在）

**验证内容**:
- ✅ 必需字段检查
- ✅ 数据类型检查
- ⚠️ 参数值范围验证（未实现）
- ⚠️ 实例名称唯一性检查（未实现）
- ⚠️ 连接关系有效性检查（未实现）

---

## 待实现的功能

### 1. 参数验证（使用param_definitions）❌

**需求**: 使用`config/param_definitions.py`中的参数定义进行验证

**需要实现**:
- 验证参数类型
- 验证参数范围（min/max）
- 验证必需参数是否存在
- 验证参数单位（可选）

**示例**:
```python
def validate_config_params(self, config: Dict[str, Any]) -> List[str]:
    """验证配置参数，返回错误列表"""
    errors = []
    # 使用param_definitions验证参数
    return errors
```

---

### 2. 配置模板生成 ❌

**需求**: 根据参数定义自动生成配置模板

**需要实现**:
- 根据模型类型生成模型配置模板
- 根据算法类型生成算法配置模板
- 使用param_definitions中的默认值

**示例**:
```python
def generate_model_template(self, model_type: str, instance_name: str) -> Dict[str, Any]:
    """生成模型配置模板"""
    pass
```

---

### 3. 配置比较和可视化 ❌

**需求**: 提供更友好的差异展示

**需要实现**:
- 格式化差异输出
- 生成差异报告（文本/HTML）
- 可视化差异（可选）

**示例**:
```python
def format_diff_report(self, diff: Dict[str, Any]) -> str:
    """格式化差异报告"""
    pass
```

---

### 4. 配置导入导出 ❌

**需求**: 支持配置的导入导出功能

**需要实现**:
- 导出配置为JSON格式
- 导入JSON配置
- 配置备份和恢复

**示例**:
```python
def export_config(self, output_file: str, format: str = 'yaml') -> bool:
    """导出配置"""
    pass

def import_config(self, input_file: str, format: str = 'yaml') -> Dict[str, Any]:
    """导入配置"""
    pass
```

---

### 5. 配置版本管理 ❌

**需求**: 支持配置版本管理

**需要实现**:
- 配置版本号
- 配置变更历史
- 配置回滚

**示例**:
```python
def save_config_version(self, version: str = None) -> bool:
    """保存配置版本"""
    pass

def load_config_version(self, version: str) -> Dict[str, Any]:
    """加载配置版本"""
    pass
```

---

### 6. 配置合并 ❌

**需求**: 支持配置合并功能

**需要实现**:
- 合并多个配置文件
- 配置冲突解决策略
- 配置继承

**示例**:
```python
def merge_configs(self, configs: List[Dict[str, Any]], strategy: str = 'override') -> Dict[str, Any]:
    """合并多个配置"""
    pass
```

---

## 当前功能使用示例

### 完整示例

```python
from config.configuration import ConfigurationManager
from plc.plc_configuration import Configuration

# 1. 初始化组态管理器
manager = ConfigurationManager(
    config_dir="config",
    local_dir="plc/local"
)

# 2. 加载组态文件
try:
    config = manager.load_config_file("example_config.yaml")
    print("✓ 组态文件加载成功")
except FileNotFoundError as e:
    print(f"✗ 文件不存在: {e}")
except Exception as e:
    print(f"✗ 加载失败: {e}")

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
        print("✓ 配置更新成功")
        # 保存到本地
        manager.save_config_to_local()
    else:
        print("✗ 配置更新失败")
else:
    print("\n配置无变更，无需更新")

# 7. 或者使用一键同步
success, diff = manager.sync_config_to_plc(
    config_file="example_config.yaml",
    plc_configuration=plc_config,
    save_to_local=True
)
```

---

## 功能完整性评估

### ✅ 已实现（7/13）

1. ✅ 加载组态文件
2. ✅ 管理组态内容
3. ✅ 获取PLC运行配置
4. ✅ 分析组态差异
5. ✅ 更新组态到PLC
6. ✅ 保存配置到本地
7. ✅ 同步组态到PLC（一键操作）

### ⚠️ 部分实现（1/13）

8. ⚠️ 配置格式验证（基本验证已实现，但缺少参数验证）

### ❌ 未实现（5/13）

9. ❌ 参数验证（使用param_definitions）
10. ❌ 配置模板生成
11. ❌ 配置比较和可视化
12. ❌ 配置导入导出
13. ❌ 配置版本管理
14. ❌ 配置合并

---

## 下一步建议

### 高优先级

1. **参数验证功能**
   - 使用`param_definitions.py`验证参数类型和范围
   - 提供详细的验证错误信息

2. **配置模板生成**
   - 根据模型/算法类型生成配置模板
   - 使用param_definitions中的默认值

### 中优先级

3. **配置比较和可视化**
   - 格式化差异输出
   - 生成差异报告

4. **配置导入导出**
   - 支持JSON格式导出
   - 配置备份和恢复

### 低优先级

5. **配置版本管理**
   - 配置版本号
   - 配置变更历史

6. **配置合并**
   - 合并多个配置文件
   - 配置冲突解决

