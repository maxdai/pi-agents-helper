"""meeting_loop.wake_llm 单元测试——mock Popen 覆盖三条路径 + SIGTERM handler。

背景（2026-09-01）：wake_llm 从 subprocess.run 改为 Popen + 15s 分片
communicate（目录清理检测 + 自退出）。现有测试用 fake_agent（不走
wake_llm）——修改零覆盖，必须补本测试保证核心唤醒功能三条路径语义：
1. 正常结束 → CompletedProcess（原语义）
2. 目录被清理 → SystemExit(0) + pi terminate（新功能）
3. 总超时 → TimeoutExpired + pi terminate（恢复原语义）
4. SIGTERM handler → terminate 唤醒中的 pi + SystemExit
"""

import json
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

    def __init__(self, behavior, sticky_terminate=False, rc=0, out="OUT", err="ERR"):
        self.behavior = behavior  # ok | timeout-then-removed | always-timeout
        self.sticky_terminate = sticky_terminate  # terminate 后仍不退出（测 kill 兜底）
        self.returncode = rc
        self.out_text = out
        self.err_text = err
        self.terminated = False
        self.killed = False
        self.calls = 0

    def communicate(self, timeout=None):
        self.calls += 1
        if self.killed:
            return ("", "")  # kill 生效后正常返回（模拟进程已死）
        if self.sticky_terminate:
            # 模拟 terminate 无效：communicate 始终超时（触发 kill 兜底）
            raise subprocess.TimeoutExpired("pi", timeout)
        if self.behavior == "ok":
            return (self.out_text, self.err_text)
        if self.behavior == "timeout-then-removed":
            if self.calls == 1:
                raise subprocess.TimeoutExpired("pi", timeout)
            return ("", "")
        # always-timeout
        raise subprocess.TimeoutExpired("pi", timeout)

    def poll(self):
        if self.terminated or self.killed:
            return self.returncode
        return None  # 仍在运行

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


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

    def test_normal_returns_saves_session(self):
        """正常路径完整功能：返回 (sid, 0) + status 文件写入。"""
        proc = FakeProc("ok")
        result = self._run(proc)
        sid = meeting_loop.session_id(self.workdir, "a")
        self.assertEqual(result, (sid, 0))
        status = os.path.join(self.base, "status-a.json")
        self.assertTrue(os.path.exists(status))
        with open(status) as f:
            self.assertEqual(json.load(f), {"sessionID": sid})

    def test_parse_session_header(self):
        """parse_session：解析 pi JSON 输出的 session 头。"""
        stdout = '{"type":"session","id":"abc123"}\n{"type":"message"}\n'
        self.assertEqual(meeting_loop.parse_session(stdout), "abc123")
        self.assertIsNone(meeting_loop.parse_session("no json here"))

    def test_no_session_found_clears_status(self):
        """stderr 含 No session found：删 status 文件（下轮重建）+ 返回。"""
        # 预置 status 文件（模拟已有 session）
        status = os.path.join(self.base, "status-a.json")
        with open(status, "w") as f:
            json.dump({"sessionID": "old"}, f)
        proc = FakeProc("ok", rc=1, out="", err="Error: No session found")
        result = self._run(proc)
        self.assertEqual(result[1], 1)
        self.assertFalse(os.path.exists(status))

    def test_returncode_error_keeps_status(self):
        """returncode != 0 且非 session 错误：status 保留（可诊断）。"""
        status = os.path.join(self.base, "status-a.json")
        with open(status, "w") as f:
            json.dump({"sessionID": "old"}, f)
        proc = FakeProc("ok", rc=1, out="", err="boom")
        result = self._run(proc)
        self.assertEqual(result[1], 1)
        self.assertTrue(os.path.exists(status))


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


class TestKillProc(unittest.TestCase):
    """_kill_proc 两条路径（2026-09-01 新增，e2e 卡死 bug 的修复）。"""

    def test_terminate_suffices(self):
        """terminate 生效（communicate 返回）：不触发 kill。"""
        proc = FakeProc("ok")
        meeting_loop._kill_proc(proc)
        self.assertTrue(proc.terminated)
        self.assertFalse(proc.killed)

    def test_kill_fallback(self):
        """terminate 无效（communicate 持续超时）：5s 后 SIGKILL 兜底。"""
        proc = FakeProc("ok", sticky_terminate=True)
        meeting_loop._kill_proc(proc)
        self.assertTrue(proc.terminated)
        self.assertTrue(proc.killed)

    def test_already_exited(self):
        """进程已退出：直接返回，不操作。"""
        proc = FakeProc("ok")
        proc.terminate()  # poll 返回非 None
        meeting_loop._kill_proc(proc)
        self.assertEqual(proc.calls, 0)  # communicate 未被调用

    def test_wake_llm_removed_dir_uses_kill_proc(self):
        """目录清理路径最终走 _kill_proc（SystemExit 前必杀 pi）。"""
        proc = FakeProc("timeout-then-removed", sticky_terminate=True)
        with self.assertRaises(SystemExit) as cm:
            t = TestWakeLlm("test_dir_removed_during_wake")
            t.setUp()
            try:
                t._run(proc, repo_git_exists=False)
            finally:
                t.tearDown()
        self.assertEqual(cm.exception.code, 0)
        self.assertTrue(proc.killed)


class TestBuildWakePrompt(unittest.TestCase):
    """build_wake_prompt：未读消息清单格式（打磨项 2026-09-01 去陈旧标注）。"""

    def test_meta_lists_paths_no_stale_marker(self):
        meta = [
            {"path": "a/0001.md", "stale": False},
            {"path": "b/0002.md", "stale": True},
        ]
        p = meeting_loop.build_wake_prompt("a", meta, False, "meeting", False, msg_path="a/0003.md")
        self.assertIn("- a/0001.md", p)
        self.assertIn("- b/0002.md", p)
        self.assertNotIn("陈旧", p)  # 打磨项：标注已去掉

    def test_msg_path_and_state(self):
        p = meeting_loop.build_wake_prompt("a", None, True, "meeting", False, msg_path="a/0001.md")
        self.assertIn("a/0001.md", p)
        self.assertIn("第一位发言者", p)


if __name__ == "__main__":
    unittest.main()
