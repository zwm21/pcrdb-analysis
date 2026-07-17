import sys
import ast
import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QFileDialog,
    QMessageBox, QStatusBar, QAbstractItemView, QMenu, QAction, QDialog,
    QComboBox, QLineEdit, QSpinBox
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

        # 全局搜索
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("昵称 / viewer_id")
        self.search_input.setFixedWidth(180)
        self.search_input.returnPressed.connect(self.search_player)
        self.btn_search = QPushButton("搜索玩家")
        self.btn_search.clicked.connect(self.search_player)
        top_layout.addWidget(self.search_input)
        top_layout.addWidget(self.btn_search)
        main_layout.addLayout(top_layout)

        # 主选项卡
        self.main_tab = QTabWidget()
        main_layout.addWidget(self.main_tab)

        # 预留页面
        self.tab_power = QWidget()
        self.tab_unit = QWidget()
        self.tab_rank = QWidget()
        self.tab_talent = QWidget()
        self.tab_clan = QWidget()
        self.main_tab.addTab(self.tab_power, "战力前100")
        self.main_tab.addTab(self.tab_unit, "图鉴数分布")
        self.main_tab.addTab(self.tab_rank, "骑士等级分布")
        self.main_tab.addTab(self.tab_talent, "深域关卡")
        self.main_tab.addTab(self.tab_clan, "公会排行")
        self.clan_min_members = 1

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
        self.build_clan_table(self.df)

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
        # 保留表格引用，供调用方直接连接信号
        # （不要用 findChild 查找：旧控件 deleteLater 后仍可能被同步找到）
        widget.table = table
        return widget

    def copy_cell(self, table, row, col):
        """双击单元格时复制其内容到剪贴板"""
        item = table.item(row, col)
        if item is None:
            return
        QApplication.clipboard().setText(item.text())
        self.statusBar.showMessage(f"已复制：{item.text()}", 2000)

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
        return table_widget.table

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

        tbl = self.populate_tab(self.tab_power, top100,
                                columns=['排名', '战力', '玩家昵称', '玩家id'],
                                col_keys=['排名', '战力', '玩家昵称', '玩家id'])
        tbl.cellDoubleClicked.connect(lambda r, c, t=tbl: self.copy_cell(t, r, c))

        # 在表格上方插入提示文字
        hint = QLabel("双击单元格可复制内容")
        hint.setStyleSheet("color: #666; font-size: 9pt; margin: 4px;")
        self.tab_power.layout().insertWidget(0, hint)

    # ---------- 图鉴数分布 ----------
    def build_unit_table(self, df):
        unit_counts = df['unit_num'].value_counts().sort_index(ascending=False)
        unit_df = unit_counts.reset_index()
        unit_df.columns = ['unit_num', 'count']
        unit_df = unit_df.sort_values('unit_num', ascending=False)

        tbl = self.populate_tab(self.tab_unit, unit_df,
                                columns=['图鉴数', '玩家数量'],
                                col_keys=['unit_num', 'count'])
        tbl.cellDoubleClicked.connect(self.show_unit_players)

        # 在表格上方插入提示文字
        hint = QLabel("双击图鉴数可查看对应玩家列表")
        hint.setStyleSheet("color: #666; font-size: 9pt; margin: 4px;")
        self.tab_unit.layout().insertWidget(0, hint)

    # ---------- 骑士等级分布 ----------
    def build_rank_table(self, df):
        rank_counts = df['princess_knight_rank'].value_counts().sort_index(ascending=False)
        rank_df = rank_counts.reset_index()
        rank_df.columns = ['rank', 'count']
        rank_df = rank_df.sort_values('rank', ascending=False)

        tbl = self.populate_tab(self.tab_rank, rank_df,
                                columns=['骑士等级', '玩家数量'],
                                col_keys=['rank', 'count'])
        tbl.cellDoubleClicked.connect(self.show_rank_players)

        # 在表格上方插入提示文字
        hint = QLabel("双击骑士等级可查看对应玩家列表")
        hint.setStyleSheet("color: #666; font-size: 9pt; margin: 4px;")
        self.tab_rank.layout().insertWidget(0, hint)

    def _choose_sort_and_show(self, filtered, title_template):
        """弹出排序选择窗口，排序后显示玩家列表"""
        dlg_sort = QDialog(self)
        dlg_sort.setWindowTitle("选择排序方式")
        dlg_sort.resize(400, 150)
        layout = QVBoxLayout(dlg_sort)

        layout.addWidget(QLabel("请选择排序方式："))

        combo = QComboBox()
        combo.addItems([
            "公会id 升序，viewer_id 升序",
            "公会id 升序，viewer_id 降序",
            "公会id 降序，viewer_id 升序",
            "公会id 降序，viewer_id 降序",
            "viewer_id 升序",
            "viewer_id 降序",
        ])
        layout.addWidget(combo)

        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("确定")
        btn_cancel = QPushButton("取消")
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        btn_ok.clicked.connect(dlg_sort.accept)
        btn_cancel.clicked.connect(dlg_sort.reject)

        if dlg_sort.exec_() != QDialog.Accepted:
            return

        # 排序
        method = combo.currentIndex()
        if method == 0:
            filtered = filtered.sort_values(['join_clan_id', 'viewer_id'], ascending=[True, True])
        elif method == 1:
            filtered = filtered.sort_values(['join_clan_id', 'viewer_id'], ascending=[True, False])
        elif method == 2:
            filtered = filtered.sort_values(['join_clan_id', 'viewer_id'], ascending=[False, True])
        elif method == 3:
            filtered = filtered.sort_values(['join_clan_id', 'viewer_id'], ascending=[False, False])
        elif method == 4:
            filtered = filtered.sort_values('viewer_id', ascending=True)
        elif method == 5:
            filtered = filtered.sort_values('viewer_id', ascending=False)
        filtered = filtered.reset_index(drop=True)

        # 显示玩家列表
        dlg = QDialog(self)
        dlg.setWindowTitle(title_template.format(len(filtered)))
        dlg.resize(750, 500)
        layout2 = QVBoxLayout(dlg)

        tbl2 = CopyableTable(len(filtered), 4)
        tbl2.setHorizontalHeaderLabels(['玩家id', '玩家昵称', '公会名称', '公会id'])
        tbl2.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl2.verticalHeader().setVisible(False)
        tbl2.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl2.setAlternatingRowColors(True)
        tbl2.cellDoubleClicked.connect(lambda r, c, t=tbl2: self.copy_cell(t, r, c))

        for i, (_, player) in enumerate(filtered.iterrows()):
            for j, key in enumerate(['viewer_id', 'user_name', 'join_clan_name', 'join_clan_id']):
                value = player[key]
                item = QTableWidgetItem(str(value) if pd.notna(value) else '')
                item.setTextAlignment(Qt.AlignCenter)
                tbl2.setItem(i, j, item)

        layout2.addWidget(tbl2)
        dlg.exec_()

    def show_rank_players(self, row, _col):
        """双击骑士等级行时，弹窗显示该等级下所有玩家"""
        tbl = self.sender()
        if not isinstance(tbl, QTableWidget):
            return
        rank_item = tbl.item(row, 0)
        if not rank_item:
            return
        rank = int(rank_item.text())
        filtered = self.df[self.df['princess_knight_rank'] == rank][['viewer_id', 'user_name', 'join_clan_name', 'join_clan_id']]
        self._choose_sort_and_show(filtered, f"骑士等级 {rank} — 玩家列表（共 {{}} 人）")

    def show_unit_players(self, row, _col):
        """双击图鉴数行时，弹窗显示该图鉴数下所有玩家"""
        tbl = self.sender()
        if not isinstance(tbl, QTableWidget):
            return
        unit_item = tbl.item(row, 0)
        if not unit_item:
            return
        unit_num = int(unit_item.text())
        filtered = self.df[self.df['unit_num'] == unit_num][['viewer_id', 'user_name', 'join_clan_name', 'join_clan_id']]
        self._choose_sort_and_show(filtered, f"图鉴数 {unit_num} — 玩家列表（共 {{}} 人）")

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
        hint = QLabel("双击关卡编号可查看对应玩家列表")
        hint.setStyleSheet("color: #666; font-size: 9pt; margin: 4px;")
        layout.addWidget(hint)

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
            tbl = table_widget.table
            tbl.cellDoubleClicked.connect(
                lambda r, c, t=tbl, a=attr: self.show_talent_players(t, a, r)
            )
            sub_tab.addTab(table_widget, f"{attr}属性")
        layout.addWidget(sub_tab)

    def show_talent_players(self, tbl, attr, row):
        """双击深域关卡行时，弹窗显示通关该属性该关卡的所有玩家"""
        level_item = tbl.item(row, 0)
        if not level_item:
            return
        level = int(level_item.text())
        filtered = self.df[self.df[attr] == level][['viewer_id', 'user_name', 'join_clan_name', 'join_clan_id']]
        self._choose_sort_and_show(filtered, f"{attr}属性 关卡 {level} — 玩家列表（共 {{}} 人）")

    # ---------- 公会排行 ----------
    def build_clan_table(self, df=None):
        if df is None:
            df = self.df
        if df is None:
            return

        layout = self.tab_clan.layout()
        if layout is None:
            layout = QVBoxLayout(self.tab_clan)
        else:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        # 筛选栏（放入 QWidget 便于整体清理）
        bar_widget = QWidget()
        bar = QHBoxLayout(bar_widget)
        bar.setContentsMargins(4, 4, 4, 0)
        bar.addWidget(QLabel("仅显示人数 ≥"))
        spin = QSpinBox()
        spin.setRange(1, 30)
        spin.setValue(self.clan_min_members)
        bar.addWidget(spin)
        bar.addWidget(QLabel("的公会"))
        btn_apply = QPushButton("应用筛选")
        bar.addWidget(btn_apply)
        bar.addStretch()
        layout.addWidget(bar_widget)

        hint = QLabel("按公会总战力排行；双击单元格可复制内容")
        hint.setStyleSheet("color: #666; font-size: 9pt; margin: 4px;")
        layout.addWidget(hint)

        # 按公会聚合
        data = df.dropna(subset=['join_clan_id']).copy()
        data['total_power'] = pd.to_numeric(data['total_power'], errors='coerce')
        data['深域平均'] = data[['火', '水', '风', '光', '暗']].mean(axis=1)
        clan = data.groupby('join_clan_id').agg(
            公会名称=('join_clan_name', 'first'),
            人数=('viewer_id', 'count'),
            公会总战力=('total_power', 'sum'),
            平均骑士等级=('princess_knight_rank', 'mean'),
            深域平均层数=('深域平均', 'mean'),
        ).reset_index()
        clan = clan[clan['人数'] >= self.clan_min_members]
        clan['公会总战力'] = clan['公会总战力'].round(0).astype('Int64')
        clan['平均骑士等级'] = clan['平均骑士等级'].round(2)
        clan['深域平均层数'] = clan['深域平均层数'].round(2)
        clan['join_clan_id'] = clan['join_clan_id'].astype('Int64')
        clan = clan.sort_values('公会总战力', ascending=False).reset_index(drop=True)
        clan.index += 1
        clan.reset_index(inplace=True)
        clan = clan.rename(columns={'index': '排名', 'join_clan_id': '公会id'})

        table_widget = self.create_copyable_table(
            clan,
            columns=['排名', '公会id', '公会名称', '人数', '公会总战力', '平均骑士等级', '深域平均层数'],
            col_keys=['排名', '公会id', '公会名称', '人数', '公会总战力', '平均骑士等级', '深域平均层数']
        )
        tbl = table_widget.table
        tbl.cellDoubleClicked.connect(lambda r, c, t=tbl: self.copy_cell(t, r, c))
        layout.addWidget(table_widget)

        def apply_filter():
            self.clan_min_members = spin.value()
            self.build_clan_table()
        btn_apply.clicked.connect(apply_filter)

    # ---------- 全局搜索 ----------
    def search_player(self):
        if self.df is None:
            QMessageBox.information(self, "提示", "请先加载 CSV 文件")
            return
        query = self.search_input.text().strip()
        if not query:
            return
        df = self.df
        mask = (df['user_name'].astype(str).str.contains(query, case=False, na=False, regex=False)
                | df['viewer_id'].astype(str).str.contains(query, na=False, regex=False))
        results = df[mask]
        if len(results) == 0:
            QMessageBox.information(self, "搜索结果", f"未找到匹配“{query}”的玩家")
            return
        if len(results) == 1:
            self.show_player_profile(results.iloc[0])
            return

        # 多个结果：弹窗列表，双击查看画像
        dlg = QDialog(self)
        dlg.setWindowTitle(f"搜索“{query}” — 共 {len(results)} 个结果（双击查看玩家画像）")
        dlg.resize(750, 500)
        layout = QVBoxLayout(dlg)

        results = results.reset_index(drop=True)
        tbl = CopyableTable(len(results), 4)
        tbl.setHorizontalHeaderLabels(['玩家id', '玩家昵称', '公会名称', '战力'])
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setAlternatingRowColors(True)
        for i, (_, player) in enumerate(results.iterrows()):
            for j, key in enumerate(['viewer_id', 'user_name', 'join_clan_name', 'total_power']):
                value = player[key]
                item = QTableWidgetItem(str(value) if pd.notna(value) else '')
                item.setTextAlignment(Qt.AlignCenter)
                tbl.setItem(i, j, item)
        tbl.cellDoubleClicked.connect(
            lambda r, c, res=results: self.show_player_profile(res.iloc[r])
        )
        layout.addWidget(tbl)
        dlg.exec_()

    def show_player_profile(self, player):
        """弹窗显示单个玩家的完整画像（player 为 df 的一行 Series）"""
        df = self.df
        power = pd.to_numeric(df['total_power'], errors='coerce')
        my_power = pd.to_numeric(pd.Series([player['total_power']]), errors='coerce').iloc[0]
        power_rank = int((power > my_power).sum()) + 1 if pd.notna(my_power) else None
        rank_rank = int((df['princess_knight_rank'] > player['princess_knight_rank']).sum()) + 1
        unit_rank = int((df['unit_num'] > player['unit_num']).sum()) + 1

        rows = [
            ('玩家id', player['viewer_id']),
            ('玩家昵称', player['user_name']),
            ('队伍等级', player['team_level']),
            ('战力', f"{player['total_power']}（全服第 {power_rank} 名）" if power_rank else player['total_power']),
            ('图鉴数', f"{player['unit_num']}（全服第 {unit_rank} 名）"),
            ('骑士等级', f"{player['princess_knight_rank']}（全服第 {rank_rank} 名）"),
            ('公会', f"{player['join_clan_name']}（id: {player['join_clan_id']}）"),
            ('竞技场排名', f"第 {player['arena_group']} 场 {player['arena_rank']} 名"),
            ('公主竞技场排名', f"第 {player['grand_arena_group']} 场 {player['grand_arena_rank']} 名"),
            ('喜爱角色', player['favorite_unit_name']),
            ('深域通关（火/水/风/光/暗）', ' / '.join(str(player[a]) for a in ['火', '水', '风', '光', '暗'])),
            ('个人留言', player['user_comment']),
            ('最后登录', player['last_login_time']),
            ('数据采集时间', player['collected_at']),
        ]

        dlg = QDialog(self)
        dlg.setWindowTitle(f"玩家画像 — {player['user_name']}（{player['viewer_id']}）")
        dlg.resize(620, 560)
        layout = QVBoxLayout(dlg)

        hint = QLabel("双击单元格可复制内容")
        hint.setStyleSheet("color: #666; font-size: 9pt; margin: 4px;")
        layout.addWidget(hint)

        tbl = CopyableTable(len(rows), 2)
        tbl.setHorizontalHeaderLabels(['字段', '值'])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setAlternatingRowColors(True)
        for i, (label, value) in enumerate(rows):
            item_k = QTableWidgetItem(label)
            item_v = QTableWidgetItem(str(value) if pd.notna(value) else '')
            tbl.setItem(i, 0, item_k)
            tbl.setItem(i, 1, item_v)
        tbl.cellDoubleClicked.connect(lambda r, c, t=tbl: self.copy_cell(t, r, c))
        layout.addWidget(tbl)
        dlg.exec_()

# ---------- 入口 ----------
if __name__ == "__main__":
    auto_file = sys.argv[1] if len(sys.argv) > 1 else None
    app = QApplication(sys.argv)
    window = DataAnalyzer(auto_file=auto_file)
    window.show()
    sys.exit(app.exec_())