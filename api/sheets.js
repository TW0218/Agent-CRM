const SHEET_ID = '1yoGe4xa7rKx9yC0Rs1HBDZZE3nQKkHVJNVEZ-0V-LBc';

const GID_MAP = {
  '2026-5': '1996885083',  // 2026June
  '2026-6': '411333865',   // 2026July
  '2026-7': '1314662842',  // 2026August
  '2026-8': '1583425868',  // 2026September
};

export default async function handler(req, res) {
  const { year, month } = req.query; // month: 0-indexed
  const key = `${year}-${month}`;
  const gid = GID_MAP[key];
  if (!gid) return res.status(404).json({ error: `${year}年${parseInt(month)+1}月のシートが登録されていません` });
  const url = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/export?format=csv&gid=${gid}`;
  try {
    const r = await fetch(url, { redirect: 'follow' });
    if (!r.ok) return res.status(502).json({ error: 'シートの取得に失敗しました' });
    const text = await r.text();
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    res.status(200).send(text);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
}
