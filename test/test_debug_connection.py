"""
调试脚本：检查连接关系是否正确应用
"""
import redis
import json
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

print("="*60)
print("连接关系检查")
print("="*60)
print("监控关键参数变化...")
print("连接关系：tank1.level -> pid1.pv")
print("按Ctrl+C停止\n")

try:
    for i in range(20):
        current_data = redis_client.get("plc:data:current")
        if current_data:
            data = json.loads(current_data)
            params = data.get('params', {})
            
            # 获取关键参数
            tank1_level = params.get('tank1.level', None)
            pid1_pv = params.get('pid1.pv', None)
            pid1_sv = params.get('pid1.sv', None)
            pid1_mv = params.get('pid1.mv', None)
            valve1_target = params.get('valve1.target_opening', None)
            valve1_current = params.get('valve1.current_opening', None)
            tank1_valve_opening = params.get('tank1.valve_opening', None)
            
            print(f"\n周期 #{i+1}")
            print(f"  tank1.level: {tank1_level}")
            print(f"  pid1.pv: {pid1_pv} {'⚠ 应该等于 tank1.level' if pid1_pv != tank1_level else '✓'}")
            print(f"  pid1.sv: {pid1_sv}")
            print(f"  pid1.mv: {pid1_mv}")
            print(f"  valve1.target_opening: {valve1_target}")
            print(f"  valve1.current_opening: {valve1_current}")
            print(f"  tank1.valve_opening: {tank1_valve_opening}")
            
            # 检查连接关系
            if pid1_pv is not None and tank1_level is not None:
                if abs(pid1_pv - tank1_level) > 0.0001:
                    print(f"  ⚠ 警告：pid1.pv ({pid1_pv}) != tank1.level ({tank1_level})")
                    print(f"     连接关系可能未正确应用！")
            
            if valve1_target is not None and pid1_mv is not None:
                if abs(valve1_target - pid1_mv) > 0.0001:
                    print(f"  ⚠ 警告：valve1.target_opening ({valve1_target}) != pid1.mv ({pid1_mv})")
                    print(f"     连接关系可能未正确应用！")
        
        time.sleep(0.6)  # 等待一个周期多一点
        
except KeyboardInterrupt:
    print("\n\n监控已停止")

