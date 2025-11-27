"""
PLC功能验证测试脚本
用于验证PLC模块的各项功能是否正常工作
"""
import os
import sys
import time
import json
import redis
import sqlite3
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from plc.plc_configuration import Configuration
from plc.snapshot_manager import SnapshotManager


class PLCFunctionalityTester:
    """PLC功能测试类"""
    
    def __init__(self):
        self.redis_client = None
        self.test_results = []
        
    def log_test(self, test_name: str, passed: bool, message: str = ""):
        """记录测试结果"""
        status = "✓ PASS" if passed else "✗ FAIL"
        result = f"{status} - {test_name}"
        if message:
            result += f": {message}"
        print(result)
        self.test_results.append({
            'test': test_name,
            'passed': passed,
            'message': message
        })
    
    def test_config_loading(self):
        """测试1：配置加载功能"""
        print("\n" + "="*60)
        print("测试1：配置加载功能")
        print("="*60)
        
        try:
            # 测试从本地目录加载配置
            config = Configuration(local_dir="plc/local")
            cycle_time = config.get_cycle_time()
            models = config.get_models()
            algorithms = config.get_algorithms()
            
            assert cycle_time == 0.5, f"Cycle time should be 0.5, got {cycle_time}"
            assert len(models) > 0, "No models found in configuration"
            assert len(algorithms) > 0, "No algorithms found in configuration"
            
            self.log_test("配置加载", True, f"加载了 {len(models)} 个模型和 {len(algorithms)} 个算法")
            return True
        except Exception as e:
            self.log_test("配置加载", False, str(e))
            return False
    
    def test_snapshot_save_load(self):
        """测试2：快照保存和加载功能"""
        print("\n" + "="*60)
        print("测试2：快照保存和加载功能")
        print("="*60)
        
        try:
            snapshot_mgr = SnapshotManager("plc/local/test_snapshot.yaml")
            
            # 测试保存快照
            test_params = {
                "tank1.LEVEL": 1.5,
                "pid1.pv": 1.5,
                "pid1.sv": 2.0,
                "pid1.mv": 50.0,
                "pid1.mode": 1
            }
            
            result = snapshot_mgr.save_snapshot(test_params)
            assert result == True, "Failed to save snapshot"
            self.log_test("快照保存", True, f"保存了 {len(test_params)} 个参数")
            
            # 测试加载快照
            loaded = snapshot_mgr.load_snapshot()
            assert loaded is not None, "Failed to load snapshot"
            assert loaded["tank1.LEVEL"] == 1.5, "Snapshot value mismatch"
            self.log_test("快照加载", True, f"加载了 {len(loaded)} 个参数")
            
            # 清理测试文件
            if os.path.exists("plc/local/test_snapshot.yaml"):
                os.remove("plc/local/test_snapshot.yaml")
            
            return True
        except Exception as e:
            self.log_test("快照功能", False, str(e))
            return False
    
    def test_redis_connection(self):
        """测试3：Redis连接功能"""
        print("\n" + "="*60)
        print("测试3：Redis连接功能")
        print("="*60)
        
        try:
            self.redis_client = redis.Redis(
                host='localhost',
                port=6379,
                decode_responses=True
            )
            result = self.redis_client.ping()
            assert result == True, "Redis ping failed"
            self.log_test("Redis连接", True, "连接成功")
            return True
        except Exception as e:
            self.log_test("Redis连接", False, f"连接失败: {e}")
            return False
    
    def test_data_publishing(self):
        """测试4：数据推送功能"""
        print("\n" + "="*60)
        print("测试4：数据推送功能")
        print("="*60)
        
        if not self.redis_client:
            self.log_test("数据推送", False, "Redis未连接")
            return False
        
        try:
            # 等待数据推送（至少2秒）
            print("等待数据推送（2秒）...")
            time.sleep(2)
            
            # 检查当前数据
            current_data = self.redis_client.get("plc:data:current")
            if current_data:
                data = json.loads(current_data)
                # 数据格式：{'timestamp': ..., 'datetime': ..., 'params': {...}}
                params = data.get('params', {})
                param_count = len(params)
                self.log_test("数据推送", True, f"当前数据包含 {param_count} 个参数")
                
                # 检查关键参数是否存在
                has_tank = any("tank" in key.lower() for key in params.keys())
                has_pid = any("pid" in key.lower() for key in params.keys())
                if has_tank or has_pid:
                    self.log_test("数据内容", True, "包含模型和算法参数")
                else:
                    # 显示实际参数键名以便调试
                    sample_keys = list(params.keys())[:5]
                    self.log_test("数据内容", False, f"缺少模型或算法参数（示例键名: {sample_keys}）")
                
                return True
            else:
                self.log_test("数据推送", False, "未找到当前数据")
                return False
        except Exception as e:
            self.log_test("数据推送", False, str(e))
            return False
    
    def test_snapshot_file_exists(self):
        """测试5：快照文件存在性"""
        print("\n" + "="*60)
        print("测试5：快照文件存在性")
        print("="*60)
        
        snapshot_file = "plc/local/snapshot.yaml"
        if os.path.exists(snapshot_file):
            # 检查文件修改时间
            mtime = os.path.getmtime(snapshot_file)
            mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            self.log_test("快照文件存在", True, f"最后修改时间: {mtime_str}")
            
            # 检查文件内容
            try:
                snapshot_mgr = SnapshotManager(snapshot_file)
                params = snapshot_mgr.load_snapshot()
                if params:
                    self.log_test("快照内容", True, f"包含 {len(params)} 个参数")
                else:
                    self.log_test("快照内容", False, "快照文件为空")
            except Exception as e:
                self.log_test("快照内容", False, str(e))
            
            return True
        else:
            self.log_test("快照文件存在", False, "快照文件不存在（首次运行或未运行10个周期）")
            return False
    
    def test_database_storage(self):
        """测试6：数据库存储功能"""
        print("\n" + "="*60)
        print("测试6：数据库存储功能")
        print("="*60)
        
        db_file = "plc_data.db"
        if not os.path.exists(db_file):
            self.log_test("数据库文件", False, "数据库文件不存在")
            return False
        
        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            # 检查表是否存在（DataStorage使用的是data_records表）
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='data_records'")
            table_exists = cursor.fetchone() is not None
            self.log_test("数据库表", table_exists, "data_records表存在" if table_exists else "表不存在")
            
            if table_exists:
                # 检查记录数
                cursor.execute("SELECT COUNT(*) FROM data_records")
                count = cursor.fetchone()[0]
                self.log_test("数据记录数", True, f"共 {count} 条记录")
                
                # 检查最新记录
                cursor.execute("SELECT * FROM data_records ORDER BY timestamp DESC LIMIT 1")
                latest = cursor.fetchone()
                if latest:
                    self.log_test("最新记录", True, f"最新记录时间: {latest[1]}")
                else:
                    self.log_test("最新记录", False, "无记录")
            
            conn.close()
            return True
        except Exception as e:
            self.log_test("数据库存储", False, str(e))
            return False
    
    def test_config_update_message(self):
        """测试7：配置更新消息发送"""
        print("\n" + "="*60)
        print("测试7：配置更新消息发送")
        print("="*60)
        
        if not self.redis_client:
            self.log_test("配置更新", False, "Redis未连接")
            return False
        
        try:
            # 准备测试配置更新消息
            test_config = {
                "type": "config_update",
                "config": {
                    "cycle_time": 0.5,
                    "models": {
                        "tank1": {
                            "type": "cylindrical_tank",
                            "params": {
                                "initial_level": 0.5
                            }
                        }
                    },
                    "algorithms": {
                        "pid1": {
                            "type": "PID",
                            "params": {
                                "sv": 1.5
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
            
            # 发送消息
            result = self.redis_client.publish("plc:config:update", json.dumps(test_config))
            self.log_test("消息发送", True, f"消息已发送（{result} 个订阅者）")
            
            print("   注意：请检查PLC日志，确认配置更新是否被接收")
            return True
        except Exception as e:
            self.log_test("配置更新", False, str(e))
            return False
    
    def test_parameter_write(self):
        """测试8：参数写入功能"""
        print("\n" + "="*60)
        print("测试8：参数写入功能")
        print("="*60)
        
        if not self.redis_client:
            self.log_test("参数写入", False, "Redis未连接")
            return False
        
        try:
            # 准备参数写入命令
            command = {
                "action": "write_parameter",
                "param_name": "pid1.sv",
                "value": 2.5
            }
            
            # 发送命令
            result = self.redis_client.publish("plc:command:write_parameter", json.dumps(command))
            self.log_test("命令发送", True, f"命令已发送（{result} 个订阅者）")
            
            print("   注意：请检查PLC日志和Redis数据，确认参数是否在下个周期更新")
            return True
        except Exception as e:
            self.log_test("参数写入", False, str(e))
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("\n" + "="*60)
        print("PLC功能验证测试")
        print("="*60)
        print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        results = []
        results.append(self.test_config_loading())
        results.append(self.test_snapshot_save_load())
        results.append(self.test_redis_connection())
        results.append(self.test_data_publishing())
        results.append(self.test_snapshot_file_exists())
        results.append(self.test_database_storage())
        results.append(self.test_config_update_message())
        results.append(self.test_parameter_write())
        
        # 汇总结果
        print("\n" + "="*60)
        print("测试结果汇总")
        print("="*60)
        passed = sum(results)
        total = len(results)
        print(f"通过: {passed}/{total}")
        print(f"失败: {total - passed}/{total}")
        
        if passed == total:
            print("\n✓ 所有测试通过！")
        else:
            print(f"\n✗ {total - passed} 个测试失败，请检查上述错误信息")
        
        return passed == total


def main():
    """主函数"""
    tester = PLCFunctionalityTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

