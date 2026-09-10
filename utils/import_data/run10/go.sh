#!/bin/zsh
# MFA 两个 key 的 S/A 级展品审计 · claude-sonnet-5 · batch 48
#
# 【范围】用户 2026-09-10 决定只跑 S/A：
#     mfa_boston_ext  S 38 + A 561 = 599 件  -> 13 次调用
#     mfa_boston      S 15 + A  86 = 101 件  ->  3 次调用
#   B/C 段 3967 件暂不跑 —— 昨天实测新判据下 B/C 进队列 0%，
#   它们的价值主要是「确认没问题」，晚跑不影响结论，而占 85% 的额度。
#
# 【为什么是 sonnet-5】2026-09-09 五个模型横评 + 零重合留出集复核。
#   sonnet-5 在留出集上：进队列 4%、事实错误 7 件、
#   missing 分布 {0:5, 1:33, 2:10} —— 逐件在判断，不摆烂不凑数。
#   ⚠ 同一模型在两批样本上差别很大（调参集事实错误 0 件、留出集 7 件），
#   差别来自展品本身而非模型。所以「零检出」不能直接判成模型漏检。
#
# 【batch 48】每件 1,820 -> 1,184 token（省 35%），质量无下降。
#   省的是 CLI 按次收费的固定开销（每次仅 cached 输入就 1.8 万 token）。
#
# 【额度】5 小时窗口是账号级的，与用户自己用 Claude Code 共用。
#   失败后先探 API：探不通判为外部条件、不计入放弃计数，每 5 分钟探一次
#   最多等 12 小时，恢复后自动续跑。用户明确要求过「额度光了就等待」。
cd "$(dirname "$0")/.."
PY=../../.venv_local/bin/python3
LOG=run10/progress.log
STALL_MAX=5
MODEL=claude-sonnet-5

log() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> $LOG; }
api_ok() { echo ok | claude -p --model "$MODEL" --output-format json \
                     --system-prompt 'reply ok' >/dev/null 2>&1; }
wait_quota() {
  local n=0
  while [ $n -lt 144 ]; do
    n=$((n+1))
    [ $((n % 6)) -eq 1 ] && log "  额度不可用，已等 $((n*5-5)) 分钟，每 5 分钟探一次"
    sleep 300
    if api_ok; then log "  额度已恢复（共等约 $((n*5)) 分钟），续跑"; return 0; fi
  done
  log "  等满 12 小时仍不可用，交回人工"; return 1
}

supervise() {   # supervise <馆> <片名>
  local mk=$1 tag=$2
  local jsonl="run10/$tag/${mk}_audit1_slim.jsonl"
  local stall=0 attempt=0
  while true; do
    attempt=$((attempt+1))
    local before=$(wc -l < "$jsonl" 2>/dev/null || echo 0)
    $PY -u audit_meta.py --museum "$mk" --slim --stage 1 --batch 48 \
        --provider claude_cli --model "$MODEL" --tier S,A \
        --out-dir "run10/$tag" >> "run10/$tag.log" 2>&1
    local rc=$?
    local after=$(wc -l < "$jsonl" 2>/dev/null || echo 0)
    if [ $rc -eq 0 ]; then log "$tag 完成（${after} 件，第 ${attempt} 次尝试）"; return 0; fi
    if [ "$after" -gt "$before" ]; then
      stall=0; log "$tag 中断（rc=$rc），推进 $((after-before)) 件，累计 ${after}，续跑"
    else
      if ! api_ok; then
        log "$tag 中断（rc=$rc），API 不可用 -> 外部条件，不计入放弃计数"
        wait_quota || return 1
        continue
      fi
      stall=$((stall+1)); log "$tag 中断（rc=$rc），一件未推进（第 ${stall}/${STALL_MAX} 次）"
      [ $stall -ge $STALL_MAX ] && { log "$tag 放弃：连续 ${STALL_MAX} 次无进展，见 run10/$tag.log"; return 1; }
    fi
    sleep $((10 * stall + 5))
  done
}

log "=== 启动（sonnet-5，S/A 共 700 件，batch 48，并发 2）==="
{ supervise mfa_boston_ext ext; } &
{ supervise mfa_boston     old; } &
wait
log "=== 全部结束 ==="
