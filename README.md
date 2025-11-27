# PLC Mock Server

工业控制+工业流程数据模拟系统

## 功能特性

- **PLC组态模块**: 支持在线/离线配置，管理物理模型实例、算法实例及其关联关系
- **PLC运行模块**: 每500ms执行一个周期，执行控制算法和物理模型计算，将数据推送到Redis
- **PLC通信模块**: OPCUA Server，支持动态节点创建，从Redis读取数据并更新到OPCUA节点
- **PLC数据模块**: SQLite存储，提供历史数据查询和统计接口
- **PLC监控模块**: Web界面，实时和历史数据展示

## 技术栈

- Python 3.13
- OPCUA (asyncua)
- Redis
- SQLite (SQLAlchemy)
- Flask + Flask-SocketIO (Web监控界面)

## 安装

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 配置Redis（确保Redis服务正在运行）

3. 配置系统配置文件 `config/config.yaml`

4. 配置组态文件 `config/example_config.yaml`

## 运行

```bash
python main.py --config config/config.yaml --group-config config/example_config.yaml
```

## 访问

- Web监控界面: http://localhost:5000
- OPCUA Server: opc.tcp://0.0.0.0:18951

## 项目结构

```
mock_server_v1/
├── doc/                    # 文档目录
├── module/                 # 物理模型模块
├── algorithm/              # 控制算法模块
├── plc/                    # PLC相关模块
│   ├── configuration.py   # 组态模块
│   ├── runner.py          # 运行模块
│   ├── communication.py   # 通信模块
│   ├── data_storage.py    # 数据模块
│   └── clock.py           # 时钟模块
├── monitor/                # 监控模块
│   ├── web_server.py      # Web服务器
│   └── templates/         # HTML模板
├── utils/                  # 工具模块
│   └── logger.py          # 日志模块
├── config/                 # 配置文件目录
├── main.py                 # 主程序入口
└── requirements.txt        # 依赖文件
```

