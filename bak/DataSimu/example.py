"""
示例代码：使用数据模拟平台进行PID控制水箱液位模拟
"""
from plc.configuration import Configuration
from plc.data_simulator import DataSimulator
from utils.plotter import DataPlotter

def main():
    # 方式1：从YAML文件加载配置
    config = Configuration(config_file='example_config_pidex.yaml')
    
    # 创建数据模拟器
    simulator = DataSimulator(config)
    
    # 从配置文件获取导出配置
    export_config = config.get_export_config()
    output_file = export_config['output_file']
    tag_names = export_config['tag_names']
    tag_descriptions = export_config['tag_descriptions']
    
    # 运行模拟
    # 如果配置文件中设置了start_datetime和end_datetime，则使用数据生成模式
    # 否则使用duration参数指定持续时间
    print("开始数据模拟...")
    if config.get_start_datetime() and config.get_end_datetime():
        print(f"配置：从 {config.get_start_datetime()} 到 {config.get_end_datetime()}")
        print(f"采样间隔：{config.get_sample_interval()}秒")
    else:
        print("使用默认持续时间")
    
    if tag_names:
        print(f"导出参数：{', '.join(tag_names)}")
    print(f"输出文件：{output_file}")
    
    simulator.run(
        output_file=output_file,
        tag_names=tag_names,
        tag_descriptions=tag_descriptions
    )
    print(f"模拟完成，数据已导出到 {output_file}")
    
    # 绘制数据曲线图
    print("\n开始绘制数据曲线图...")
    plotter = DataPlotter(output_file)
    
    # 方式1：每个位号单独一个子图
    plotter.plot(
        output_file=output_file.replace('.csv', '_plot.png'),
        tag_names=tag_names,
        title="PID控制数据曲线图"
    )
    
    # 方式2：所有曲线在同一张图中（可选）
    # plotter.plot_multiple_in_one(
    #     output_file=output_file.replace('.csv', '_plot_combined.png'),
    #     tag_names=tag_names,
    #     title="PID控制数据曲线图（合并）"
    # )
    
    print(f"曲线图已保存到 {output_file.replace('.csv', '_plot.png')}")

if __name__ == '__main__':
    main()

