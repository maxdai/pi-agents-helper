/**
 * agents-helper-human —— 讨论插话命令（零 LLM 参与）
 *
 * 用户输入 `/agents-helper-human <文本>` 时立即执行 human_sayer：
 * 把文本作为 human 消息注入当前讨论（agents 可见可回应）。
 * 不经过 LLM——命令 handler 直接 spawn human_sayer.py（一次调用一次返回），
 * 结果用 ctx.ui.notify 反馈。
 *
 * 讨论目录来源：主 pi 的 skill 流程（discuss.sh --start）会把当前讨论目录
 * 写入 <状态文件>；handler 读它。无讨论或目录不存在 → 提示用户。
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

// 当前讨论目录状态文件：主 pi 的 --start 写入、--cleanup 删除
// 位置：项目下（session cwd）——不污染全局；wrapper 的 $PWD 与扩展的
// ctx.cwd 同源（主 pi session 的工作目录）。不同项目 session 互不干扰；
// 同一目录多 session 并发讨论是已知边界（后启动覆盖）。
function stateFile(cwd: string): string {
  return path.join(cwd, ".agents-helper-current");
}

function readCurrentDir(cwd: string): string | null {
  try {
    const p = stateFile(cwd);
    if (!fs.existsSync(p)) return null;
    const dir = fs.readFileSync(p, "utf8").trim();
    return dir && fs.existsSync(dir) ? dir : null;
  } catch {
    return null;
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
      const dir = readCurrentDir(ctx.cwd);
      if (!dir) {
        ctx.ui.notify(
          "没有正在进行的讨论（agents-helper-current 状态文件缺失或目录已清理）。" +
            "先用 /agents-helper 启动讨论。",
          "error"
        );
        return;
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
