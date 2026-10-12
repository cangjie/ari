#!/bin/sh
# 在服务器上给 ari-web-api 建它自己的数据库账号 ari_web，并写好 /etc/ari/web-api.my.cnf。
#
# 这个账号只够导览站的游客互动用：
#   ari.tour_topic        SELECT / INSERT / UPDATE   —— 不能删
#   ari.tour_qa_setting   SELECT                     —— 服务自己改不了自己的上限
# ari 库的其它表它一概碰不到。
#
# 用法（在服务器上，以 ubuntu 身份）：
#
#   sh /home/ubuntu/ari/web_api/sql/create_ari_web.sh        # 会问一次 MySQL root 口令，输入时不回显
#
# 从本机一条命令跑：ssh -t ubuntu@44.207.251.65 'sh /home/ubuntu/ari/web_api/sql/create_ari_web.sh'
# 不在终端里跑时，改从标准输入读 root 的客户端配置（[client] 段，含 user 与 password）。
# 两种方式口令都不进命令行，只落在一个用完即删的临时文件里。
#
# 新账号的口令在这里随机生成，直接写进配置文件，不打印。可以重复跑：每跑一次换一个新口令。
# 应用在第一次用到时才读配置文件，跑完不用重启服务（已经连上过库的要重启才换用新口令）。
set -eu
umask 077

CNF=/etc/ari/web-api.my.cnf
ROOT_CNF=$(mktemp)
trap 'stty echo 2>/dev/null || true; rm -f "$ROOT_CNF"' EXIT

if [ -t 0 ]; then
  printf 'MySQL root 口令：' >&2
  stty -echo
  IFS= read -r ROOT_PW
  stty echo
  printf '\n' >&2
  printf '[client]\nuser=root\npassword="%s"\n' "$ROOT_PW" > "$ROOT_CNF"
  unset ROOT_PW
else
  cat > "$ROOT_CNF"
fi

M="mysql --defaults-extra-file=$ROOT_CNF"
if ! WHO=$($M -N -e "SELECT CURRENT_USER()" 2>&1); then
  # root@localhost 与允许远程登录的 root@% 是两个账号，口令可能不同。
  # 走 TCP 连本机的内网地址再试一次，这样服务端匹配到的是后者
  M="$M --protocol=tcp -h $(hostname -I | cut -d' ' -f1)"
  if ! WHO=$($M -N -e "SELECT CURRENT_USER()" 2>&1); then
    echo "root 登录失败（本机套接字与 TCP 都试过）：$(printf '%s' "$WHO" | cut -c1-160)" >&2
    exit 2
  fi
fi
echo "root 登录成功：$WHO"

# 服务走本机套接字：服务端看到的来源恒为 localhost，caching_sha2_password 也不需要额外的加密库
SOCK=$($M -N -e "SELECT @@socket")
PW=$(openssl rand -hex 20)

$M <<SQL
CREATE USER IF NOT EXISTS 'ari_web'@'localhost' IDENTIFIED BY '$PW';
ALTER USER 'ari_web'@'localhost' IDENTIFIED BY '$PW';
GRANT SELECT, INSERT, UPDATE ON ari.tour_topic TO 'ari_web'@'localhost';
GRANT SELECT ON ari.tour_qa_setting TO 'ari_web'@'localhost';
SQL

printf '# ari-web-api 连库用的账号，由 web_api/sql/create_ari_web.sh 生成。重跑那个脚本会换口令\n[client]\nsocket = %s\nuser = ari_web\npassword = %s\ndatabase = ari\n' \
  "$SOCK" "$PW" | sudo -n install -m 640 -o root -g ari /dev/stdin "$CNF"
unset PW

echo "已写入 $CNF（套接字 $SOCK）。ari_web 的权限："
$M -N -e "SHOW GRANTS FOR 'ari_web'@'localhost'" | sed -E 's/ IDENTIFIED .*//'
