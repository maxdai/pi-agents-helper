"""薄壳（meeting_loop）纯函数测试（review6 #5：薄壳零测试违反设计 7.3）。

meeting_loop 是真实 LLM 适配层——此前整文件零测试覆盖。本次补
build_wake_prompt 渲染测试（纯函数可字面构造，不需要 LLM）。

验证点：
1. 首启 prompt：包含状态/参与指引/meta 文件列表
2. 重试 prompt：包含"必须写消息"强制表态
3. msg_path 注入：LLM 应写的消息路径（用户 9618：文件名由 loop 决定）
4. 不传 git HEAD（用户 9773：LLM 不需要知道 git）
5. RR 状态 vs meeting 状态文案区分
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meeting_loop import build_wake_prompt


class TestBuildWakePrompt(unittest.TestCase):
    """build_wake_prompt 渲染（薄壳纯函数，无 LLM 依赖）。"""

    def _meta(self, paths):
        return [{"path": p, "from": p.split("/")[0], "stale": False}
                for p in paths]

    def test_first_wake_contains_meta_files(self):
        """首启：meta 中他人消息文件应出现在 prompt（LLM 要读的内容）。"""
        meta = self._meta(["b/0001.md", "b/0002.md"])
        p = build_wake_prompt("a", meta, True, "meeting", False)
        self.assertIn("b/0001.md", p, "首启 prompt 应含待处理文件")
        self.assertIn("b/0002.md", p, "首启 prompt 应含待处理文件")
        self.assertIn("meeting", p.lower(), "应含状态")

    def test_retry_forces_response(self):
        """重试：无静默铁律——必须写消息。"""
        p = build_wake_prompt("a", [], False, "meeting", True)
        self.assertIn("必须写", p, "重试应强制表态")

    def test_msg_path_injected(self):
        """msg_path：loop 指定 LLM 应写的文件（用户 9618）。"""
        p = build_wake_prompt("a", [], True, "meeting", False,
                              msg_path="a/0003.md")
        self.assertIn("a/0003.md", p, "prompt 应指定消息路径")
        self.assertIn("写到", p, "应指示写到指定文件")

    def test_no_git_head(self):
        """LLM 不需要知道 git HEAD（用户 9773）——prompt 不含 HEAD。"""
        p = build_wake_prompt("a", [], True, "meeting", False)
        self.assertNotIn("HEAD", p, "prompt 不应含 git HEAD")

    def test_rr_state_wording(self):
        """RR 状态：轮到你写 pass 确认（单向流）。"""
        p = build_wake_prompt("a", [], False, "round-robin（轮到你：写 pass 确认共识，单向流无异议）", False)
        self.assertIn("pass", p.lower(), "RR 状态应提 pass")

    def test_meeting_state_wording(self):
        """meeting 状态：可发言或 freezing。"""
        p = build_wake_prompt("a", [], False, "meeting（有未读新消息，可发言或 freezing）", False)
        self.assertIn("freezing", p.lower(), "meeting 状态应提 freezing")


if __name__ == "__main__":
    unittest.main()


class TestPiSessionHelpers(unittest.TestCase):
    """Pi 适配薄壳的 session/配置纯函数测试。"""

    def test_session_id_sanitized(self):
        from meeting_loop import session_id
        sid = session_id("/tmp/discussion-my_meet/work-a", "a")
        self.assertIn("discuss-", sid)
        self.assertIn("-a", sid)
        # 必须符合 pi 的 session id 字符集
        import re
        self.assertRegex(sid, r"^[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9]$")

    def test_parse_session_header(self):
        from meeting_loop import parse_session
        out = ('{"type":"session","version":3,"id":"abc-123",'
               '"timestamp":"...","cwd":"/tmp"}\n'
               '{"type":"message","id":"x"}\n')
        self.assertEqual(parse_session(out), "abc-123")

    def test_parse_session_no_header(self):
        from meeting_loop import parse_session
        self.assertIsNone(parse_session("not json\n"))

    def test_read_agent_config(self):
        import tempfile
        from meeting_loop import read_agent_config
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "pi-agent.json"), "w") as f:
                f.write('{"model":"m","thinking":"high","prompt_file":"x"}')
            cfg = read_agent_config(d, "a")
            self.assertEqual(cfg["thinking"], "high")
        # 缺失/损坏返回空 dict
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(read_agent_config(d, "a"), {})


if __name__ == "__main__":
    unittest.main()


class TestWakeLlmCommand(unittest.TestCase):
    """验证 wake_llm 构造的 pi 命令行（Pi 适配核心）。"""

    def test_command_contains_pi_session_and_prompt_file(self):
        import tempfile
        from unittest import mock
        from meeting_loop import wake_llm
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, "discussion-test")
            workdir = os.path.join(base, "work-a")
            os.makedirs(os.path.join(workdir, ".pi", "agent"))
            os.makedirs(os.path.join(base, "pi-sessions"), exist_ok=True)
            with open(os.path.join(workdir, "pi-agent.json"), "w") as f:
                f.write(json.dumps({
                    "model": "opencode-go/deepseek-v4-flash",
                    "thinking": "high",
                    "prompt_file": ".pi/agent/a.md",
                }))
            with open(os.path.join(workdir, ".pi", "agent", "a.md"), "w") as f:
                f.write("你是 a")
            fake = mock.Mock()
            fake.returncode = 0
            fake.return_value.stdout = '{"type":"session","id":"abc-123"}\n'
            fake.return_value.returncode = 0
            fake.return_value.stderr = ""
            with mock.patch("subprocess.run", fake) as mrun:
                sid, code = wake_llm(workdir, "a", "hello", pure=True)
            self.assertEqual(sid, "abc-123")
            self.assertEqual(code, 0)
            # 检查 status 写入
            status = json.load(open(os.path.join(base, "status-a.json")))
            self.assertEqual(status["sessionID"], "abc-123")
            # 检查命令行
            args, kwargs = mrun.call_args
            cmd = args[0]
            self.assertEqual(cmd[0], "pi")
            self.assertIn("--session-id", cmd)
            self.assertIn("--session-dir", cmd)
            self.assertIn(os.path.join(base, "pi-sessions"), cmd)
            self.assertIn("--model", cmd)
            self.assertIn("opencode-go/deepseek-v4-flash", cmd)
            self.assertIn("--thinking", cmd)
            self.assertIn("high", cmd)
            self.assertIn("--append-system-prompt", cmd)
            self.assertIn(os.path.join(workdir, ".pi", "agent", "a.md"), cmd)
            self.assertIn("--no-extensions", cmd)  # pure
            self.assertEqual(kwargs["cwd"], workdir)
            self.assertIn("hello", cmd)


if __name__ == "__main__":
    unittest.main()
