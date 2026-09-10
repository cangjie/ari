#!/bin/zsh
# opus-4-6 的两批质量验证。**产物放仓库目录不放 /private/tmp** ——
# 2026-09-09 scratchpad 在会话之间被清空，24/48 的进度凭空消失过一次。
# （所幸 llm_cache 按提示词哈希缓存，重跑全命中不花钱，但白等一轮。）
#
# tuning48  = 调参样本：规则 4b、B/C 兜底、排除清单都是看着它调出来的
# holdout48 = 留出样本：与调参样本零重合，不同随机种子，seq 跨度 53–4421
# 两批差距 = 判据泛化能力的真实估计。在调参样本上验证等于自己给自己判卷。
cd "$(dirname "$0")/.."
PY=../../.venv_local/bin/python3
run() {   # run <名字> <seq 文件>
  local seqs=$($PY -c "print(' '.join('--only-seq '+s for s in open('$2').read().split()))")
  $PY -u audit_meta.py --museum mfa_boston_ext --slim --stage 1 \
      --provider claude_cli --model claude-opus-4-6 \
      --out-dir "validate/$1" ${=seqs} >> "validate/$1.log" 2>&1
  echo "[$(date '+%H:%M:%S')] $1 退出码 $?" >> validate/progress.log
}
run tuning48  validate/sample_seqs.txt
run holdout48 validate/holdout_seqs.txt
echo "[$(date '+%H:%M:%S')] 两批验证结束" >> validate/progress.log
