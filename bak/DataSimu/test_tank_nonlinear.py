"""
测试水箱模型的非线性特性
使用调整后的参数以突出非线性行为
"""
from module.cylindrical_tank import CylindricalTank
from module.module_displayer import ModuleDisplayer

def test_tank_nonlinear():
    """测试水箱模型的非线性特性"""
    print("测试水箱模型的非线性特性...")
    print("使用调整后的参数以突出非线性行为")
    print()
    
    # 创建水箱模型 - 使用更能突出非线性特性的参数
    # 减小底面积（减小半径），增大出水口面积，减小入水流量
    tank = CylindricalTank(
        height=10.0,
        radius=0.5,  # 减小半径：从2.0改为0.5，底面积从12.57变为0.785 m²
        inlet_area=0.01,
        inlet_velocity=2.0,  # 减小入水速度：从5.0改为2.0
        outlet_area=0.01,  # 增大出水口面积：从0.005改为0.01
        initial_level=1.0,  # 从较低的水位开始
        step=0.1
    )
    
    print("参数设置:")
    print(f"  半径: 0.5 m (底面积: {3.14159 * 0.5**2:.3f} m²)")
    print(f"  入水速度: 2.0 m/s (最大入水流量: 0.01 * 2.0 = 0.02 m³/s)")
    print(f"  出水口面积: 0.01 m²")
    print(f"  初始水位: 1.0 m")
    print()
    
    # 创建测试显示器
    displayer = ModuleDisplayer(tank, step=0.1)
    
    # 定义时间节点和目标值（阶跃测试）
    # 从低水位开始，给一个较大的阶跃，观察非线性响应
    time_points = [0, 30, 60, 90]  # 秒
    target_values = [0, 100, 50, 0]  # 阀门开度百分比
    
    print("阶跃测试:")
    print("  0秒: 阀门开度 0%")
    print("  30秒: 阀门开度 100% (阶跃)")
    print("  60秒: 阀门开度 50%")
    print("  90秒: 阀门开度 0%")
    print()
    
    # 运行阶跃测试并绘制结果
    displayer.step_test(
        time_points=time_points,
        target_values=target_values,
        duration=120.0,
        output_file='tank_nonlinear_test.png'
    )
    
    print("测试完成，结果已保存到 tank_nonlinear_test.png")
    print()
    print("分析:")
    print("  1. 当阀门突然打开到100%时，入水流量增加")
    print("  2. 水位上升，但上升速度会逐渐减慢（因为出水流量随水位平方根增加）")
    print("  3. 最终会达到平衡点（入水流量 = 出水流量）")
    print("  4. 这种非线性特性在调整后的参数下会更加明显")

if __name__ == '__main__':
    test_tank_nonlinear()

