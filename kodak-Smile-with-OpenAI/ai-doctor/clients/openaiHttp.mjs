// clients/openaiHttp.mjs
// ✅ Ollama/OpenAI-compatible client (Node 18): uses /v1/chat/completions
// ✅ Forces JSON-only replies to avoid ai_parse
// ✅ Supports optional images (if your server supports it)

import "dotenv/config";

function base64ToDataUrl(b64) {
  const isJpeg = typeof b64 === "string" && b64.startsWith("/9j");
  const mime = isJpeg ? "image/jpeg" : "image/png";
  return `data:${mime};base64,${b64}`;
}

function extractJsonCandidate(text) {
  if (typeof text !== "string") return "";
  // Try to extract the first JSON object/array from the response (robust to extra text)
  const m = text.match(/(\{[\s\S]*\}|\[[\s\S]*\])/);
  return m ? m[0] : text;
}

export async function callOpenAI({
  apiKey,
  baseUrl,
  model,
  prompt,
  images = [],
  timeoutMs = 600000,
}) {
  if (!prompt) throw new Error("callOpenAI: prompt is required");

  const resolvedApiKey = apiKey || process.env.OPENAI_API_KEY || "ollama";

  const resolvedBaseUrl = String(
    baseUrl || process.env.OPENAI_BASE_URL || "https://api.openai.com/v1"
  ).replace(/\/$/, "");

  const resolvedModel =
    model || process.env.OPENAI_MODEL || "llama3.2:3b-instruct-q4_K_M";

  const url = `${resolvedBaseUrl}/chat/completions`;

  console.log("🤖 OpenAI BASE_URL:", resolvedBaseUrl);
  console.log("🤖 OpenAI URL:", url);
  console.log("🧠 Model:", resolvedModel);

  // Build multimodal message (text + optional images)
  const userContent = [{ type: "text", text: prompt }];

  if (Array.isArray(images) && images.length > 0) {
    for (const b64 of images) {
      if (!b64) continue;
      userContent.push({
        type: "image_url",
        image_url: { url: base64ToDataUrl(b64) },
      });
    }
  }

  const payload = {
    model: resolvedModel,
    temperature: Number(process.env.OPENAI_TEMPERATURE || "0"),
    messages: [
      {
        role: "system",
        content:
          'Reply with ONLY valid JSON. Do not include any extra text, markdown, or explanations. Example: {"ok":true}',
      },
      { role: "user", content: userContent },
    ],
  };

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${resolvedApiKey}`,
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    const txt = await res.text();

    if (!res.ok) {
      throw new Error(`OpenAI HTTP ${res.status}: ${txt}`);
    }

    const data = JSON.parse(txt);
    const content = data?.choices?.[0]?.message?.content ?? "";

    // Return only JSON (best-effort), so your pipeline JSON parser succeeds
    return extractJsonCandidate(content);
  } finally {
    clearTimeout(timer);
  }
}