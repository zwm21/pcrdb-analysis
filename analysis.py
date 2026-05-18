import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import ast

# 设置 Matplotlib 中文字体（避免图表中文乱码）
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

class PlayerDataAnalyzer:
    def __init__(self, root):
        self.root = root
        self.root.title("玩家数据可视化工具")
        self.root.geometry("500x400")

        # 主界面控件
        self.label = tk.Label(root, text="请选择 player_profile_snapshots_*.csv 文件：", font=("微软雅黑", 12))
        self.label.pack(pady=20)

        self.select_btn = tk.Button(root, text="选择文件并分析", command=self.select_file,
                                    font=("微软雅黑", 11), bg="#4CAF50", fg="white", padx=20, pady=5)
        self.select_btn.pack(pady=10)

        # 信息展示区域
        self.info_label = tk.Label(root, text="分析信息：", font=("微软雅黑", 10, "bold"))
        self.info_label.pack(anchor="w", padx=20, pady=(10, 0))
        self.text_area = scrolledtext.ScrolledText(root, width=55, height=15, font=("Consolas", 9))
        self.text_area.pack(padx=20, pady=5)

    def select_file(self):
        filepath = filedialog.askopenfilename(
            title="选择 CSV 文件",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")]
        )
        if not filepath:
            return
        try:
            self.text_area.delete(1.0, tk.END)
            self.text_area.insert(tk.END, f"正在加载：{filepath}\n")
            self.root.update()

            df = self.load_data(filepath)
            self.text_area.insert(tk.END, f"共读取 {len(df)} 条记录\n\n")
            self.analyze(df)

        except Exception as e:
            messagebox.showerror("错误", f"读取或分析文件时出错：\n{str(e)}")

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

        df['talent_list'] = df['talent_quest_clear'].apply(parse_talent)
        talent_df = pd.DataFrame(df['talent_list'].tolist(), columns=['火', '水', '风', '光', '暗'])
        df = pd.concat([df, talent_df], axis=1)
        return df

    def analyze(self, df):
        # 细节1：战力前100玩家
        self.text_area.insert(tk.END, "生成图表1：战力前100玩家\n")
        self.plot_top100_power(df)

        # 细节2：图鉴数前10数值玩家数量
        self.text_area.insert(tk.END, "生成图表2：图鉴数前10数值玩家数量\n")
        self.plot_top10_unit_num(df)

        # 细节3：骑士等级前10数值玩家数量
        self.text_area.insert(tk.END, "生成图表3：骑士等级前10数值玩家数量\n")
        self.plot_top10_rank(df)

        # 细节4：深域关卡分析
        self.text_area.insert(tk.END, "生成图表4：深域关卡最难属性通关人数统计\n")
        hardest_info = self.plot_hardest_talent(df)
        self.text_area.insert(tk.END, hardest_info)
        self.text_area.see(tk.END)

        self.text_area.insert(tk.END, "\n所有图表已弹出，可关闭图表窗口后继续使用。\n")

    def plot_top100_power(self, df):
        top100 = df.nlargest(100, 'total_power')[['viewer_id', 'user_name', 'total_power']]
        plt.figure(figsize=(12, 6))
        plt.bar(range(len(top100)), top100['total_power'], color='steelblue')
        plt.xlabel('玩家排名')
        plt.ylabel('战力 (total_power)')
        plt.title('战力最高的前100名玩家')
        plt.tight_layout()
        plt.show(block=False)  # 非阻塞显示，允许多个图表同时弹出

    def plot_top10_unit_num(self, df):
        unit_counts = df['unit_num'].value_counts().sort_index(ascending=False)
        top10 = unit_counts.head(10)
        plt.figure(figsize=(10, 6))
        bars = plt.bar(top10.index.astype(str), top10.values, color='coral')
        plt.xlabel('图鉴数 (unit_num)')
        plt.ylabel('玩家数量')
        plt.title('图鉴数前10数值的玩家数量分布')
        for bar, val in zip(bars, top10.values):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height()+0.5, str(val), ha='center')
        plt.tight_layout()
        plt.show(block=False)

    def plot_top10_rank(self, df):
        rank_counts = df['princess_knight_rank'].value_counts().sort_index(ascending=False)
        top10 = rank_counts.head(10)
        plt.figure(figsize=(10, 6))
        bars = plt.bar(top10.index.astype(str), top10.values, color='mediumseagreen')
        plt.xlabel('骑士等级 (princess_knight_rank)')
        plt.ylabel('玩家数量')
        plt.title('骑士等级前10数值的玩家数量分布')
        for bar, val in zip(bars, top10.values):
            plt.text(bar.get_x() + bar.get_width()/2, bar.get_height()+0.5, str(val), ha='center')
        plt.tight_layout()
        plt.show(block=False)

    def plot_hardest_talent(self, df):
        talents = ['火', '水', '风', '光', '暗']
        avg_levels = df[talents].mean()
        hardest = avg_levels.idxmin()
        hardest_avg = avg_levels.min()

        # 生成文字信息
        info = "\n各属性平均通关层数：\n"
        for attr in talents:
            info += f"  {attr}：{avg_levels[attr]:.2f}\n"
        info += f"最难通关属性：{hardest}（平均 {hardest_avg:.2f}）\n"

        # 统计该属性各关卡人数
        level_counts = df[hardest].value_counts().sort_index()
        plt.figure(figsize=(12, 6))
        plt.bar(level_counts.index.astype(str), level_counts.values, color='orchid')
        plt.xlabel(f'{hardest}属性关卡编号')
        plt.ylabel('通关人数')
        plt.title(f'最难通关属性 [{hardest}] 各关卡通关人数统计 (平均进度 {hardest_avg:.2f})')
        if len(level_counts) > 30:
            for i, (x, y) in enumerate(zip(level_counts.index, level_counts.values)):
                if i % 5 == 0:
                    plt.text(i, y+0.5, str(y), ha='center', fontsize=8)
        else:
            for i, (x, y) in enumerate(zip(level_counts.index, level_counts.values)):
                plt.text(i, y+0.5, str(y), ha='center', fontsize=8)
        plt.tight_layout()
        plt.show(block=False)
        return info

if __name__ == "__main__":
    root = tk.Tk()
    app = PlayerDataAnalyzer(root)
    root.mainloop()