#!/usr/bin/env python3
"""注視選手JSON（exports/watch_players.json）を Supabase の最新データで更新する。

毎週月曜 06:00 に launchd から実行される。
  ログ: ~/Library/Logs/agent-crm-watchplayers.log

手動実行:
  /usr/bin/python3 scripts/update_watch_players.py

スケジュール設定（plist）の控えは scripts/ にある。launchd は
~/Library/LaunchAgents/ しか読まないので、実体はそちらに置く必要がある。
新しいMacで復元する場合:
  cp scripts/com.tw0218.agent-crm.watchplayers.plist ~/Library/LaunchAgents/
  # plist 内の絶対パスをそのMacのリポジトリ位置に直してから
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.tw0218.agent-crm.watchplayers.plist
Desktop配下にリポジトリを置く場合は、python3 にフルディスクアクセスの付与も要る
（macOSがバックグラウンドプロセスからのDesktopアクセスを既定で拒否するため）。

注視選手の条件は index.html の WATCH_STATUSES を読む。定義を持たないことで
二重管理を避けている。
"""
import json
import plistlib
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "index.html"
OUT = REPO / "exports" / "watch_players.json"
PLIST_NAME = "com.tw0218.agent-crm.watchplayers.plist"
PLIST_REPO = REPO / "scripts" / PLIST_NAME
PLIST_INSTALLED = Path.home() / "Library" / "LaunchAgents" / PLIST_NAME
GIT = "/usr/bin/git"


def log(msg):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def git(*args, check=True):
    return subprocess.run(
        [GIT, *args], cwd=REPO, check=check, capture_output=True, text=True
    )


def read_index_config():
    """index.html から接続情報と注視選手の条件を読む。

    この3つはアプリ側が正解を持っている。スクリプトが自前の値を持つと
    定義がズレたまま静かに動き続けるので、既定値へのフォールバックはしない。
    読めなければ止めて、ログとexit codeで気づけるようにする。
    """
    src = INDEX.read_text(encoding="utf-8")

    url = re.search(r"const\s+SURL\s*=\s*'([^']+)'", src)
    key = re.search(r"const\s+SKEY\s*=\s*'([^']+)'", src)
    if not url or not key:
        raise RuntimeError("index.html から SURL / SKEY を読み取れませんでした")

    arr = re.search(r"const\s+WATCH_STATUSES\s*=\s*\[([^\]]*)\]", src)
    if not arr:
        raise RuntimeError(
            "index.html から WATCH_STATUSES を読み取れませんでした。"
            "定数名か配列リテラルの形が変わっていないか確認してください"
        )
    statuses = [s for s in re.findall(r"'([^']*)'", arr.group(1)) if s]
    if not statuses:
        raise RuntimeError("WATCH_STATUSES が空です")

    return url.group(1), key.group(1), statuses


def check_schedule_drift():
    """稼働中の実行スケジュールがリポジトリの控えと食い違っていないか見る。

    plist の実体は launchd の都合で ~/Library/LaunchAgents/ に置くしかなく、
    リポジトリの控えと二重になる。ズレを防げない以上、気づけるようにしておく。
    絶対パスはMacごとに違うので、比較するのは実行時刻だけにする。
    """
    try:
        if not (PLIST_REPO.exists() and PLIST_INSTALLED.exists()):
            return
        repo_sched = plistlib.loads(PLIST_REPO.read_bytes()).get("StartCalendarInterval")
        live_sched = plistlib.loads(PLIST_INSTALLED.read_bytes()).get("StartCalendarInterval")
        if repo_sched != live_sched:
            log(f"警告: 実行スケジュールがリポジトリの控えと違います（控え={repo_sched} / 稼働中={live_sched}）")
    except Exception as e:
        log(f"警告: スケジュールの照合に失敗しました: {e}")


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
    check_schedule_drift()

    surl, skey, statuses = read_index_config()
    log(f"対象ステータス: {' / '.join(statuses)}")
    all_scouting = fetch_scouting(surl, skey)
    watch = [s for s in all_scouting if s.get("scoutStatus") in statuses]
    log(f"全レポート {len(all_scouting)}件 のうち注視選手 {len(watch)}件")

    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []

    # 条件の読み違いやSupabase側の障害で、既存のJSONを空や虚無で
    # 上書きしてしまう事故を防ぐ。異常なら書かずに止める。
    if old and not watch:
        raise RuntimeError(
            f"注視選手が0件になりました（前回{len(old)}名）。"
            "異常の可能性があるためファイルは更新しません"
        )
    if old and len(watch) * 2 < len(old):
        log(f"警告: 注視選手が半数以下に減りました（{len(old)}名 → {len(watch)}名）。内容を確認してください。")

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
