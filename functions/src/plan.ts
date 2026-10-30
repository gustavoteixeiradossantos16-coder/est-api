// Regras de plano. O app (est-web/src/lib/plan.ts) tem uma cópia só para exibir a interface;
// quem decide de verdade é este arquivo. Mudou aqui? Atualize lá também.

export type Plan = 'free' | 'pro';
export type DayKey = 'dom' | 'seg' | 'ter' | 'qua' | 'qui' | 'sex' | 'sab';

export const FREE_MINUTES_PER_DAY = 30;
export const FREE_DAYS_PER_WEEK = 4;
// Teto de perguntas por dia para controlar o custo do Gemini (o Premium é "ilimitado" no uso normal)
export const MESSAGES_PER_DAY: Record<Plan, number> = { free: 60, pro: 400 };
// Intervalo mínimo entre dois registros de minuto (o app chama a cada 60 s)
export const MIN_SECONDS_BETWEEN_MINUTES = 50;

// Documento users/{uid}
export interface UserProfile {
  email: string;
  plan: Plan;
  goal: string | null;
  studyDays: DayKey[];
  studyDate: string; // YYYY-MM-DD no fuso de Brasília
  minutesToday: number;
  // Campos gravados só pelo servidor
  messagesToday?: number;
  lastMinuteAt?: number; // epoch em ms
}

// Brasília é UTC-3 o ano todo (sem horário de verão desde 2019)
function brasiliaNow(now: Date): Date {
  return new Date(now.getTime() - 3 * 60 * 60 * 1000);
}

export function todayKey(now = new Date()): string {
  return brasiliaNow(now).toISOString().slice(0, 10);
}

export function todayDay(now = new Date()): DayKey {
  const keys: DayKey[] = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sab'];
  return keys[brasiliaNow(now).getUTCDay()];
}

// Contadores do dia atual (zerados quando o último registro é de outro dia)
export function usageToday(profile: UserProfile, now = new Date()): { minutes: number; messages: number } {
  if (profile.studyDate !== todayKey(now)) return { minutes: 0, messages: 0 };
  return { minutes: profile.minutesToday ?? 0, messages: profile.messagesToday ?? 0 };
}

export type BlockReason = 'daily-limit' | 'not-study-day' | null;

export function blockReason(profile: UserProfile, now = new Date()): BlockReason {
  if (profile.plan === 'pro') return null;
  if (!profile.studyDays?.includes(todayDay(now))) return 'not-study-day';
  if (usageToday(profile, now).minutes >= FREE_MINUTES_PER_DAY) return 'daily-limit';
  return null;
}
