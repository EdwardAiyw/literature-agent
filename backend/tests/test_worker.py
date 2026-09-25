from concurrent.futures import Future
from threading import Thread

from literature_agent.worker import LocalRunWorker


class ImmediateExecutor:
    def submit(self, function, *args):
        future = Future()
        future.set_result(function(*args))
        return future

    def shutdown(self, wait=True, cancel_futures=False):
        pass


def test_completed_future_callback_does_not_deadlock():
    worker = LocalRunWorker(object(), object())
    worker.executor.shutdown()
    worker.executor = ImmediateExecutor()

    submission = Thread(target=worker._submit, args=("run-id", lambda: None), daemon=True)
    submission.start()
    submission.join(timeout=1)

    assert not submission.is_alive()
    assert worker._futures == {}
