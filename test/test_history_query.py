"""
历史数据查询测试模块
直接调用data_storage模块，验证历史数据查询功能
"""
import yaml
from datetime import datetime, timedelta
from plc.configuration import Configuration
from plc.data_storage import DataStorage, DataRecord
from sqlalchemy import func
from utils.logger import get_logger

logger = get_logger()


def test_history_query(
    config_file: str = "config/config.yaml",
    group_config_file: str = "config/example_config.yaml",
    param_name: str = "pid1.pv",
    seconds: int = 60,
    sample_interval: float = 1.0
):
    """
    测试历史数据查询
    
    Args:
        config_file: 系统配置文件路径
        group_config_file: 组态配置文件路径
        param_name: 参数名称，如"pid1.pv"
        seconds: 查询过去多少秒的数据
        sample_interval: 采样间隔（秒）
    """
    print("=" * 80)
    print("历史数据查询测试")
    print("=" * 80)
    
    # 加载系统配置
    print(f"\n1. 加载配置文件...")
    print(f"   系统配置: {config_file}")
    print(f"   组态配置: {group_config_file}")
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        print("   ✓ 系统配置加载成功")
    except Exception as e:
        print(f"   ✗ 系统配置加载失败: {e}")
        return
    
    # 初始化组态配置
    try:
        group_config = Configuration(config_file=group_config_file)
        print("   ✓ 组态配置加载成功")
    except Exception as e:
        print(f"   ✗ 组态配置加载失败: {e}")
        return
    
    # 初始化数据存储模块
    print(f"\n2. 初始化数据存储模块...")
    redis_config = config.get('redis', {})
    storage_config = config.get('storage', {})
    db_path = storage_config.get('db_path', 'plc_data.db')
    
    print(f"   Redis配置: {redis_config}")
    print(f"   数据库路径: {db_path}")
    
    try:
        data_storage = DataStorage(group_config, redis_config, db_path)
        print("   ✓ 数据存储模块初始化成功")
    except Exception as e:
        print(f"   ✗ 数据存储模块初始化失败: {e}")
        return
    
    # 查询历史数据
    print(f"\n3. 查询历史数据...")
    print(f"   参数名: {param_name}")
    print(f"   时间段: 过去 {seconds} 秒")
    print(f"   采样间隔: {sample_interval} 秒")
    
    # 计算时间范围
    end_time = datetime.now()
    start_time = end_time - timedelta(seconds=seconds)
    
    print(f"   开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 执行查询
        records = data_storage.query_history(
            param_name=param_name,
            start_time=start_time,
            end_time=end_time,
            limit=1000,
            sample_interval=sample_interval
        )
        
        # 先检查数据库中该参数的总记录数（不限制时间范围）
        print(f"\n   检查数据库中该参数的总记录数...")
        total_count = data_storage.session.query(func.count(DataRecord.id)).filter(
            DataRecord.param_name == param_name
        ).scalar()
        print(f"   数据库中 {param_name} 的总记录数: {total_count}")
        
        # 检查时间范围内的总记录数（不采样）
        records_no_sample = data_storage.query_history(
            param_name=param_name,
            start_time=start_time,
            end_time=end_time,
            limit=10000,
            sample_interval=None  # 不采样
        )
        print(f"   时间范围内（不采样）的记录数: {len(records_no_sample)}")
        
        print(f"\n4. 查询结果（采样后）:")
        print(f"   返回记录数: {len(records)}")
        
        if len(records) == 0:
            print("\n   ⚠ 警告: 没有查询到任何数据！")
            print("\n   可能的原因:")
            print("   1. 数据库中确实没有该参数的数据")
            print("   2. 参数名格式不正确（注意大小写，如 pid1.pv）")
            print("   3. 时间范围内没有数据")
            print("   4. 系统刚启动，还没有存储数据")
            
            # 检查数据库中是否有该参数的数据
            print("\n   检查数据库中是否有该参数的数据...")
            all_records = data_storage.query_history(
                param_name=param_name,
                limit=10
            )
            if len(all_records) > 0:
                print(f"   ✓ 数据库中有该参数的数据，共 {len(all_records)} 条（最近10条）")
                print(f"   最新数据时间: {all_records[0]['timestamp']}")
                print(f"   最新数据值: {all_records[0]['param_value']}")
            else:
                # 检查是否有其他参数的数据
                print("   检查数据库中是否有其他参数的数据...")
                total_count = data_storage.session.query(func.count(DataRecord.id)).scalar()
                print(f"   数据库总记录数: {total_count}")
                
                if total_count > 0:
                    # 查询所有不同的参数名
                    param_names = data_storage.session.query(DataRecord.param_name).distinct().all()
                    param_names = [p[0] for p in param_names]
                    print(f"   数据库中的参数名列表（共 {len(param_names)} 个）:")
                    for pn in sorted(param_names)[:20]:  # 只显示前20个
                        print(f"     - {pn}")
                    if len(param_names) > 20:
                        print(f"     ... 还有 {len(param_names) - 20} 个参数")
        else:
            print("\n   ✓ 查询成功！")
            print(f"\n   数据详情（显示前10条）:")
            print(f"   {'时间':<20} {'参数值':<15} {'实例名':<15} {'类型':<10}")
            print(f"   {'-' * 60}")
            for i, record in enumerate(records[:10]):
                timestamp = record['timestamp']
                value = record['param_value']
                instance = record['instance_name']
                param_type = record['param_type']
                print(f"   {timestamp:<20} {value:<15.4f} {instance:<15} {param_type:<10}")
            
            if len(records) > 10:
                print(f"   ... 还有 {len(records) - 10} 条数据")
            
            # 统计信息
            values = [r['param_value'] for r in records]
            print(f"\n   统计信息:")
            print(f"   最小值: {min(values):.4f}")
            print(f"   最大值: {max(values):.4f}")
            print(f"   平均值: {sum(values) / len(values):.4f}")
        
    except Exception as e:
        print(f"\n   ✗ 查询失败: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 关闭数据库连接
        data_storage.close()
        print(f"\n5. 测试完成，已关闭数据库连接")


if __name__ == '__main__':
    # 测试查询 pid1.pv 在过去60秒，间隔1秒的数据
    test_history_query(
        config_file="config/config.yaml",
        group_config_file="config/example_config.yaml",
        param_name="pid1.pv",
        seconds=60,
        sample_interval=1.0
    )

