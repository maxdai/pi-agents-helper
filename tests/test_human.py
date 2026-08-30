"""human 插话功能单元测试（pi-agents-helper 阶段 1）。

覆盖（docs/pi-helper-design.md §7）：
1. human_msg_count：bare 中 human 消息计数（配额增量输入）
2. rr_next_speaker 跳过非参与者消息（human 不参与轮转，不断链）
3. 保留名校验：--agents 含 human → 报错
4. viewer：增量输出（--since）、消息格式化、状态/done 检测
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meeting_fs import run_git
from meeting_engine import rr_next_speaker, human_msg_count, aggregate_mode
from tests.test_meeting_concurrency import setup_env, write_msg


class TestHumanMsgCount(unittest.TestCase):
    def test_empty(self):
        base, bare, _ = setup_env("human-count-empty", ["a", "b"])
        self.addCleanup(shutil.rmtree, base)
        self.assertEqual(human_msg_count(bare), 0)

    def test_two_human_messages(self):
        base, bare, wd = setup_env("human-count-2", ["a", "b"])
        self.addCleanup(shutil.rmtree, base)
        write_msg(wd["human"], "human/0001.md",
                   {"from": "human", "type": "message", "mode": "meeting",
                    "seen_at": "", "to": "all"}, "插话一")
        write_msg(wd["human"], "human/0002.md",
                   {"from": "human", "type": "message", "mode": "meeting",
                    "seen_at": "", "to": "all"}, "插话二")
        self.assertEqual(human_msg_count(bare), 2)

    def test_participant_messages_not_counted(self):
        base, bare, wd = setup_env("human-count-agent", ["a", "b"])
        self.addCleanup(shutil.rmtree, base)
        write_msg(wd["a"], "a/0001.md",
                   {"from": "a", "type": "message", "mode": "meeting",
                    "seen_at": "", "to": "all"}, "a 发言")
        self.assertEqual(human_msg_count(bare), 0)

    def test_non_message_files_not_counted(self):
        """human/ 下非 4 位数字 md（README 等）不计入。"""
        base, bare, wd = setup_env("human-count-junk", ["a", "b"])
        self.addCleanup(shutil.rmtree, base)
        write_msg(wd["human"], "human/README.md",
                  {"from": "human", "type": "message"}, "说明文件")
        write_msg(wd["human"], "human/0001.md",
                  {"from": "human", "type": "message", "mode": "meeting",
                   "seen_at": "", "to": "all"}, "真插话")
        self.assertEqual(human_msg_count(bare), 1)


class TestRRNextSpeakerSkipHuman(unittest.TestCase):
    def _rr_setup(self, name):
        """RR 场景：a 写 pass（next=b）后可选写 human 消息。"""
        base, bare, wd = setup_env(name, ["a", "b"])
        self.addCleanup(shutil.rmtree, base)
        write_msg(wd["a"], "a/0001.md",
                   {"from": "a", "type": "pass", "mode": "round-robin",
                    "next": "b", "seen_at": "", "to": "all"}, "a pass")
        return base, bare, wd

    def test_normal_no_human(self):
        """回归：HEAD 是参与者消息 → 直接读其 next。"""
        _, bare, _ = self._rr_setup("rr-normal")
        self.assertEqual(rr_next_speaker(bare, ["a", "b"]), "b")

    def test_human_on_head(self):
        """human 插话在 HEAD → 跳过，找 a 的 pass 的 next。"""
        _, bare, wd = self._rr_setup("rr-human-head")
        write_msg(wd["human"], "human/0001.md",
                   {"from": "human", "type": "message", "mode": "round-robin",
                    "seen_at": "", "to": "all"}, "人插话")
        self.assertEqual(rr_next_speaker(bare, ["a", "b"]), "b")

    def test_multiple_human(self):
        """连续 2 条 human 插话 → 逐 commit 跳过。"""
        _, bare, wd = self._rr_setup("rr-human-multi")
        write_msg(wd["human"], "human/0001.md",
                   {"from": "human", "type": "message", "mode": "round-robin",
                    "seen_at": "", "to": "all"}, "插话一")
        write_msg(wd["human"], "human/0002.md",
                   {"from": "human", "type": "message", "mode": "round-robin",
                    "seen_at": "", "to": "all"}, "插话二")
        self.assertEqual(rr_next_speaker(bare, ["a", "b"]), "b")

    def test_human_between_rounds(self):
        """轮次之间插话：a pass → human → b pass(next=a) → 找 b 的 next。"""
        _, bare, wd = self._rr_setup("rr-human-between")
        write_msg(wd["human"], "human/0001.md",
                   {"from": "human", "type": "message", "mode": "round-robin",
                    "seen_at": "", "to": "all"}, "插话")
        write_msg(wd["b"], "b/0001.md",
                   {"from": "b", "type": "pass", "mode": "round-robin",
                    "next": "a", "seen_at": "", "to": "all"}, "b pass")
        self.assertEqual(rr_next_speaker(bare, ["a", "b"]), "a")

    def test_human_mode_not_affect_aggregate(self):
        """human 消息不进入聚合判定（mode 仍由参与者决定）。"""
        _, bare, wd = self._rr_setup("rr-human-agg")
        write_msg(wd["human"], "human/0001.md",
                   {"from": "human", "type": "message", "mode": "meeting",
                    "seen_at": "", "to": "all"}, "插话")
        # 参与者最后一条仍是 a 的 pass（round-robin）→ 聚合仍 round-robin
        self.assertEqual(aggregate_mode(bare, ["a", "b"]), "round-robin")


class TestReservedName(unittest.TestCase):
    def _cli(self, agents):
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run(
                [sys.executable, "start_discussion.py",
                 "--dir", os.path.join(tmp, "disc"),
                 "--agents", agents, "--topic", "t"],
                capture_output=True, text=True,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            return r.stdout

    def test_human_in_agents(self):
        out = self._cli("a,human")
        self.assertIn("保留名", out)
        self.assertIn("human", out)

    def test_human_alone(self):
        out = self._cli("human")
        self.assertIn("保留名", out)

    def test_normal_agents_ok(self):
        # 正常参与者不报保留名错误（后续可能报 topic/环境错误，但不含保留名）
        out = self._cli("a,b")
        self.assertNotIn("保留名", out)

    def test_human_in_spec_agents(self):
        """spec/agents/ 推断含 human → 同样报错（两个入口都拦）。"""
        with tempfile.TemporaryDirectory() as tmp:
            spec = os.path.join(tmp, "spec")
            os.makedirs(os.path.join(spec, "agents"))
            with open(os.path.join(spec, "question.md"), "w") as f:
                f.write("# 用途注释（首行跳过）\n# 讨论主题\n")
            for name in ("a", "human"):
                with open(os.path.join(spec, "agents", f"{name}.md"), "w") as f:
                    f.write(f"{name} 定义\n")
            r = subprocess.run(
                [sys.executable, "start_discussion.py",
                 "--dir", os.path.join(tmp, "disc"), "--spec", spec],
                capture_output=True, text=True,
                cwd=os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__))))
            self.assertIn("保留名", r.stdout)
            self.assertIn("human", r.stdout)


class TestViewer(unittest.TestCase):
    def _env(self, name):
        base, bare, wd = setup_env(name, ["a", "b"])
        self.addCleanup(shutil.rmtree, base)
        return base, bare, wd

    def test_format_message(self):
        from human_viewer import format_message
        content = ("---\nfrom: a\ntype: message\nsummary: 观点\n---\n"
                   "正文第一行\n正文第二行\n")
        s = format_message("a/0001.md", content)
        self.assertIn("[a/0001.md] a (message): 观点", s)
        self.assertIn("正文第一行", s)
        self.assertIn("正文第二行", s)

    def test_incremental_all(self):
        """无 since：输出全部消息（参与者 + human）+ 状态。"""
        from human_viewer import incremental
        base, bare, wd = self._env("viewer-all")
        write_msg(wd["a"], "a/0001.md",
                   {"from": "a", "type": "message", "mode": "meeting",
                    "seen_at": "", "to": "all", "summary": "a 观点"}, "a 正文")
        write_msg(wd["human"], "human/0001.md",
                   {"from": "human", "type": "message", "mode": "meeting",
                    "seen_at": "", "to": "all", "summary": "人插话"}, "人正文")
        mode, lines, _, done = incremental(bare, ["a", "b"], None)
        self.assertEqual(mode, "meeting")
        self.assertEqual(len(lines), 2)
        self.assertTrue(any("[a/0001.md] a (message): a 观点" in s
                            for s in lines), lines)
        self.assertTrue(any("[human/0001.md] human (message): 人插话" in s
                            for s in lines), lines)
        self.assertFalse(done)

    def test_incremental_since(self):
        """--since 增量：只含 since 之后的消息。"""
        from human_viewer import incremental, new_messages
        base, bare, wd = self._env("viewer-since")
        write_msg(wd["a"], "a/0001.md",
                   {"from": "a", "type": "message", "mode": "meeting",
                    "seen_at": "", "to": "all"}, "a 正文")
        head1 = run_git(bare, "rev-parse", "HEAD").stdout.strip()
        write_msg(wd["human"], "human/0001.md",
                   {"from": "human", "type": "message", "mode": "meeting",
                    "seen_at": "", "to": "all"}, "人正文")
        msgs = new_messages(bare, head1)
        self.assertEqual([p for _, p in msgs], ["human/0001.md"])
        mode, lines, _, _ = incremental(bare, ["a", "b"], head1)
        self.assertEqual(mode, "meeting")
        self.assertEqual(len(lines), 1)
        self.assertIn("[human/0001.md]", lines[0])

    def test_done_detection(self):
        """concluded → done=True（viewer 退出条件）。"""
        from human_viewer import incremental
        base, bare, wd = self._env("viewer-done")
        write_msg(wd["a"], "a/0001.md",
                   {"from": "a", "type": "concluded", "mode": "concluded",
                    "seen_at": "", "to": "all"}, "收尾")
        mode, _, _, done = incremental(bare, ["a", "b"], None)
        self.assertEqual(mode, "concluded")
        self.assertTrue(done)

    def test_follow_cursor(self):
        """--follow 游标：增量后写游标，重启从游标继续。"""
        from human_viewer import follow, _read_cursor
        import threading
        base, bare, wd = self._env("viewer-cursor")
        write_msg(wd["a"], "a/0001.md",
                   {"from": "a", "type": "message", "mode": "meeting",
                    "seen_at": "", "to": "all"}, "a 正文")
        head1 = run_git(bare, "rev-parse", "HEAD").stdout.strip()
        # follow 在后台线程跑一轮（poll 间隔小），主线程写 concluded → 退出
        out = []

        def _run():
            class FakeOut:
                def write(self, s):
                    out.append(s)

                def flush(self):
                    pass
            old = sys.stdout
            sys.stdout = FakeOut()
            try:
                follow(base, bare, ["a", "b"], poll_interval=0.05)
            finally:
                sys.stdout = old

        t = threading.Thread(target=_run)
        t.start()
        write_msg(wd["a"], "a/0002.md",
                   {"from": "a", "type": "concluded", "mode": "concluded",
                    "seen_at": "", "to": "all"}, "收尾")
        t.join(timeout=10)
        self.assertFalse(t.is_alive(), "follow 未在 concluded 后退出")
        # 游标已持久化且为最终 HEAD
        self.assertEqual(_read_cursor(base),
                         run_git(bare, "rev-parse", "HEAD").stdout.strip())


def _types_at_head(bare):
    """HEAD 树中消息类型分布（含 human）。"""
    from meeting_fs import is_message_file
    types = {}
    r = run_git(bare, "ls-tree", "-r", "--name-only", "HEAD")
    for f in r.stdout.strip().splitlines():
        if is_message_file(f):
            r3 = run_git(bare, "show", f"HEAD:{f}", check=False)
            for l in r3.stdout.splitlines():
                if l.startswith("type:"):
                    t = l.split(":", 1)[1].strip()
                    types[t] = types.get(t, 0) + 1
    return types


class TestFakeAgentWithHuman(unittest.TestCase):
    """FakeAgent 多进程：human 插话注入（meeting + RR 阶段），讨论仍收敛。

    检测力：若 rr_next_speaker 未跳过 human（轮转链断）→ 讨论死锁 →
    wait_all 超时 → 本测试失败。
    """

    def test_discussion_converges_with_human_interjections(self):
        import time as _time
        from tests.test_meeting_concurrency import spawn_agents, wait_all
        base, bare, wd = setup_env("human-e2e", ["a", "b"])
        self.addCleanup(shutil.rmtree, base)
        procs, _ = spawn_agents(wd, ["a", "b"], {}, {},
                                max_meeting=4, max_rr=5)
        try:
            # meeting 阶段注入（等首启发言落 bare）
            _time.sleep(5)
            write_msg(wd["human"], "human/0001.md",
                       {"from": "human", "type": "message",
                        "mode": "meeting", "seen_at": "", "to": "all"},
                       "meeting 阶段插话")
            # 稍后注入第二条（可能已进入 RR 阶段）
            _time.sleep(8)
            write_msg(wd["human"], "human/0002.md",
                       {"from": "human", "type": "message",
                        "mode": "meeting", "seen_at": "", "to": "all"},
                       "第二条插话")
            all_exit, alive = wait_all(procs, timeout=180)
            self.assertTrue(all_exit, f"进程未退出: {alive}")
            types = _types_at_head(bare)
            self.assertIn("concluded", types,
                          f"讨论未收敛（轮转链被 human 打断?）: {types}")
            # human 消息确实存在且被看到（讨论继续推进到收尾 = 触发正常）
            self.assertIn("message", types)
        finally:
            for p in procs.values():
                if p.poll() is None:
                    p.terminate()


class TestQuotaIncrement(unittest.TestCase):
    """配额增量公式的行为验证（helper 设计 §4.1）。

    max_meeting=1 + human 插话（h_count=1）→ 配额上限 1+1=2：
    agent 首启 1 条 message 后不被冻结，能响应 human 写第 2 条。
    若公式未生效（quota=1）→ 首启后 ⑤.2 即冻结 → 无法响应 → 超时失败。
    """

    def test_quota_increment_lets_agent_respond(self):
        import threading
        import time
        from meeting_engine import agent_loop
        from meeting_fs import list_my_messages, next_msg_id, write_message
        base, bare, wd = setup_env("quota-inc", ["a", "b"])
        self.addCleanup(shutil.rmtree, base)
        # b 的角色：**不活跃参与者**（存在但 last=None，不跑 loop）——
        # 防止单 agent 环境 others_frozen 空集全真（all([])=True →
        # 无触发时立即确定性 freezing，测试目标被旁路）。
        # human 消息走独立 work-human 通道（wd["human"]），不占名额。

        def responder(workdir, agent, head, meta, is_first, rr_turn, retry,
                      finalizing=False, finalize_reason=None):
            mid = next_msg_id(workdir, agent)
            write_message(workdir, f"{agent}/{mid}.md",
                          {"type": "message", "summary": "测试响应"},
                          "正文")
            return True

        # 关键时序（三次修正沉淀，调试实证：首启分支 continue 后下一轮
        # 循环**立即**执行无 sleep——⑤.2 在首启 commit 后 ~50ms 即判定，
        # poll_interval 无法扩大此窗口；human 后注入必然赶不上 → 已冻结
        # 是正确语义。正确序列：
        # 1. human/0001 先注入（h_count=1 → quota=2）
        # 2. a 首启：meta 已含 human（首启响应即回应），seen_at 推进
        # 3. a 下一轮 ⑤.2：1 >= 2 false → 不冻结（公式失效则 1>=1 → 冻结）
        # 4. 注入 human/0002（h_count=2 → quota=3）→ a 被触发 → 响应第 2 条
        # 区分力：公式失效 → 步骤 3 冻结 → 步骤 4 触发被发言锁挡住 →
        # 永远只有 1 条 message → 超时失败。完全确定，无竞态。
        write_msg(wd["human"], "human/0001.md",
                  {"from": "human", "type": "message", "mode": "meeting",
                   "seen_at": "", "to": "all"}, "人插话一")

        t = threading.Thread(
            target=agent_loop,
            args=(wd["a"], "a", responder),
            kwargs={"max_meeting": 1, "max_rr": 5, "poll_interval": 1.0},
            daemon=True)
        t.start()
        try:
            # 等首启完成（a 有 1 条 message 落 bare）
            deadline = time.time() + 30
            while time.time() < deadline:
                if len(list_my_messages(wd["a"], "a")) >= 1:
                    break
                time.sleep(0.2)
            # 第二条 human：触发 a 响应（quota=3，允许第 2 条 message）
            write_msg(wd["human"], "human/0002.md",
                      {"from": "human", "type": "message", "mode": "meeting",
                       "seen_at": "", "to": "all"}, "人插话二")
            # 等 a 响应（message 数 == 2）
            deadline = time.time() + 30
            while time.time() < deadline:
                msgs = [fm for fm in list_my_messages(wd["a"], "a")
                        if fm.get("type") == "message"]
                if len(msgs) >= 2:
                    break
                time.sleep(0.2)
            msgs = [fm for fm in list_my_messages(wd["a"], "a")
                    if fm.get("type") == "message"]
            self.assertGreaterEqual(
                len(msgs), 2,
                "配额增量未生效：a 首启 1 条后即被冻结（quota 未含 h_count），"
                "human/0002 触发被发言锁挡住（应能响应写第 2 条 message）")
        finally:
            pass  # daemon 线程随测试进程退出


if __name__ == "__main__":
    unittest.main()
