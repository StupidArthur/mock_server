"""
DataStorage 历史数据查询性能测试脚本

测试场景：
1. 生成测试数据（模拟大量历史数据）
2. 测试基础查询性能
3. 测试时间范围查询性能
4. 测试采样查询性能
5. 测试统计查询性能
6. 测试最新值查询性能
"""
import yaml
import time
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any
from plc.configuration import Configuration
from plc.data_storage import DataStorage, DataRecord
from sqlalchemy import func
from utils.logger import get_logger

logger = get_logger()


class PerformanceTest:
    """性能测试类"""
    
    def __init__(self, config_file: str = "config/config.yaml", 
                 local_dir: str = "plc/local"):
        """
        初始化性能测试
        
        Args:
            config_file: 系统配置文件路径
            local_dir: 本地配置目录
        """
        # 加载系统配置
        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        # 初始化组态配置
        self.group_config = Configuration(local_dir=local_dir)
        
        # 初始化数据存储模块
        redis_config = self.config.get('redis', {})
        storage_config = self.config.get('storage', {})
        db_path = storage_config.get('db_path', 'plc_data.db')
        
        self.data_storage = DataStorage(
            configuration=self.group_config,
            redis_config=redis_config,
            db_path=db_path
        )
        
        # 测试参数
        self.test_params = [
            'tank1.level',
            'tank1.valve_opening',
            'pid1.pv',
            'pid1.mv',
            'pid1.sv',
            'pid2.pv',
            'pid2.mv',
            'pid2.sv'
        ]
    
    def generate_test_data(self, num_records: int = 10000, 
                          hours: int = 24) -> None:
        """
        生成测试数据
        
        Args:
            num_records: 每个参数生成的记录数
            hours: 数据时间跨度（小时）
        """
        print("=" * 80)
        print("生成测试数据")
        print("=" * 80)
        print(f"参数数量: {len(self.test_params)}")
        print(f"每个参数记录数: {num_records}")
        print(f"总记录数: {len(self.test_params) * num_records:,}")
        print(f"时间跨度: {hours} 小时")
        
        start_time = time.time()
        
        # 计算时间范围
        end_time = datetime.now()
        start_datetime = end_time - timedelta(hours=hours)
        time_span = (end_time - start_datetime).total_seconds()
        time_step = time_span / num_records
        
        records_batch = []
        batch_size = 1000  # 每批插入1000条
        
        for param_name in self.test_params:
            print(f"\n生成参数 {param_name} 的数据...")
            current_time = start_datetime
            
            for i in range(num_records):
                # 生成模拟数据值（根据参数类型）
                if 'level' in param_name:
                    value = 50.0 + random.uniform(-10, 10)  # 液位：40-60
                elif 'valve_opening' in param_name:
                    value = random.uniform(0, 100)  # 阀门开度：0-100
                elif 'pv' in param_name:
                    value = 50.0 + random.uniform(-5, 5)  # PV：45-55
                elif 'mv' in param_name:
                    value = random.uniform(0, 100)  # MV：0-100
                elif 'sv' in param_name:
                    value = 60.0  # SV：固定值60
                else:
                    value = random.uniform(0, 100)
                
                # 解析实例名和参数名
                parts = param_name.split('.', 1)
                instance_name = parts[0]
                param = parts[1]
                
                # 判断类型
                models_config = self.group_config.get_models()
                algorithms_config = self.group_config.get_algorithms()
                
                if instance_name in models_config:
                    param_type = 'model'
                elif instance_name in algorithms_config:
                    param_type = 'algorithm'
                else:
                    param_type = 'unknown'
                
                # 创建记录
                record = DataRecord(
                    timestamp=current_time,
                    param_name=param_name,
                    param_value=float(value),
                    instance_name=instance_name,
                    param_type=param_type
                )
                records_batch.append(record)
                
                # 批量插入
                if len(records_batch) >= batch_size:
                    self.data_storage.session.bulk_save_objects(records_batch)
                    self.data_storage.session.flush()
                    records_batch = []
                
                # 更新时间
                current_time += timedelta(seconds=time_step)
            
            # 插入剩余记录
            if records_batch:
                self.data_storage.session.bulk_save_objects(records_batch)
                self.data_storage.session.flush()
                records_batch = []
        
        # 提交所有数据
        self.data_storage.session.commit()
        
        elapsed_time = time.time() - start_time
        total_records = len(self.test_params) * num_records
        
        print(f"\n✓ 测试数据生成完成")
        print(f"  总记录数: {total_records:,}")
        print(f"  耗时: {elapsed_time:.2f} 秒")
        print(f"  插入速度: {total_records / elapsed_time:.0f} 条/秒")
    
    def test_basic_query(self, param_name: str, limit: int = 1000) -> Dict[str, Any]:
        """
        测试基础查询性能
        
        Args:
            param_name: 参数名
            limit: 返回记录数限制
        
        Returns:
            性能统计字典
        """
        start_time = time.time()
        records = self.data_storage.query_history(
            param_name=param_name,
            limit=limit
        )
        elapsed_time = time.time() - start_time
        
        return {
            'test_name': '基础查询',
            'param_name': param_name,
            'limit': limit,
            'records_count': len(records),
            'elapsed_time': elapsed_time,
            'records_per_second': len(records) / elapsed_time if elapsed_time > 0 else 0
        }
    
    def test_time_range_query(self, param_name: str, hours: int = 1, 
                             limit: int = 1000) -> Dict[str, Any]:
        """
        测试时间范围查询性能
        
        Args:
            param_name: 参数名
            hours: 查询时间范围（小时）
            limit: 返回记录数限制
        
        Returns:
            性能统计字典
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        start = time.time()
        records = self.data_storage.query_history(
            param_name=param_name,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        elapsed_time = time.time() - start
        
        return {
            'test_name': '时间范围查询',
            'param_name': param_name,
            'hours': hours,
            'limit': limit,
            'records_count': len(records),
            'elapsed_time': elapsed_time,
            'records_per_second': len(records) / elapsed_time if elapsed_time > 0 else 0
        }
    
    def test_sampled_query(self, param_name: str, hours: int = 24,
                          sample_interval: float = 60.0, 
                          limit: int = 1000) -> Dict[str, Any]:
        """
        测试采样查询性能
        
        Args:
            param_name: 参数名
            hours: 查询时间范围（小时）
            sample_interval: 采样间隔（秒）
            limit: 返回记录数限制
        
        Returns:
            性能统计字典
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        start = time.time()
        records = self.data_storage.query_history(
            param_name=param_name,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            sample_interval=sample_interval
        )
        elapsed_time = time.time() - start
        
        return {
            'test_name': '采样查询',
            'param_name': param_name,
            'hours': hours,
            'sample_interval': sample_interval,
            'limit': limit,
            'records_count': len(records),
            'elapsed_time': elapsed_time,
            'records_per_second': len(records) / elapsed_time if elapsed_time > 0 else 0
        }
    
    def test_statistics_query(self, param_name: str, hours: int = 24) -> Dict[str, Any]:
        """
        测试统计查询性能
        
        Args:
            param_name: 参数名
            hours: 查询时间范围（小时）
        
        Returns:
            性能统计字典
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        start = time.time()
        stats = self.data_storage.get_statistics(
            param_name=param_name,
            start_time=start_time,
            end_time=end_time
        )
        elapsed_time = time.time() - start
        
        return {
            'test_name': '统计查询',
            'param_name': param_name,
            'hours': hours,
            'count': stats.get('count', 0),
            'elapsed_time': elapsed_time,
            'records_per_second': stats.get('count', 0) / elapsed_time if elapsed_time > 0 else 0
        }
    
    def test_latest_values_query(self, instance_name: str = None) -> Dict[str, Any]:
        """
        测试最新值查询性能
        
        Args:
            instance_name: 实例名（可选）
        
        Returns:
            性能统计字典
        """
        start = time.time()
        latest = self.data_storage.get_latest_values(instance_name=instance_name)
        elapsed_time = time.time() - start
        
        return {
            'test_name': '最新值查询',
            'instance_name': instance_name or 'all',
            'params_count': len(latest),
            'elapsed_time': elapsed_time
        }
    
    def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        total_count = self.data_storage.session.query(func.count(DataRecord.id)).scalar()
        
        # 获取参数统计
        param_stats = self.data_storage.session.query(
            DataRecord.param_name,
            func.count(DataRecord.id).label('count')
        ).group_by(DataRecord.param_name).all()
        
        # 获取时间范围
        min_time = self.data_storage.session.query(func.min(DataRecord.timestamp)).scalar()
        max_time = self.data_storage.session.query(func.max(DataRecord.timestamp)).scalar()
        
        return {
            'total_records': total_count,
            'param_count': len(param_stats),
            'time_range': {
                'start': min_time.isoformat() if min_time else None,
                'end': max_time.isoformat() if max_time else None
            },
            'param_stats': {name: count for name, count in param_stats}
        }
    
    def run_performance_tests(self) -> None:
        """运行所有性能测试"""
        print("\n" + "=" * 80)
        print("开始性能测试")
        print("=" * 80)
        
        # 获取数据库统计信息
        print("\n1. 数据库统计信息")
        print("-" * 80)
        db_stats = self.get_database_stats()
        print(f"总记录数: {db_stats['total_records']:,}")
        print(f"参数数量: {db_stats['param_count']}")
        if db_stats['time_range']['start']:
            print(f"时间范围: {db_stats['time_range']['start']} ~ {db_stats['time_range']['end']}")
        
        # 测试结果列表
        test_results = []
        
        # 2. 基础查询测试
        print("\n2. 基础查询性能测试")
        print("-" * 80)
        for param_name in self.test_params[:3]:  # 只测试前3个参数
            result = self.test_basic_query(param_name, limit=1000)
            test_results.append(result)
            print(f"  参数: {result['param_name']:<20} "
                  f"记录数: {result['records_count']:>6} "
                  f"耗时: {result['elapsed_time']*1000:>6.2f}ms "
                  f"速度: {result['records_per_second']:>8.0f} 条/秒")
        
        # 3. 时间范围查询测试
        print("\n3. 时间范围查询性能测试")
        print("-" * 80)
        for hours in [1, 6, 24]:
            result = self.test_time_range_query(
                param_name=self.test_params[0],
                hours=hours,
                limit=1000
            )
            test_results.append(result)
            print(f"  时间范围: {hours:>2}小时 "
                  f"记录数: {result['records_count']:>6} "
                  f"耗时: {result['elapsed_time']*1000:>6.2f}ms "
                  f"速度: {result['records_per_second']:>8.0f} 条/秒")
        
        # 4. 采样查询测试
        print("\n4. 采样查询性能测试")
        print("-" * 80)
        for sample_interval in [10.0, 60.0, 300.0]:  # 10秒、1分钟、5分钟
            result = self.test_sampled_query(
                param_name=self.test_params[0],
                hours=24,
                sample_interval=sample_interval,
                limit=1000
            )
            test_results.append(result)
            print(f"  采样间隔: {sample_interval:>6.0f}秒 "
                  f"记录数: {result['records_count']:>6} "
                  f"耗时: {result['elapsed_time']*1000:>6.2f}ms "
                  f"速度: {result['records_per_second']:>8.0f} 条/秒")
        
        # 5. 统计查询测试
        print("\n5. 统计查询性能测试")
        print("-" * 80)
        for hours in [1, 6, 24]:
            result = self.test_statistics_query(
                param_name=self.test_params[0],
                hours=hours
            )
            test_results.append(result)
            print(f"  时间范围: {hours:>2}小时 "
                  f"记录数: {result['count']:>8,} "
                  f"耗时: {result['elapsed_time']*1000:>6.2f}ms "
                  f"速度: {result['records_per_second']:>8.0f} 条/秒")
        
        # 6. 最新值查询测试
        print("\n6. 最新值查询性能测试")
        print("-" * 80)
        result = self.test_latest_values_query()
        test_results.append(result)
        print(f"  实例: {result['instance_name']:<20} "
              f"参数数: {result['params_count']:>6} "
              f"耗时: {result['elapsed_time']*1000:>6.2f}ms")
        
        result = self.test_latest_values_query(instance_name="tank1")
        test_results.append(result)
        print(f"  实例: {result['instance_name']:<20} "
              f"参数数: {result['params_count']:>6} "
              f"耗时: {result['elapsed_time']*1000:>6.2f}ms")
        
        # 7. 性能总结
        print("\n" + "=" * 80)
        print("性能测试总结")
        print("=" * 80)
        
        # 按测试类型分组
        test_groups = {}
        for result in test_results:
            test_name = result['test_name']
            if test_name not in test_groups:
                test_groups[test_name] = []
            test_groups[test_name].append(result)
        
        for test_name, results in test_groups.items():
            print(f"\n{test_name}:")
            avg_time = sum(r['elapsed_time'] for r in results) / len(results)
            min_time = min(r['elapsed_time'] for r in results)
            max_time = max(r['elapsed_time'] for r in results)
            print(f"  平均耗时: {avg_time*1000:.2f}ms")
            print(f"  最快耗时: {min_time*1000:.2f}ms")
            print(f"  最慢耗时: {max_time*1000:.2f}ms")
        
        print("\n" + "=" * 80)
        print("性能测试完成")
        print("=" * 80)
    
    def cleanup(self) -> None:
        """清理资源"""
        self.data_storage.close()


def main():
    """主函数"""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description='DataStorage 性能测试')
    parser.add_argument('--config', type=str, default='config/config.yaml',
                       help='系统配置文件路径')
    parser.add_argument('--local-dir', type=str, default='plc/local',
                       help='本地配置目录')
    parser.add_argument('--generate', action='store_true',
                       help='生成测试数据')
    parser.add_argument('--records', type=int, default=10000,
                       help='每个参数生成的记录数（默认10000）')
    parser.add_argument('--hours', type=int, default=24,
                       help='数据时间跨度（小时，默认24）')
    
    args = parser.parse_args()
    
    try:
        print("=" * 80)
        print("DataStorage 性能测试")
        print("=" * 80)
        print(f"配置文件: {args.config}")
        print(f"本地配置目录: {args.local_dir}")
        print(f"生成测试数据: {args.generate}")
        if args.generate:
            print(f"每个参数记录数: {args.records}")
            print(f"时间跨度: {args.hours} 小时")
        print()
        
        # 创建测试实例
        print("初始化测试环境...")
        tester = PerformanceTest(
            config_file=args.config,
            local_dir=args.local_dir
        )
        print("✓ 测试环境初始化完成\n")
        
        # 生成测试数据（如果需要）
        if args.generate:
            tester.generate_test_data(
                num_records=args.records,
                hours=args.hours
            )
        
        # 运行性能测试
        tester.run_performance_tests()
    
    except Exception as e:
        print(f"\n✗ 测试失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        # 清理资源
        try:
            tester.cleanup()
        except:
            pass


if __name__ == '__main__':
    main()

