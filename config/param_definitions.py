"""
参数定义文件
定义所有模型和算法的参数元数据，用于UI界面自动生成参数编辑表格
"""
from typing import Dict, Any

# 模型参数定义
MODEL_PARAMS: Dict[str, Dict[str, Dict[str, Any]]] = {
    'cylindrical_tank': {
        'height': {
            'type': float,
            'default': 2.0,
            'unit': '米',
            'desc': '水箱高度',
            'min': 0.01,
            'max': 100.0
        },
        'radius': {
            'type': float,
            'default': 0.5,
            'unit': '米',
            'desc': '水箱半径',
            'min': 0.01,
            'max': 10.0
        },
        'inlet_area': {
            'type': float,
            'default': 0.06,
            'unit': '平方米',
            'desc': '入水管面积',
            'min': 0.0,
            'max': 1.0
        },
        'inlet_velocity': {
            'type': float,
            'default': 3.0,
            'unit': '米/秒',
            'desc': '入水口水流速',
            'min': 0.0,
            'max': 100.0
        },
        'outlet_area': {
            'type': float,
            'default': 0.001,
            'unit': '平方米',
            'desc': '出水口面积',
            'min': 0.0,
            'max': 1.0
        },
        'initial_level': {
            'type': float,
            'default': 0.0,
            'unit': '米',
            'desc': '初始水位高度',
            'min': 0.0,
            'max': None  # 动态，取决于height
        },
        'step': {
            'type': float,
            'default': 0.5,
            'unit': '秒',
            'desc': '步进时间',
            'min': 0.01,
            'max': 10.0
        }
    },
    'valve': {
        'min_opening': {
            'type': float,
            'default': 0.0,
            'unit': '%',
            'desc': '最小开度',
            'min': 0.0,
            'max': 100.0
        },
        'max_opening': {
            'type': float,
            'default': 100.0,
            'unit': '%',
            'desc': '最大开度',
            'min': 0.0,
            'max': 100.0
        },
        'step': {
            'type': float,
            'default': 0.5,
            'unit': '秒',
            'desc': '步进时间',
            'min': 0.01,
            'max': 10.0
        },
        'full_travel_time': {
            'type': float,
            'default': 5.0,
            'unit': '秒',
            'desc': '满行程时间',
            'min': 0.1,
            'max': 1000.0
        }
    }
}

# 算法参数定义
ALGORITHM_PARAMS: Dict[str, Dict[str, Dict[str, Any]]] = {
    'PID': {
        'name': {
            'type': str,
            'default': 'PID',
            'unit': '',
            'desc': '算法名称',
            'min': None,
            'max': None
        },
        'kp': {
            'type': float,
            'default': 12.0,
            'unit': '',
            'desc': '比例系数',
            'min': 0.0,
            'max': 1000.0
        },
        'ti': {
            'type': float,
            'default': 30.0,
            'unit': '秒',
            'desc': '积分时间',
            'min': 0.0,
            'max': 10000.0
        },
        'td': {
            'type': float,
            'default': 0.15,
            'unit': '秒',
            'desc': '微分时间',
            'min': 0.0,
            'max': 1000.0
        },
        'pv': {
            'type': float,
            'default': 0.0,
            'unit': '',
            'desc': '过程变量初始值',
            'min': None,
            'max': None
        },
        'sv': {
            'type': float,
            'default': 0.0,
            'unit': '',
            'desc': '设定值',
            'min': None,
            'max': None
        },
        'mv': {
            'type': float,
            'default': 0.0,
            'unit': '',
            'desc': '输出值初始值',
            'min': None,
            'max': None
        },
        'h': {
            'type': float,
            'default': 100.0,
            'unit': '',
            'desc': '输出上限',
            'min': None,
            'max': None
        },
        'l': {
            'type': float,
            'default': 0.0,
            'unit': '',
            'desc': '输出下限',
            'min': None,
            'max': None
        },
        'sample_time': {
            'type': float,
            'default': 0.5,
            'unit': '秒',
            'desc': '采样周期（通常等于cycle_time）',
            'min': 0.01,
            'max': 10.0
        }
    }
}

# 模型可输出参数列表（用于连接关系）
MODEL_OUTPUT_PARAMS: Dict[str, list] = {
    'cylindrical_tank': ['level'],
    'valve': ['current_opening', 'target_opening']
}

# 模型可输入参数列表
MODEL_INPUT_PARAMS: Dict[str, list] = {
    'cylindrical_tank': ['valve_opening'],
    'valve': ['target_opening']
}

# 算法可输出参数列表
ALGORITHM_OUTPUT_PARAMS: Dict[str, list] = {
    'PID': ['mv', 'mode']
}

# 算法可输入参数列表
ALGORITHM_INPUT_PARAMS: Dict[str, list] = {
    'PID': ['pv', 'sv']
}

# 算法可配置参数列表（运行时可能修改）
ALGORITHM_CONFIG_PARAMS: Dict[str, list] = {
    'PID': ['kp', 'ti', 'td']
}


def get_model_param_def(model_type: str, param_name: str) -> Dict[str, Any]:
    """获取模型参数定义"""
    return MODEL_PARAMS.get(model_type, {}).get(param_name, {})


def get_algorithm_param_def(algorithm_type: str, param_name: str) -> Dict[str, Any]:
    """获取算法参数定义"""
    return ALGORITHM_PARAMS.get(algorithm_type, {}).get(param_name, {})


def get_model_output_params(model_type: str) -> list:
    """获取模型可输出参数列表"""
    return MODEL_OUTPUT_PARAMS.get(model_type, [])


def get_model_input_params(model_type: str) -> list:
    """获取模型可输入参数列表"""
    return MODEL_INPUT_PARAMS.get(model_type, [])


def get_algorithm_output_params(algorithm_type: str) -> list:
    """获取算法可输出参数列表"""
    return ALGORITHM_OUTPUT_PARAMS.get(algorithm_type, [])


def get_algorithm_input_params(algorithm_type: str) -> list:
    """获取算法可输入参数列表"""
    return ALGORITHM_INPUT_PARAMS.get(algorithm_type, [])

