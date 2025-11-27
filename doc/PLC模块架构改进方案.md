# PLC模块架构改进方案

## 需求分析

### 当前问题
1. PLC模块直接加载config目录下的组态文件，与组态模块耦合
2. PLC模块和组态模块应该独立运行
3. 缺少运行时状态保存和恢复机制
4. 缺少配置更新机制

### 改进目标
1. **独立运行**：PLC模块使用本地组态文件，不依赖config目录
2. **状态持久化**：支持运行时快照保存和恢复
3. **配置更新**：通过消息机制接收组态更新
4. **异常恢复**：异常关闭后重启能恢复运行状态

---

## 架构设计

### 1. 目录结构

```
plc/
├── local/                    # PLC模块本地目录
│   ├── config.yaml          # 初始组态文件（配置结构）
│   └── snapshot.yaml        # 运行时快照（当前参数值）
├── configuration.py         # 组态管理（增强）
├── snapshot_manager.py       # 快照管理（新增）
└── runner.py                # 运行模块（增强）
```

### 2. 文件说明

#### 2.1 `plc/local/config.yaml`
- **用途**：存储初始组态配置（结构信息）
- **内容**：模型定义、算法定义、连接关系
- **更新时机**：组态模块发送配置更新时

#### 2.2 `plc/local/snapshot.yaml`
- **用途**：存储运行时数据快照（当前参数值）
- **内容**：所有实例的当前参数值
- **更新时机**：每个周期或定期保存
- **恢复时机**：启动时自动加载

---

## 功能设计

### 1. 快照管理模块（新增）

#### 1.1 SnapshotManager类

**职责**：
- 保存运行时快照
- 加载运行时快照
- 合并快照到配置

**主要方法**：
```python
class SnapshotManager:
    def __init__(self, snapshot_file: str = "plc/local/snapshot.yaml"):
        """初始化快照管理器"""
    
    def save_snapshot(self, params: Dict[str, Any]) -> bool:
        """保存运行时快照"""
    
    def load_snapshot(self) -> Optional[Dict[str, Any]]:
        """加载运行时快照"""
    
    def apply_snapshot_to_config(self, config: Configuration, snapshot: Dict[str, Any]) -> None:
        """将快照应用到配置（更新初始参数值）"""
```

### 2. Configuration模块增强

#### 2.1 新增方法

```python
class Configuration:
    def load_from_local(self, local_dir: str = "plc/local") -> bool:
        """从本地目录加载组态文件"""
    
    def save_to_local(self, local_dir: str = "plc/local") -> bool:
        """保存组态文件到本地目录"""
    
    def update_from_dict(self, config_dict: dict) -> bool:
        """从字典更新配置（用于接收配置更新）"""
    
    def get_snapshot_data(self) -> Dict[str, Any]:
        """获取当前配置的快照数据（用于保存）"""
```

### 3. Runner模块增强

#### 3.1 新增功能

```python
class Runner:
    def __init__(self, local_dir: str = "plc/local", redis_config: dict = None, ...):
        """从本地目录加载配置和快照"""
    
    def _load_configuration(self) -> Configuration:
        """加载组态配置（优先从本地目录）"""
    
    def _load_snapshot(self) -> Optional[Dict[str, Any]]:
        """加载运行时快照"""
    
    def _save_snapshot(self) -> None:
        """保存运行时快照（定期调用）"""
    
    def _config_update_subscriber(self) -> None:
        """订阅配置更新消息（Redis）"""
    
    def apply_config_update(self, config_dict: dict) -> bool:
        """应用配置更新"""
```

#### 3.2 启动流程

```
1. 检查本地目录是否存在
   ├─ 不存在：创建默认配置
   └─ 存在：加载 config.yaml

2. 检查快照文件是否存在
   ├─ 存在：加载快照，合并到配置
   └─ 不存在：使用配置中的初始值

3. 初始化模型和算法（使用合并后的参数）

4. 启动运行循环

5. 启动配置更新订阅线程
```

#### 3.3 运行流程

```
每个周期：
1. 执行实例计算
2. 更新参数值
3. 定期保存快照（如每10个周期）

配置更新：
1. 接收Redis消息
2. 解析配置更新
3. 应用配置更新
4. 保存到本地config.yaml
5. 重建实例（如果需要）
```

---

## Redis消息格式

### 1. 配置更新消息

**Channel**: `plc:config:update`

**消息格式**:
```json
{
    "type": "config_update",  // 或 "config_reset"
    "config": {
        "cycle_time": 0.5,
        "models": {...},
        "algorithms": {...},
        "connections": [...]
    },
    "timestamp": "2025-11-27T10:00:00"
}
```

### 2. 参数更新消息

**Channel**: `plc:config:param_update`

**消息格式**:
```json
{
    "type": "param_update",
    "params": {
        "tank1.LEVEL": 1.5,
        "pid1.sv": 6.0
    },
    "timestamp": "2025-11-27T10:00:00"
}
```

---

## 快照格式

### snapshot.yaml格式

```yaml
# 运行时快照
# 保存时间：2025-11-27 10:00:00
timestamp: "2025-11-27T10:00:00"

# 模型参数快照
models:
  tank1:
    LEVEL: 1.5
  valve1:
    CURRENT_OPENING: 50.0
    TARGET_OPENING: 50.0

# 算法参数快照
algorithms:
  pid1:
    config:
      kp: 12.0
      ti: 30.0
      td: 0.15
    input:
      pv: 1.5
      sv: 5.0
    output:
      mv: 50.0
      mode: 1
```

---

## 实现步骤

### 阶段1：基础功能
1. ✅ 创建 `plc/local/` 目录结构
2. ✅ 实现 `SnapshotManager` 类
3. ✅ 增强 `Configuration` 类（本地文件管理）
4. ✅ 修改 `Runner` 初始化流程（加载本地配置和快照）

### 阶段2：快照功能
5. ✅ 实现快照保存（定期保存）
6. ✅ 实现快照加载（启动时恢复）
7. ✅ 实现快照合并到配置

### 阶段3：配置更新
8. ✅ 实现Redis配置更新订阅
9. ✅ 实现配置更新应用
10. ✅ 实现参数更新应用

### 阶段4：测试和优化
11. ✅ 测试异常恢复功能
12. ✅ 测试配置更新功能
13. ✅ 优化性能（快照保存频率）

---

## 配置更新流程

### 1. 组态模块发送更新

```python
# 组态模块代码
import redis
import json

redis_client = redis.Redis(...)
config_update = {
    "type": "config_update",
    "config": {...},
    "timestamp": datetime.now().isoformat()
}
redis_client.publish("plc:config:update", json.dumps(config_update))
```

### 2. PLC模块接收更新

```python
# Runner模块
def _config_update_subscriber(self):
    pubsub = self.redis_client.pubsub()
    pubsub.subscribe("plc:config:update")
    
    for message in pubsub.listen():
        if message['type'] == 'message':
            config_dict = json.loads(message['data'])
            self.apply_config_update(config_dict['config'])
```

### 3. 应用配置更新

```python
def apply_config_update(self, config_dict: dict):
    with self._lock:
        # 1. 更新Configuration
        self.config.update_from_dict(config_dict)
        
        # 2. 保存到本地config.yaml
        self.config.save_to_local("plc/local")
        
        # 3. 重建实例（如果需要）
        self.update_configuration(rebuild_instances=True)
        
        # 4. 重新计算执行顺序
        self.execution_order = self.config.get_execution_order()
```

---

## 异常恢复流程

### 1. 正常关闭
```
1. 保存当前快照
2. 停止运行循环
3. 清理资源
```

### 2. 异常关闭
```
1. 快照文件保留（上次保存的快照）
2. 下次启动时自动加载
```

### 3. 重启恢复
```
1. 加载 config.yaml（组态结构）
2. 加载 snapshot.yaml（运行时参数）
3. 合并快照到配置
4. 使用合并后的参数初始化实例
5. 继续运行
```

---

## 注意事项

1. **快照保存频率**：
   - 建议每10个周期保存一次（避免频繁IO）
   - 或者每个周期保存（更安全但性能影响）

2. **配置更新冲突**：
   - 配置更新时，如果实例正在运行，需要安全地重建实例
   - 保留实例的内部状态（如PID的积分项）

3. **快照文件大小**：
   - 如果参数很多，快照文件可能较大
   - 考虑压缩或增量保存

4. **目录权限**：
   - 确保PLC模块有权限读写 `plc/local/` 目录

5. **向后兼容**：
   - 如果本地目录不存在，从config目录加载（兼容旧版本）
   - 逐步迁移到新架构

---

## 迁移方案

### 阶段1：兼容模式（当前）
- PLC模块优先从 `plc/local/` 加载
- 如果不存在，从 `config/` 加载（向后兼容）

### 阶段2：完全迁移
- 移除从 `config/` 加载的逻辑
- 所有配置都从 `plc/local/` 加载

---

## 测试场景

1. **正常启动**：无快照文件，使用初始配置
2. **恢复启动**：有快照文件，恢复运行状态
3. **配置更新**：接收配置更新，应用并保存
4. **参数更新**：接收参数更新，下个周期生效
5. **异常恢复**：模拟异常关闭，重启后恢复

