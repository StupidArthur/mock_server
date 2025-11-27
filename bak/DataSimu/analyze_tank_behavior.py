"""
分析水箱模型的行为特性
"""
import math

# 当前参数
height = 10.0
radius = 2.0
inlet_area = 0.01
inlet_velocity = 5.0
outlet_area = 0.005
g = 9.81

# 计算
base_area = math.pi * radius ** 2
max_inlet_flow = inlet_area * inlet_velocity

print("Current parameters analysis:")
print(f"Base area: {base_area:.3f} m2")
print(f"Max inlet flow: {max_inlet_flow:.6f} m3/s")
print()

# Analyze outlet flow at different water levels
print("Outlet flow at different water levels:")
for h in [1, 3, 5, 7, 10]:
    outlet_flow = outlet_area * math.sqrt(2 * g * h)
    print(f"Water level {h}m: outlet flow = {outlet_flow:.6f} m3/s")
print()

# Analyze net flow
print("Net flow at 100% valve opening:")
for h in [1, 3, 5, 7, 10]:
    inlet_flow = max_inlet_flow
    outlet_flow = outlet_area * math.sqrt(2 * g * h)
    net_flow = inlet_flow - outlet_flow
    level_change_rate = net_flow / base_area
    print(f"Water level {h}m: net flow = {net_flow:.6f} m3/s, level change rate = {level_change_rate:.6f} m/s")
print()

# Analysis
print("Problem analysis:")
print("1. Base area is very large (12.57 m2), causing very small level change rate")
print("2. Outlet flow changes with square root of water level, but the change is relatively small")
print("3. When inlet flow is much larger or smaller than outlet flow, net flow is mainly determined by inlet flow")
print()
print("Suggestions to highlight nonlinear characteristics:")
print("- Reduce base area (reduce radius)")
print("- Increase outlet area")
print("- Reduce inlet flow")

