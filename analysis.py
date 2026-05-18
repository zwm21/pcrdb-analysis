import sys
import ast
import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QFileDialog,
    QMessageBox, QStatusBar
)
from PyQt5.QtCore import Qt

class DataAnalyzer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("玩家数据可视化分析")
        self.resize(900, 650)
        self.df = None

        # 主界面布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 顶部文件选择区域
        top_layout = QHBoxLayout()
        self.btn_select = QPushButton("选择 CSV 文件并分析")
        self.btn_select.clicked.connect(self.select_file)
        self.label_file = QLabel("未选择文件")
        self.label_file.setStyleSheet("color: gray;")
        top_layout.addWidget(self.btn_select)
        top_layout.addWidget(self.label_file)
        top_layout.addStretch()
        main_layout.addLayout(top_layout)

        # 主体选项卡
        self.main_tab = QTabWidget()
        main_layout.addWidget(self.main_tab)

        # 为四个分析创建占位页面
        self.tab_power = QWidget()
        self.tab_unit = QWidget()
        self.tab_rank = QWidget()
        self.tab_talent = QWidget()
        self.main_tab.addTab(self.tab_power, "战力前100")
        self.main_tab.addTab(self.tab_unit, "图鉴数分布")
        self.main_tab.addTab(self.tab_rank, "骑士等级分布")
        self.main_tab.addTab(self.tab_talent, "深域关卡")

        # 状态栏
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)

    def select_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择 player_profile_snapshots_*.csv",
            filter="CSV 文件 (*.csv);;所有文件 (*.*)"
        )
        if not filepath:
            return
        self.label_file.setText(filepath)
        try:
            self.statusBar.showMessage("正在加载数据...")
            self.df = self.load_data(filepath)
            self.statusBar.showMessage(f"加载完成，共 {len(self.df)} 条记录")
            self.create_all_tables()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"数据加载失败：{str(e)}")
            self.statusBar.showMessage("加载失败")

    def load_data(self, filepath):
        df = pd.read_csv(filepath)
        df.columns = df.columns.str.strip()

        # 解析深域数据
        def parse_talent(x):
            if isinstance(x, str):
                try:
                    return ast.literal_eval(x)
                except:
                    return [0,0,0,0,0]
            return [0,0,0,0,0]
        talent_list = df['talent_quest_clear'].apply(parse_talent)
        talent_df = pd.DataFrame(talent_list.tolist(), columns=['火', '水', '风', '光', '暗'])
        df = pd.concat([df, talent_df], axis=1)
        return df

    def create_all_tables(self):
        if self.df is None:
            return
        # 战力前100
        self.build_power_table(self.df)
        # 图鉴数前10
        self.build_unit_table(self.df)
        # 骑士等级前10
        self.build_rank_table(self.df)
        # 深域5属性
        self.build_talent_tables(self.df)

    def build_power_table(self, df):
        # 取战力前100，按战力降序
        top100 = df.nlargest(100, 'total_power')[['total_power', 'user_name']]
        top100 = top100.sort_values('total_power', ascending=False)
        self.populate_tab(self.tab_power, top100,
                          columns=['战力', '玩家昵称'],
                          col_keys=['total_power', 'user_name'])

    def build_unit_table(self, df):
        # 图鉴数分布：取前10个数值（按图鉴数降序）
        unit_counts = df['unit_num'].value_counts().sort_index(ascending=False)
        top10 = unit_counts.head(10).reset_index()
        top10.columns = ['unit_num', 'count']
        top10 = top10.sort_values('unit_num', ascending=False)
        self.populate_tab(self.tab_unit, top10,
                          columns=['图鉴数', '玩家数量'],
                          col_keys=['unit_num', 'count'])

    def build_rank_table(self, df):
        # 骑士等级分布：取前10个等级（按等级降序）
        rank_counts = df['princess_knight_rank'].value_counts().sort_index(ascending=False)
        top10 = rank_counts.head(10).reset_index()
        top10.columns = ['rank', 'count']
        top10 = top10.sort_values('rank', ascending=False)
        self.populate_tab(self.tab_rank, top10,
                          columns=['骑士等级', '玩家数量'],
                          col_keys=['rank', 'count'])

    def build_talent_tables(self, df):
        # 清除深域选项卡原有内容，重新构建
        layout = self.tab_talent.layout()
        if layout is None:
            layout = QVBoxLayout(self.tab_talent)
        else:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        # 显示平均进度与最难属性
        talents = ['火', '水', '风', '光', '暗']
        avg = {attr: df[attr].mean() for attr in talents}
        hardest = min(avg, key=avg.get)
        hardest_avg = avg[hardest]

        info_text = "各属性平均通关层数：\n"
        for attr in talents:
            info_text += f"  {attr}：{avg[attr]:.2f}\n"
        info_text += f"\n最难通关属性：【{hardest}】（平均层数 {hardest_avg:.2f}）"
        lbl_info = QLabel(info_text)
        lbl_info.setStyleSheet("font-size: 10pt; margin: 10px;")
        layout.addWidget(lbl_info)

        # 子选项卡：5个属性
        sub_tab = QTabWidget()
        for attr in talents:
            counts = df[attr].value_counts().sort_index(ascending=False)  # 关卡编号降序
            counts = counts.reset_index()
            counts.columns = ['关卡编号', '通关人数']
            # 确保降序
            counts = counts.sort_values('关卡编号', ascending=False)

            table = self.create_table(counts,
                                      columns=['关卡编号', '通关人数'],
                                      col_keys=['关卡编号', '通关人数'])
            sub_tab.addTab(table, f"{attr}属性")
        layout.addWidget(sub_tab)

    def populate_tab(self, tab_widget, df, columns, col_keys):
        """在给定tab上创建表格布局，替换原有内容"""
        layout = tab_widget.layout()
        if layout is None:
            layout = QVBoxLayout(tab_widget)
        else:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        table = self.create_table(df, columns, col_keys)
        layout.addWidget(table)

    def create_table(self, df, columns, col_keys):
        """根据DataFrame创建一个QTableWidget并返回"""
        rows, cols = df.shape[0], len(columns)
        table = QTableWidget(rows, cols)
        table.setHorizontalHeaderLabels(columns)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)

        for i, row in df.iterrows():
            for j, key in enumerate(col_keys):
                value = row[key]
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(i, j, item)

        return table

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DataAnalyzer()
    window.show()
    sys.exit(app.exec_())