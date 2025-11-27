"""
调试脚本：检查PID算法执行情况
"""
import redis
import json
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

print("="*60)
print("PID算法执行情况检查")
print("="*60)
print("监控PID1的关键参数变化...")
print("按Ctrl+C停止\n")

try:
    last_pv = None
    last_sv = None
    last_mv = None
    last_level = None
    
    for i in range(20):
        current_data = redis_client.get("plc:data:current")
        if current_data:
            data = json.loads(current_data)
            params = data.get('params', {})
            
            # 获取PID1的关键参数
            pv = params.get('pid1.pv', None)
            sv = params.get('pid1.sv', None)
            mv = params.get('pid1.mv', None)
            level = params.get('tank1.LEVEL', None)
            
            # 检查是否有变化
            pv_changed = pv != last_pv if last_pv is not None else False
            sv_changed = sv != last_sv if last_sv is not None else False
            mv_changed = mv != last_mv if last_mv is not None else False
            level_changed = level != last_level if last_level is not None else False
            
            print(f"\n周期 #{i+1}")
            print(f"  pid1.pv: {pv} {'(变化)' if pv_changed else ''}")
            print(f"  pid1.sv: {sv} {'(变化)' if sv_changed else ''}")
            print(f"  pid1.mv: {mv} {'(变化)' if mv_changed else ''}")
            print(f"  tank1.LEVEL: {level} {'(变化)' if level_changed else ''}")
            
            if pv is not None and sv is not None:
                error = sv - pv
                print(f"  误差 (sv-pv): {error:.4f}")
            
            if mv is not None and mv != 0:
                print(f"  ⚠ PID输出不为0，但level未变化，可能存在问题")
            
            last_pv = pv
            last_sv = sv
            last_mv = mv
            last_level = level
        
        time.sleep(0.6)  # 等待一个周期多一点
        
except KeyboardInterrupt:
    print("\n\n监控已停止")

