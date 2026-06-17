export default async function handler(req, res) {
  const SHEET_ID = '1uxo1zGHJzcaEdbqbeeJLMUdvfzyaQbYc';
  const GID = '1996885083';
  const url = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/export?format=csv&gid=${GID}`;
  try {
    const r = await fetch(url, { redirect: 'follow' });
    if (!r.ok) return res.status(502).json({ error: 'Failed to fetch sheet' });
    const text = await r.text();
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.status(200).send(text);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
}
