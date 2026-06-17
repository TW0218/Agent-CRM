const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];

export default async function handler(req, res) {
  const SHEET_ID = '1uxo1zGHJzcaEdbqbeeJLMUdvfzyaQbYc';
  const { year, month } = req.query; // month: 0-indexed
  const sheetName = year && month !== undefined
    ? `${year}${MONTHS[parseInt(month)]}`
    : null;
  const url = sheetName
    ? `https://docs.google.com/spreadsheets/d/${SHEET_ID}/export?format=csv&sheet=${encodeURIComponent(sheetName)}`
    : `https://docs.google.com/spreadsheets/d/${SHEET_ID}/export?format=csv&gid=1996885083`;
  try {
    const r = await fetch(url, { redirect: 'follow' });
    if (!r.ok) return res.status(502).json({ error: `シート "${sheetName}" が見つかりません` });
    const text = await r.text();
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.status(200).send(text);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
}
