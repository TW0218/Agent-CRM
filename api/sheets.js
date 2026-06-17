export default async function handler(req, res) {
  const SHEET_ID = '1uxo1zGHJzcaEdbqbeeJLMUdvfzyaQbYc';
  const { sheet } = req.query;
  if (!sheet) return res.status(400).json({ error: 'sheet parameter required' });
  const url = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/export?format=csv&sheet=${encodeURIComponent(sheet)}`;
  try {
    const r = await fetch(url, { redirect: 'follow' });
    if (!r.ok) return res.status(502).json({ error: `シート "${sheet}" が見つかりません` });
    const text = await r.text();
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    res.status(200).send(text);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
}
