export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  const { image, mediaType, playerKnowledge } = req.body;
  if (!image) return res.status(400).json({ error: 'No image' });
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) return res.status(500).json({ error: 'No API key' });
  try {
    const knowledgeText = playerKnowledge && playerKnowledge.length
      ? `\n\n【選手データベース（過去の試合から蓄積）】\n画像に登場する選手と名前が一致または類似する場合、データベースの情報で不明項目を補完してください。ただし画像に明記されている情報は必ず画像を優先してください。\n${JSON.stringify(playerKnowledge)}`
      : '';
    const isPdf = mediaType === 'application/pdf';
    const prompt = `あなたはサッカーのメンバー表を正確に読み取る専門家です。
${isPdf ? 'PDFから' : '画像から'}メンバー表の情報を抽出し、JSONのみ返してください。説明・コメント不要。

【読み取りの注意点】
- 選手名は漢字・ひらがな・カタカナを正確に読み取ること。似た字（例：「渡邊」と「渡辺」、「齋藤」と「斎藤」）も正確に区別すること
- 所属チーム名は略さず、画像に記載された正式名称をそのまま入力すること
- 背番号・ポジション・年齢・利き足は画像に記載があれば正確に入力すること
- 身長・体重は画像に記載がある場合のみ入力し、ない場合は空文字にすること
- 確信が持てない文字は推測せず、空文字にすること${knowledgeText}

【出力形式】JSONのみ。余分なテキスト不要。
{"homeTeam":"","awayTeam":"","competition":"","venue":"","date":"YYYY-MM-DD","homeFormation":"","awayFormation":"","homePlayers":[{"num":"","name":"","position":"","club":"","age":"","foot":"","height":"","weight":""}],"awayPlayers":[{"num":"","name":"","position":"","club":"","age":"","foot":"","height":"","weight":""}]}`;

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({
        model: 'claude-opus-4-8',
        max_tokens: 4000,
        messages: [{ role: 'user', content: [
          isPdf
            ? { type: 'document', source: { type: 'base64', media_type: 'application/pdf', data: image } }
            : { type: 'image', source: { type: 'base64', media_type: mediaType || 'image/jpeg', data: image } },
          { type: 'text', text: prompt }
        ]}]
      })
    });
    const result = await response.json();
    if (result.error) return res.status(500).json({ error: result.error.message });
    const text = result.content?.[0]?.text || '';
    const match = text.match(/\{[\s\S]*\}/);
    if (!match) return res.status(500).json({ error: 'JSON not found: ' + text.slice(0, 100) });
    res.status(200).json({ data: JSON.parse(match[0]) });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
}
