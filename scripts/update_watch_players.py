#!/usr/bin/env python3
"""注視選手JSON（exports/watch_players.json）を Supabase の最新データで更新する。

毎週月曜 06:00 に launchd から実行される。
  設定: ~/Library/LaunchAgents/com.tw0218.agent-crm.watchplayers.plist
  ログ: ~/Library/Logs/agent-crm-watchplayers.log

手動実行:
  /usr/bin/python3 scripts/update_watch_players.py

注視選手の定義は index.html のダッシュボード（watchPlayers）と揃えている。
片方を変えたらもう片方も直すこと。
"""
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "index.html"
OUT = REPO / "exports" / "watch_players.json"
GIT = "/usr/bin/git"

# index.html の watchPlayers と同じ条件
WATCH_STATUSES = ("継続監視", "契約打診", "獲得推奨")


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def git(*args, check=True):
    return subprocess.run(
        [GIT, *args], cwd=REPO, check=check, capture_output=True, text=True
    )


def read_credentials():
    """index.html から Supabase のエンドポイントと publishable key を読む。

    キーが更新されてもスクリプト側の修正が要らないよう、値は持たず毎回読む。
    """
    src = INDEX.read_text(encoding="utf-8")
    url = re.search(r"const\s+SURL\s*=\s*'([^']+)'", src)
    key = re.search(r"const\s+SKEY\s*=\s*'([^']+)'", src)
    if not url or not key:
        raise RuntimeError("index.html から SURL / SKEY を読み取れませんでした")
    return url.group(1), key.group(1)


def fetch_scouting(surl, skey):
    req = urllib.request.Request(
        f"{surl}/rest/v1/crm_data?key=eq.scouting&select=value",
        headers={"apikey": skey, "Authorization": f"Bearer {skey}"},
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        rows = json.load(res)
    if not rows:
        raise RuntimeError("Supabase に scouting レコードがありません")
    return rows[0].get("value") or []


def report_changes(old, new, all_scouting):
    """増減を人間が読める形でログに出す。

    除外された選手は「ステータス変更」と「レポート自体の削除」を区別する。
    後者は取りこぼしに気づきにくいので明示する。
    """
    old_names = [p.get("playerName") for p in old]
    new_names = [p.get("playerName") for p in new]
    added = [n for n in new_names if n not in old_names]
    removed = [n for n in old_names if n not in new_names]

    log(f"注視選手: {len(old)}名 → {len(new)}名")
    if added:
        log(f"  追加: {', '.join(added)}")
    for name in removed:
        rec = next((s for s in all_scouting if s.get("playerName") == name), None)
        if rec is None:
            log(f"  除外: {name}（選手レポート自体が削除されています）")
        else:
            log(f"  除外: {name}（ステータスが「{rec.get('scoutStatus') or '未設定'}」に変更）")


def commit_and_push():
    """当該ファイルだけをコミットする。他に未pushのコミットがあれば push は見送る。"""
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != "main":
        log(f"ブランチが main ではありません（{branch}）。ファイルは更新しましたがコミットは見送ります。")
        return

    # 自動 push が、レビュー前の手元のコミットを巻き込まないようにする
    unpushed = git("rev-list", "@{u}..HEAD", "--count", check=False)
    pending = int(unpushed.stdout.strip()) if unpushed.returncode == 0 else -1

    git("add", "--", str(OUT.relative_to(REPO)))
    count = len(json.loads(OUT.read_text(encoding="utf-8")))
    git("commit", "-m", f"注視選手JSONを自動更新（{count}名）\n\nscripts/update_watch_players.py による週次更新。")
    log("コミットしました")

    if pending > 0:
        log(f"他に未pushのコミットが {pending} 件あるため push は見送りました。手動で確認してください。")
        return
    if pending < 0:
        log("上流ブランチを特定できないため push は見送りました。")
        return

    res = git("push", check=False)
    if res.returncode == 0:
        log("push しました")
    else:
        log(f"push に失敗しました（コミットは手元に残っています）: {res.stderr.strip()}")


def main():
    log("=== 注視選手JSONの更新を開始 ===")
    surl, skey = read_credentials()
    all_scouting = fetch_scouting(surl, skey)
    watch = [s for s in all_scouting if s.get("scoutStatus") in WATCH_STATUSES]
    log(f"全レポート {len(all_scouting)}件 のうち注視選手 {len(watch)}件")

    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(watch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if not git("status", "--porcelain", "--", str(OUT.relative_to(REPO))).stdout.strip():
        log("変更なし。コミットは不要です。")
        return

    report_changes(old, watch, all_scouting)
    commit_and_push()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"エラー: {e}")
        sys.exit(1)
    finally:
        log("=== 終了 ===")
