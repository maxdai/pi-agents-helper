/**
 * agents-helper-human —— 讨论插话命令（零 LLM 参与）
 *
 * 用户输入 `/agents-helper-human <文本>` 时立即执行 human_sayer：
 * 把文本作为 human 消息注入当前讨论（agents 可见可回应）。
 * 不经过 LLM——命令 handler 直接 spawn human_sayer.py（一次调用一次返回），
 * 结果用 ctx.ui.notify 反馈。
 *
 * 讨论目录发现（零状态文件，方案 3，用户 2026-08-31 定）：
 *   wrapper --start 的目录名 = discuss-<PI_SESSION_ID>-<时间戳>
 *   （aft 不再替换 bash 后 PI_SESSION_ID 注入可用）；
 *   handler 用 ctx.sessionManager.getSessionId() 取本 session id，
 *   glob ctx.cwd/discuss-<sid>-* 取最新目录——session 隔离（同目录
 *   多 session 并发讨论也互不干扰），无状态文件、无 cleanup 比对。
 *
 * 观看讨论仍用 `!!` bash 流式（human_viewer --follow）——命令 API 无原生
 * 流式通道（handler 返回 Promise<void>），且 bash 流式是平台原生能力。
 */

import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

// 项目绝对路径（AGENTS.md 维护规则：SKILL/扩展引用必须用绝对路径）
const HELPER_DIR = "/root/pi-agents-helper";
const SAYER = path.join(HELPER_DIR, "human_sayer.py");

/** 按 (cwd, sessionId) 推导当前讨论目录：优先 discuss-<sid>-<stamp>（session
 *  隔离），找不到回退 discuss-<stamp>（无 sid 目录——bash:false 缺失时
 *  wrapper 拿不到 PI_SESSION_ID，降级为项目下最新讨论，警告提示）。 */
function findCurrentDir(cwd: string, sid: string): {
  dir: string | null;
  degraded: boolean;
} {
  try {
    const names = fs.readdirSync(cwd, { withFileTypes: true });
    const bySid = names
      .filter((e) => e.isDirectory() && e.name.startsWith(`discuss-${sid}-`))
      .map((e) => e.name)
      .sort();
    if (bySid.length > 0) {
      const dir = path.join(cwd, bySid[bySid.length - 1]);
      return { dir: fs.existsSync(dir) ? dir : null, degraded: false };
    }
    const any = names
      .filter((e) => e.isDirectory() && e.name.startsWith("discuss-"))
      .map((e) => e.name)
      .sort();
    if (any.length > 0) {
      const dir = path.join(cwd, any[any.length - 1]);
      return { dir: fs.existsSync(dir) ? dir : null, degraded: true };
    }
    return { dir: null, degraded: false };
  } catch {
    return { dir: null, degraded: false };
  }
}

/** 执行 human_sayer.py 一次插话。返回 { ok, output }。 */
function runSayer(dir: string, text: string): Promise<{ ok: boolean; output: string }> {
  return new Promise((resolve) => {
    const proc = spawn("python3", [SAYER, dir, text], {
      stdio: ["ignore", "pipe", "pipe"],
    });
    let out = "";
    proc.stdout.on("data", (d) => (out += d.toString()));
    proc.stderr.on("data", (d) => (out += d.toString()));
    proc.on("close", (code) => resolve({ ok: code === 0, output: out.trim() }));
    proc.on("error", (e) => resolve({ ok: false, output: String(e) }));
  });
}

export default function register(pi: any) {
  pi.registerCommand("agents-helper-human", {
    description: "向正在进行的多 agent 讨论插话（human 消息，agents 可见可回应）",
    argumentHint: "<插话内容>",
    getArgumentCompletions: () => null,
    handler: async (args: string, ctx: any) => {
      const text = args.trim();
      if (!text) {
        ctx.ui.notify("插话内容为空——用法: /agents-helper-human <文本>", "warning");
        return;
      }
      const sid = ctx.sessionManager.getSessionId();
      const found = findCurrentDir(ctx.cwd, sid);
      const dir = found.dir;
      if (!dir) {
        ctx.ui.notify(
          "没有正在进行的讨论（cwd 下无 discuss-* 目录）。" +
            "先用 /agents-helper 启动讨论。",
          "error"
        );
        return;
      }
      if (found.degraded) {
        ctx.ui.notify(
          `未找到本 session 的讨论（讨论目录不含 session id，可能是 aft 未设置 "bash": false）——插话指向项目下最新讨论: ${dir}`,
          "warning"
        );
      }
      const { ok, output } = await runSayer(dir, text);
      if (ok && output) {
        ctx.ui.notify(output, "success");
      } else if (ok) {
        ctx.ui.notify("插话已发送", "success");
      } else {
        ctx.ui.notify(`插话失败: ${output || "未知错误"}`, "error");
      }
    },
  });
}
