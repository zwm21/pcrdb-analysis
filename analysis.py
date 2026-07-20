import sys
import ast
import traceback
import pandas as pd
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QFileDialog,
    QMessageBox, QStatusBar, QAbstractItemView, QDialog,
    QComboBox, QLineEdit, QSpinBox
)
from PyQt5.QtCore import Qt

# ---------- 剪贴板导出防护 ----------
def sanitize_for_clipboard(text):
    """防电子表格公式注入：昵称/公会名/留言等玩家可控字段可能以
    = + - @ 等开头，粘贴进 Excel/WPS 会被当作公式解析（DDE 注入）。
    对危险前缀加单引号转义；纯数字（如负数）不受影响。
    同时清洗字段内嵌的 \\t/\\r/\\n：CSV 引号字段允许包含它们（多行留言等），
    粘贴 TSV 时会拆列/拆行，既破坏对齐，也会让换行后的内容落在新单元格
    开头，从而绕过仅检查首字符的前缀转义。"""
    if not text:
        return text
    for ch in ('\t', '\r', '\n'):
        if ch in text:
            text = text.replace(ch, ' ')
    if text[0] in ('=', '+', '-', '@'):
        try:
            float(text)
            return text  # 合法数字，无注入风险
        except ValueError:
            return "'" + text
    return text


# ---------- 支持复制功能的表格类 ----------
class CopyableTable(QTableWidget):
    def keyPressEvent(self, event):
        # Ctrl+C 复制选中区域
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_C:
            self.copy_selection()
        else:
            super().keyPressEvent(event)

    def copy_selection(self):
        """复制选中单元格：仅包含实际选中的单元格，制表符分隔列，换行分隔行"""
        cells = sorted({(idx.row(), idx.column()) for idx in self.selectedIndexes()})
        if not cells:
            return

        lines = []
        current_row = None
        row_items = []
        for row, col in cells:
            if row != current_row:
                if row_items:
                    lines.append("\t".join(row_items))
                row_items = []
                current_row = row
            item = self.item(row, col)
            row_items.append(sanitize_for_clipboard(item.text()) if item else "")
        if row_items:
            lines.append("\t".join(row_items))

        QApplication.clipboard().setText("\n".join(lines))

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
                row_items.append(sanitize_for_clipboard(item.text()) if item else "")
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
        self.tab_level = QWidget()
        self.tab_talent = QWidget()
        self.tab_clan = QWidget()
        self.tab_arena = QWidget()
        self.main_tab.addTab(self.tab_power, "战力前100")
        self.main_tab.addTab(self.tab_unit, "图鉴数分布")
        self.main_tab.addTab(self.tab_rank, "骑士等级分布")
        self.main_tab.addTab(self.tab_level, "玩家等级分布")
        self.main_tab.addTab(self.tab_talent, "深域关卡")
        self.main_tab.addTab(self.tab_clan, "公会排行")
        self.main_tab.addTab(self.tab_arena, "竞技场分布")
        self.clan_min_members = 1
        self.clan_sort_key = '公会平均战力'
        self.clan_sort_asc = False
        self.clan_search_text = ''
        self.arena_type_index = 0   # 0=战斗竞技场 1=公主竞技场
        self.arena_group = '全部'

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        if auto_file:
            self.load_csv_file(auto_file)

    # ---------- 数据加载 ----------
    def load_csv_file(self, filepath):
        """加载指定的 CSV 文件并刷新所有表格"""
        try:
            self.status_bar.showMessage("正在加载数据...")
            self.df = self.load_data(filepath)
            # 成功后才更新文件标签，避免失败时"标签显示新文件、表格仍是旧数据"
            self.label_file.setText(filepath)
            self.status_bar.showMessage(f"加载完成，共 {len(self.df)} 条记录")
            self.create_all_tables()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"数据加载失败：{str(e)}")
            self.status_bar.showMessage("加载失败")

    def select_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择 player_profile_snapshots_*.csv",
            filter="CSV 文件 (*.csv);;所有文件 (*.*)"
        )
        if not filepath:
            return
        self.load_csv_file(filepath)

    def load_data(self, filepath):
        # 兼容 UTF-8（含 BOM）和 GBK 编码
        df = None
        for enc in ('utf-8-sig', 'gbk'):
            try:
                df = pd.read_csv(filepath, encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        if df is None:
            raise ValueError("无法识别文件编码（已尝试 UTF-8/GBK），请将文件另存为 UTF-8 编码后重试")
        df.columns = df.columns.str.strip()

        # 校验必需列，缺列时给出明确提示而不是后续 KeyError
        required = ['viewer_id', 'user_name', 'unit_num', 'total_power',
                    'princess_knight_rank', 'join_clan_id', 'join_clan_name',
                    'talent_quest_clear']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"CSV 缺少必需列：{', '.join(missing)}")

        def parse_talent(x):
            """解析深域通关字段，任何格式/类型不符都回退为全 0"""
            default = [0, 0, 0, 0, 0]
            if not isinstance(x, str):
                return default
            try:
                v = ast.literal_eval(x)
            except (ValueError, SyntaxError):
                return default
            if not isinstance(v, (list, tuple)) or len(v) != 5:
                return default
            try:
                return [int(e) for e in v]
            except (TypeError, ValueError):
                return default

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
        self.build_level_table(self.df)
        self.build_talent_tables(self.df)
        self.build_clan_table(self.df)
        self.build_arena_table(self.df)

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

        # 用 enumerate 生成行位置，避免把 DataFrame 索引值当作表格行号
        for i, (_, row) in enumerate(data_df.iterrows()):
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

    def _open_profile_by_viewer_id(self, viewer_id_text):
        """按 viewer_id 从 self.df 查完整行，调用 show_player_profile"""
        try:
            vid = int(float(viewer_id_text))
        except (ValueError, TypeError):
            return
        match = self.df[self.df['viewer_id'] == vid]
        if match.empty:
            return
        self.show_player_profile(match.iloc[0])

    def _route_double_click(self, tbl, row, col, name_col, id_col):
        """双击路由：点击玩家昵称列时查看玩家画像，其余列复制内容"""
        if col == name_col:
            id_item = tbl.item(row, id_col)
            if id_item:
                self._open_profile_by_viewer_id(id_item.text())
        else:
            self.copy_cell(tbl, row, col)

    def copy_cell(self, table, row, col):
        """双击单元格时复制其内容到剪贴板"""
        item = table.item(row, col)
        if item is None:
            return
        text = sanitize_for_clipboard(item.text())
        QApplication.clipboard().setText(text)
        self.status_bar.showMessage(f"已复制：{text}", 2000)

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
        # 玩家昵称列（col 2）双击查看画像，其余双击复制；玩家id 在 col 3
        tbl.cellDoubleClicked.connect(
            lambda r, c, t=tbl: self._route_double_click(t, r, c, name_col=2, id_col=3))

        # 在表格上方插入提示文字
        hint = QLabel("双击玩家昵称查看画像，双击其他单元格复制内容")
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

    # ---------- 玩家等级分布 ----------
    def build_level_table(self, df):
        # team_level 为非必需列，缺列时页签内提示而不是整体加载失败
        if 'team_level' not in df.columns:
            layout = self.tab_level.layout()
            if layout is None:
                layout = QVBoxLayout(self.tab_level)
            else:
                while layout.count():
                    child = layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
            lbl = QLabel("当前 CSV 缺少玩家等级列：team_level")
            lbl.setStyleSheet("color: #a00; margin: 10px;")
            layout.addWidget(lbl)
            layout.addStretch()
            return

        level_counts = df['team_level'].value_counts().sort_index(ascending=False)
        level_df = level_counts.reset_index()
        level_df.columns = ['level', 'count']
        level_df = level_df.sort_values('level', ascending=False)

        tbl = self.populate_tab(self.tab_level, level_df,
                                columns=['玩家等级', '玩家数量'],
                                col_keys=['level', 'count'])
        tbl.cellDoubleClicked.connect(self.show_level_players)

        # 在表格上方插入提示文字
        hint = QLabel("双击玩家等级可查看对应玩家列表")
        hint.setStyleSheet("color: #666; font-size: 9pt; margin: 4px;")
        self.tab_level.layout().insertWidget(0, hint)

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
        self._show_player_list(
            filtered, title_template.format(len(filtered)),
            headers=['玩家id', '玩家昵称', '公会名称', '公会id'],
            col_keys=['viewer_id', 'user_name', 'join_clan_name', 'join_clan_id'])

    def _show_player_list(self, filtered, title, headers, col_keys):
        """弹窗显示玩家列表：双击玩家昵称查看画像，双击其他单元格复制内容"""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(750, 500)
        layout = QVBoxLayout(dlg)

        tbl = CopyableTable(len(filtered), len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setAlternatingRowColors(True)
        # 玩家昵称列（col 1）双击查看画像，其余双击复制；viewer_id 固定在 col 0
        tbl.cellDoubleClicked.connect(
            lambda r, c, t=tbl: self._route_double_click(t, r, c, name_col=1, id_col=0))

        for i, (_, player) in enumerate(filtered.iterrows()):
            for j, key in enumerate(col_keys):
                value = player[key]
                item = QTableWidgetItem(str(value) if pd.notna(value) else '')
                item.setTextAlignment(Qt.AlignCenter)
                tbl.setItem(i, j, item)

        layout.addWidget(tbl)
        dlg.exec_()

    def show_rank_players(self, row, _col):
        """双击骑士等级行时，弹窗显示该等级下所有玩家"""
        tbl = self.sender()
        if not isinstance(tbl, QTableWidget):
            return
        rank_item = tbl.item(row, 0)
        if not rank_item:
            return
        try:
            # 列含空值时 pandas 会转成 float，单元格可能显示 "338.0"
            rank = int(float(rank_item.text()))
        except ValueError:
            return
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
        try:
            unit_num = int(float(unit_item.text()))
        except ValueError:
            return
        filtered = self.df[self.df['unit_num'] == unit_num][['viewer_id', 'user_name', 'join_clan_name', 'join_clan_id']]
        self._choose_sort_and_show(filtered, f"图鉴数 {unit_num} — 玩家列表（共 {{}} 人）")

    def show_level_players(self, row, _col):
        """双击玩家等级行时，弹窗显示该等级下所有玩家"""
        tbl = self.sender()
        if not isinstance(tbl, QTableWidget):
            return
        level_item = tbl.item(row, 0)
        if not level_item:
            return
        try:
            # 列含空值时 pandas 会转成 float，单元格可能显示 "348.0"
            level = int(float(level_item.text()))
        except ValueError:
            return
        filtered = self.df[self.df['team_level'] == level][['viewer_id', 'user_name', 'join_clan_name', 'join_clan_id']]
        self._choose_sort_and_show(filtered, f"玩家等级 {level} — 玩家列表（共 {{}} 人）")

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
        try:
            level = int(float(level_item.text()))
        except ValueError:
            return
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

        # 筛选/排序/搜索栏（放入 QWidget 便于整体清理）
        bar_widget = QWidget()
        bar = QVBoxLayout(bar_widget)
        bar.setContentsMargins(4, 4, 4, 0)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("仅显示人数 ≥"))
        spin = QSpinBox()
        spin.setRange(1, 30)
        spin.setValue(self.clan_min_members)
        row1.addWidget(spin)
        row1.addWidget(QLabel("的公会"))
        row1.addSpacing(16)
        row1.addWidget(QLabel("排序："))
        combo_key = QComboBox()
        sort_keys = ['公会平均战力', '人数', '平均骑士等级', '深域平均层数', '公会id']
        combo_key.addItems(sort_keys)
        if self.clan_sort_key in sort_keys:
            combo_key.setCurrentText(self.clan_sort_key)
        row1.addWidget(combo_key)
        combo_order = QComboBox()
        combo_order.addItems(['降序', '升序'])
        combo_order.setCurrentIndex(1 if self.clan_sort_asc else 0)
        row1.addWidget(combo_order)
        btn_apply = QPushButton("应用")
        row1.addWidget(btn_apply)
        row1.addStretch()
        bar.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("搜索公会名："))
        search_edit = QLineEdit()
        search_edit.setPlaceholderText("输入公会名关键字，留空显示全部")
        search_edit.setFixedWidth(220)
        search_edit.setText(self.clan_search_text)
        row2.addWidget(search_edit)
        btn_clear = QPushButton("清除搜索")
        row2.addWidget(btn_clear)
        row2.addStretch()
        bar.addLayout(row2)
        layout.addWidget(bar_widget)

        hint = QLabel("双击公会id或公会名称可查看该公会玩家列表（按玩家id升序）；双击其他单元格复制内容")
        hint.setStyleSheet("color: #666; font-size: 9pt; margin: 4px;")
        layout.addWidget(hint)

        # 按公会聚合
        data = df.dropna(subset=['join_clan_id']).copy()
        data['total_power'] = pd.to_numeric(data['total_power'], errors='coerce')
        data['深域平均'] = data[['火', '水', '风', '光', '暗']].mean(axis=1)
        clan = data.groupby('join_clan_id').agg(
            公会名称=('join_clan_name', 'first'),
            人数=('viewer_id', 'count'),
            公会平均战力=('total_power', 'mean'),
            平均骑士等级=('princess_knight_rank', 'mean'),
            深域平均层数=('深域平均', 'mean'),
        ).reset_index()
        clan['公会平均战力'] = clan['公会平均战力'].round(0).astype('Int64')
        clan['平均骑士等级'] = clan['平均骑士等级'].round(2)
        clan['深域平均层数'] = clan['深域平均层数'].round(2)
        clan['join_clan_id'] = clan['join_clan_id'].astype('Int64')

        # 排名始终按公会平均战力降序编号（人数筛选/搜索/自选排序均不改变排名归属）
        clan = clan.sort_values('公会平均战力', ascending=False).reset_index(drop=True)
        clan.index += 1
        clan.reset_index(inplace=True)
        clan = clan.rename(columns={'index': '排名', 'join_clan_id': '公会id'})

        # 人数筛选：放在编号之后，只隐藏行、不重排名次（与搜索行为一致）
        clan = clan[clan['人数'] >= self.clan_min_members]

        # 公会名搜索（子串匹配，忽略大小写）
        if self.clan_search_text:
            clan = clan[clan['公会名称'].astype(str).str.contains(
                self.clan_search_text, case=False, na=False, regex=False)]

        # 自选排序
        clan = clan.sort_values(self.clan_sort_key, ascending=self.clan_sort_asc).reset_index(drop=True)

        table_widget = self.create_copyable_table(
            clan,
            columns=['排名', '公会id', '公会名称', '人数', '公会平均战力', '平均骑士等级', '深域平均层数'],
            col_keys=['排名', '公会id', '公会名称', '人数', '公会平均战力', '平均骑士等级', '深域平均层数']
        )
        tbl = table_widget.table
        # 公会id/公会名称列双击查看玩家列表，其余列双击复制
        tbl.cellDoubleClicked.connect(
            lambda r, c, t=tbl: self.show_clan_players(t, r) if c in (1, 2) else self.copy_cell(t, r, c)
        )
        layout.addWidget(table_widget)

        if self.clan_search_text:
            self.status_bar.showMessage(f"公会名包含“{self.clan_search_text}”：共 {len(clan)} 个公会", 3000)

        def apply_filter():
            self.clan_min_members = spin.value()
            self.clan_sort_key = combo_key.currentText()
            self.clan_sort_asc = (combo_order.currentIndex() == 1)
            self.clan_search_text = search_edit.text().strip()
            self.build_clan_table()
        btn_apply.clicked.connect(apply_filter)
        search_edit.returnPressed.connect(apply_filter)

        def clear_search():
            search_edit.setText('')
            apply_filter()
        btn_clear.clicked.connect(clear_search)

    def show_clan_players(self, tbl, row):
        """双击公会行时，弹窗显示该公会全部玩家（按玩家id升序）"""
        id_item = tbl.item(row, 1)
        name_item = tbl.item(row, 2)
        if not id_item:
            return
        try:
            clan_id = int(id_item.text())
        except ValueError:
            return
        clan_name = name_item.text() if name_item else ''
        filtered = self.df[self.df['join_clan_id'] == clan_id][
            ['viewer_id', 'user_name', 'total_power', 'princess_knight_rank']]
        filtered = filtered.sort_values('viewer_id', ascending=True).reset_index(drop=True)
        self._show_player_list(
            filtered, f"公会 {clan_name}（id: {clan_id}）— 玩家列表（共 {len(filtered)} 人）",
            headers=['玩家id', '玩家昵称', '战力', '骑士等级'],
            col_keys=['viewer_id', 'user_name', 'total_power', 'princess_knight_rank'])

    # ---------- 竞技场分布 ----------
    def build_arena_table(self, df=None):
        if df is None:
            df = self.df
        if df is None:
            return

        layout = self.tab_arena.layout()
        if layout is None:
            layout = QVBoxLayout(self.tab_arena)
        else:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

        arena_defs = [
            ('战斗竞技场', 'arena_group', 'arena_rank'),
            ('公主竞技场', 'grand_arena_group', 'grand_arena_rank'),
        ]
        _, group_col, rank_col = arena_defs[self.arena_type_index]

        # CSV 可能缺少竞技场列，给出提示而不是报错
        missing = [c for c in ('arena_group', 'arena_rank', 'grand_arena_group', 'grand_arena_rank')
                   if c not in df.columns]
        if missing:
            lbl = QLabel(f"当前 CSV 缺少竞技场相关列：{', '.join(missing)}")
            lbl.setStyleSheet("color: #a00; margin: 10px;")
            layout.addWidget(lbl)
            layout.addStretch()
            return

        # 筛选栏（放入 QWidget 便于整体清理）
        bar_widget = QWidget()
        bar = QHBoxLayout(bar_widget)
        bar.setContentsMargins(4, 4, 4, 0)
        bar.addWidget(QLabel("竞技场："))
        combo_type = QComboBox()
        combo_type.addItems([name for name, _, _ in arena_defs])
        combo_type.setCurrentIndex(self.arena_type_index)
        bar.addWidget(combo_type)
        bar.addSpacing(12)
        bar.addWidget(QLabel("组别（场次）："))
        combo_group = QComboBox()
        bar.addWidget(combo_group)
        bar.addStretch()
        layout.addWidget(bar_widget)

        hint = QLabel("选择竞技场与组别后自动刷新，列表按排名升序；双击玩家昵称查看画像，双击其他单元格复制内容")
        hint.setStyleSheet("color: #666; font-size: 9pt; margin: 4px;")
        layout.addWidget(hint)

        # 数据准备
        data = df.copy()
        data[group_col] = pd.to_numeric(data[group_col], errors='coerce')
        data[rank_col] = pd.to_numeric(data[rank_col], errors='coerce')
        data = data.dropna(subset=[group_col, rank_col])

        # 组别下拉：全部 + 数据中出现的组别
        groups = sorted(int(g) for g in data[group_col].unique())
        combo_group.addItem('全部')
        for g in groups:
            combo_group.addItem(str(g))
        if self.arena_group != '全部' and self.arena_group in [str(g) for g in groups]:
            combo_group.setCurrentText(self.arena_group)
        else:
            self.arena_group = '全部'

        # 筛选 + 排名升序（"全部"时先按组别再按排名）
        view = data
        if self.arena_group != '全部':
            view = view[view[group_col] == int(self.arena_group)]
        view = view.sort_values([group_col, rank_col], ascending=[True, True]).reset_index(drop=True)

        show = view[[group_col, rank_col, 'viewer_id', 'user_name', 'join_clan_name']].copy()
        show[group_col] = show[group_col].astype(int)
        show[rank_col] = show[rank_col].astype(int)

        table_widget = self.create_copyable_table(
            show,
            columns=['组别', '排名', '玩家id', '玩家昵称', '公会名称'],
            col_keys=[group_col, rank_col, 'viewer_id', 'user_name', 'join_clan_name']
        )
        tbl = table_widget.table
        # 竞技场表：列顺序 组别(0) 排名(1) 玩家id(2) 玩家昵称(3) 公会名称(4)
        # 双击昵称列查看画像，其余列复制
        tbl.cellDoubleClicked.connect(
            lambda r, c, t=tbl: self._route_double_click(t, r, c, name_col=3, id_col=2))
        layout.addWidget(table_widget)

        self.status_bar.showMessage(
            f"{arena_defs[self.arena_type_index][0]} 组别[{self.arena_group}]：共 {len(show)} 名玩家", 3000)

        # 信号在控件填充完成后再连接，避免初始化期间误触发
        def on_type_changed(idx):
            self.arena_type_index = idx
            self.arena_group = '全部'   # 切换竞技场时组别重置
            self.build_arena_table()
        combo_type.currentIndexChanged.connect(on_type_changed)

        def on_group_changed(_idx):
            self.arena_group = combo_group.currentText()
            self.build_arena_table()
        combo_group.currentIndexChanged.connect(on_group_changed)

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

        def val(col):
            """可选列容错：CSV 缺列或值为空时显示 '-'，避免 KeyError 弹错误框"""
            if col in player.index and pd.notna(player[col]):
                return player[col]
            return '-'

        def fmt_arena(g_col, r_col):
            g, r = val(g_col), val(r_col)
            if g == '-' and r == '-':
                return '-'
            return f"第 {g} 场 {r} 名"

        power = pd.to_numeric(df['total_power'], errors='coerce')
        my_power = pd.to_numeric(pd.Series([player['total_power']]), errors='coerce').iloc[0]
        power_rank = int((power > my_power).sum()) + 1 if pd.notna(my_power) else None
        rank_rank = int((df['princess_knight_rank'] > player['princess_knight_rank']).sum()) + 1
        unit_rank = int((df['unit_num'] > player['unit_num']).sum()) + 1

        rows = [
            ('玩家id', player['viewer_id']),
            ('玩家昵称', player['user_name']),
            ('队伍等级', val('team_level')),
            ('战力', f"{player['total_power']}（全服第 {power_rank} 名）" if power_rank else player['total_power']),
            ('图鉴数', f"{player['unit_num']}（全服第 {unit_rank} 名）"),
            ('骑士等级', f"{player['princess_knight_rank']}（全服第 {rank_rank} 名）"),
            ('公会', f"{player['join_clan_name']}（id: {player['join_clan_id']}）"),
            ('竞技场排名', fmt_arena('arena_group', 'arena_rank')),
            ('公主竞技场排名', fmt_arena('grand_arena_group', 'grand_arena_rank')),
            ('喜爱角色', val('favorite_unit_name')),
            ('深域通关（火/水/风/光/暗）', ' / '.join(str(player[a]) for a in ['火', '水', '风', '光', '暗'])),
            ('个人留言', val('user_comment')),
            ('最后登录', val('last_login_time')),
            ('数据采集时间', val('collected_at')),
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
def _excepthook(exc_type, exc_value, exc_tb):
    """全局异常兜底。

    PyQt5 >= 5.5 中槽函数内未捕获的 Python 异常会触发 qFatal 直接终止进程，
    这里改为打印堆栈并弹窗提示，让程序继续运行。
    """
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    if sys.stderr:  # PyInstaller --noconsole 下 stderr 可能为 None
        sys.stderr.write(msg)
    QMessageBox.critical(None, "程序错误",
                         f"发生未处理的异常：{exc_value}\n\n{msg[-1500:]}")


if __name__ == "__main__":
    sys.excepthook = _excepthook
    auto_file = sys.argv[1] if len(sys.argv) > 1 else None
    app = QApplication(sys.argv)
    window = DataAnalyzer(auto_file=auto_file)
    window.show()
    sys.exit(app.exec_())