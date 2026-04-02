#!/usr/bin/env python3
"""
上下文使用率状态栏指示器
在终端底部实时显示当前上下文使用百分比
"""

import time
import sys
import os
import threading
from typing import Optional
from dataclasses import dataclass

@dataclass
class ContextUsage:
    """上下文使用情况"""
    used_tokens: int = 0
    total_tokens: int = 200000  # 假设Claude 3.5/4.0上下文窗口为200k
    percentage: float = 0.0

    def update(self, used: Optional[int] = None):
        """更新使用率"""
        if used is not None:
            self.used_tokens = used
        self.percentage = (self.used_tokens / self.total_tokens) * 100 if self.total_tokens > 0 else 0

class ContextIndicator:
    """上下文指示器"""

    def __init__(self, total_tokens: int = 200000):
        self.context_usage = ContextUsage(total_tokens=total_tokens)
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.update_interval = 2.0  # 更新间隔（秒）

    def estimate_token_usage(self) -> int:
        """
        估算当前token使用量
        这是一个简单的估算方法，基于对话历史和当前文件
        """
        # 尝试获取当前对话的估算token数
        # 这里使用简单的启发式方法
        estimated = 0

        # 1. 检查当前目录下可能的对话文件
        current_dir = os.getcwd()
        for file in os.listdir(current_dir):
            if file.endswith('.jsonl') or file.endswith('.log'):
                try:
                    filepath = os.path.join(current_dir, file)
                    if os.path.isfile(filepath):
                        size = os.path.getsize(filepath)
                        # 粗略估算：1个token ≈ 4个字符（英文）
                        estimated += int(size / 4)
                except:
                    pass

        # 2. 添加当前进程内存使用的估算（如果可用）
        try:
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            # 非常粗略的估算：1MB内存 ≈ 1000个token
            estimated += int(mem_info.rss / 1024 / 1024 * 1000)
        except ImportError:
            pass

        return min(estimated, self.context_usage.total_tokens)

    def display_status_bar(self):
        """显示状态栏"""
        usage = self.context_usage

        # 计算进度条
        bar_length = 30
        filled_length = int(bar_length * usage.percentage / 100)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)

        # 颜色编码
        color_code = ""
        reset_code = ""

        if usage.percentage < 70:
            color_code = "\033[92m"  # 绿色
        elif usage.percentage < 90:
            color_code = "\033[93m"  # 黄色
        else:
            color_code = "\033[91m"  # 红色

        # 构建状态栏
        status_line = f"{color_code}上下文使用率: {usage.percentage:.1f}% [{bar}] {usage.used_tokens:,}/{usage.total_tokens:,} tokens{reset_code}"

        # 使用ANSI转义序列：
        # \033[2K - 清除整行
        # \033[1G - 移动到行首
        # \033[{}B - 向下移动n行（到底部）

        # 保存光标位置
        sys.stdout.write("\033[s")

        # 移动到窗口底部
        try:
            rows, _ = os.get_terminal_size()
            # 移动到倒数第二行（避免干扰输入）
            sys.stdout.write(f"\033[{rows-2};0H")
        except:
            # 如果无法获取终端大小，使用默认位置
            sys.stdout.write("\033[20;0H")

        # 清除行并显示状态栏
        sys.stdout.write("\033[2K")
        sys.stdout.write(status_line)

        # 恢复光标位置
        sys.stdout.write("\033[u")
        sys.stdout.flush()

    def update_loop(self):
        """更新循环"""
        while self.is_running:
            try:
                # 估算token使用量
                estimated_tokens = self.estimate_token_usage()
                self.context_usage.update(estimated_tokens)

                # 显示状态栏
                self.display_status_bar()

                # 等待
                time.sleep(self.update_interval)

            except KeyboardInterrupt:
                break
            except Exception as e:
                # 发生错误时继续运行
                time.sleep(self.update_interval)

    def start(self):
        """启动指示器"""
        if self.is_running:
            return

        print("\033[?1049h")  # 进入备用屏幕缓冲区（可选）
        print("\033[2J")  # 清屏

        self.is_running = True
        self.thread = threading.Thread(target=self.update_loop, daemon=True)
        self.thread.start()

        print("上下文指示器已启动。按 Ctrl+C 停止。")

    def stop(self):
        """停止指示器"""
        self.is_running = False

        if self.thread:
            self.thread.join(timeout=2.0)

        # 清除状态栏
        sys.stdout.write("\033[2K\033[1G")
        sys.stdout.flush()

        print("\033[?1049l")  # 退出备用屏幕缓冲区（如果使用了的话）
        print("上下文指示器已停止。")

    def manual_update(self, used_tokens: Optional[int] = None):
        """手动更新显示"""
        if used_tokens is not None:
            self.context_usage.update(used_tokens)
        else:
            estimated = self.estimate_token_usage()
            self.context_usage.update(estimated)

        self.display_status_bar()

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='上下文使用率状态栏指示器')
    parser.add_argument('--total', type=int, default=200000,
                       help='总上下文token数（默认：200000）')
    parser.add_argument('--interval', type=float, default=2.0,
                       help='更新间隔（秒，默认：2.0）')

    args = parser.parse_args()

    indicator = ContextIndicator(total_tokens=args.total)
    indicator.update_interval = args.interval

    try:
        indicator.start()

        # 保持主线程运行
        while indicator.is_running:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                print("\n正在停止指示器...")
                indicator.stop()
                break

    except Exception as e:
        print(f"错误: {e}")
        indicator.stop()

if __name__ == "__main__":
    main()