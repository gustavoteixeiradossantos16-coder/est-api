import { HttpsError } from 'firebase-functions/v2/https';

export interface ChatMessage {
  role: 'user' | 'model';
  text: string;
}

export const MAX_HISTORY = 20;
export const MAX_MESSAGE_CHARS = 2000;

// Valida o que vem do app: nunca confie no formato enviado pelo cliente
export function parseHistory(data: unknown): ChatMessage[] {
  const history = (data as { history?: unknown } | null)?.history;
  if (!Array.isArray(history) || history.length === 0 || history.length > MAX_HISTORY) {
    throw new HttpsError('invalid-argument', `Envie de 1 a ${MAX_HISTORY} mensagens.`);
  }
  const parsed = history.map((item) => {
    const { role, text } = (item ?? {}) as Record<string, unknown>;
    if ((role !== 'user' && role !== 'model') || typeof text !== 'string' || !text.trim()) {
      throw new HttpsError('invalid-argument', 'Mensagem inválida.');
    }
    if (text.length > MAX_MESSAGE_CHARS) {
      throw new HttpsError('invalid-argument', `Cada mensagem pode ter até ${MAX_MESSAGE_CHARS} caracteres.`);
    }
    return { role, text } as ChatMessage;
  });
  if (parsed[0].role !== 'user' || parsed[parsed.length - 1].role !== 'user') {
    throw new HttpsError('invalid-argument', 'A conversa deve começar e terminar com uma mensagem do aluno.');
  }
  return parsed;
}

export function systemInstruction(goal: string | null): string {
  const focus = goal ? `\nO foco de estudo do aluno é: "${goal.slice(0, 120)}".` : '';
  return `Você é o tutor do StudyTimeIA, especialista em concursos públicos do Brasil.
Seja encorajador, direto, focado na banca organizadora (se informada) e use formatação limpa em texto simples.
Evite textos muito longos, ensine usando tópicos ou metodologias ativas.
Responda só sobre estudos e concursos; recuse com educação pedidos fora desse tema.${focus}`;
}

interface GeminiResponse {
  candidates?: { content?: { parts?: { text?: string }[] } }[];
}

export async function callGemini(opts: {
  apiKey: string;
  model: string;
  goal: string | null;
  history: ChatMessage[];
}): Promise<string> {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(opts.model)}:generateContent`;
  const response = await fetch(url, {
    method: 'POST',
    // A chave vai no cabeçalho, não na URL (o protótipo a expunha no navegador)
    headers: { 'Content-Type': 'application/json', 'x-goog-api-key': opts.apiKey },
    body: JSON.stringify({
      systemInstruction: { parts: [{ text: systemInstruction(opts.goal) }] },
      contents: opts.history.map((m) => ({ role: m.role, parts: [{ text: m.text }] })),
      generationConfig: { maxOutputTokens: 1024 },
    }),
    signal: AbortSignal.timeout(50_000),
  });

  if (!response.ok) {
    throw new Error(`Gemini respondeu ${response.status}: ${(await response.text()).slice(0, 300)}`);
  }
  const result = (await response.json()) as GeminiResponse;
  const text = result.candidates?.[0]?.content?.parts?.map((p) => p.text ?? '').join('').trim();
  if (!text) throw new Error('Gemini não retornou texto');
  return text;
}
