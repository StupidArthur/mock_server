#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试config/configuration与plc/plc_configuration的交互
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.configuration import ConfigurationManager
from plc.plc_configuration import Configuration

def main():
    print("=" * 60)
    print("config/configuration 与 PLC组态交互测试")
    print("=" * 60)
    
    # 1. 初始化模块
    print("\n1. 初始化模块...")
    config_manager = ConfigurationManager(
        config_dir="config",
        local_dir="plc/local"
    )
    plc_config = Configuration(local_dir="plc/local")
    print("✓ 模块初始化完成")
    
    # 2. 获取PLC运行配置
    print("\n2. 获取PLC当前运行的配置...")
    try:
        plc_running_config = config_manager.get_plc_running_config(plc_config)
        print(f"✓ 获取成功")
        print(f"  - 运行周期: {plc_running_config.get('cycle_time', 'N/A')}")
        print(f"  - 模型数量: {len(plc_running_config.get('models', {}))}")
        print(f"  - 算法数量: {len(plc_running_config.get('algorithms', {}))}")
        print(f"  - 连接数量: {len(plc_running_config.get('connections', []))}")
        
        # 打印模型和算法名称
        if plc_running_config.get('models'):
            print(f"  - 模型列表: {list(plc_running_config['models'].keys())}")
        if plc_running_config.get('algorithms'):
            print(f"  - 算法列表: {list(plc_running_config['algorithms'].keys())}")
    except Exception as e:
        print(f"✗ 获取失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 3. 加载配置文件
    print("\n3. 加载配置文件...")
    try:
        file_config = config_manager.load_config_file("config/example_config.yaml")
        print(f"✓ 加载成功: example_config.yaml")
        print(f"  - 模型数量: {len(file_config.get('models', {}))}")
        print(f"  - 算法数量: {len(file_config.get('algorithms', {}))}")
        print(f"  - 连接数量: {len(file_config.get('connections', []))}")
        
        # 打印模型和算法名称
        if file_config.get('models'):
            print(f"  - 模型列表: {list(file_config['models'].keys())}")
        if file_config.get('algorithms'):
            print(f"  - 算法列表: {list(file_config['algorithms'].keys())}")
    except Exception as e:
        print(f"✗ 加载失败: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 4. 分析差异
    print("\n4. 分析配置差异...")
    diff = config_manager.analyze_config_diff(file_config, plc_running_config)
    
    print("\n差异详情:")
    has_diff = False
    if diff['added_models']:
        print(f"  ✓ 新增模型: {list(diff['added_models'].keys())}")
        has_diff = True
    if diff['removed_models']:
        print(f"  ✗ 删除模型: {list(diff['removed_models'].keys())}")
        has_diff = True
    if diff['modified_models']:
        print(f"  ~ 修改模型: {list(diff['modified_models'].keys())}")
        has_diff = True
    if diff['added_algorithms']:
        print(f"  ✓ 新增算法: {list(diff['added_algorithms'].keys())}")
        has_diff = True
    if diff['removed_algorithms']:
        print(f"  ✗ 删除算法: {list(diff['removed_algorithms'].keys())}")
        has_diff = True
    if diff['modified_algorithms']:
        print(f"  ~ 修改算法: {list(diff['modified_algorithms'].keys())}")
        has_diff = True
    if diff['added_connections']:
        print(f"  ✓ 新增连接: {len(diff['added_connections'])}个")
        for conn in diff['added_connections'][:5]:  # 只显示前5个
            print(f"    - {conn.get('from')} -> {conn.get('to')}")
        if len(diff['added_connections']) > 5:
            print(f"    ... 还有 {len(diff['added_connections']) - 5} 个")
        has_diff = True
    if diff['removed_connections']:
        print(f"  ✗ 删除连接: {len(diff['removed_connections'])}个")
        for conn in diff['removed_connections'][:5]:  # 只显示前5个
            print(f"    - {conn.get('from')} -> {conn.get('to')}")
        if len(diff['removed_connections']) > 5:
            print(f"    ... 还有 {len(diff['removed_connections']) - 5} 个")
        has_diff = True
    if diff['cycle_time_changed']:
        print(f"  ~ cycle_time变更: {diff['cycle_time']['from']} -> {diff['cycle_time']['to']}")
        has_diff = True
    
    if not has_diff:
        print("  ✓ 配置一致，无差异")
    
    # 5. 演示如何更新（不实际执行）
    print("\n5. 更新配置到PLC的方法:")
    print("   # 方法1: 使用sync_config_to_plc（推荐）")
    print("   success, diff = config_manager.sync_config_to_plc(")
    print("       config_file='config/example_config.yaml',")
    print("       plc_configuration=plc_config,")
    print("       save_to_local=True")
    print("   )")
    print()
    print("   # 方法2: 分步执行")
    print("   config = config_manager.load_config_file('config/example_config.yaml')")
    print("   success = config_manager.update_config_to_plc(plc_config, config)")
    print("   config_manager.save_config_to_local(config)")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == '__main__':
    main()

