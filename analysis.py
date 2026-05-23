import sys
import ast
import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QFileDialog,
    QMessageBox, QStatusBar, QAbstractItemView, QMenu, QAction, QDialog
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence

# ---------- 支持复制功能的表格类 ----------
class CopyableTable(QTableWidget):
    def keyPressEvent(self, event):
        # Ctrl+C 复制选中区域
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_C:
            self.copy_selection()
        else:
            super().keyPressEvent(event)

    def copy_selection(self):
        """复制选中单元格，用制表符分隔列，换行分隔行"""
        selected = self.selectedRanges()
        if not selected:
            return

        # 获取选中范围的最小/最大行列
        rows = set()
        cols = set()
        for r in selected:
            for row in range(r.topRow(), r.bottomRow() + 1):
                for col in range(r.leftColumn(), r.rightColumn() + 1):
                    rows.add(row)
                    cols.add(col)
        rows = sorted(rows)
        cols = sorted(cols)

        text_lines = []
        for row in rows:
            line_items = []
            for col in cols:
                item = self.item(row, col)
                line_items.append(item.text() if item else "")
            text_lines.append("\t".join(line_items))
        clipboard_text = "\n".join(text_lines)

        QApplication.clipboard().setText(clipboard_text)

    def copy_all(self):
        """复制整个表格（包括表头）"""
        header = []
        for c in range(self.columnCount()):
            header_item = self.horizontalHeaderItem(c)
            header.append(header_item.text() if header_item else "")

        body_lines = []
        for r in range(self.rowCount()):
            row_items = []
            for c in range(self.columnCount()):
                item = self.item(r, c)
                row_items.append(item.text() if item else "")
            body_lines.append("\t".join(row_items))

        full_text = "\t".join(header) + "\n" + "\n".join(body_lines)
        QApplication.clipboard().setText(full_text)

# ---------- 主窗口 ----------
class DataAnalyzer(QMainWindow):
    def __init__(self, auto_file=None):
        super().__init__()
        self.setWindowTitle("玩家数据可视化分析")
        self.resize(950, 680)
        self.df = None

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # 顶部文件选择
        top_layout = QHBoxLayout()
        self.btn_select = QPushButton("选择 CSV 文件并分析")
        self.btn_select.clicked.connect(self.select_file)
        self.label_file = QLabel("未选择文件")
        self.label_file.setStyleSheet("color: gray;")
        top_layout.addWidget(self.btn_select)
        top_layout.addWidget(self.label_file)
        top_layout.addStretch()
        main_layout.addLayout(top_layout)

        # 主选项卡
        self.main_tab = QTabWidget()
        main_layout.addWidget(self.main_tab)

        # 预留四个页面
        self.tab_power = QWidget()
        self.tab_unit = QWidget()
        self.tab_rank = QWidget()
        self.tab_talent = QWidget()
        self.main_tab.addTab(self.tab_power, "战力前100")
        self.main_tab.addTab(self.tab_unit, "图鉴数分布")
        self.main_tab.addTab(self.tab_rank, "骑士等级分布")
        self.main_tab.addTab(self.tab_talent, "深域关卡")

        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)

        if auto_file:
            self.load_csv_file(auto_file)

    # ---------- 数据加载 ----------
    def load_csv_file(self, filepath):
        """加载指定的 CSV 文件并刷新所有表格"""
        self.label_file.setText(filepath)
        try:
            self.statusBar.showMessage("正在加载数据...")
            self.df = self.load_data(filepath)
            self.statusBar.showMessage(f"加载完成，共 {len(self.df)} 条记录")
            self.create_all_tables()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"数据加载失败：{str(e)}")
            self.statusBar.showMessage("加载失败")

    def select_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择 player_profile_snapshots_*.csv",
            filter="CSV 文件 (*.csv);;所有文件 (*.*)"
        )
        if not filepath:
            return
        self.load_csv_file(filepath)

    def load_data(self, filepath):
        df = pd.read_csv(filepath)
        df.columns = df.columns.str.strip()

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

    # ---------- 创建所有表格 ----------
    def create_all_tables(self):
        if self.df is None:
            return
        self.build_power_table(self.df)
        self.build_unit_table(self.df)
        self.build_rank_table(self.df)
        self.build_talent_tables(self.df)

    # ---------- 带复制按钮的表格生成器 ----------
    def create_copyable_table(self, data_df, columns, col_keys):
        """
        创建一个包含“复制表格”按钮和可复制表格的 QWidget
        data_df: pandas DataFrame
        columns: 表头文字列表
        col_keys: 对应 data_df 的列名
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # 按钮栏
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_copy = QPushButton("复制表格")
        btn_layout.addWidget(btn_copy)
        layout.addLayout(btn_layout)

        # 表格
        table = CopyableTable(data_df.shape[0], len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)

        for i, row in data_df.iterrows():
            for j, key in enumerate(col_keys):
                value = row[key]
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                table.setItem(i, j, item)

        # 连接复制按钮
        btn_copy.clicked.connect(table.copy_all)

        layout.addWidget(table)
        return widget

    def populate_tab(self, tab_widget, data_df, columns, col_keys):
        """替换指定选项卡内的内容为带复制功能的表格"""
        layout = tab_widget.layout()
        if layout is None:
            layout = QVBoxLayout(tab_widget)
        else:
            # 清除旧内容
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        table_widget = self.create_copyable_table(data_df, columns, col_keys)
        layout.addWidget(table_widget)

    # ---------- 战力前100 ----------
    def build_power_table(self, df):
        # 强制转换数值，去除无效
        top100 = df[['total_power', 'user_name', 'viewer_id']].copy()
        top100['total_power'] = pd.to_numeric(top100['total_power'], errors='coerce')
        top100 = top100.dropna(subset=['total_power'])
        top100 = top100.sort_values('total_power', ascending=False).head(100)
        top100 = top100.reset_index(drop=True)
        # 添加排名列 (1开始)
        top100.index += 1
        top100.reset_index(inplace=True)
        top100.columns = ['排名', 'total_power', 'user_name', 'viewer_id']
        top100 = top100.rename(columns={'total_power': '战力', 'user_name': '玩家昵称', 'viewer_id': '玩家id'})

        self.populate_tab(self.tab_power, top100,
                          columns=['排名', '战力', '玩家昵称', '玩家id'],
                          col_keys=['排名', '战力', '玩家昵称', '玩家id'])

    # ---------- 图鉴数分布 ----------
    def build_unit_table(self, df):
        unit_counts = df['unit_num'].value_counts().sort_index(ascending=False)
        unit_df = unit_counts.reset_index()
        unit_df.columns = ['unit_num', 'count']
        unit_df = unit_df.sort_values('unit_num', ascending=False)

        self.populate_tab(self.tab_unit, unit_df,
                          columns=['图鉴数', '玩家数量'],
                          col_keys=['unit_num', 'count'])

        # 在表格上方插入提示文字
        hint = QLabel("双击图鉴数可查看对应玩家列表")
        hint.setStyleSheet("color: #666; font-size: 9pt; margin: 4px;")
        self.tab_unit.layout().insertWidget(0, hint)

        # 获取表格并连接双击事件
        table_widget = self.tab_unit.findChild(QWidget)
        if table_widget:
            tbl = table_widget.findChild(CopyableTable)
            if tbl:
                tbl.cellDoubleClicked.connect(self.show_unit_players)

    # ---------- 骑士等级分布 ----------
    def build_rank_table(self, df):
        rank_counts = df['princess_knight_rank'].value_counts().sort_index(ascending=False)
        rank_df = rank_counts.reset_index()
        rank_df.columns = ['rank', 'count']
        rank_df = rank_df.sort_values('rank', ascending=False)

        self.populate_tab(self.tab_rank, rank_df,
                          columns=['骑士等级', '玩家数量'],
                          col_keys=['rank', 'count'])

        # 在表格上方插入提示文字
        hint = QLabel("双击骑士等级可查看对应玩家列表")
        hint.setStyleSheet("color: #666; font-size: 9pt; margin: 4px;")
        self.tab_rank.layout().insertWidget(0, hint)

        # 获取表格并连接双击事件
        table_widget = self.tab_rank.findChild(QWidget)
        if table_widget:
            tbl = table_widget.findChild(CopyableTable)
            if tbl:
                tbl.cellDoubleClicked.connect(self.show_rank_players)

    def show_rank_players(self, row, _col):
        """双击骑士等级行时，弹窗显示该等级下所有玩家"""
        tbl = self.sender()
        if not isinstance(tbl, QTableWidget):
            return
        rank_item = tbl.item(row, 0)
        if not rank_item:
            return
        rank = int(rank_item.text())
        filtered = self.df[self.df['princess_knight_rank'] == rank][['viewer_id', 'user_name', 'join_clan_name']]
        filtered = filtered.sort_values('viewer_id', ascending=True)
        filtered = filtered.reset_index(drop=True)

        # 弹窗
        dlg = QDialog(self)
        dlg.setWindowTitle(f"骑士等级 {rank} — 玩家列表（共 {len(filtered)} 人）")
        dlg.resize(700, 500)
        layout = QVBoxLayout(dlg)

        tbl2 = CopyableTable(len(filtered), 3)
        tbl2.setHorizontalHeaderLabels(['玩家id', '玩家昵称', '公会名称'])
        tbl2.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl2.verticalHeader().setVisible(False)
        tbl2.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl2.setAlternatingRowColors(True)

        tbl2.cellDoubleClicked.connect(lambda r, c: None)  # 不响应双击

        for i, (_, player) in enumerate(filtered.iterrows()):
            for j, key in enumerate(['viewer_id', 'user_name', 'join_clan_name']):
                value = player[key]
                item = QTableWidgetItem(str(value) if pd.notna(value) else '')
                item.setTextAlignment(Qt.AlignCenter)
                tbl2.setItem(i, j, item)

        layout.addWidget(tbl2)
        dlg.exec_()

    def show_unit_players(self, row, _col):
        """双击图鉴数行时，弹窗显示该图鉴数下所有玩家"""
        tbl = self.sender()
        if not isinstance(tbl, QTableWidget):
            return
        unit_item = tbl.item(row, 0)
        if not unit_item:
            return
        unit_num = int(unit_item.text())
        filtered = self.df[self.df['unit_num'] == unit_num][['viewer_id', 'user_name', 'join_clan_name']]
        filtered = filtered.sort_values('viewer_id', ascending=True)
        filtered = filtered.reset_index(drop=True)

        # 弹窗
        dlg = QDialog(self)
        dlg.setWindowTitle(f"图鉴数 {unit_num} — 玩家列表（共 {len(filtered)} 人）")
        dlg.resize(700, 500)
        layout = QVBoxLayout(dlg)

        tbl2 = CopyableTable(len(filtered), 3)
        tbl2.setHorizontalHeaderLabels(['玩家id', '玩家昵称', '公会名称'])
        tbl2.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl2.verticalHeader().setVisible(False)
        tbl2.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl2.setAlternatingRowColors(True)

        for i, (_, player) in enumerate(filtered.iterrows()):
            for j, key in enumerate(['viewer_id', 'user_name', 'join_clan_name']):
                value = player[key]
                item = QTableWidgetItem(str(value) if pd.notna(value) else '')
                item.setTextAlignment(Qt.AlignCenter)
                tbl2.setItem(i, j, item)

        layout.addWidget(tbl2)
        dlg.exec_()

    # ---------- 深域关卡 ----------
    def build_talent_tables(self, df):
        layout = self.tab_talent.layout()
        if layout is None:
            layout = QVBoxLayout(self.tab_talent)
        else:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        talents = ['火', '水', '风', '光', '暗']
        avg = {attr: df[attr].mean() for attr in talents}
        hardest = min(avg, key=avg.get)
        hardest_avg = avg[hardest]

        # 基础信息文本
        info_text = "各属性平均通关层数：\n"
        for attr in talents:
            info_text += f"  {attr}：{avg[attr]:.2f}\n"
        info_text += f"\n最难通关属性：【{hardest}】（平均层数 {hardest_avg:.2f}）\n"

        # 追加各属性最高关卡及通关人数
        info_text += "\n各属性最高关卡及通关人数：\n"
        for attr in talents:
            max_level = df[attr].max()
            count_max = (df[attr] == max_level).sum()
            info_text += f"  {attr}：最高关卡 {max_level}，通关人数 {count_max}\n"

        lbl_info = QLabel(info_text)
        lbl_info.setStyleSheet("font-size: 10pt; margin: 10px;")
        layout.addWidget(lbl_info)

        # 子选项卡：5个属性表格
        sub_tab = QTabWidget()
        for attr in talents:
            counts = df[attr].value_counts().sort_index(ascending=False)
            counts = counts.reset_index()
            counts.columns = ['关卡编号', '通关人数']
            counts = counts.sort_values('关卡编号', ascending=False)

            table_widget = self.create_copyable_table(
                counts,
                columns=['关卡编号', '通关人数'],
                col_keys=['关卡编号', '通关人数']
            )
            sub_tab.addTab(table_widget, f"{attr}属性")
        layout.addWidget(sub_tab)

# ---------- 入口 ----------
if __name__ == "__main__":
    auto_file = sys.argv[1] if len(sys.argv) > 1 else None
    app = QApplication(sys.argv)
    window = DataAnalyzer(auto_file=auto_file)
    window.show()
    sys.exit(app.exec_())