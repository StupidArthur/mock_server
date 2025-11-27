# PLC功能验证指南

## 验证功能列表

### 1. 基础功能验证
- ✅ 本地配置加载
- ✅ 快照保存和恢复
- ✅ 运行时数据推送（Redis）
- ✅ OPCUA Server节点更新
- ✅ 数据存储功能

### 2. 高级功能验证
- ✅ 配置更新（Redis订阅）
- ✅ 异常恢复（异常恢复）
- ✅ 参数写入功能

---

## 测试前提条件

**重要**：在进行功能验证之前，请确保：

1. ✅ **PLC正在运行**：`python run_plc.py` 已启动并正常运行
2. ✅ **Redis服务运行**：Redis服务器已启动（默认 localhost:6379）
3. ✅ **数据库文件存在**：`plc_data.db` 文件已创建（DataStorage模块启动后自动创建）

**注意**：
- 某些测试（如数据推送、数据库存储）需要PLC正在运行
- 某些测试（如配置加载、快照功能）可以在PLC未运行时进行

---

## 验证步骤

### 1. 验证本地配置加载

#### 1.1 检查配置文件
```bash
# 检查本地配置文件是否存在
ls plc/local/config.yaml

# 查看配置文件内容
cat plc/local/config.yaml
```

#### 1.2 启动PLC并检查日志
```bash
python run_plc.py
```

**预期日志**：
```
Configuration loaded from local directory: plc/local/config.yaml
Configuration initialized
```

**验证点**：
- ✅ 配置文件正确加载
- ✅ 所有模型和算法实例正确初始化
- ✅ 执行顺序正确

---

### 2. 验证快照保存和恢复

#### 2.1 首次启动（无快照）
```bash
# 删除快照文件（如果存在）
rm plc/local/snapshot.yaml

# 启动PLC
python run_plc.py
```

**预期日志**：
```
No snapshot found, using configuration file values
```

**验证点**：
- ✅ 没有快照时，使用配置文件中的初始值
- ✅ 运行一段时间后，快照文件自动创建

#### 2.2 检查快照文件
```bash
# 等待至少10个周期（约5秒），然后检查快照文件
ls plc/local/snapshot.yaml

# 查看快照内容
cat plc/local/snapshot.yaml
```

**预期结果**：
- ✅ 快照文件存在
- ✅ 包含所有实例的参数值
- ✅ 包含时间戳

#### 2.3 重启验证（有快照）
```bash
# 停止PLC（Ctrl+C）
# 再次启动
python run_plc.py
```

**预期日志**：
```
Snapshot found, loading base config and applying snapshot (XX parameters)
Configuration initialized from snapshot
```

**验证点**：
- ✅ 快照被正确加载
- ✅ 参数值恢复到快照时的状态
- ✅ 模型和算法使用快照中的参数值初始化

#### 2.4 验证参数值恢复
```bash
# 启动PLC后，检查参数值是否与快照一致
# 可以通过Redis或OPCUA客户端查看
```

**验证点**：
- ✅ 模型参数（如 tank1.LEVEL）恢复到快照值
- ✅ 算法参数（如 pid1.pv, pid1.sv, pid1.mv）恢复到快照值
- ✅ PID的mode恢复到快照值

---

### 3. 验证运行时数据推送（Redis）

#### 3.1 检查Redis数据
```bash
# 使用redis-cli连接Redis
redis-cli

# 查看当前数据
GET plc:data:current

# 查看历史数据列表长度
LLEN plc:data:history
```

**预期结果**：
- ✅ `plc:data:current` 包含最新的参数值
- ✅ `plc:data:history` 列表不断增长
- ✅ 数据格式正确（JSON）

#### 3.2 实时监控数据
```bash
# 实时查看最新数据（每秒更新）
# 注意：数据格式为 {'timestamp': ..., 'datetime': ..., 'params': {...}}
# 实际参数在 params 字段中
watch -n 1 'redis-cli GET plc:data:current | python -c "import sys, json; d=json.load(sys.stdin); print(json.dumps(d.get(\"params\", {}), indent=2))"'
```

或者使用Python脚本：
```python
import redis
import json
import time

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

while True:
    data = redis_client.get("plc:data:current")
    if data:
        parsed = json.loads(data)
        params = parsed.get('params', {})
        print(f"\n时间: {parsed.get('datetime')}")
        print(f"参数数量: {len(params)}")
        # 显示部分参数
        for key in list(params.keys())[:5]:
            print(f"  {key}: {params[key]}")
    time.sleep(1)
```

**验证点**：
- ✅ 数据每0.5秒更新一次
- ✅ 参数值随时间变化
- ✅ 数据格式正确

---

### 4. 验证OPCUA Server节点更新

#### 4.1 使用OPCUA客户端连接
```
服务器地址：opc.tcp://localhost:18951
命名空间：1
节点ID类型：String
```

#### 4.2 检查节点值
```
节点示例：
- pid1.pv
- pid1.sv
- pid1.mv
- pid1.mode
- tank1.LEVEL
- valve1.CURRENT_OPENING
```

**验证点**：
- ✅ 节点值实时更新
- ✅ 节点值变化与Redis数据一致
- ✅ 可以写入节点值（如 pid1.sv）

---

### 5. 验证数据存储功能

#### 5.1 检查数据库文件
```bash
# 检查数据库文件是否存在
ls plc_data.db

# 使用sqlite3查看数据
sqlite3 plc_data.db

# 查看表结构
.schema

# 查看数据记录数（注意：表名是 data_records，不是 history_data）
SELECT COUNT(*) FROM data_records;

# 查看最新数据
SELECT * FROM data_records ORDER BY timestamp DESC LIMIT 10;
```

**验证点**：
- ✅ 数据库文件存在
- ✅ 数据不断写入数据库
- ✅ 时间戳正确
- ✅ 参数值正确

---

### 6. 验证配置更新（Redis订阅）

#### 6.1 发送配置更新消息
```python
import redis
import json
from datetime import datetime

# 连接Redis
redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

# 准备配置更新消息
config_update = {
    "type": "config_update",
    "config": {
        "cycle_time": 0.5,
        "models": {
            "tank1": {
                "type": "cylindrical_tank",
                "params": {
                    "initial_level": 1.0  # 修改初始水位
                }
            }
        },
        "algorithms": {
            "pid1": {
                "type": "PID",
                "params": {
                    "sv": 2.0  # 修改设定值
                }
            }
        },
        "connections": [
            {"from": "pid1.mv", "to": "valve1.TARGET_OPENING"},
            {"from": "valve1.CURRENT_OPENING", "to": "tank1.VALVE_OPENING"},
            {"from": "tank1.LEVEL", "to": "pid1.pv"}
        ],
        "execution_order": ["pid1", "valve1", "tank1"]
    },
    "timestamp": datetime.now().isoformat()
}

# 发送配置更新
redis_client.publish("plc:config:update", json.dumps(config_update))
print("Configuration update sent")
```

#### 6.2 检查配置是否更新
```bash
# 检查本地配置文件是否更新
cat plc/local/config.yaml

# 检查日志
tail -f logs/mock_server_info.log | grep "Configuration update"
```

**验证点**：
- ✅ 配置更新消息被接收
- ✅ 本地配置文件被更新
- ✅ 实例参数被更新
- ✅ 下个周期生效

---

### 7. 验证异常恢复功能

#### 7.1 模拟异常关闭
```bash
# 启动PLC
python run_plc.py

# 运行一段时间后，强制终止（模拟异常）
# Windows: Ctrl+Break 或 任务管理器结束进程
# Linux: kill -9 <pid>
```

#### 7.2 检查快照文件
```bash
# 检查快照文件是否存在
ls plc/local/snapshot.yaml

# 查看快照时间戳
cat plc/local/snapshot.yaml | grep timestamp
```

#### 7.3 重启验证
```bash
# 重新启动PLC
python run_plc.py
```

**验证点**：
- ✅ 快照文件存在（异常关闭前保存）
- ✅ 重启后自动加载快照
- ✅ 参数值恢复到异常关闭前的状态
- ✅ 系统继续正常运行

---

### 8. 验证参数写入功能

#### 8.1 通过Redis发送参数写入命令
```python
import redis
import json

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

# 写入参数命令
command = {
    "action": "write_parameter",
    "param_name": "pid1.sv",
    "value": 3.0
}

# 发送命令
redis_client.publish("plc:command:write_parameter", json.dumps(command))
print("Parameter write command sent")
```

#### 8.2 检查参数是否更新
```bash
# 通过Redis查看参数值
redis-cli GET plc:data:current | python -m json.tool | grep "pid1.sv"

# 或通过OPCUA客户端查看
```

**验证点**：
- ✅ 参数写入命令被接收
- ✅ 参数值在下个周期更新
- ✅ 更新后的值正确

---

## 自动化测试脚本

### 测试脚本1：基础功能测试
```python
# test_basic_functionality.py
import redis
import json
import time
from plc.configuration import Configuration
from plc.runner import Runner

def test_config_loading():
    """测试配置加载"""
    print("1. Testing configuration loading...")
    config = Configuration(local_dir="plc/local")
    assert config.get_cycle_time() == 0.5
    assert len(config.get_models()) > 0
    assert len(config.get_algorithms()) > 0
    print("   ✓ Configuration loaded successfully")

def test_snapshot():
    """测试快照功能"""
    print("2. Testing snapshot functionality...")
    from plc.snapshot_manager import SnapshotManager
    
    snapshot_mgr = SnapshotManager("plc/local/snapshot.yaml")
    
    # 测试保存快照
    test_params = {"tank1.LEVEL": 1.5, "pid1.pv": 1.5}
    assert snapshot_mgr.save_snapshot(test_params) == True
    print("   ✓ Snapshot saved")
    
    # 测试加载快照
    loaded = snapshot_mgr.load_snapshot()
    assert loaded is not None
    assert loaded["tank1.LEVEL"] == 1.5
    print("   ✓ Snapshot loaded successfully")

def test_redis_connection():
    """测试Redis连接"""
    print("3. Testing Redis connection...")
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    assert redis_client.ping() == True
    print("   ✓ Redis connection successful")

if __name__ == '__main__':
    test_config_loading()
    test_snapshot()
    test_redis_connection()
    print("\nAll basic tests passed!")
```

### 测试脚本2：运行时验证
```python
# test_runtime.py
import redis
import json
import time

def test_data_publishing():
    """测试数据推送"""
    print("Testing data publishing...")
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    # 等待数据推送
    time.sleep(2)
    
    # 检查当前数据
    current_data = redis_client.get("plc:data:current")
    assert current_data is not None
    
    data = json.loads(current_data)
    assert "tank1" in data or "pid1" in data
    print("   ✓ Data publishing works")

def test_snapshot_auto_save():
    """测试快照自动保存"""
    print("Testing snapshot auto-save...")
    import os
    
    snapshot_file = "plc/local/snapshot.yaml"
    if os.path.exists(snapshot_file):
        # 获取文件修改时间
        mtime_before = os.path.getmtime(snapshot_file)
        
        # 等待至少10个周期（5秒）
        time.sleep(6)
        
        # 检查文件是否更新
        mtime_after = os.path.getmtime(snapshot_file)
        assert mtime_after > mtime_before
        print("   ✓ Snapshot auto-save works")
    else:
        print("   ⚠ Snapshot file not found (will be created after 10 cycles)")

if __name__ == '__main__':
    test_data_publishing()
    test_snapshot_auto_save()
    print("\nRuntime tests completed!")
```

---

## 快速验证清单

### ✅ 启动验证
- [ ] PLC正常启动，无错误
- [ ] 配置文件正确加载
- [ ] 所有模块初始化成功
- [ ] 执行顺序正确

### ✅ 快照验证
- [ ] 首次启动：使用配置文件初始值
- [ ] 运行后：快照文件自动创建
- [ ] 重启后：快照被正确加载
- [ ] 参数值恢复到快照状态

### ✅ 数据推送验证
- [ ] Redis中有最新数据（`plc:data:current`）
- [ ] 历史数据列表增长（`plc:data:history`）
- [ ] 数据格式正确（JSON）
- [ ] 数据实时更新（每0.5秒）

### ✅ OPCUA验证
- [ ] OPCUA Server正常启动
- [ ] 客户端可以连接
- [ ] 节点值实时更新
- [ ] 可以写入节点值

### ✅ 数据存储验证
- [ ] 数据库文件存在
- [ ] 数据不断写入
- [ ] 时间戳正确
- [ ] 可以查询历史数据

### ✅ 配置更新验证
- [ ] Redis配置更新消息被接收
- [ ] 本地配置文件被更新
- [ ] 实例参数被更新
- [ ] 下个周期生效

### ✅ 异常恢复验证
- [ ] 异常关闭前保存快照
- [ ] 重启后自动加载快照
- [ ] 参数值恢复正确
- [ ] 系统继续正常运行

---

## 常见问题排查

### 问题1：快照文件不存在
**原因**：首次运行，还未保存快照
**解决**：等待至少10个周期（约5秒），快照会自动创建

### 问题2：配置更新不生效
**原因**：消息格式错误或Redis连接失败
**解决**：检查消息格式，确保Redis连接正常

### 问题3：参数值不更新
**原因**：参数名格式错误或实例不存在
**解决**：检查参数名格式（如 `pid1.sv`），确保实例存在

### 问题4：OPCUA连接失败
**原因**：服务器未启动或端口被占用
**解决**：检查日志，确认OPCUA Server已启动

---

## 验证工具推荐

1. **Redis客户端**：
   - `redis-cli`（命令行）
   - RedisInsight（图形界面）

2. **OPCUA客户端**：
   - UaExpert（Windows）
   - opcua-client（Python库）

3. **数据库工具**：
   - `sqlite3`（命令行）
   - DB Browser for SQLite（图形界面）

4. **日志查看**：
   - `tail -f logs/mock_server_info.log`（Linux）
   - `Get-Content logs/mock_server_info.log -Wait`（Windows PowerShell）

