"""meeting_loop.wake_llm 单元测试——mock Popen 覆盖三条路径 + SIGTERM handler。

背景（2026-09-01）：wake_llm 从 subprocess.run 改为 Popen + 15s 分片
communicate（目录清理检测 + 自退出）。现有测试用 fake_agent（不走
wake_llm）——修改零覆盖，必须补本测试保证核心唤醒功能三条路径语义：
1. 正常结束 → CompletedProcess（原语义）
2. 目录被清理 → SystemExit(0) + pi terminate（新功能）
3. 总超时 → TimeoutExpired + pi terminate（恢复原语义）
4. SIGTERM handler → terminate 唤醒中的 pi + SystemExit
"""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import meeting_loop  # noqa: E402


class FakeProc:
    """模拟 pi 子进程：communicate 行为可配置。"""

    def __init__(self, behavior):
        self.behavior = behavior  # ok | timeout-then-removed | always-timeout
        self.returncode = 0
        self.terminated = False
        self.calls = 0

    def communicate(self, timeout=None):
        self.calls += 1
        if self.behavior == "ok":
            return ("OUT", "ERR")
        if self.behavior == "timeout-then-removed":
            if self.calls == 1:
                raise subprocess.TimeoutExpired("pi", timeout)
            return ("", "")
        # always-timeout
        raise subprocess.TimeoutExpired("pi", timeout)

    def poll(self):
        return None  # 仍在运行

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True


class TestWakeLlm(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wake-llm-test-")
        self.workdir = os.path.join(self.tmp, "work-a")
        os.makedirs(self.workdir)
        self.base = os.path.dirname(self.workdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)
        meeting_loop._current_proc = None

    def _run(self, proc, repo_git_exists=True, max_wake_sec=None):
        """跑 wake_llm（mock Popen + 可控 repo.git 存在性）。"""
        orig_max = meeting_loop.MAX_WAKE_SEC
        orig_isdir = os.path.isdir
        orig_popen = subprocess.Popen
        try:
            if max_wake_sec is not None:
                meeting_loop.MAX_WAKE_SEC = max_wake_sec
            subprocess.Popen = mock.Mock(return_value=proc)

            def fake_isdir(p):
                if isinstance(p, str) and p.endswith("repo.git"):
                    return repo_git_exists
                return orig_isdir(p)

            os.path.isdir = fake_isdir
            return meeting_loop.wake_llm(self.workdir, "a", "PROMPT")
        finally:
            meeting_loop.MAX_WAKE_SEC = orig_max
            os.path.isdir = orig_isdir
            subprocess.Popen = orig_popen

    def test_normal_completion(self):
        """pi 正常结束：返回不抛异常、communicate 只调一次、不 terminate。"""
        proc = FakeProc("ok")
        self._run(proc)  # 不抛异常即通过
        self.assertEqual(proc.calls, 1)
        self.assertFalse(proc.terminated)

    def test_dir_removed_during_wake(self):
        """目录被清理：SystemExit(0) + pi 被 terminate。"""
        proc = FakeProc("timeout-then-removed")
        with self.assertRaises(SystemExit) as cm:
            self._run(proc, repo_git_exists=False)
        self.assertEqual(cm.exception.code, 0)
        self.assertTrue(proc.terminated)

    def test_total_timeout(self):
        """总超时：抛 TimeoutExpired（原语义）+ pi 被 terminate。"""
        proc = FakeProc("always-timeout")
        with self.assertRaises(subprocess.TimeoutExpired):
            self._run(proc, repo_git_exists=True, max_wake_sec=0.05)
        self.assertTrue(proc.terminated)

    def test_dir_removed_after_timeout_expired(self):
        """目录清理发生在分片检测（communicate 抛超时后检查目录）。"""
        proc = FakeProc("timeout-then-removed")
        with self.assertRaises(SystemExit) as cm:
            # 目录存在性在第一次 TimeoutExpired 后被检查——先 True 再切 False
            # 模拟：清理发生在唤醒期间（检测时目录已删）
            self._run(proc, repo_git_exists=False)
        self.assertEqual(cm.exception.code, 0)
        self.assertTrue(proc.terminated)


class TestSigtermHandler(unittest.TestCase):
    def test_terminates_current_proc(self):
        """SIGTERM handler：terminate 唤醒中的 pi + SystemExit。"""
        proc = FakeProc("ok")
        meeting_loop._current_proc = proc
        with self.assertRaises(SystemExit):
            meeting_loop._handle_sigterm(None, None)
        self.assertTrue(proc.terminated)

    def test_no_proc_just_exits(self):
        """无唤醒中的 pi：直接退出，不报错。"""
        meeting_loop._current_proc = None
        with self.assertRaises(SystemExit):
            meeting_loop._handle_sigterm(None, None)


if __name__ == "__main__":
    unittest.main()
