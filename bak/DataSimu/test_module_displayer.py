"""
测试module_displayer模块的示例代码
"""
from module.cylindrical_tank import CylindricalTank
from module.valve import Valve
from module.module_displayer import ModuleDisplayer

def test_valve():
    """测试阀门模型"""
    print("测试阀门模型...")
    
    # 创建阀门模型
    valve = Valve(
        min_opening=0.0,
        max_opening=100.0,
        step=0.1,
        full_travel_time=20.0
    )
    
    # 创建测试显示器
    displayer = ModuleDisplayer(valve, step=0.1)
    
    # 定义时间节点和目标值（阶跃测试）
    time_points = [0, 10, 30, 50, 70]  # 秒
    target_values = [0, 50, 100, 30, 0]  # 百分比
    
    # 运行阶跃测试并绘制结果
    displayer.step_test(
        time_points=time_points,
        target_values=target_values,
        duration=100.0,
        output_file='valve_step_test.png'
    )
    
    print("阀门模型测试完成，结果已保存到 valve_step_test.png")

def test_tank():
    """测试水箱模型"""
    print("测试水箱模型...")
    
    # 创建水箱模型
    tank = CylindricalTank(
        height=10.0,
        radius=2.0,
        inlet_area=0.01,
        inlet_velocity=5.0,
        outlet_area=0.005,
        initial_level=5.0,
        step=0.1
    )
    
    # 创建测试显示器
    displayer = ModuleDisplayer(tank, step=0.1)
    
    # 定义时间节点和目标值（阶跃测试）
    time_points = [0, 20, 40, 60, 80]  # 秒
    target_values = [0, 50, 100, 50, 0]  # 阀门开度百分比
    
    # 运行阶跃测试并绘制结果
    displayer.step_test(
        time_points=time_points,
        target_values=target_values,
        duration=100.0,
        output_file='tank_step_test.png'
    )
    
    print("水箱模型测试完成，结果已保存到 tank_step_test.png")

if __name__ == '__main__':
    # 测试阀门模型
    test_valve()
    
    # 测试水箱模型
    test_tank()
    
    print("\n所有测试完成！")

