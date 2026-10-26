"""通知后端抽象接口。

未来升级（卡通形象小人提醒等）只需实现同样的接口并在工厂注册，
主程序与轮询逻辑完全不用改动。
"""


class Notifier:
    """通知后端基类。

    - start(): 进入通知循环（可能阻塞，如 Tk mainloop）。
    - show(event): 收到一条"任务结束"事件（跨线程调用需自行保证安全）。
    - request_stop(): 任何线程调用，请求退出循环。
    - stop(): 退出。
    """

    name = "base"

    def start(self):
        raise NotImplementedError

    def show(self, event):
        raise NotImplementedError

    def request_stop(self):
        self.stop()

    def stop(self):
        raise NotImplementedError
