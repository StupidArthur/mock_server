"""简单的性能测试脚本"""
import sys
import yaml
import time
from datetime import datetime, timedelta
from plc.configuration import Configuration
from plc.data_storage import DataStorage, DataRecord
from sqlalchemy import func

# 强制刷新输出
sys.stdout.reconfigure(encoding='utf-8')

print("=" * 80, flush=True)
print("DataStorage 性能测试", flush=True)
print("=" * 80, flush=True)

try:
    # 加载配置
    print("1. 加载配置...", flush=True)
    with open('config/config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    group_config = Configuration(local_dir='plc/local')
    redis_config = config.get('redis', {})
    db_path = config.get('storage', {}).get('db_path', 'plc_data.db')
    
    print(f"   数据库路径: {db_path}", flush=True)
    
    # 初始化数据存储
    print("2. 初始化数据存储模块...", flush=True)
    data_storage = DataStorage(group_config, redis_config, db_path)
    
    # 获取数据库统计
    print("3. 获取数据库统计信息...", flush=True)
    total_count = data_storage.session.query(func.count(DataRecord.id)).scalar()
    print(f"   总记录数: {total_count:,}", flush=True)
    
    if total_count == 0:
        print("\n   ⚠ 数据库中没有数据，请先运行 --generate 生成测试数据", flush=True)
        data_storage.close()
        sys.exit(0)
    
    # 获取参数列表
    param_names = data_storage.session.query(DataRecord.param_name).distinct().limit(5).all()
    param_names = [p[0] for p in param_names]
    print(f"   测试参数: {param_names[:3]}", flush=True)
    
    # 测试1: 基础查询
    print("\n4. 测试基础查询性能...", flush=True)
    if param_names:
        param_name = param_names[0]
        start = time.time()
        records = data_storage.query_history(param_name=param_name, limit=1000)
        elapsed = time.time() - start
        print(f"   参数: {param_name}", flush=True)
        print(f"   记录数: {len(records)}", flush=True)
        print(f"   耗时: {elapsed*1000:.2f}ms", flush=True)
        print(f"   速度: {len(records)/elapsed:.0f} 条/秒", flush=True)
    
    # 测试2: 时间范围查询
    print("\n5. 测试时间范围查询性能...", flush=True)
    if param_names:
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)
        start = time.time()
        records = data_storage.query_history(
            param_name=param_name,
            start_time=start_time,
            end_time=end_time,
            limit=1000
        )
        elapsed = time.time() - start
        print(f"   时间范围: 1小时", flush=True)
        print(f"   记录数: {len(records)}", flush=True)
        print(f"   耗时: {elapsed*1000:.2f}ms", flush=True)
    
    # 测试3: 统计查询
    print("\n6. 测试统计查询性能...", flush=True)
    if param_names:
        start = time.time()
        stats = data_storage.get_statistics(param_name=param_name)
        elapsed = time.time() - start
        print(f"   参数: {param_name}", flush=True)
        print(f"   记录数: {stats.get('count', 0):,}", flush=True)
        print(f"   耗时: {elapsed*1000:.2f}ms", flush=True)
        if stats.get('count', 0) > 0:
            print(f"   速度: {stats['count']/elapsed:.0f} 条/秒", flush=True)
    
    # 测试4: 最新值查询
    print("\n7. 测试最新值查询性能...", flush=True)
    start = time.time()
    latest = data_storage.get_latest_values()
    elapsed = time.time() - start
    print(f"   参数数量: {len(latest)}", flush=True)
    print(f"   耗时: {elapsed*1000:.2f}ms", flush=True)
    
    print("\n" + "=" * 80, flush=True)
    print("性能测试完成", flush=True)
    print("=" * 80, flush=True)
    
    data_storage.close()
    
except Exception as e:
    print(f"\n✗ 错误: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

