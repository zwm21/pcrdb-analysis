# pcrdb-analysis
基于pcrdb导出的csv文件进行可视化分析

## 功能
- 加载 `player_profile_snapshots_*.csv`（也支持命令行传入文件路径直接加载）
- 战力前100：排行表格，双击单元格自动复制内容
- 图鉴数分布：双击图鉴数查看对应玩家列表
- 骑士等级分布：双击骑士等级查看对应玩家列表
- 深域关卡：五属性平均/最高通关层数统计，双击关卡编号查看对应通关玩家列表
- 弹出的玩家列表支持自选排序（公会id / viewer_id 组合），双击单元格自动复制内容
- 所有表格支持 Ctrl+C 复制选区、"复制表格"按钮一键复制整表

## 打包
运行 `build_exe.bat` 一键打包为 `dist\pcrdb_analyzer.exe`（需要 Python 环境，脚本会自动安装 PyInstaller）。
