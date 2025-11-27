"""
PLC运行时监控脚本
实时监控PLC运行状态和数据更新
"""
import redis
import json
import time
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))


class PLCRuntimeMonitor:
    """PLC运行时监控器"""
    
    def __init__(self):
        try:
            self.redis_client = redis.Redis(
                host='localhost',
                port=6379,
                decode_responses=True
            )
            self.redis_client.ping()
            print("✓ Redis连接成功")
        except Exception as e:
            print(f"✗ Redis连接失败: {e}")
            sys.exit(1)
    
    def monitor_current_data(self, interval: float = 1.0, duration: int = 30):
        """
        监控当前数据
        
        Args:
            interval: 更新间隔（秒）
            duration: 监控时长（秒），0表示无限监控
        """
        print("\n" + "="*60)
        print("监控当前数据（按Ctrl+C停止）")
        print("="*60)
        
        start_time = time.time()
        count = 0
        
        try:
            while True:
                current_data = self.redis_client.get("plc:data:current")
                if current_data:
                    data = json.loads(current_data)
                    # 数据格式：{'timestamp': ..., 'datetime': ..., 'params': {...}}
                    params = data.get('params', {})
                    count += 1
                    
                    # 显示关键参数
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 更新 #{count}")
                    print("-" * 60)
                    
                    # 显示PID参数
                    for key in sorted(params.keys()):
                        if 'pid' in key.lower():
                            print(f"  {key}: {params[key]}")
                    
                    # 显示模型参数
                    for key in sorted(params.keys()):
                        if 'tank' in key.lower() or 'valve' in key.lower():
                            print(f"  {key}: {params[key]}")
                
                if duration > 0 and (time.time() - start_time) >= duration:
                    break
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n监控已停止")
    
    def check_snapshot_status(self):
        """检查快照状态"""
        import os
        
        print("\n" + "="*60)
        print("快照状态检查")
        print("="*60)
        
        snapshot_file = "plc/local/snapshot.yaml"
        if os.path.exists(snapshot_file):
            mtime = os.path.getmtime(snapshot_file)
            mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            file_size = os.path.getsize(snapshot_file)
            
            print(f"✓ 快照文件存在")
            print(f"  文件路径: {snapshot_file}")
            print(f"  最后修改: {mtime_str}")
            print(f"  文件大小: {file_size} bytes")
            
            # 计算距离现在的时间
            age = time.time() - mtime
            if age < 60:
                print(f"  更新时间: {age:.1f} 秒前")
            elif age < 3600:
                print(f"  更新时间: {age/60:.1f} 分钟前")
            else:
                print(f"  更新时间: {age/3600:.1f} 小时前")
        else:
            print("✗ 快照文件不存在")
            print("  说明: 首次运行或未运行10个周期")
    
    def check_redis_status(self):
        """检查Redis状态"""
        print("\n" + "="*60)
        print("Redis状态检查")
        print("="*60)
        
        try:
            # 检查当前数据
            current_data = self.redis_client.get("plc:data:current")
            if current_data:
                data = json.loads(current_data)
                # 数据格式：{'timestamp': ..., 'datetime': ..., 'params': {...}}
                params = data.get('params', {})
                print(f"✓ 当前数据存在")
                print(f"  参数数量: {len(params)}")
                print(f"  数据大小: {len(current_data)} bytes")
                if 'datetime' in data:
                    print(f"  时间戳: {data['datetime']}")
            else:
                print("✗ 当前数据不存在")
            
            # 检查历史数据
            history_len = self.redis_client.llen("plc:data:history")
            print(f"✓ 历史数据列表长度: {history_len}")
            
        except Exception as e:
            print(f"✗ 检查失败: {e}")
    
    def monitor_interactive(self):
        """交互式监控"""
        print("\n" + "="*60)
        print("PLC运行时监控")
        print("="*60)
        print("1. 监控当前数据")
        print("2. 检查快照状态")
        print("3. 检查Redis状态")
        print("4. 退出")
        
        while True:
            try:
                choice = input("\n请选择 (1-4): ").strip()
                
                if choice == '1':
                    duration = input("监控时长（秒，0=无限）: ").strip()
                    duration = int(duration) if duration else 30
                    self.monitor_current_data(duration=duration)
                elif choice == '2':
                    self.check_snapshot_status()
                elif choice == '3':
                    self.check_redis_status()
                elif choice == '4':
                    print("退出监控")
                    break
                else:
                    print("无效选择，请重新输入")
            except KeyboardInterrupt:
                print("\n\n退出监控")
                break
            except Exception as e:
                print(f"错误: {e}")


def main():
    """主函数"""
    monitor = PLCRuntimeMonitor()
    monitor.monitor_interactive()


if __name__ == '__main__':
    main()

